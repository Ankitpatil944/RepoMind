from flask import Blueprint, jsonify

from app.security import login_required
from app.services.stock import low_stock, stock_value

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


@reports_bp.route("/low-stock")
@login_required
def low_stock_report():
    """Items below their reorder threshold (staff only)."""
    return jsonify(low_stock())


@reports_bp.route("/valuation")
@login_required
def valuation():
    return jsonify(total=stock_value())


@reports_bp.route("/summary")
def public_summary():
    return jsonify(items=len(low_stock()))
