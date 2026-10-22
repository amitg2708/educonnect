"""
External Messaging Provider Integration for EduConnect.
Supports Email, SMS, and WhatsApp dispatch with delivery status tracking.

Enforces strict compliance with the core architectural principle:
'Do not claim that email, SMS or WhatsApp messages were delivered unless the real provider confirms delivery.'
"""

import uuid
from typing import Any, Dict, Optional
from django.utils import timezone
from apps.notifications.models import (
    DeliveryChannel,
    DeliveryStatus,
    MessageDeliveryRecord,
)


class BaseMessagingProvider:
    """
    Abstract interface for external communications gateways (Email, SMS, WhatsApp).
    """

    provider_name = "base"

    def dispatch(
        self,
        recipient_address: str,
        subject: str,
        body: str,
        channel: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Dispatches message to the external gateway.
        Returns a dictionary:
        {
            "success": bool,
            "provider_message_id": str,
            "confirmed_delivered": bool,  # True ONLY if provider confirms real-time delivery
            "raw_response": str,
            "error_message": str,
        }
        """
        raise NotImplementedError("Subclasses must implement dispatch()")


class MockQueuedMessagingProvider(BaseMessagingProvider):
    """
    Simulates standard carrier gateways (e.g., SMTP or SMS Aggregators) that accept
    a message into their transmission queue without providing immediate delivery confirmation.
    Status remains 'SENT' (never 'DELIVERED') until a delivery webhook/receipt confirms it.
    """

    provider_name = "mock_queued_gateway"

    def dispatch(
        self,
        recipient_address: str,
        subject: str,
        body: str,
        channel: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        msg_id = f"GW-{uuid.uuid4().hex[:10].upper()}"
        return {
            "success": True,
            "provider_message_id": msg_id,
            "confirmed_delivered": False,  # Only queued/transmitted, NOT yet confirmed delivered
            "raw_response": f"Message queued with transmission ID {msg_id}",
            "error_message": "",
        }


class MockConfirmedMessagingProvider(BaseMessagingProvider):
    """
    Simulates high-touch real-time carriers (e.g., verified WhatsApp Business API or webhook-verified SMS)
    where delivery to the end-user device has been explicitly acknowledged and confirmed.
    """

    provider_name = "mock_confirmed_carrier"

    def dispatch(
        self,
        recipient_address: str,
        subject: str,
        body: str,
        channel: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        msg_id = f"DELIV-{uuid.uuid4().hex[:10].upper()}"
        return {
            "success": True,
            "provider_message_id": msg_id,
            "confirmed_delivered": True,  # Explicitly confirmed delivery by carrier
            "raw_response": f"Delivered to handset at {timezone.now().isoformat()} with ID {msg_id}",
            "error_message": "",
        }


class MockFailingMessagingProvider(BaseMessagingProvider):
    """
    Simulates network failures or invalid recipient address errors from provider.
    """

    provider_name = "mock_failing_carrier"

    def dispatch(
        self,
        recipient_address: str,
        subject: str,
        body: str,
        channel: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "success": False,
            "provider_message_id": "",
            "confirmed_delivered": False,
            "raw_response": "",
            "error_message": "Provider rejected message: 550 Invalid recipient or carrier unreachable.",
        }


# Default provider instance
DEFAULT_PROVIDER = MockQueuedMessagingProvider()


def send_external_message(
    recipient,
    channel: str,
    subject: str,
    message_body: str,
    recipient_address: Optional[str] = None,
    provider: Optional[BaseMessagingProvider] = None,
    institution=None,
) -> MessageDeliveryRecord:
    """
    Dispatches an external notification via Email, SMS, or WhatsApp.
    Ensures message delivery status accurately reflects provider confirmation.
    """
    if not recipient_address:
        if channel == DeliveryChannel.EMAIL:
            recipient_address = getattr(recipient, "email", "")
        else:
            recipient_address = getattr(recipient, "phone_number", "") or getattr(recipient, "phone", "")

    if not recipient_address:
        recipient_address = f"user-{recipient.id}@destination.local"

    if provider is None:
        provider = DEFAULT_PROVIDER

    record = MessageDeliveryRecord.objects.create(
        institution=institution or getattr(recipient, "institution", None),
        recipient=recipient,
        channel=channel,
        recipient_address=recipient_address,
        subject=subject.strip(),
        body=message_body.strip(),
        status=DeliveryStatus.PENDING,
        provider_name=provider.provider_name,
    )

    try:
        result = provider.dispatch(
            recipient_address=recipient_address,
            subject=subject,
            body=message_body,
            channel=channel,
        )

        if result.get("success"):
            provider_id = result.get("provider_message_id", "")
            raw_resp = result.get("raw_response", "")

            # Strict delivery rule: Only set to DELIVERED if confirmed by provider!
            if result.get("confirmed_delivered"):
                record.confirm_delivery(
                    provider_message_id=provider_id,
                    provider_response=raw_resp,
                )
            else:
                record.status = DeliveryStatus.SENT
                record.provider_message_id = provider_id
                record.provider_response = raw_resp
                record.save(update_fields=["status", "provider_message_id", "provider_response"])
        else:
            record.status = DeliveryStatus.FAILED
            record.error_message = result.get("error_message", "Unknown provider dispatch error.")
            record.save(update_fields=["status", "error_message"])

    except Exception as exc:
        record.status = DeliveryStatus.FAILED
        record.error_message = str(exc)
        record.save(update_fields=["status", "error_message"])

    return record


def handle_provider_delivery_receipt(provider_message_id: str, confirmation_payload: str = "") -> Optional[MessageDeliveryRecord]:
    """
    Webhook callback handler to record delivery confirmation from provider receipts.
    Transitions status from SENT to DELIVERED when real carrier reports delivery.
    """
    try:
        record = MessageDeliveryRecord.objects.get(provider_message_id=provider_message_id)
        record.confirm_delivery(
            provider_message_id=provider_message_id,
            provider_response=confirmation_payload or f"Delivery receipt confirmed at {timezone.now().isoformat()}",
        )
        return record
    except MessageDeliveryRecord.DoesNotExist:
        return None
