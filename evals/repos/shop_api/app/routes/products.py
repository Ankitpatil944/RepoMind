from fastapi import APIRouter, Depends

from app.db import run_query
from app.security import require_admin
from app.utils.pagination import paginate, parse_page_params

router = APIRouter(prefix="/products")


@router.get("/")
def list_products(page: int | None = None, size: int | None = None):
    """Public catalogue listing, paginated."""
    page, size = parse_page_params(page, size)
    rows = run_query("SELECT id, name, price_cents FROM products ORDER BY id")
    return paginate(rows, page, size)


@router.get("/{product_id}")
def get_product(product_id: int):
    rows = run_query("SELECT id, name, price_cents FROM products WHERE id = %s", (product_id,))
    return rows[0] if rows else None


@router.post("/", dependencies=[Depends(require_admin)])
def create_product(name: str, price_cents: int):
    run_query("INSERT INTO products (name, price_cents) VALUES (%s, %s)", (name, price_cents))
    return {"ok": True}
