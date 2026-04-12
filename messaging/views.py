import json
import logging

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .models import ChatMessage

logger = logging.getLogger(__name__)


def _get_session_key(request) -> str:
    """Return a stable session identifier for the current visitor."""
    if request.user.is_authenticated:
        return f"user_{request.user.id}"
    if not request.session.session_key:
        request.session.create()
    return f"anon_{request.session.session_key}"


def chat_view(request):
    """Render the chat page, pre-loading the last 60 messages for this session."""
    session_key = _get_session_key(request)
    messages = list(
        ChatMessage.objects.filter(session_key=session_key).order_by("created_at")[:60]
    )
    return render(request, "messaging/chat.html", {"messages": messages})


@require_POST
def send_message(request):
    """
    Receive a user message, run the AI agent, return the reply as JSON.

    Request body:  {"message": "Hello"}
    Response body: {"reply": "Hi there! ..."}
    """
    try:
        body = json.loads(request.body).get("message", "").strip()
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if not body:
        return JsonResponse({"error": "Message is required"}, status=400)

    session_key = _get_session_key(request)
    user = request.user if request.user.is_authenticated else None

    # Persist user message
    ChatMessage.objects.create(
        user=user,
        session_key=session_key,
        role=ChatMessage.Role.USER,
        body=body,
    )

    # Run AI agent
    from .ai_agent import run_agent
    try:
        reply = run_agent(session_key=session_key, user=user, incoming_message=body)
    except Exception:
        logger.exception("AI agent failed for session %s", session_key)
        reply = "Sorry, something went wrong. Please try again."

    # Re-fetch user in case registration happened during this turn
    if user is None:
        from .models import ConversationHistory
        history = ConversationHistory.objects.filter(phone_number=session_key).first()
        if history and history.user:
            user = history.user

    # Persist AI reply
    ChatMessage.objects.create(
        user=user,
        session_key=session_key,
        role=ChatMessage.Role.ASSISTANT,
        body=reply,
    )

    return JsonResponse({"reply": reply})
