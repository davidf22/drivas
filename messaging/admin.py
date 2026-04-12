from django.contrib import admin
from .models import ConversationHistory, ChatMessage


@admin.register(ConversationHistory)
class ConversationHistoryAdmin(admin.ModelAdmin):
    list_display = ("phone_number", "user", "message_count", "updated_at")
    list_filter = ("updated_at",)
    search_fields = ("phone_number", "user__username", "user__first_name")
    readonly_fields = ("updated_at", "messages")

    @admin.display(description="Messages")
    def message_count(self, obj):
        return len(obj.messages)

    actions = ["clear_history"]

    @admin.action(description="Clear conversation history")
    def clear_history(self, request, queryset):
        queryset.update(messages=[])
        self.message_user(request, f"Cleared history for {queryset.count()} conversation(s).")


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "role", "user", "session_key", "body_preview", "created_at")
    list_filter = ("role", "created_at")
    search_fields = ("session_key", "body", "user__username")
    readonly_fields = ("created_at",)

    @admin.display(description="Message")
    def body_preview(self, obj):
        return obj.body[:80]
