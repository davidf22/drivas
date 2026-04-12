from django.contrib import admin
from .models import JobEngagement, JobStatusLog


class JobStatusLogInline(admin.TabularInline):
    model = JobStatusLog
    extra = 0
    readonly_fields = ("status", "changed_by", "timestamp", "note")


@admin.register(JobEngagement)
class JobEngagementAdmin(admin.ModelAdmin):
    list_display = (
        "id", "employment_type", "client", "driver", "status",
        "work_location", "agreed_rate", "created_at",
    )
    list_filter = ("status", "employment_type")
    search_fields = ("client__username", "driver__username", "work_location")
    readonly_fields = ("created_at", "hired_at", "started_at", "ended_at")
    inlines = [JobStatusLogInline]


@admin.register(JobStatusLog)
class JobStatusLogAdmin(admin.ModelAdmin):
    list_display = ("job", "status", "changed_by", "timestamp")
    list_filter = ("status",)
