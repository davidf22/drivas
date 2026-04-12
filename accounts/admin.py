from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, DriverProfile, ClientProfile


def send_welcome_message(modeladmin, request, queryset):
    """Admin action: send a WhatsApp welcome message to selected users."""
    from messaging.whatsapp import send_whatsapp

    sent, skipped = 0, 0
    for user in queryset:
        if not user.whatsapp_number:
            skipped += 1
            continue
        send_whatsapp(
            to_number=str(user.whatsapp_number),
            body=(
                f"Welcome to Drivas, {user.first_name or user.username}!\n"
                "Send HELP to see available commands."
            ),
            user=user,
        )
        sent += 1
    modeladmin.message_user(
        request,
        f"Welcome message sent to {sent} user(s). {skipped} skipped (no WhatsApp number).",
        messages.SUCCESS,
    )


send_welcome_message.short_description = "Send WhatsApp welcome message"


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "role", "phone", "whatsapp_number", "is_active")
    list_filter = ("role", "is_active", "is_staff")
    actions = [send_welcome_message]
    fieldsets = UserAdmin.fieldsets + (
        (
            "Drivas",
            {
                "fields": (
                    "role",
                    "phone",
                    "whatsapp_number",
                    "profile_photo",
                )
            },
        ),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "Drivas",
            {
                "fields": (
                    "role",
                    "phone",
                    "whatsapp_number",
                )
            },
        ),
    )


@admin.register(DriverProfile)
class DriverProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "license_number",
        "status",
        "rating",
        "total_jobs",
        "is_verified",
    )
    list_filter = ("status", "is_verified")
    search_fields = ("user__username", "license_number")


@admin.register(ClientProfile)
class ClientProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "total_jobs")
    search_fields = ("user__username",)
