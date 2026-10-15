from flask import Blueprint, jsonify, request

from app.security import admin_required, login_required
from app.services.pricing import apply_markup
from app.services.stock import adjust_stock, get_item, list_items

items_bp = Blueprint("items", __name__, url_prefix="/items")


@items_bp.route("", methods=["GET"])
def list_all():
    """Public catalogue listing, optionally filtered by category."""
    return jsonify(list_items(request.args.get("category")))


@items_bp.route("/<int:item_id>", methods=["GET"])
def detail(item_id: int):
    item = get_item(item_id)
    return jsonify({**item, "price": apply_markup(item["cost"])})


@items_bp.route("", methods=["POST"])
@login_required
def create():
    body = request.get_json()
    return jsonify(adjust_stock(None, body["sku"], body.get("quantity", 0))), 201


@items_bp.route("/<int:item_id>/stock", methods=["PATCH"])
@login_required
def restock(item_id: int):
    delta = request.get_json()["delta"]
    return jsonify(adjust_stock(item_id, None, delta))


@items_bp.route("/<int:item_id>", methods=["DELETE"])
@admin_required
def remove(item_id: int):
    return jsonify(removed=item_id)
