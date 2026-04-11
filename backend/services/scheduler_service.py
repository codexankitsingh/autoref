"""
Scheduler Service — Follow-up automation using APScheduler.
Checks for pending follow-ups, generates AI-powered follow-up emails, and sends them.
"""
from datetime import datetime, timedelta
import time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from config import get_settings
from database import SessionLocal
from models.email_thread import EmailThread
from models.message import Message
from models.follow_up_job import FollowUpJob
from services.ai_service import ai_service
from services.email_service import email_service


class SchedulerService:
    """Manages scheduled follow-up jobs using APScheduler."""

    def __init__(self):
        self.settings = get_settings()
        self._scheduler = None

    @property
    def scheduler(self):
        if self._scheduler is None:
            self._scheduler = BackgroundScheduler()
        return self._scheduler

    def start(self):
        """Start the background scheduler with a periodic check job."""
        if not self.scheduler.running:
            # Check for pending follow-ups every 5 minutes
            self.scheduler.add_job(
                self._process_pending_followups,
                IntervalTrigger(minutes=5),
                id="process_followups",
                replace_existing=True,
            )
            # Check for inbox replies every 1 minute
            self.scheduler.add_job(
                self._check_inbox_replies,
                IntervalTrigger(minutes=1),
                id="check_inbox_replies",
                replace_existing=True,
            )
            self.scheduler.start()
            print("📅 Scheduler started — checking follow-ups (5m) and replies (1m)")

    def stop(self):
        """Stop the background scheduler."""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            print("📅 Scheduler stopped")

    def schedule_follow_ups(self, thread_id: int, interval_days: int = 3, max_follow_ups: int = 3):
        """Create follow-up job records in the database."""
        db = SessionLocal()
        try:
            thread = db.query(EmailThread).filter(EmailThread.id == thread_id).first()
            if not thread:
                return

            # Create follow-up job entries
            for i in range(1, max_follow_ups + 1):
                scheduled_time = datetime.utcnow() + timedelta(days=interval_days * i)

                # Check if already exists
                existing = db.query(FollowUpJob).filter(
                    FollowUpJob.thread_id == thread_id,
                    FollowUpJob.follow_up_number == i,
                ).first()

                if not existing:
                    job = FollowUpJob(
                        thread_id=thread_id,
                        follow_up_number=i,
                        scheduled_time=scheduled_time,
                        status="pending",
                    )
                    db.add(job)

            db.commit()
            print(f"📅 Scheduled {max_follow_ups} follow-ups for thread {thread_id}")
        except Exception as e:
            print(f"Error scheduling follow-ups: {e}")
            db.rollback()
        finally:
            db.close()

    def cancel_follow_ups(self, thread_id: int):
        """Cancel all pending follow-ups for a thread."""
        db = SessionLocal()
        try:
            db.query(FollowUpJob).filter(
                FollowUpJob.thread_id == thread_id,
                FollowUpJob.status == "pending",
            ).update({"status": "cancelled"})
            db.commit()
            print(f"📅 Cancelled follow-ups for thread {thread_id}")
        except Exception as e:
            print(f"Error cancelling follow-ups: {e}")
            db.rollback()
        finally:
            db.close()

    def _process_pending_followups(self):
        """Process all pending follow-up jobs that are due."""
        db = SessionLocal()
        try:
            now = datetime.utcnow()

            # Find all due follow-up jobs
            due_jobs = db.query(FollowUpJob).filter(
                FollowUpJob.status == "pending",
                FollowUpJob.scheduled_time <= now,
            ).all()

            if not due_jobs:
                return

            print(f"📅 Processing {len(due_jobs)} pending follow-ups (max 3 per cycle, 2 min gap)...")

            sent_count = 0
            for job in due_jobs:
                if sent_count >= 3:
                    print(f"📅 Hit per-cycle cap (3). Remaining follow-ups deferred to next cycle.")
                    break
                try:
                    self._execute_follow_up(db, job)
                    sent_count += 1
                    # Throttle: wait 2 minutes between sends to avoid Gmail spam flags
                    if sent_count < 3 and sent_count < len(due_jobs):
                        print(f"📅 Cooling down for 2 minutes before next follow-up...")
                        time.sleep(120)
                except Exception as e:
                    print(f"Error processing follow-up job {job.id}: {e}")
                    continue

        except Exception as e:
            print(f"Error in follow-up processing: {e}")
        finally:
            db.close()

    def _execute_follow_up(self, db: Session, job: FollowUpJob):
        """Execute a single follow-up job."""
        thread = db.query(EmailThread).filter(EmailThread.id == job.thread_id).first()
        if not thread:
            job.status = "cancelled"
            db.commit()
            return

        # Stop conditions
        if thread.replied or thread.status in ("replied", "interview_scheduled", "closed"):
            job.status = "cancelled"
            db.commit()
            print(f"📅 Skipping follow-up for thread {thread.id} (replied/closed)")
            return

        # CRITICAL: Fresh Gmail reply check RIGHT BEFORE sending
        # Prevents race condition where reply arrived between scheduler cycles
        if thread.gmail_thread_id and thread.sender_account_id:
            try:
                fresh_replies = email_service.check_replies(
                    db=db,
                    gmail_thread_id=thread.gmail_thread_id,
                    sender_account_id=thread.sender_account_id,
                )
                if fresh_replies:
                    print(f"📅 ⛔ Last-second reply detected for thread {thread.id}! Aborting follow-up.")
                    thread.replied = True
                    thread.status = "replied"
                    thread.last_activity_at = datetime.utcnow()
                    job.status = "cancelled"
                    # Cancel ALL remaining follow-ups
                    db.query(FollowUpJob).filter(
                        FollowUpJob.thread_id == thread.id,
                        FollowUpJob.status == "pending",
                    ).update({"status": "cancelled"})
                    db.commit()
                    return
            except Exception as e:
                print(f"📅 Warning: Pre-send reply check failed for thread {thread.id}: {e}")

        # Get original email content
        original_msg = db.query(Message).filter(
            Message.thread_id == thread.id,
            Message.message_type == "initial",
        ).first()

        if not original_msg:
            job.status = "cancelled"
            db.commit()
            return

        # Generate follow-up email using AI
        follow_up_body = ai_service.generate_follow_up(
            original_email=original_msg.content,
            follow_up_number=job.follow_up_number,
        )

        # Send the follow-up
        try:
            from models.recipient import Recipient
            recipient = db.query(Recipient).filter(Recipient.id == thread.recipient_id).first()
            if not recipient:
                job.status = "cancelled"
                db.commit()
                return

            send_result = email_service.send_email(
                db=db,
                sender_account_id=thread.sender_account_id,
                recipient_email=recipient.email,
                subject=f"Re: {original_msg.subject}",
                body=follow_up_body,
                thread_id=thread.gmail_thread_id,
            )

            # Create message record
            message = Message(
                thread_id=thread.id,
                gmail_message_id=send_result.get("gmail_message_id"),
                message_type="follow_up",
                subject=f"Re: {original_msg.subject}",
                content=follow_up_body,
                sent_at=datetime.utcnow(),
            )
            db.add(message)

            # Update thread
            thread.follow_up_count = job.follow_up_number
            thread.status = f"follow_up_{job.follow_up_number}"
            thread.last_activity_at = datetime.utcnow()

            # Update job
            job.status = "sent"

            db.commit()
            print(f"📅 Sent follow-up #{job.follow_up_number} for thread {thread.id}")

        except Exception as e:
            print(f"📅 Failed to send follow-up #{job.follow_up_number}: {e}")
            job.status = "pending"  # Keep as pending to retry
            db.commit()

    def _check_inbox_replies(self):
        """Poll Gmail for candidate replies on active threads."""
        db = SessionLocal()
        try:
            # Active threads that haven't received a reply yet
            active_threads = db.query(EmailThread).filter(
                EmailThread.replied == 0,
                EmailThread.status.in_(["sent", "follow_up_1", "follow_up_2", "follow_up_3"])
            ).all()

            if not active_threads:
                return

            print(f"📅 Checking inbox replies for {len(active_threads)} active threads...")

            for thread in active_threads:
                if not thread.gmail_thread_id or not thread.sender_account_id:
                    continue

                try:
                    replies = email_service.check_replies(
                        db=db,
                        gmail_thread_id=thread.gmail_thread_id,
                        sender_account_id=thread.sender_account_id
                    )

                    if replies:
                        print(f"📅 ✉️  Reply detected for thread {thread.id}! Updating status.")
                        # Mark thread as replied
                        thread.replied = True
                        thread.status = "replied"
                        thread.last_activity_at = datetime.utcnow()

                        # Save the latest reply as a message record
                        for reply in replies:
                            # Ensure we don't save duplicates by checking message_id
                            existing_msg = db.query(Message).filter(Message.gmail_message_id == reply.get("gmail_message_id")).first()
                            if not existing_msg:
                                new_msg = Message(
                                    thread_id=thread.id,
                                    gmail_message_id=reply.get("gmail_message_id"),
                                    message_type="reply",
                                    subject=f"Reply from {reply.get('from', 'Unknown')}",
                                    content=reply.get("content", ""),
                                    sent_at=datetime.utcnow()
                                )
                                db.add(new_msg)

                        # Cancel any pending follow-ups
                        db.query(FollowUpJob).filter(
                            FollowUpJob.thread_id == thread.id,
                            FollowUpJob.status == "pending"
                        ).update({"status": "cancelled"})

                        db.commit()
                except Exception as inner_e:
                    print(f"📅 Error checking replies for thread {thread.id}: {inner_e}")
                    db.rollback()
                    continue

        except Exception as e:
            print(f"Error checking inbox replies: {e}")
        finally:
            db.close()


# Singleton
scheduler_service = SchedulerService()
