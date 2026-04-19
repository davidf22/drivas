import json
import logging

from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST

from .models import ChatMessage

logger = logging.getLogger(__name__)


def _is_admin(user) -> bool:
    return user.is_authenticated and (user.is_staff or user.is_superuser or getattr(user, "role", "") == "admin")


def _get_session_key(request) -> str:
    """Return a stable session identifier for the current visitor."""
    if request.user.is_authenticated:
        return f"user_{request.user.id}"
    if not request.session.session_key:
        request.session.create()
    return f"anon_{request.session.session_key}"


def chat_view(request):
    """Render the chat page, pre-loading the last 60 messages for this session."""
    if _is_admin(request.user):
        return redirect("/admin/")

    session_key = _get_session_key(request)
    user = request.user if request.user.is_authenticated else None

    # Send a greeting on the very first visit (no messages yet)
    if not ChatMessage.objects.filter(session_key=session_key).exists():
        if user:
            greeting = (
                f"Welcome back, {user.first_name or user.username}! 👋\n"
                f"I'm the Drivas assistant. How can I help you today?"
            )
        else:
            greeting = (
                "Welcome to Drivas! 👋\n"
                "I'm your AI assistant. I can help you find a driver job or hire a professional driver.\n\n"
                "Are you joining as a **Client** (looking to hire a driver) or a **Driver** (looking for work)?"
            )
        ChatMessage.objects.create(
            user=user,
            session_key=session_key,
            role=ChatMessage.Role.ASSISTANT,
            body=greeting,
        )

    messages = list(
        ChatMessage.objects.filter(session_key=session_key).order_by("created_at")[:60]
    )
    return render(request, "messaging/chat.html", {"chat_messages": messages})


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

    if _is_admin(request.user):
        return JsonResponse({"error": "Admins do not have access to the chat platform."}, status=403)

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


@require_POST
def job_action(request):
    """
    Handle Accept / Decline button clicks on job offer messages.

    Request body: {"job_id": 1, "action": "accept" | "decline"}
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Login required."}, status=403)

    try:
        data = json.loads(request.body)
        job_id = int(data["job_id"])
        action = data["action"]
    except (json.JSONDecodeError, KeyError, ValueError):
        return JsonResponse({"error": "Invalid request."}, status=400)

    session_key = _get_session_key(request)
    user = request.user

    if action == "accept":
        from .tools import execute_tool
        context = {"user": user, "session_key": session_key}
        result = execute_tool("accept_job", {"job_id": job_id}, context)
        reply = result
        # Client notification is handled inside _accept_job → _notify_client_of_acceptance
    elif action == "decline":
        reply = f"You have declined job #{job_id}. You will continue to receive new job offers."
    else:
        return JsonResponse({"error": "Unknown action."}, status=400)

    # Log both the action and the reply in chat
    ChatMessage.objects.create(
        user=user,
        session_key=session_key,
        role=ChatMessage.Role.USER,
        body="Accept job" if action == "accept" else "Decline job",
    )
    ChatMessage.objects.create(
        user=user,
        session_key=session_key,
        role=ChatMessage.Role.ASSISTANT,
        body=reply,
    )

    return JsonResponse({"reply": reply})
