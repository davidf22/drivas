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
            "Collect their first name, last name, and email through conversation "
            "BEFORE calling this. Email is required for clients. Confirm the details with the user first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "first_name": {"type": "string"},
                "last_name": {"type": "string"},
                "email": {
                    "type": "string",
                    "description": "Client's email address (required).",
                },
            },
            "required": ["first_name", "last_name", "email"],
        },
    },
    {
        "name": "register_driver",
        "description": (
            "Register a new driver in Drivas. "
            "Drivers do NOT bring their own vehicle — they drive the client's car. "
            "Collect first name, last name, phone number, email address, and driver's license number through conversation. "
            "All fields are required. Confirm the details before calling this tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "first_name": {"type": "string"},
                "last_name": {"type": "string"},
                "phone_number": {
                    "type": "string",
                    "description": "Driver's phone number (e.g. +2348012345678). Shared with clients after job acceptance.",
                },
                "email": {
                    "type": "string",
                    "description": "Driver's email address (required for job notifications).",
                },
                "license_number": {
                    "type": "string",
                    "description": "Driver's official license number.",
                },
            },
            "required": ["first_name", "last_name", "phone_number", "email", "license_number"],
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
                    "description": "Agreed monthly salary (optional).",
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
            "The message will appear in their chat the next time they open it. "
            "When notifying a driver about a job offer, pass job_id so they get Accept/Decline buttons."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer"},
                "message": {"type": "string"},
                "job_id": {
                    "type": "integer",
                    "description": "Pass the job ID when this is a job offer notification to a driver.",
                },
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

    if not email:
        return "Error: email address is required to register as a client. Please ask the user for their email."

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
    phone_number = data.get("phone_number", "").strip()

    if not email:
        return "Error: email address is required to register as a driver. Please ask the user for their email."

    if not phone_number:
        return "Error: phone number is required to register as a driver. Please ask the user for their phone number."

    password = _generate_password()

    if DriverProfile.objects.filter(license_number=license_number).exists():
        return f"Error: a driver with license number {license_number} is already registered."

    username = _unique_username(f"{first.lower()}_{last.lower()}")
    user = CustomUser.objects.create_user(
        username=username,
        first_name=first,
        last_name=last,
        email=email,
        phone=phone_number,
        role=CustomUser.Role.DRIVER,
        password=password,
    )
    DriverProfile.objects.create(
        user=user,
        license_number=license_number,
        status="available",
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

    # Email all available verified drivers
    _email_available_drivers(job)

    rate_line = f"\nAgreed Rate: ${job.agreed_rate}/month" if job.agreed_rate else ""
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
        rate = f" | Rate: ${j.agreed_rate}/month" if j.agreed_rate else ""
        lines.append(
            f"  #{j.id} | {j.get_employment_type_display()} | "
            f"{j.work_location}{rate}"
            + (f" | {j.requirements[:60]}" if j.requirements else "")
        )
    return "\n".join(lines)


def _get_or_create_history(user):
    """Get or create ConversationHistory for a user, keyed by user_{id}."""
    from .models import ConversationHistory
    session_key = f"user_{user.id}"
    history = ConversationHistory.objects.filter(phone_number=session_key).first()
    if history is None:
        history = ConversationHistory.objects.filter(user=user).first()
        if history:
            history.phone_number = session_key
            history.save(update_fields=["phone_number"])
        else:
            history = ConversationHistory.objects.create(phone_number=session_key, user=user)
    if history.user is None:
        history.user = user
        history.save(update_fields=["user"])
    return history, session_key


def _notify_client_of_acceptance(job, driver) -> None:
    """
    Notify the client that a driver has accepted their job.
    Driver contact details are withheld until the client completes salary payment.
    """
    from .models import ChatMessage
    from .contract import generate_contract_pdf

    client = job.client
    payment_url = f"{settings.SITE_URL}/chat/pay/{job.id}/"
    contract_url = f"{settings.SITE_URL}/chat/contract/{job.id}/"
    message = (
        f"Great news! A driver has accepted your job offer.\n"
        f"{'─' * 30}\n"
        f"Job #{job.id} — {job.get_employment_type_display()}\n"
        f"Location:  {job.work_location}\n\n"
        f"To receive your driver's contact details, please complete the salary payment:\n"
        f"{payment_url}\n\n"
        f"Your employment contract is also ready to download:\n{contract_url}"
    )

    history, session_key = _get_or_create_history(client)
    history.append_assistant(message)
    history.save()

    ChatMessage.objects.create(
        user=client,
        session_key=session_key,
        role=ChatMessage.Role.ASSISTANT,
        body=message,
    )

    # Email the client with PDF contract attached — driver phone still withheld
    if client.email:
        from django.core.mail import get_connection, EmailMessage
        from django.conf import settings
        import ssl, certifi
        try:
            pdf_bytes = generate_contract_pdf(job)
            connection = get_connection(
                ssl_context=ssl.create_default_context(cafile=certifi.where())
            )
            email = EmailMessage(
                subject=f"Drivas — A driver has accepted your job (#{job.id})",
                body=(
                    f"Hi {client.first_name or client.username},\n\n"
                    f"Great news! A driver has accepted your job offer on Drivas.\n\n"
                    f"Job #{job.id}\n"
                    f"{'─' * 30}\n"
                    f"Type:      {job.get_employment_type_display()}\n"
                    f"Location:  {job.work_location}\n\n"
                    f"To receive your driver's contact details, please complete the salary payment:\n"
                    f"{payment_url}\n\n"
                    f"Your employment contract is attached. Both parties should sign and keep a copy.\n\n"
                    f"Log in to your Drivas chat for updates: {settings.SITE_URL}/chat/\n\n"
                    f"— The Drivas Team"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[client.email],
                connection=connection,
            )
            email.attach(
                f"drivas_contract_{job.id}.pdf",
                pdf_bytes,
                "application/pdf",
            )
            email.send(fail_silently=True)
        except Exception as exc:
            logger.error("Failed to email client %s on job acceptance: %s", client.id, exc)


def _notify_driver_of_acceptance(job, driver) -> None:
    """Push an in-chat notification and email (with PDF contract) to the driver after they accept a job."""
    from .models import ChatMessage
    from .contract import generate_contract_pdf

    contract_url = f"{settings.SITE_URL}/chat/contract/{job.id}/"
    message = (
        f"You have successfully accepted job #{job.id}.\n"
        f"{'─' * 30}\n"
        f"Client:    {job.client.get_full_name()}\n"
        f"Location:  {job.work_location}\n"
        f"Type:      {job.get_employment_type_display()}\n\n"
        f"Your employment contract is ready to download:\n{contract_url}\n\n"
        f"Please report to the work location as agreed. Good luck!"
    )

    history, session_key = _get_or_create_history(driver)
    history.append_assistant(message)
    history.save()

    ChatMessage.objects.create(
        user=driver,
        session_key=session_key,
        role=ChatMessage.Role.ASSISTANT,
        body=message,
    )

    # Email the driver with PDF attachment
    if driver.email:
        from django.core.mail import get_connection, EmailMessage
        from django.conf import settings
        import ssl, certifi
        try:
            pdf_bytes = generate_contract_pdf(job)
            connection = get_connection(
                ssl_context=ssl.create_default_context(cafile=certifi.where())
            )
            email = EmailMessage(
                subject=f"Drivas — Contract for job #{job.id}",
                body=(
                    f"Hi {driver.first_name or driver.username},\n\n"
                    f"You have accepted a job on Drivas. Here are the details:\n\n"
                    f"Job #{job.id}\n"
                    f"{'─' * 30}\n"
                    f"Client:    {job.client.get_full_name()}\n"
                    f"Location:  {job.work_location}\n"
                    f"Type:      {job.get_employment_type_display()}\n\n"
                    f"Your employment contract is attached. Please sign and keep a copy.\n\n"
                    f"Log in to your Drivas chat: {settings.SITE_URL}/chat/\n\n"
                    f"— The Drivas Team"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[driver.email],
                connection=connection,
            )
            email.attach(
                f"drivas_contract_{job.id}.pdf",
                pdf_bytes,
                "application/pdf",
            )
            email.send(fail_silently=True)
        except Exception as exc:
            logger.error("Failed to email driver %s on job acceptance: %s", driver.id, exc)


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

    # Notify client and send contract to both parties
    _notify_client_of_acceptance(job, user)
    _notify_driver_of_acceptance(job, user)

    return (
        f"Job #{job.id} accepted!\n"
        f"Client:       {job.client.get_full_name()}\n"
        f"Location:     {job.work_location}\n"
        f"Type:         {job.get_employment_type_display()}\n"
        f"Requirements: {job.requirements or 'None'}\n"
        f"The client has been notified and contracts have been sent to both parties."
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
    rate = f"\nAgreed Rate:  ${job.agreed_rate}/month" if job.agreed_rate else ""
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


def _email_available_drivers(job) -> None:
    """Send job notification emails and in-chat notifications to all available verified drivers."""
    from accounts.models import DriverProfile
    from .email_utils import send_job_notification_email
    from .models import ConversationHistory, ChatMessage

    rate_line = f"\nRate:         ${job.agreed_rate}/month" if job.agreed_rate else ""
    message = (
        f"New job available! Job #{job.id}\n"
        f"{'─' * 24}\n"
        f"Type:         {job.get_employment_type_display()}\n"
        f"Location:     {job.work_location}{rate_line}\n"
        f"Requirements: {job.requirements or 'None'}\n\n"
        f"Would you like to accept this job?"
    )

    candidates = (
        DriverProfile.objects.filter(status="available", is_verified=True)
        .select_related("user")
    )
    for profile in candidates:
        driver = profile.user
        history, session_key = _get_or_create_history(driver)
        history.append_assistant(message)
        history.save()

        ChatMessage.objects.create(
            user=driver,
            session_key=session_key,
            role=ChatMessage.Role.ASSISTANT,
            body=message,
            job_offer_id=job.id,
        )

        send_job_notification_email(driver, job)


def _notify_user(data: dict, context: dict) -> str:
    from accounts.models import CustomUser
    from .models import ConversationHistory, ChatMessage

    try:
        recipient = CustomUser.objects.get(pk=data["user_id"])
    except CustomUser.DoesNotExist:
        return f"Error: user ID {data['user_id']} not found."

    message = data["message"]
    job_id = data.get("job_id")

    history, session_key = _get_or_create_history(recipient)
    history.append_assistant(message)
    history.save()

    ChatMessage.objects.create(
        user=recipient,
        session_key=session_key,
        role=ChatMessage.Role.ASSISTANT,
        body=message,
        job_offer_id=job_id,
    )

    return f"Notification delivered to {recipient.get_full_name()} (user #{recipient.id})."
