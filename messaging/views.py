import json
import logging
import secrets

import requests as http_requests

from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
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
    last_message_time = messages[-1].created_at.isoformat() if messages else ""
    return render(request, "messaging/chat.html", {
        "chat_messages": messages,
        "last_message_time": last_message_time,
    })


def poll_messages(request):
    """
    Return any new ChatMessages since `after` (ISO timestamp).
    Called every few seconds by the client via JS to pick up server-pushed notifications.
    """
    after = request.GET.get("after", "")
    session_key = _get_session_key(request)

    qs = ChatMessage.objects.filter(session_key=session_key).order_by("created_at")
    if after:
        try:
            from django.utils.dateparse import parse_datetime
            after_dt = parse_datetime(after)
            if after_dt:
                qs = qs.filter(created_at__gt=after_dt)
        except Exception:
            pass

    messages = [
        {
            "role": m.role,
            "body": m.body,
            "job_offer_id": m.job_offer_id,
            "created_at": m.created_at.isoformat(),
            "time": m.created_at.strftime("%H:%M"),
        }
        for m in qs[:20]
    ]
    return JsonResponse({"messages": messages})


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
        reply = "Sorry, something went wrong. Please try again or contact support at fayankindavid@gmail.com."

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


# ── Paystack salary payment ───────────────────────────────────────────────────

def pay_salary(request, job_id):
    """
    GET:  Show the salary payment form for a specific job.
    POST: Initialize a Paystack transaction and redirect the client to Paystack.
    """
    user = request.user
    if not user.is_authenticated:
        return redirect(f"/accounts/login/?next=/chat/pay/{job_id}/")
    if getattr(user, "role", "") != "client":
        return HttpResponse("Only clients can send salary payments.", status=403)

    from jobs.models import JobEngagement, SalaryPayment

    job = get_object_or_404(JobEngagement, pk=job_id, client=user)
    if not job.driver:
        return render(request, "messaging/pay_salary.html", {
            "job": job, "error": "This job has no assigned driver yet."
        })

    error = None

    if request.method == "POST":
        try:
            amount_ngn = float(request.POST.get("amount", 0))
        except ValueError:
            amount_ngn = 0

        if amount_ngn <= 0:
            error = "Please enter a valid salary amount."
        elif not settings.PAYSTACK_SECRET_KEY:
            error = "Payment gateway is not configured. Please contact support at fayankindavid@gmail.com."
        else:
            reference = "drivas-" + secrets.token_hex(10)
            callback_url = request.build_absolute_uri(f"/chat/pay/callback/?reference={reference}")

            payload = {
                "email": user.email,
                "amount": int(amount_ngn * 100),   # Paystack expects kobo
                "reference": reference,
                "callback_url": callback_url,
                "metadata": {
                    "job_id": job.id,
                    "driver_id": job.driver.id,
                    "driver_name": job.driver.get_full_name(),
                    "client_id": user.id,
                },
            }
            try:
                resp = http_requests.post(
                    "https://api.paystack.co/transaction/initialize",
                    json=payload,
                    headers={"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"},
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("status"):
                    SalaryPayment.objects.create(
                        job=job,
                        amount=amount_ngn,
                        reference=reference,
                        status=SalaryPayment.Status.PENDING,
                    )
                    return redirect(data["data"]["authorization_url"])
                else:
                    error = data.get("message", "Payment initialization failed.")
            except Exception as exc:
                logger.error("Paystack init failed for job %s: %s", job_id, exc)
                error = "Could not reach payment gateway. Please try again."

    return render(request, "messaging/pay_salary.html", {"job": job, "error": error})


def pay_callback(request):
    """
    Paystack redirects here after the client completes (or cancels) payment.
    Verifies the transaction and records the result.
    """
    reference = request.GET.get("reference", "")
    if not reference:
        return redirect("/chat/")

    from jobs.models import SalaryPayment

    try:
        payment = SalaryPayment.objects.get(reference=reference)
    except SalaryPayment.DoesNotExist:
        logger.warning("pay_callback: unknown reference %s", reference)
        return redirect("/chat/")

    if payment.status != SalaryPayment.Status.PENDING:
        return render(request, "messaging/pay_result.html", {"payment": payment, "job": payment.job})

    verified = False
    error_msg = None
    try:
        resp = http_requests.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers={"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") and data["data"]["status"] == "success":
            verified = True
    except Exception as exc:
        logger.error("Paystack verify failed for ref %s: %s", reference, exc)
        error_msg = "Could not verify payment. Please contact support at fayankindavid@gmail.com."

    if verified:
        payment.status = SalaryPayment.Status.SUCCESS
        payment.paid_at = timezone.now()
        payment.save()
        _notify_salary_paid(payment)
    else:
        payment.status = SalaryPayment.Status.FAILED
        payment.save()

    return render(request, "messaging/pay_result.html", {
        "payment": payment,
        "job": payment.job,
        "error": error_msg,
    })


@csrf_exempt
def pay_webhook(request):
    """
    Paystack webhook endpoint — verifies HMAC-SHA512 signature before processing.
    """
    import hashlib, hmac

    sig = request.META.get("HTTP_X_PAYSTACK_SIGNATURE", "")
    expected = hmac.new(
        settings.PAYSTACK_SECRET_KEY.encode(),
        request.body,
        hashlib.sha512,
    ).hexdigest()

    if not hmac.compare_digest(sig, expected):
        return HttpResponse(status=400)

    try:
        event = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    if event.get("event") == "charge.success":
        reference = event["data"]["reference"]
        from jobs.models import SalaryPayment
        payment = SalaryPayment.objects.filter(
            reference=reference, status=SalaryPayment.Status.PENDING
        ).first()
        if payment:
            payment.status = SalaryPayment.Status.SUCCESS
            payment.paid_at = timezone.now()
            payment.save()
            _notify_salary_paid(payment)

    return HttpResponse(status=200)


def _notify_salary_paid(payment) -> None:
    """Push in-chat notification and email to driver and client when salary is paid."""
    from .tools import _get_or_create_history

    job = payment.job
    driver = job.driver
    client = job.client
    if not driver:
        return

    driver_msg = (
        f"Salary payment received!\n"
        f"{'─' * 28}\n"
        f"Job #{job.id} — {job.get_employment_type_display()}\n"
        f"Amount:  ₦{payment.amount:,.2f}\n"
        f"From:    {client.get_full_name()}\n"
        f"Date:    {payment.paid_at.strftime('%B %d, %Y %H:%M UTC') if payment.paid_at else 'Just now'}\n\n"
        f"Thank you for your great work!"
    )
    history, session_key = _get_or_create_history(driver)
    history.append_assistant(driver_msg)
    history.save()
    ChatMessage.objects.create(
        user=driver, session_key=session_key,
        role=ChatMessage.Role.ASSISTANT, body=driver_msg,
    )

    if driver.email:
        from django.core.mail import get_connection, send_mail
        import ssl, certifi
        try:
            connection = get_connection(ssl_context=ssl.create_default_context(cafile=certifi.where()))
            send_mail(
                subject=f"Drivas — Salary payment of ₦{payment.amount:,.2f} received",
                message=(
                    f"Hi {driver.first_name or driver.username},\n\n"
                    f"You have received a salary payment on Drivas.\n\n"
                    f"Job #{job.id} — {job.get_employment_type_display()}\n"
                    f"{'─' * 28}\n"
                    f"Amount: ₦{payment.amount:,.2f}\n"
                    f"From:   {client.get_full_name()}\n"
                    f"Date:   {payment.paid_at.strftime('%B %d, %Y') if payment.paid_at else 'Today'}\n\n"
                    f"Log in to your Drivas chat: http://localhost:8000/chat/\n\n"
                    f"— The Drivas Team"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[driver.email],
                fail_silently=True,
                connection=connection,
            )
        except Exception as exc:
            logger.error("Failed to email driver %s salary notification: %s", driver.id, exc)

    # Reveal driver contact details to client now that payment is confirmed
    phone_line = f"\nPhone:   {driver.phone}" if driver.phone else ""
    client_msg = (
        f"Payment confirmed! Here are your driver's contact details:\n"
        f"{'─' * 30}\n"
        f"Driver:  {driver.get_full_name()}{phone_line}\n\n"
        f"Payment receipt:\n"
        f"Amount:  ₦{payment.amount:,.2f}\n"
        f"Job:     #{job.id} — {job.get_employment_type_display()}\n"
        f"Ref:     {payment.reference}\n\n"
        f"Your driver will be in touch shortly. Good luck!"
    )
    client_history, client_sk = _get_or_create_history(client)
    client_history.append_assistant(client_msg)
    client_history.save()
    ChatMessage.objects.create(
        user=client, session_key=client_sk,
        role=ChatMessage.Role.ASSISTANT, body=client_msg,
    )


def download_contract(request, job_id):
    """Serve the mock employment contract PDF for a job engagement."""
    from jobs.models import JobEngagement
    from .contract import generate_contract_pdf

    job = get_object_or_404(JobEngagement, pk=job_id)

    user = request.user
    if not user.is_authenticated:
        return redirect(f"/accounts/login/?next=/chat/contract/{job_id}/")
    if user != job.client and user != job.driver and not _is_admin(user):
        return HttpResponse("Forbidden", status=403)

    pdf_bytes = generate_contract_pdf(job)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="drivas_contract_{job_id}.pdf"'
    return response


def upload_license(request):
    """
    GET:  Show the license image upload form.
    POST: Save the uploaded image, auto-verify the driver, send notification.
    """
    user = request.user
    if not user.is_authenticated or getattr(user, "role", "") != "driver":
        return redirect("/accounts/login/?next=/chat/upload-license/")

    from accounts.models import DriverProfile
    from .models import ChatMessage

    try:
        profile = DriverProfile.objects.get(user=user)
    except DriverProfile.DoesNotExist:
        return redirect("/chat/")

    error = None
    success = False

    if request.method == "POST":
        image = request.FILES.get("license_image")
        if not image:
            error = "Please select an image file to upload."
        elif not image.content_type.startswith("image/"):
            error = "Only image files are accepted (JPG, PNG, etc.)."
        else:
            profile.license_image = image
            if not profile.is_verified:
                profile.is_verified = True
                # Notify driver in chat
                session_key = f"user_{user.id}"
                verified_msg = (
                    f"Your driver's license has been verified successfully! ✓\n"
                    f"Your account is now active and you can accept job offers.\n\n"
                    f"Return to the chat to browse available jobs."
                )
                from .models import ConversationHistory
                history = ConversationHistory.objects.filter(phone_number=session_key).first()
                if history:
                    history.append_assistant(verified_msg)
                    history.save()
                ChatMessage.objects.create(
                    user=user,
                    session_key=session_key,
                    role=ChatMessage.Role.ASSISTANT,
                    body=verified_msg,
                )
                # Email driver
                if user.email:
                    from django.core.mail import get_connection, send_mail
                    from django.conf import settings as dj_settings
                    import ssl, certifi
                    try:
                        connection = get_connection(
                            ssl_context=ssl.create_default_context(cafile=certifi.where())
                        )
                        send_mail(
                            subject="Drivas — Your account is verified!",
                            message=(
                                f"Hi {user.first_name or user.username},\n\n"
                                f"Your driver's license image has been received and your Drivas account "
                                f"is now verified. You can log in and start accepting job offers.\n\n"
                                f"Log in here: http://localhost:8000/chat/\n\n"
                                f"— The Drivas Team"
                            ),
                            from_email=dj_settings.DEFAULT_FROM_EMAIL,
                            recipient_list=[user.email],
                            fail_silently=True,
                            connection=connection,
                        )
                    except Exception as exc:
                        logger.error("Failed to send verification email to driver %s: %s", user.id, exc)
            profile.save()
            success = True

    return render(request, "messaging/upload_license.html", {
        "profile": profile,
        "error": error,
        "success": success,
    })


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
