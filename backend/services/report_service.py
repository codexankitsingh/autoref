from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import SessionLocal
from models.user import User
from models.mail_account import MailAccount
from models.email_thread import EmailThread
from models.message import Message
from models.scraped_job import ScrapedJob
from services.email_service import email_service


class ReportService:
    def generate_weekly_report(self):
        """Generates and sends the weekly intelligence report for all active users."""
        db = SessionLocal()
        try:
            users = db.query(User).all()
            for user in users:
                self._send_report_for_user(db, user)
        except Exception as e:
            print(f"Error generating weekly reports: {e}")
        finally:
            db.close()

    def _send_report_for_user(self, db: Session, user: User):
        # 1. Get user's primary mail account for sending the report
        account = db.query(MailAccount).filter(
            MailAccount.user_id == user.id,
            MailAccount.is_active == 1
        ).first()

        if not account:
            print(f"User {user.email} has no active mail account. Skipping report.")
            return

        one_week_ago = datetime.utcnow() - timedelta(days=7)

        # 2. Gather Funnel Metrics
        threads = db.query(EmailThread).filter(
            EmailThread.user_id == user.id,
            EmailThread.created_at >= one_week_ago
        ).all()
        
        emails_sent = len(threads)
        replies = sum(1 for t in threads if t.replied)
        interviews = sum(1 for t in threads if t.interview_scheduled)
        
        # Calculate total opens for threads created this week
        total_opens = 0
        for t in threads:
            total_opens += sum((m.open_count or 0) for m in t.messages)

        # 3. Action Items (Warm Leads: Opened > 0, no reply, status != closed/interview)
        warm_leads = []
        recent_threads = db.query(EmailThread).filter(
            EmailThread.user_id == user.id,
            EmailThread.status.notin_(["closed", "interview_scheduled", "draft", "replied"])
        ).all()
        
        for t in recent_threads:
            thread_opens = sum((m.open_count or 0) for m in t.messages)
            if thread_opens > 0 and not t.replied:
                company = t.application.company if t.application else "Unknown Company"
                warm_leads.append({"company": company, "opens": thread_opens})
                
        # Sort warm leads by open count descending
        warm_leads = sorted(warm_leads, key=lambda x: x["opens"], reverse=True)[:5]

        # 4. Top Discovered Jobs (Score >= 80, status = saved)
        top_jobs = db.query(ScrapedJob).filter(
            ScrapedJob.user_id == user.id,
            ScrapedJob.created_at >= one_week_ago,
            ScrapedJob.status == "saved",
            ScrapedJob.match_score >= 80
        ).order_by(ScrapedJob.match_score.desc()).limit(5).all()

        # 5. Build HTML Report
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #2563eb; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px;">AutoRef Weekly Intelligence Report</h2>
            <p>Hi {user.name}, here is your outreach summary for the past 7 days.</p>
            
            <div style="background-color: #f3f4f6; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                <h3 style="margin-top: 0; color: #1f2937;">📊 Weekly Funnel</h3>
                <ul style="list-style-type: none; padding-left: 0;">
                    <li><strong>Emails Sent:</strong> {emails_sent}</li>
                    <li><strong>Total Opens:</strong> {total_opens}</li>
                    <li><strong>Replies Received:</strong> {replies}</li>
                    <li><strong>Interviews Scheduled:</strong> {interviews}</li>
                </ul>
            </div>
        """

        if warm_leads:
            html_body += """
            <div style="margin-bottom: 20px;">
                <h3 style="color: #d97706;">🔥 Warm Leads (Opened, No Reply)</h3>
                <ul>
            """
            for lead in warm_leads:
                html_body += f"<li><strong>{lead['company']}</strong>: {lead['opens']} opens</li>"
            html_body += "</ul></div>"

        if top_jobs:
            html_body += """
            <div style="margin-bottom: 20px;">
                <h3 style="color: #059669;">🎯 Top Discovered Jobs</h3>
                <ul>
            """
            for job in top_jobs:
                html_body += f"<li><strong>{job.company}</strong> - {job.title} <span style='background-color: #d1fae5; color: #065f46; padding: 2px 6px; border-radius: 4px; font-size: 12px; margin-left: 8px;'>Score: {job.match_score}</span></li>"
            html_body += "</ul></div>"
            
        if not top_jobs and not warm_leads and emails_sent == 0:
            html_body += "<p>It looks like a quiet week! Check your dashboard to scrape new jobs or start a new outreach campaign.</p>"

        html_body += """
            <p style="font-size: 12px; color: #6b7280; margin-top: 30px; border-top: 1px solid #e5e7eb; padding-top: 10px;">
                Sent automatically by AutoRef v2.0
            </p>
        </body>
        </html>
        """

        # 6. Send the email (User emails themselves)
        subject = f"AutoRef Weekly Report - {datetime.utcnow().strftime('%b %d, %Y')}"
        try:
            email_service.send_email(
                db=db,
                sender_account_id=account.id,
                recipient_email=user.email,
                subject=subject,
                body=html_body,
                tracking_id=None # No need to track our own reports
            )
            print(f"✅ Weekly report sent to {user.email}")
        except Exception as e:
            print(f"Failed to send weekly report to {user.email}: {e}")

report_service = ReportService()
