import hashlib
import hmac
import os

import httpx

PAYMENT_API = "https://payments.example.com/v1"
PAYMENT_KEY = os.environ.get("PAYMENT_KEY", "")


def _sign_payload(body: bytes) -> str:
    return hmac.new(PAYMENT_KEY.encode(), body, hashlib.sha256).hexdigest()


def charge_card(order_id: int, amount_cents: int, card_token: str) -> dict:
    """Charge a customer's credit card through the payment provider."""
    body = f"{order_id}:{amount_cents}:{card_token}".encode()
    resp = httpx.post(
        f"{PAYMENT_API}/charges",
        content=body,
        headers={"X-Signature": _sign_payload(body)},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def refund_payment(charge_id: str, amount_cents: int | None = None) -> dict:
    """Refund a previous charge, fully or partially."""
    resp = httpx.post(
        f"{PAYMENT_API}/refunds",
        json={"charge": charge_id, "amount": amount_cents},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()
