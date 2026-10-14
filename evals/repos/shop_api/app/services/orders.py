from app.db import run_query
from app.models import Order

DISCOUNT_CODES = {"WELCOME10": 10, "VIP25": 25}


def apply_discount(subtotal_cents: int, code: str | None) -> int:
    """Return the subtotal after applying a percentage discount code."""
    percent = DISCOUNT_CODES.get(code or "", 0)
    return subtotal_cents - subtotal_cents * percent // 100


def compute_total(items: list[tuple[int, int]], prices: dict[int, int], code: str | None = None) -> int:
    """Sum price * quantity for each line item, then apply any discount code."""
    subtotal = sum(prices[product_id] * qty for product_id, qty in items)
    return apply_discount(subtotal, code)


def create_order(user_id: int, items: list[tuple[int, int]]) -> Order:
    """Persist a new pending order for the user."""
    rows = run_query(
        "INSERT INTO orders (user_id, total) VALUES (%s, 0) RETURNING id", (user_id,)
    )
    return Order(id=rows[0][0], user_id=user_id, items=items)


def cancel_order(order_id: int, user_id: int) -> bool:
    """Cancel a pending order owned by the user; paid orders cannot be cancelled."""
    rows = run_query(
        "UPDATE orders SET status = 'cancelled' WHERE id = %s AND user_id = %s "
        "AND status = 'pending' RETURNING id",
        (order_id, user_id),
    )
    return bool(rows)
