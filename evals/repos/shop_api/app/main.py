from fastapi import FastAPI

from app.db import init_db
from app.routes import admin, auth, orders, products

app = FastAPI(title="Shop API")
app.include_router(auth.router)
app.include_router(orders.router)
app.include_router(products.router)
app.include_router(admin.router)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}
