"""
Celery tasks for background AI notifications.
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def notify_drivers_of_new_job(self, job_id: int):
    """
    Notify all available verified drivers about a newly posted job.
    Called from JobListCreateView.perform_create (REST API path).
    The AI agent's own post_job flow handles notification via notify_user tool directly.
    """
    from accounts.models import DriverProfile
    from jobs.models import JobEngagement
    from .models import ConversationHistory, ChatMessage

    try:
        job = JobEngagement.objects.select_related("client").get(pk=job_id)
    except JobEngagement.DoesNotExist:
        logger.warning("notify_drivers_of_new_job: Job %s not found", job_id)
        return

    available = DriverProfile.objects.filter(
        status="available",
        is_verified=True,
    ).select_related("user")

    if not available.exists():
        logger.info("No available drivers for job %s", job_id)
        return

    rate_line = f"\nRate:         ${job.agreed_rate}/hr" if job.agreed_rate else ""
    message = (
        f"New job available! Job #{job.id}\n"
        f"────────────────────────\n"
        f"Type:         {job.get_employment_type_display()}\n"
        f"Location:     {job.work_location}{rate_line}\n"
        f"Requirements: {job.requirements or 'None'}\n\n"
        f"Open your Drivas chat and type 'accept job {job.id}' to take this job."
    )

    for profile in available:
        driver = profile.user
        session_key = f"user_{driver.id}"
        try:
            history, _ = ConversationHistory.objects.get_or_create(
                phone_number=session_key,
                defaults={"user": driver},
            )
            history.append_assistant(message)
            history.save()

            ChatMessage.objects.create(
                user=driver,
                session_key=session_key,
                role=ChatMessage.Role.ASSISTANT,
                body=message,
            )
        except Exception as exc:
            logger.error("Failed to notify driver %s: %s", driver.id, exc)
