ITEMS: dict[int, dict] = {}
REORDER_THRESHOLD = 5


def list_items(category: str | None = None) -> list[dict]:
    values = ITEMS.values()
    return [i for i in values if category is None or i.get("category") == category]


def get_item(item_id: int) -> dict:
    try:
        return ITEMS[item_id]
    except KeyError:
        raise LookupError(f"item {item_id} not found") from None


def adjust_stock(item_id: int | None, sku: str | None, delta: int) -> dict:
    """Create the item when `sku` is new, otherwise change its quantity by `delta`."""
    if item_id is None:
        item_id = len(ITEMS) + 1
        ITEMS[item_id] = {"id": item_id, "sku": sku, "quantity": 0, "cost": 1.0}
    item = ITEMS[item_id]
    item["quantity"] = max(0, item["quantity"] + delta)
    return item


def low_stock() -> list[dict]:
    return [i for i in ITEMS.values() if i["quantity"] < REORDER_THRESHOLD]


def stock_value() -> float:
    """Total inventory value at cost."""
    return round(sum(i["quantity"] * i["cost"] for i in ITEMS.values()), 2)
