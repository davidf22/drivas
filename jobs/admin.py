from django.contrib import admin
from .models import JobEngagement, JobStatusLog, SalaryPayment


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


@admin.register(SalaryPayment)
class SalaryPaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "job", "amount", "status", "paid_at", "created_at")
    list_filter = ("status",)
    readonly_fields = ("reference", "created_at", "paid_at")
    search_fields = ("reference", "job__client__username", "job__driver__username")
