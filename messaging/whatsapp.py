"""
Thin client for the Meta WhatsApp Cloud API.

Handles outbound message sending and inbound webhook signature verification.
No SDK dependency — plain HTTPS calls via `requests`, same as the Paystack integration.
"""
import hashlib
import hmac
import logging

import requests

from django.conf import settings

logger = logging.getLogger(__name__)


def normalize_phone(raw: str) -> str:
    """Meta sends sender numbers as bare digits (e.g. '2348012345678'); store/compare as E.164."""
    digits = "".join(ch for ch in raw if ch.isdigit())
    return f"+{digits}"


def verify_webhook_signature(raw_body: bytes, signature_header: str) -> bool:
    """Validate the X-Hub-Signature-256 header Meta sends with every webhook POST."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        settings.WHATSAPP_APP_SECRET.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    provided = signature_header.split("=", 1)[1]
    return hmac.compare_digest(expected, provided)


def send_whatsapp_message(to: str, text: str) -> bool:
    """
    Send a freeform text message to a WhatsApp user via the Cloud API.
    `to` should be the bare-digit wa_id (no '+'), matching what Meta sends as the sender.
    Returns True on success, False otherwise (never raises — notifications shouldn't break callers).
    """
    if not settings.WHATSAPP_TOKEN or not settings.WHATSAPP_PHONE_NUMBER_ID:
        logger.warning("WhatsApp Cloud API not configured — message to %s not sent", to)
        return False

    to_digits = to.lstrip("+")
    url = (
        f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/"
        f"{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    )
    payload = {
        "messaging_product": "whatsapp",
        "to": to_digits,
        "type": "text",
        "text": {"body": text},
    }
    try:
        resp = requests.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.error("Failed to send WhatsApp message to %s: %s", to_digits, exc)
        return False
