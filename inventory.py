"""Supplies, food and clothes.

Split of work
- ROUTES (bottom half): done. They read forms, validate them and pick templates.
- DATA LAYER (top half): YOUR TODOs. Each function says what it gets and must return.
  Until you write them, pages still load; they just show empty lists.

Visibility rule for every query: a profile sees shared items (owner_id IS NULL)
plus its OWN items. Never someone else's private items.
"""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from db import get_db  # noqa: F401  (you'll use this in the TODOs)

bp = Blueprint("inventory", __name__)

CATEGORIES = {"products": "Products", "food": "Food", "clothes": "Clothes", "other": "Other"}
SEASONS = ["all", "summer", "rainy", "cold"]
SORTS = {"name": "Name", "quantity": "Quantity", "expiry": "Expiry date", "newest": "Newest"}


# =============================================================================
# DATA LAYER: your TODOs
# Every item dict you return needs these keys (None is fine where empty):
#   id, qr_code_id, name, category, owner_id, owner_name, quantity, threshold,
#   location, expiry_date (a date), size, color, season, notes, is_low (bool)
# Tip: owner_name comes from LEFT JOIN users ON users.id = items.owner_id
# Tip: is_low can be computed in SQL:  (quantity <= threshold) AS is_low
# =============================================================================

def list_items(user_id, category=None, q="", owner="all", low_only=False, sort="name"):
    """Return a list of item dicts this user may see.

    category: one of CATEGORIES keys, or None for every category
    q:        text to search in name/notes (LIKE %q%); "" means no search
    owner:    "all" (shared + mine), "mine" (owner_id = user_id), "shared" (owner_id IS NULL)
    low_only: only items where quantity <= threshold
    sort:     one of SORTS keys -> ORDER BY name / quantity / expiry_date / created_at DESC

    Build the WHERE clause from pieces + a params list. Never put values into the
    SQL string with f-strings; pass them as execute(sql, params).
    ORDER BY can't use %s, so map `sort` to a column name from a fixed dict.
    """
    # TODO
    return []


def get_item(qr_code_id, user_id):
    """Return one item dict (same keys as above) or None if missing or not visible to user_id."""
    # TODO
    return None


def create_item(data, user_id):
    """INSERT a new item. `data` is the dict from _read_item_form(). Return the new qr_code_id.

    - qr_code_id: make one from the name, e.g. "Dish Soap" -> "dish-soap";
      if that's taken, add -2, -3... (SELECT to check first)
    - owner_id: user_id if data["private"] else None
    """
    # TODO
    return None


def update_item(item_id, data, user_id):
    """UPDATE an item the user may see. Keep its qr_code_id (printed QRs must keep working)."""
    # TODO
    pass


def delete_item(item_id, user_id):
    """DELETE an item the user may see."""
    # TODO
    pass


def change_quantity(qr_code_id, user_id, delta):
    """Add delta (+1, -1, +5...) to quantity, never below 0. Return the updated item dict.

    Do it in one statement so two phones tapping at once can't clash:
      UPDATE items SET quantity = GREATEST(quantity + %s, 0) WHERE ...
    Then call check_low_stock(item).
    """
    # TODO
    return None


def check_low_stock(item):
    """Alert once when an item becomes low; reset the flag when it's restocked.

    - quantity <= threshold and not low_stock_alert_sent -> send_discord_alert(...), set flag TRUE
    - quantity >  threshold and low_stock_alert_sent     -> set flag FALSE
    """
    # TODO
    pass


def send_discord_alert(message):
    """POST {"content": message} to DISCORD_WEBHOOK_URL (skip if it's empty)."""
    # TODO: import os, requests; requests.post(url, json={...}, timeout=5)
    pass


# =============================================================================
# ROUTES: done
# =============================================================================

def _read_item_form():
    """Validate the add/edit form. Returns (data, error)."""
    f = request.form
    data = {
        "name": f.get("name", "").strip()[:100],
        "category": f.get("category", ""),
        "quantity": f.get("quantity", type=int),
        "threshold": f.get("threshold", type=int),
        "location": f.get("location", "").strip()[:60] or None,
        "expiry_date": f.get("expiry_date") or None,  # "YYYY-MM-DD" string or None
        "size": f.get("size", "").strip()[:20] or None,
        "color": f.get("color", "").strip()[:30] or None,
        "season": f.get("season") if f.get("season") in SEASONS else None,
        "notes": f.get("notes", "").strip()[:2000] or None,
        "private": f.get("private") == "on",
    }
    if not data["name"]:
        return data, "Give the item a name."
    if data["category"] not in CATEGORIES:
        return data, "Pick a category."
    if data["quantity"] is None or data["quantity"] < 0:
        return data, "Quantity must be 0 or more."
    if data["threshold"] is None or data["threshold"] < 0:
        return data, "Alert level must be 0 or more."
    if data["category"] == "clothes":
        data["expiry_date"] = None
    else:
        data.update(size=None, color=None, season=None)
    return data, None


def _filters_from_args():
    category = request.args.get("category")
    return {
        "category": category if category in CATEGORIES else None,
        "q": request.args.get("q", "").strip()[:100],
        "owner": request.args.get("owner") if request.args.get("owner") in ("all", "mine", "shared") else "all",
        "low_only": request.args.get("low") == "1",
        "sort": request.args.get("sort") if request.args.get("sort") in SORTS else "name",
    }


@bp.route("/")
def dashboard():
    filters = _filters_from_args()
    items = list_items(g.user["id"], **filters)
    return render_template("dashboard.html", items=items, filters=filters,
                           categories=CATEGORIES, sorts=SORTS)


@bp.route("/item/<qr_code_id>")
def item_page(qr_code_id):
    # GET only: opening a QR link must never change data
    item = get_item(qr_code_id, g.user["id"])
    if item is None:
        abort(404)
    return render_template("item.html", item=item, categories=CATEGORIES)


@bp.route("/item/<qr_code_id>/use", methods=["POST"])
def use_item(qr_code_id):
    amount = max(request.form.get("amount", 1, type=int), 1)
    change_quantity(qr_code_id, g.user["id"], -amount)
    return redirect(request.form.get("back") == "list" and url_for("inventory.dashboard")
                    or url_for("inventory.item_page", qr_code_id=qr_code_id))


@bp.route("/item/<qr_code_id>/restock", methods=["POST"])
def restock_item(qr_code_id):
    amount = max(request.form.get("amount", 1, type=int), 1)
    change_quantity(qr_code_id, g.user["id"], amount)
    return redirect(request.form.get("back") == "list" and url_for("inventory.dashboard")
                    or url_for("inventory.item_page", qr_code_id=qr_code_id))


@bp.route("/add", methods=["GET", "POST"])
def add_item():
    data = {"category": request.args.get("category", "products"), "quantity": 1, "threshold": 0}
    if request.method == "POST":
        data, error = _read_item_form()
        if error is None:
            qr_code_id = create_item(data, g.user["id"])
            flash(f"Added {data['name']}.", "success")
            if qr_code_id:
                return redirect(url_for("inventory.item_page", qr_code_id=qr_code_id))
            return redirect(url_for("inventory.dashboard"))
        flash(error, "error")
    return render_template("item_form.html", item=data, mode="add",
                           categories=CATEGORIES, seasons=SEASONS)


@bp.route("/item/<qr_code_id>/edit", methods=["GET", "POST"])
def edit_item(qr_code_id):
    item = get_item(qr_code_id, g.user["id"])
    if item is None:
        abort(404)
    if request.method == "POST":
        data, error = _read_item_form()
        if error is None:
            update_item(item["id"], data, g.user["id"])
            flash("Saved.", "success")
            return redirect(url_for("inventory.item_page", qr_code_id=qr_code_id))
        flash(error, "error")
        item = {**item, **data}
    else:
        item = {**item, "private": item["owner_id"] is not None}
    return render_template("item_form.html", item=item, mode="edit",
                           categories=CATEGORIES, seasons=SEASONS)


@bp.route("/item/<qr_code_id>/delete", methods=["POST"])
def remove_item(qr_code_id):
    item = get_item(qr_code_id, g.user["id"])
    if item is None:
        abort(404)
    delete_item(item["id"], g.user["id"])
    flash(f"Deleted {item['name']}.", "success")
    return redirect(url_for("inventory.dashboard"))
