from django.contrib.auth.models import AbstractUser
from django.db import models
from phonenumber_field.modelfields import PhoneNumberField


class CustomUser(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        DRIVER = "driver", "Driver"
        CLIENT = "client", "Client"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.CLIENT)
    phone = PhoneNumberField(unique=True, null=True, blank=True)
    whatsapp_number = PhoneNumberField(
        unique=True,
        null=True,
        blank=True,
        help_text="WhatsApp number in E.164 format, e.g. +15551234567",
    )
    profile_photo = models.ImageField(upload_to="profiles/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.role})"

    @property
    def whatsapp_id(self):
        """Returns the whatsapp: prefixed number."""
        if self.whatsapp_number:
            return f"whatsapp:{self.whatsapp_number}"
        return None


class DriverProfile(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        BUSY = "busy", "Busy"

    user = models.OneToOneField(
        CustomUser, on_delete=models.CASCADE, related_name="driver_profile"
    )
    license_number = models.CharField(max_length=50, unique=True)
    license_image = models.ImageField(upload_to="licenses/", null=True, blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.AVAILABLE
    )
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=5.00)
    total_jobs = models.PositiveIntegerField(default=0)
    current_latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    current_longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    is_verified = models.BooleanField(default=False)

    def __str__(self):
        return f"Driver: {self.user} | License: {self.license_number}"


class ClientProfile(models.Model):
    user = models.OneToOneField(
        CustomUser, on_delete=models.CASCADE, related_name="client_profile"
    )
    total_jobs = models.PositiveIntegerField(default=0)
    preferred_language = models.CharField(max_length=10, default="en")

    def __str__(self):
        return f"Client: {self.user}"
