# Models package
from models.user import User
from models.mail_account import MailAccount
from models.job_application import JobApplication
from models.recipient import Recipient
from models.email_thread import EmailThread
from models.message import Message
from models.follow_up_job import FollowUpJob
from models.reply import Reply
from models.scraped_job import ScrapedJob

__all__ = [
    "User", "MailAccount", "JobApplication", "Recipient",
    "EmailThread", "Message", "FollowUpJob", "Reply",
    "ScrapedJob",
]
