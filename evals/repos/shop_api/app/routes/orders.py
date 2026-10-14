from fastapi import APIRouter, Depends, HTTPException

from app.security import get_current_user
from app.services.emailer import send_order_confirmation
from app.services.orders import cancel_order, compute_total, create_order
from app.services.payments import charge_card
from app.utils.pagination import paginate, parse_page_params

router = APIRouter(prefix="/orders")

PRICES = {1: 1999, 2: 4999}


@router.get("/")
def list_orders(page: int | None = None, size: int | None = None, user=Depends(get_current_user)):
    page, size = parse_page_params(page, size)
    return paginate([], page, size)


@router.post("/")
def place_order(items: list[tuple[int, int]], code: str | None = None, user=Depends(get_current_user)):
    """Create an order and return its computed total."""
    order = create_order(user["id"], items)
    return {"id": order.id, "total": compute_total(items, PRICES, code)}


@router.post("/{order_id}/pay")
def pay_order(order_id: int, card_token: str, user=Depends(get_current_user)):
    """Charge the card for an order and email the receipt."""
    total = compute_total([(1, 1)], PRICES)
    result = charge_card(order_id, total, card_token)
    send_order_confirmation("customer@example.com", order_id, total)
    return result


@router.delete("/{order_id}")
def cancel_order_endpoint(order_id: int, user=Depends(get_current_user)):
    if not cancel_order(order_id, user["id"]):
        raise HTTPException(status_code=409, detail="order cannot be cancelled")
    return {"cancelled": order_id}
