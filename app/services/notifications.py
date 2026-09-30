# app/services/notifications.py
import africastalking
from app.core.config import settings

# Initialize Africa's Talking SDK
africastalking.initialize(
    username=settings.AFRICASTALKING_USERNAME,
    api_key=settings.AFRICASTALKING_API_KEY
)
sms_service = africastalking.SMS

class NotificationEngine:
    @staticmethod
    def send_sms(to_phone: str, message: str) -> dict:
        """Dispatches transactional SMS to owners or next of kin[cite: 2]."""
        try:
            response = sms_service.send(message, [to_phone])
            return {"status": "sent", "details": response}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @staticmethod
    def send_beneficiary_onboarding_email(email: str, vault_id: str, claim_link: str):
        """Sends branded onboarding and claim execution instructions[cite: 2]."""
        # Email sending logic using SMTP/Sendgrid
        pass