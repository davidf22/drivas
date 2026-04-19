"""
Email notification helpers for Drivas.
"""
import logging
import ssl
import certifi

from django.core.mail import send_mail, get_connection
from django.conf import settings

logger = logging.getLogger(__name__)


def send_job_notification_email(driver, job):
    """
    Send a job-posted email notification to a driver.

    Args:
        driver: CustomUser instance (the driver).
        job:    JobEngagement instance.
    """
    if not driver.email:
        logger.debug("Driver %s has no email — skipping email notification.", driver.id)
        return

    if not settings.EMAIL_HOST_USER:
        logger.debug("EMAIL_HOST_USER not configured — skipping email notification.")
        return

    rate_line = f"\nRate:         ${job.agreed_rate}/hr" if job.agreed_rate else ""
    subject = f"Drivas — New Job Available: {job.get_employment_type_display()} in {job.work_location}"
    body = (
        f"Hi {driver.first_name or driver.username},\n\n"
        f"A new job has been posted on Drivas that matches your profile:\n\n"
        f"Job #{job.id}\n"
        f"{'─' * 30}\n"
        f"Type:         {job.get_employment_type_display()}\n"
        f"Location:     {job.work_location}{rate_line}\n"
        f"Requirements: {job.requirements or 'None'}\n\n"
        f"Log in to your Drivas chat to accept this job:\n"
        f"http://localhost:8000/chat/\n\n"
        f"— The Drivas Team"
    )

    try:
        connection = get_connection(
            ssl_context=ssl.create_default_context(cafile=certifi.where())
        )
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[driver.email],
            fail_silently=False,
            connection=connection,
        )
        logger.info("Job notification email sent to driver %s (%s)", driver.id, driver.email)
    except Exception as exc:
        logger.error("Failed to send job notification email to driver %s: %s", driver.id, exc)
