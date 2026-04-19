from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html

from .models import CustomUser, DriverProfile, ClientProfile


def _notify_driver_verified(driver):
    """Send an in-chat message and email to a driver when their account is verified."""
    from messaging.models import ChatMessage
    from messaging.tools import _get_or_create_history

    chat_message = (
        f"Your Drivas account has been verified! ✓\n\n"
        f"Welcome to the team, {driver.first_name or driver.username}! "
        f"You are now eligible to accept job offers.\n\n"
        f"Available jobs will appear here — simply click Accept to take one on."
    )

    history, session_key = _get_or_create_history(driver)
    history.append_assistant(chat_message)
    history.save()

    ChatMessage.objects.create(
        user=driver,
        session_key=session_key,
        role=ChatMessage.Role.ASSISTANT,
        body=chat_message,
    )

    # Email notification
    if driver.email:
        from django.core.mail import get_connection, send_mail
        from django.conf import settings
        import ssl, certifi
        try:
            connection = get_connection(
                ssl_context=ssl.create_default_context(cafile=certifi.where())
            )
            send_mail(
                subject="Drivas — Your account has been verified!",
                message=(
                    f"Hi {driver.first_name or driver.username},\n\n"
                    f"Great news! Your Drivas driver account has been verified.\n"
                    f"You can now log in and accept job offers.\n\n"
                    f"Log in here: http://localhost:8000/accounts/login/\n\n"
                    f"— The Drivas Team"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[driver.email],
                fail_silently=True,
                connection=connection,
            )
        except Exception:
            pass


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "get_full_name", "email", "role", "is_active")
    list_filter = ("role", "is_active", "is_staff")
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
        "driver_name",
        "license_number",
        "status",
        "rating",
        "total_jobs",
        "verification_badge",
    )
    list_filter = ("is_verified", "status")
    search_fields = ("user__username", "user__first_name", "user__last_name", "license_number")
    readonly_fields = ("total_jobs", "rating")
    actions = ["verify_drivers", "unverify_drivers"]

    @admin.display(description="Driver")
    def driver_name(self, obj):
        return obj.user.get_full_name() or obj.user.username

    @admin.display(description="Verified")
    def verification_badge(self, obj):
        if obj.is_verified:
            return format_html(
                '<span style="color:#fff;background:#2e7d32;padding:2px 10px;'
                'border-radius:12px;font-size:12px;font-weight:600;">✓ Verified</span>'
            )
        return format_html(
            '<span style="color:#fff;background:#c62828;padding:2px 10px;'
            'border-radius:12px;font-size:12px;font-weight:600;">✗ Unverified</span>'
        )

    @admin.action(description="✓ Verify selected drivers")
    def verify_drivers(self, request, queryset):
        # Only notify drivers who were previously unverified
        to_notify = list(queryset.filter(is_verified=False).select_related("user"))
        queryset.update(is_verified=True)
        for profile in to_notify:
            _notify_driver_verified(profile.user)
        self.message_user(
            request,
            f"{len(to_notify)} driver(s) verified and notified.",
            messages.SUCCESS,
        )

    @admin.action(description="✗ Unverify selected drivers")
    def unverify_drivers(self, request, queryset):
        updated = queryset.update(is_verified=False)
        self.message_user(
            request,
            f"{updated} driver(s) unverified.",
            messages.WARNING,
        )


@admin.register(ClientProfile)
class ClientProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "total_jobs")
    search_fields = ("user__username", "user__first_name", "user__last_name")
