from django.db import models
from django.conf import settings


class JobEngagement(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        HIRED = "hired", "Hired"
        ACTIVE = "active", "Active"
        ENDED = "ended", "Ended"
        CANCELLED = "cancelled", "Cancelled"

    class EmploymentType(models.TextChoices):
        FULL_TIME = "full_time", "Full-Time"
        PART_TIME = "part_time", "Part-Time"

    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="jobs_as_client",
    )
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="jobs_as_driver",
    )
    employment_type = models.CharField(
        max_length=10, choices=EmploymentType.choices, default=EmploymentType.FULL_TIME
    )
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.OPEN
    )
    work_location = models.CharField(max_length=255)
    location_latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    location_longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    requirements = models.TextField(
        blank=True,
        help_text="Job requirements or special instructions for the driver.",
    )
    agreed_rate = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="Agreed hourly or daily rate.",
    )
    total_earned = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="Total amount earned by the driver for this engagement.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    hired_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    client_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    driver_rating = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"Job #{self.pk} [{self.status}] "
            f"{self.client} — {self.get_employment_type_display()} @ {self.work_location}"
        )


class JobStatusLog(models.Model):
    job = models.ForeignKey(
        JobEngagement, on_delete=models.CASCADE, related_name="status_logs"
    )
    status = models.CharField(max_length=15, choices=JobEngagement.Status.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["timestamp"]

    def __str__(self):
        return f"Job #{self.job_id} → {self.status} at {self.timestamp}"
