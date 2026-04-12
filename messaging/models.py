from django.db import models
from django.conf import settings


class ConversationHistory(models.Model):
    """
    Stores the AI conversation history per session.

    `session_key` identifies the conversation:
      - Authenticated users:  "user_{user_id}"
      - Anonymous visitors:   "anon_{django_session_key}"

    `messages` is a list of Anthropic-compatible message dicts:
      [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]

    Only the final text exchange is stored (not internal tool calls).
    """

    # Field kept as phone_number in the DB for migration compatibility;
    # now used as a generic session identifier.
    phone_number = models.CharField(max_length=100, unique=True, db_index=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conversation_history",
    )
    messages = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        label = str(self.user) if self.user else self.phone_number
        return f"Conversation: {label} ({len(self.messages)} messages)"

    def append_user(self, text: str):
        self.messages.append({"role": "user", "content": text})
        self._trim()

    def append_assistant(self, text: str):
        self.messages.append({"role": "assistant", "content": text})
        self._trim()

    def _trim(self):
        max_msgs = settings.AI_CONVERSATION_MAX_TURNS * 2
        if len(self.messages) > max_msgs:
            self.messages = self.messages[-max_msgs:]

    def get_history_for_api(self) -> list[dict]:
        return self.messages[:-1] if self.messages else []


class ChatMessage(models.Model):
    """
    Persisted log of every message in the web chat interface.
    One row per message bubble (user or assistant).
    """

    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    # Identifies the conversation session (same key as ConversationHistory.phone_number)
    session_key = models.CharField(max_length=100, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chat_messages",
    )
    role = models.CharField(max_length=15, choices=Role.choices)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        label = str(self.user) if self.user else self.session_key
        return f"[{self.role}] {label}: {self.body[:60]}"
