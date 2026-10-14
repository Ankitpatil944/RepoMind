from dataclasses import dataclass, field


@dataclass
class User:
    id: int
    email: str
    password_hash: str
    salt: bytes
    is_active: bool = True


@dataclass
class Product:
    id: int
    name: str
    price_cents: int


@dataclass
class Order:
    id: int
    user_id: int
    items: list[tuple[int, int]] = field(default_factory=list)  # (product_id, qty)
    status: str = "pending"
