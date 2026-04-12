"""
Tool definitions (schemas) and executors for the Drivas AI agent.

`execute_tool(name, input_data, context)` dispatches to the right handler.

`context` is a mutable dict:
  {
      "user":        CustomUser | None,  # current user
      "session_key": str,                # conversation session identifier
  }
After a successful registration the "user" key is updated in-place so
subsequent tool calls in the same agent turn have access to the new user.
"""
import logging
import secrets
import string

from django.utils import timezone

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Tool schema definitions  (passed to the Anthropic API)
# ──────────────────────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "register_client",
        "description": (
            "Register a new person as a client in Drivas. "
            "Collect their first name, last name, and optionally email through conversation "
            "BEFORE calling this. Confirm the details with the user first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "first_name": {"type": "string"},
                "last_name": {"type": "string"},
                "email": {
                    "type": "string",
                    "description": "Optional email address.",
                },
            },
            "required": ["first_name", "last_name"],
        },
    },
    {
        "name": "register_driver",
        "description": (
            "Register a new driver in Drivas. "
            "Drivers do NOT bring their own vehicle — they drive the client's car. "
            "Collect first name, last name, and driver's license number through conversation. "
            "Confirm the details before calling this tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "first_name": {"type": "string"},
                "last_name": {"type": "string"},
                "license_number": {
                    "type": "string",
                    "description": "Driver's official license number.",
                },
                "email": {
                    "type": "string",
                    "description": "Optional email address.",
                },
            },
            "required": ["first_name", "last_name", "license_number"],
        },
    },
    {
        "name": "post_job",
        "description": (
            "Post a new job engagement for the current client. "
            "A job is an employment arrangement where a driver will operate the client's own car. "
            "Always confirm work_location, employment_type, requirements, and agreed_rate "
            "with the client before calling this tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "work_location": {
                    "type": "string",
                    "description": "Address or area where the driver will report to work.",
                },
                "employment_type": {
                    "type": "string",
                    "enum": ["full_time", "part_time"],
                },
                "requirements": {
                    "type": "string",
                    "description": "Job requirements, schedule, and any special instructions.",
                },
                "agreed_rate": {
                    "type": "number",
                    "description": "Agreed hourly or daily rate (optional).",
                },
            },
            "required": ["work_location", "employment_type"],
        },
    },
    {
        "name": "get_open_jobs",
        "description": "Get a list of open job engagements the current driver can apply for.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "accept_job",
        "description": (
            "Accept a specific open job engagement as the current driver. "
            "The driver must be in Available status. "
            "After accepting, notify the client automatically."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"job_id": {"type": "integer"}},
            "required": ["job_id"],
        },
    },
    {
        "name": "start_job",
        "description": "Mark a job engagement as active (driver has reported to work and started).",
        "input_schema": {
            "type": "object",
            "properties": {"job_id": {"type": "integer"}},
            "required": ["job_id"],
        },
    },
    {
        "name": "end_job",
        "description": "Mark a job engagement as ended (work period is complete).",
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "integer"},
                "total_earned": {
                    "type": "number",
                    "description": "Total amount earned for this engagement (optional).",
                },
            },
            "required": ["job_id"],
        },
    },
    {
        "name": "cancel_job",
        "description": (
            "Cancel a job engagement. "
            "Clients can cancel open or hired jobs; drivers can cancel hired jobs only."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "integer"},
                "reason": {"type": "string"},
            },
            "required": ["job_id"],
        },
    },
    {
        "name": "get_job_info",
        "description": "Get the current status and details of a specific job engagement by ID.",
        "input_schema": {
            "type": "object",
            "properties": {"job_id": {"type": "integer"}},
            "required": ["job_id"],
        },
    },
    {
        "name": "get_my_jobs",
        "description": (
            "Get recent job engagements for the current user. "
            "Clients see their posted jobs; drivers see their accepted engagements."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "How many jobs to return (default 5)"}
            },
        },
    },
    {
        "name": "set_driver_availability",
        "description": (
            "Set the current driver's availability. "
            "Set available=true when ready to accept jobs, available=false when unavailable."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "available": {
                    "type": "boolean",
                    "description": "true = available for work, false = unavailable",
                }
            },
            "required": ["available"],
        },
    },
    {
        "name": "find_best_driver",
        "description": (
            "Find the best available verified drivers for a specific job based on rating. "
            "Returns the top candidates. Use after posting a job to identify who to notify."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "integer"},
                "max_candidates": {
                    "type": "integer",
                    "description": "How many top drivers to return (default 5)",
                },
            },
            "required": ["job_id"],
        },
    },
    {
        "name": "notify_user",
        "description": (
            "Send an in-app notification message to another registered user. "
            "Use this to notify drivers about new job openings or clients about driver acceptance. "
            "The message will appear in their chat the next time they open it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer"},
                "message": {"type": "string"},
            },
            "required": ["user_id", "message"],
        },
    },
]

# ──────────────────────────────────────────────────────────────────────────────
# Tool executor
# ──────────────────────────────────────────────────────────────────────────────

def execute_tool(name: str, input_data: dict, context: dict) -> str:
    handlers = {
        "register_client": _register_client,
        "register_driver": _register_driver,
        "post_job": _post_job,
        "get_open_jobs": _get_open_jobs,
        "accept_job": _accept_job,
        "start_job": _start_job,
        "end_job": _end_job,
        "cancel_job": _cancel_job,
        "get_job_info": _get_job_info,
        "get_my_jobs": _get_my_jobs,
        "set_driver_availability": _set_driver_availability,
        "find_best_driver": _find_best_driver,
        "notify_user": _notify_user,
    }
    handler = handlers.get(name)
    if not handler:
        return f"Error: unknown tool '{name}'"
    try:
        return handler(input_data, context)
    except Exception as exc:
        logger.exception("Tool %s raised an exception", name)
        return f"Error: {exc}"


# ──────────────────────────────────────────────────────────────────────────────
# Individual handlers
# ──────────────────────────────────────────────────────────────────────────────

def _generate_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _unique_username(base: str) -> str:
    from accounts.models import CustomUser
    username = base[:28]
    suffix = secrets.token_hex(3)
    candidate = f"{username}_{suffix}"
    while CustomUser.objects.filter(username=candidate).exists():
        candidate = f"{username}_{secrets.token_hex(3)}"
    return candidate


def _register_client(data: dict, context: dict) -> str:
    from accounts.models import CustomUser, ClientProfile

    first = data["first_name"].strip()
    last = data["last_name"].strip()
    email = data.get("email", "").strip()
    password = _generate_password()

    username = _unique_username(f"{first.lower()}_{last.lower()}")
    user = CustomUser.objects.create_user(
        username=username,
        first_name=first,
        last_name=last,
        email=email,
        role=CustomUser.Role.CLIENT,
        password=password,
    )
    ClientProfile.objects.create(user=user)
    context["user"] = user

    # Link any existing anonymous conversation history to this user
    session_key = context.get("session_key", "")
    from .models import ConversationHistory
    ConversationHistory.objects.filter(phone_number=session_key).update(user=user)

    return (
        f"Success: {first} {last} registered as a client (user ID {user.id}).\n"
        f"Login credentials:\n"
        f"  Username: {username}\n"
        f"  Password: {password}\n"
        f"Please save these — the password is not stored in plain text."
    )


def _register_driver(data: dict, context: dict) -> str:
    from accounts.models import CustomUser, DriverProfile

    first = data["first_name"].strip()
    last = data["last_name"].strip()
    license_number = data["license_number"].strip()
    email = data.get("email", "").strip()
    password = _generate_password()

    if DriverProfile.objects.filter(license_number=license_number).exists():
        return f"Error: a driver with license number {license_number} is already registered."

    username = _unique_username(f"{first.lower()}_{last.lower()}")
    user = CustomUser.objects.create_user(
        username=username,
        first_name=first,
        last_name=last,
        email=email,
        role=CustomUser.Role.DRIVER,
        password=password,
    )
    DriverProfile.objects.create(
        user=user,
        license_number=license_number,
        status="offline",
        is_verified=False,
    )
    context["user"] = user

    session_key = context.get("session_key", "")
    from .models import ConversationHistory
    ConversationHistory.objects.filter(phone_number=session_key).update(user=user)

    return (
        f"Success: {first} {last} registered as a driver (user ID {user.id}).\n"
        f"Login credentials:\n"
        f"  Username: {username}\n"
        f"  Password: {password}\n"
        f"Please save these — the password is not stored in plain text.\n"
        f"Note: your account is pending verification by an operator before you can accept jobs."
    )


def _post_job(data: dict, context: dict) -> str:
    from jobs.models import JobEngagement, JobStatusLog

    user = context.get("user")
    if not user or user.role != "client":
        return "Error: only registered clients can post jobs."

    job = JobEngagement.objects.create(
        client=user,
        employment_type=data["employment_type"],
        work_location=data["work_location"].strip(),
        requirements=data.get("requirements", "").strip(),
        agreed_rate=data.get("agreed_rate"),
        status=JobEngagement.Status.OPEN,
    )
    JobStatusLog.objects.create(job=job, status=JobEngagement.Status.OPEN, changed_by=user)

    rate_line = f"\nAgreed Rate: ${job.agreed_rate}/hr" if job.agreed_rate else ""
    return (
        f"Job #{job.id} posted successfully.\n"
        f"Type:         {job.get_employment_type_display()}\n"
        f"Location:     {job.work_location}\n"
        f"Requirements: {job.requirements or 'None'}{rate_line}\n"
        f"Status:       Open — searching for a driver."
    )


def _get_open_jobs(data: dict, context: dict) -> str:
    from jobs.models import JobEngagement

    user = context.get("user")
    if not user or user.role != "driver":
        return "Error: only drivers can view open jobs."

    jobs = JobEngagement.objects.filter(status=JobEngagement.Status.OPEN).order_by("created_at")[:10]
    if not jobs:
        return "No open jobs available at the moment."

    lines = ["Open job engagements:"]
    for j in jobs:
        rate = f" | Rate: ${j.agreed_rate}/hr" if j.agreed_rate else ""
        lines.append(
            f"  #{j.id} | {j.get_employment_type_display()} | "
            f"{j.work_location}{rate}"
            + (f" | {j.requirements[:60]}" if j.requirements else "")
        )
    return "\n".join(lines)


def _accept_job(data: dict, context: dict) -> str:
    from accounts.models import DriverProfile
    from jobs.models import JobEngagement, JobStatusLog

    user = context.get("user")
    if not user or user.role != "driver":
        return "Error: only drivers can accept jobs."

    try:
        job = JobEngagement.objects.get(pk=data["job_id"], status=JobEngagement.Status.OPEN)
    except JobEngagement.DoesNotExist:
        return f"Error: job #{data['job_id']} is not available."

    try:
        profile = DriverProfile.objects.get(user=user)
    except DriverProfile.DoesNotExist:
        return "Error: driver profile not found."

    if not profile.is_verified:
        return "Error: your account is pending verification by an operator."

    if profile.status != "available":
        return "Error: you must be set to Available before accepting a job."

    job.driver = user
    job.status = JobEngagement.Status.HIRED
    job.hired_at = timezone.now()
    job.save()
    profile.status = "busy"
    profile.save()
    JobStatusLog.objects.create(job=job, status=JobEngagement.Status.HIRED, changed_by=user)

    return (
        f"Job #{job.id} accepted!\n"
        f"Client:       {job.client.get_full_name()}\n"
        f"Location:     {job.work_location}\n"
        f"Type:         {job.get_employment_type_display()}\n"
        f"Requirements: {job.requirements or 'None'}\n"
        f"Client has been notified."
    )


def _start_job(data: dict, context: dict) -> str:
    from jobs.models import JobEngagement, JobStatusLog

    user = context.get("user")
    if not user or user.role != "driver":
        return "Error: only drivers can start jobs."

    try:
        job = JobEngagement.objects.get(pk=data["job_id"], driver=user, status=JobEngagement.Status.HIRED)
    except JobEngagement.DoesNotExist:
        return f"Error: job #{data['job_id']} not found or not in hired state."

    job.status = JobEngagement.Status.ACTIVE
    job.started_at = timezone.now()
    job.save()
    JobStatusLog.objects.create(job=job, status=JobEngagement.Status.ACTIVE, changed_by=user)

    return f"Job #{job.id} is now ACTIVE. Client has been notified. Say 'job ended' when you finish."


def _end_job(data: dict, context: dict) -> str:
    from accounts.models import DriverProfile
    from jobs.models import JobEngagement, JobStatusLog

    user = context.get("user")
    if not user or user.role != "driver":
        return "Error: only drivers can end jobs."

    try:
        job = JobEngagement.objects.get(pk=data["job_id"], driver=user, status=JobEngagement.Status.ACTIVE)
    except JobEngagement.DoesNotExist:
        return f"Error: job #{data['job_id']} not found or not active."

    job.status = JobEngagement.Status.ENDED
    job.ended_at = timezone.now()
    if data.get("total_earned"):
        job.total_earned = data["total_earned"]
    job.save()

    profile = DriverProfile.objects.filter(user=user).first()
    if profile:
        profile.status = "available"
        profile.total_jobs += 1
        profile.save()

    JobStatusLog.objects.create(job=job, status=JobEngagement.Status.ENDED, changed_by=user)

    return (
        f"Job #{job.id} marked as ENDED. Great work!\n"
        f"Your status is back to Available. Total jobs completed: {profile.total_jobs if profile else '?'}"
    )


def _cancel_job(data: dict, context: dict) -> str:
    from accounts.models import DriverProfile
    from jobs.models import JobEngagement, JobStatusLog

    user = context.get("user")
    if not user:
        return "Error: you must be registered to cancel a job."

    job_id = data["job_id"]
    if user.role == "client":
        job = JobEngagement.objects.filter(
            pk=job_id, client=user,
            status__in=[JobEngagement.Status.OPEN, JobEngagement.Status.HIRED]
        ).first()
    elif user.role == "driver":
        job = JobEngagement.objects.filter(
            pk=job_id, driver=user, status=JobEngagement.Status.HIRED
        ).first()
    else:
        job = JobEngagement.objects.filter(pk=job_id).first()

    if not job:
        return f"Error: job #{job_id} not found or cannot be cancelled in its current state."

    job.status = JobEngagement.Status.CANCELLED
    job.save()

    if job.driver:
        profile = DriverProfile.objects.filter(user=job.driver).first()
        if profile:
            profile.status = "available"
            profile.save()

    JobStatusLog.objects.create(
        job=job,
        status=JobEngagement.Status.CANCELLED,
        changed_by=user,
        note=data.get("reason", ""),
    )
    return f"Job #{job_id} has been cancelled."


def _get_job_info(data: dict, context: dict) -> str:
    from jobs.models import JobEngagement

    user = context.get("user")
    try:
        job = JobEngagement.objects.select_related("client", "driver").get(pk=data["job_id"])
    except JobEngagement.DoesNotExist:
        return f"Error: job #{data['job_id']} not found."

    if user and user.role not in ("admin",) and job.client != user and job.driver != user:
        return "Error: you do not have permission to view this job."

    driver_name = job.driver.get_full_name() if job.driver else "Not assigned yet"
    rate = f"\nAgreed Rate:  ${job.agreed_rate}/hr" if job.agreed_rate else ""
    earned = f"\nTotal Earned: ${job.total_earned}" if job.total_earned else ""
    return (
        f"Job #{job.id}\n"
        f"Status:       {job.get_status_display()}\n"
        f"Type:         {job.get_employment_type_display()}\n"
        f"Client:       {job.client.get_full_name()}\n"
        f"Driver:       {driver_name}\n"
        f"Location:     {job.work_location}\n"
        f"Requirements: {job.requirements or 'None'}{rate}{earned}\n"
        f"Posted:       {job.created_at.strftime('%Y-%m-%d %H:%M UTC')}"
    )


def _get_my_jobs(data: dict, context: dict) -> str:
    from jobs.models import JobEngagement

    user = context.get("user")
    if not user:
        return "Error: you must be registered to view jobs."

    limit = int(data.get("limit") or 5)
    if user.role == "client":
        jobs = JobEngagement.objects.filter(client=user).order_by("-created_at")[:limit]
    else:
        jobs = JobEngagement.objects.filter(driver=user).order_by("-created_at")[:limit]

    if not jobs:
        return "You have no job engagements yet."

    lines = [f"Your last {len(jobs)} job(s):"]
    for j in jobs:
        lines.append(
            f"  #{j.id} | {j.get_status_display()} | "
            f"{j.get_employment_type_display()} | {j.work_location}"
        )
    return "\n".join(lines)


def _set_driver_availability(data: dict, context: dict) -> str:
    from accounts.models import DriverProfile

    user = context.get("user")
    if not user or user.role != "driver":
        return "Error: only drivers can change availability."

    profile = DriverProfile.objects.filter(user=user).first()
    if not profile:
        return "Error: driver profile not found."

    if not profile.is_verified:
        return "Error: your account is pending verification. Contact support."

    profile.status = "available" if data["available"] else "offline"
    profile.save()
    label = "Available (you will receive job offers)" if data["available"] else "Offline"
    return f"Your status is now: {label}"


def _find_best_driver(data: dict, context: dict) -> str:
    from accounts.models import DriverProfile
    from jobs.models import JobEngagement

    try:
        job = JobEngagement.objects.get(pk=data["job_id"])
    except JobEngagement.DoesNotExist:
        return f"Error: job #{data['job_id']} not found."

    max_candidates = int(data.get("max_candidates") or 5)
    candidates = (
        DriverProfile.objects.filter(status="available", is_verified=True)
        .select_related("user")
        .order_by("-rating", "-total_jobs")[:max_candidates]
    )

    if not candidates:
        return "No available verified drivers found at this time."

    lines = [f"Top {len(candidates)} available driver(s) for job #{job.id}:"]
    for p in candidates:
        lines.append(
            f"  User ID {p.user.id} | {p.user.get_full_name()} | "
            f"Rating {p.rating} | {p.total_jobs} jobs completed"
        )
    return "\n".join(lines)


def _notify_user(data: dict, context: dict) -> str:
    from accounts.models import CustomUser
    from .models import ConversationHistory, ChatMessage

    try:
        recipient = CustomUser.objects.get(pk=data["user_id"])
    except CustomUser.DoesNotExist:
        return f"Error: user ID {data['user_id']} not found."

    message = data["message"]
    session_key = f"user_{recipient.id}"

    # Push into their conversation history so it appears next time they open chat
    history, _ = ConversationHistory.objects.get_or_create(
        phone_number=session_key,
        defaults={"user": recipient},
    )
    history.append_assistant(message)
    history.save()

    # Also log as a ChatMessage
    ChatMessage.objects.create(
        user=recipient,
        session_key=session_key,
        role=ChatMessage.Role.ASSISTANT,
        body=message,
    )

    return f"Notification delivered to {recipient.get_full_name()} (user #{recipient.id})."
