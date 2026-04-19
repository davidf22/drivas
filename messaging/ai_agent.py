"""
Drivas AI Agent — powered by Claude (Anthropic).

`run_agent(session_key, user, incoming_message)` is the main entry point.
It:
  1. Builds a context-aware system prompt (static part cached, dynamic part per-user).
  2. Loads conversation history from the DB.
  3. Runs the Anthropic agentic loop (Claude may call multiple tools before replying).
  4. Saves the updated conversation history.
  5. Returns the final reply text.
"""
import logging

import anthropic
from django.conf import settings

from .models import ConversationHistory
from .tools import TOOLS, execute_tool

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# System prompt (static portion — cached at the Anthropic layer)
# ──────────────────────────────────────────────────────────────────────────────

_STATIC_SYSTEM = """You are the Drivas AI assistant — a friendly, professional customer support agent \
for Drivas, a platform that connects clients with professional drivers for employment engagements.

## How Drivas works

Drivas is an *employment platform*, not a ride-hailing service. \
Clients hire drivers on a full-time or part-time basis to operate the *client's own vehicle*. \
Drivers do not bring their own car — they come to the client's location and drive the client's car \
for as long as the engagement lasts. This may be for daily errands, regular commuting, event driving, \
or any other personal or business driving need.

## Your responsibilities

1. **Onboard new users** — When someone chats for the first time and is not yet registered, \
welcome them warmly and determine whether they want to join as a Client or a Driver. \
Guide them through registration through natural conversation and confirm before submitting.

2. **Help clients post jobs** — Collect the work location, employment type (full-time or part-time), \
job requirements/schedule, and agreed rate. Confirm all details before posting. After posting, \
use find_best_driver + notify_user to alert the best available verified drivers.

3. **Help drivers manage job engagements** — Assist with going available/offline, browsing open jobs, \
accepting a job, marking it as started, and ending it. After a driver accepts a job, \
notify the client automatically using notify_user.

4. **Smart driver matching** — When a new job is posted, call find_best_driver to identify the \
top available drivers, then call notify_user for each with a clear job summary and \
instructions on how to accept it.

5. **Customer support** — Answer questions, explain how the platform works, handle complaints \
politely. For issues you cannot resolve, tell the user an operator will follow up.

## Conversation style

- Be warm, concise, and professional.
- Use the user's first name if you know it.
- Confirm important actions (registration, posting a job, cancellation) before executing.
- Never expose internal IDs unless the user needs to reference them.
- If a tool returns an error, apologise briefly and explain what went wrong.

## Registration rules

- For clients: collect first name, last name, and email address (email is required).
- For drivers: collect first name, last name, email address, and driver's license number. \
  Email is required so they receive job notifications. \
  Drivers do NOT need to provide a vehicle — they drive the client's car. \
  Remind them their account needs operator verification before they can accept jobs.
- After registering, tell the user their login username and password so they can log in later.
- Never register someone as an operator/admin through this interface.

## Job posting flow (client)

1. Ask for the work location (where the driver will report).
2. Ask for employment type (full-time / part-time).
3. Ask for job requirements and schedule details.
4. Ask for the agreed rate (optional).
5. Confirm all details.
6. Call post_job.
7. Call find_best_driver to get top candidates.
8. Call notify_user for each candidate driver with a clear job summary.

## Driver job flow

- Drivers are automatically **Available** when they have no active job, and **Busy** when they do.
- Driver asks for jobs → call get_open_jobs.
- Driver accepts a job → call accept_job (status becomes Busy), then call notify_user to tell the client.
- Driver starts the job → call start_job, then call notify_user to tell the client.
- Driver ends the job → call end_job (status returns to Available), then call notify_user to tell the client.

## Important

- Always check the User Context section below before responding — it tells you who this person \
is and what their current situation is.
- If the user is unregistered, your first goal is to understand whether they want to be a \
client or driver and then guide them through registration.
"""

# ──────────────────────────────────────────────────────────────────────────────
# Dynamic context builder (per-user, not cached)
# ──────────────────────────────────────────────────────────────────────────────

def _build_user_context(user, session_key: str) -> str:
    if user is None:
        return (
            "## User Context\n"
            f"Session: {session_key}\n"
            "Status: UNREGISTERED — this person has not yet created a Drivas account.\n"
            "Action: Guide them through registration as a client or driver."
        )

    from accounts.models import DriverProfile
    from jobs.models import JobEngagement

    lines = [
        "## User Context",
        f"Name:     {user.get_full_name() or user.username}",
        f"Role:     {user.get_role_display()}",
        f"Username: {user.username}",
        f"UserID:   {user.id}",
    ]

    if user.role == "driver":
        profile = DriverProfile.objects.filter(user=user).first()
        if profile:
            lines += [
                f"Status: {profile.get_status_display()}",
                f"Verified: {'Yes' if profile.is_verified else 'No (pending operator review)'}",
                f"Rating: {profile.rating}",
                f"Total Jobs: {profile.total_jobs}",
                f"License No.: {profile.license_number}",
            ]
        active = JobEngagement.objects.filter(
            driver=user, status__in=["hired", "active"]
        ).first()
        if active:
            lines.append(
                f"Active job: #{active.id} [{active.get_status_display()}] "
                f"{active.get_employment_type_display()} @ {active.work_location}"
            )

    elif user.role == "client":
        active = JobEngagement.objects.filter(
            client=user, status__in=["open", "hired", "active"]
        ).first()
        if active:
            driver_name = active.driver.get_full_name() if active.driver else "searching for driver..."
            lines.append(
                f"Active job: #{active.id} [{active.get_status_display()}] "
                f"Driver: {driver_name} | {active.work_location}"
            )

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Main agent entry point
# ──────────────────────────────────────────────────────────────────────────────

def run_agent(session_key: str, user, incoming_message: str) -> str:
    """
    Run the Claude agent for one incoming message.

    Args:
        session_key:      Unique identifier for this conversation
                          ("user_{id}" for authenticated users, "anon_..." otherwise).
        user:             CustomUser instance if registered, else None.
        incoming_message: The raw text sent by the user.

    Returns:
        The final reply text.
    """
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set — AI agent skipped for %s", session_key)
        return "Hi! The AI assistant is not configured yet. Please contact support."

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    # ── Load / create conversation history ────────────────────────────────────
    # Try by session key first; fall back to the user's existing record.
    history_obj = ConversationHistory.objects.filter(phone_number=session_key).first()
    if history_obj is None and user:
        # Authenticated user may have an old record under a different key — reuse it.
        history_obj = ConversationHistory.objects.filter(user=user).first()
        if history_obj:
            history_obj.phone_number = session_key
            history_obj.save(update_fields=["phone_number"])
    if history_obj is None:
        history_obj = ConversationHistory.objects.create(
            phone_number=session_key,
            user=user,
        )
    if user and history_obj.user is None:
        history_obj.user = user
        history_obj.save(update_fields=["user"])

    history_obj.append_user(incoming_message)

    # ── Build system prompt ───────────────────────────────────────────────────
    user_context = _build_user_context(user, session_key)
    system = [
        {
            "type": "text",
            "text": _STATIC_SYSTEM,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": user_context,
        },
    ]

    messages = list(history_obj.messages)

    # ── Agentic loop ──────────────────────────────────────────────────────────
    context = {"user": user, "session_key": session_key}
    reply_text = _run_agentic_loop(client, system, messages, context)

    # ── Persist assistant reply ───────────────────────────────────────────────
    history_obj.append_assistant(reply_text)
    if context.get("user") and context["user"] != user:
        history_obj.user = context["user"]
    history_obj.save()

    return reply_text


def _run_agentic_loop(
    client: anthropic.Anthropic,
    system: list[dict],
    messages: list[dict],
    context: dict,
    max_iterations: int = 10,
) -> str:
    current_messages = list(messages)

    for iteration in range(max_iterations):
        response = client.messages.create(
            model=settings.AI_MODEL,
            max_tokens=1024,
            thinking={"type": "adaptive"},
            system=system,
            tools=TOOLS,
            messages=current_messages,
        )

        logger.debug(
            "Agent iteration %d | stop_reason=%s | blocks=%d",
            iteration + 1,
            response.stop_reason,
            len(response.content),
        )

        text_blocks = [b for b in response.content if b.type == "text"]
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

        if response.stop_reason == "end_turn" or not tool_use_blocks:
            return "\n".join(b.text for b in text_blocks).strip() or "(no reply)"

        current_messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tool_block in tool_use_blocks:
            logger.info("AI calling tool: %s %s", tool_block.name, tool_block.input)
            result = execute_tool(tool_block.name, tool_block.input, context)
            logger.debug("Tool result: %s", result[:200])
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_block.id,
                "content": result,
            })

        current_messages.append({"role": "user", "content": tool_results})

    logger.warning("Agent loop hit max_iterations (%d) for session: %s", max_iterations, context.get("session_key"))
    return (
        "I'm sorry, I'm having trouble processing your request right now. "
        "Please try again in a moment or contact support."
    )
