"""Transactional email over HTTPS, compatible with Render's free service."""

from email.utils import parseaddr

import httpx
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class BrevoEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        count = 0
        with httpx.Client(timeout=15) as client:
            for message in email_messages:
                name, email = parseaddr(message.from_email)
                response = client.post(
                    "https://api.brevo.com/v3/smtp/email",
                    headers={"api-key": settings.BREVO_API_KEY, "accept": "application/json"},
                    json={
                        "sender": {"name": name or "Graider", "email": email},
                        "to": [{"email": address} for address in message.to],
                        "subject": message.subject,
                        "textContent": message.body,
                    },
                )
                response.raise_for_status()
                count += 1
        return count
