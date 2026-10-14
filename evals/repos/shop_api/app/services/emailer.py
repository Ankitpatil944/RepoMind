import smtplib
from email.message import EmailMessage

SMTP_HOST = "smtp.example.com"


def send_email(to: str, subject: str, body: str) -> None:
    """Low-level SMTP send used by every notification."""
    msg = EmailMessage()
    msg["To"], msg["Subject"] = to, subject
    msg.set_content(body)
    with smtplib.SMTP(SMTP_HOST) as smtp:
        smtp.send_message(msg)


def send_order_confirmation(to: str, order_id: int, total_cents: int) -> None:
    """Email the customer a receipt after a successful payment."""
    send_email(to, f"Order {order_id} confirmed", f"Total charged: {total_cents / 100:.2f}")


def send_password_reset(to: str, reset_token: str) -> None:
    """Email a one-time link for resetting a forgotten password."""
    send_email(to, "Reset your password", f"https://shop.example.com/reset?token={reset_token}")
