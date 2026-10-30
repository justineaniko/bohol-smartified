import os
import requests

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from db import get_db

bp = Blueprint("inventory", __name__)

CATEGORIES = {"products": "Products", "food": "Food", "clothes": "Clothes", "other": "Other"}
SEASONS = ["all", "summer", "rainy", "cold"]
SORTS = {"name": "Name", "quantity": "Quantity", "expiry": "Expiry date", "newest": "Newest"}
VISIBLE = "(items.owner_id = %s OR items.owner_id IS NULL)"
MAX_SHELVES = 10


def list_items(user_id, category=None, q="", owner="all", location=None, low_only=False, sort="name"):
    where = []
    params = []

    if owner == "mine":
        where.append("items.owner_id = %s")
        params.append(user_id)
    elif owner == "shared":
        where.append("items.owner_id IS NULL")
    else:
        where.append(VISIBLE)
        params.append(user_id)

    if location:
        where.append("location_id = %s")
        params.append(location)
    if category:
        where.append("category = %s")
        params.append(category)
    if q:
        where.append("name LIKE %s")
        params.append(f"%{q}%")
    if low_only:
        where.append("quantity <= threshold")

    order_by = {
        "name": "name",
        "quantity": "quantity",
        "expiry": "expiry_date",
        "newest": "items.created_at DESC"
    }.get(sort, "name")

    sql = (
        "SELECT items.*, users.display_name AS owner_name, (quantity <= threshold) AS is_low "
        "FROM items LEFT JOIN users ON items.owner_id = users.id "
        "WHERE " + " AND ".join(where) +
        " ORDER BY " + order_by
    )

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def get_item(item_id, user_id):
    sql = (
        "SELECT items.*, users.display_name AS owner_name, (quantity <= threshold) AS is_low "
        "FROM items LEFT JOIN users ON items.owner_id = users.id "
        " WHERE items.id = %s AND " + VISIBLE
    )
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (item_id, user_id))
            return cur.fetchone()


def create_item(data, user_id):
    owner_id = user_id if data["private"] else None
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO items (name, brand, pack_size, category, owner_id, quantity, threshold, "
                "location_id, shelf, expiry_date, size, color, season) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (data["name"], data["brand"], data["pack_size"], data["category"], owner_id,
                 data["quantity"], data["threshold"], data["location_id"], data["shelf"],
                 data["expiry_date"], data["size"], data["color"], data["season"]),
            )
            conn.commit()
            return cur.lastrowid


def update_item(item_id, data, user_id):
    owner_id = user_id if data["private"] else None
    sql = (
        "UPDATE items SET name = %s, brand = %s, pack_size = %s, category = %s, owner_id = %s, "
        "quantity = %s, threshold = %s, location_id = %s, shelf = %s, expiry_date = %s, "
        "size = %s, color = %s, season = %s "
        "WHERE id = %s AND " + VISIBLE
    )
    params = (data["name"], data["brand"], data["pack_size"], data["category"], owner_id,
              data["quantity"], data["threshold"], data["location_id"], data["shelf"],
              data["expiry_date"], data["size"], data["color"], data["season"],
              item_id, user_id)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            conn.commit()


def delete_item(item_id, user_id):
    sql = "DELETE FROM items WHERE id = %s AND " + VISIBLE
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (item_id, user_id))
            conn.commit()


def change_quantity(item_id, user_id, delta):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE items SET quantity = GREATEST(quantity + %s, 0) "
                "WHERE id = %s AND " + VISIBLE,
                (delta, item_id, user_id)
            )
            conn.commit()

    item = get_item(item_id, user_id)
    check_low_stock(item)
    return item


def check_low_stock(item):
    if item is None:
        return

    is_low = item["quantity"] <= item["threshold"]

    if is_low and not item["low_stock_alert_sent"]:
        send_discord_alert(f"HELLO! {item['name']} is running low ({item['quantity']} left)")
        set_alert_flag(item["id"], True)

    elif not is_low and item["low_stock_alert_sent"]:
        set_alert_flag(item["id"], False)

def set_alert_flag(item_id, value):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE items SET low_stock_alert_sent = %s WHERE id = %s",
                (value, item_id),
            )
            conn.commit()


def send_discord_alert(message):
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
       return

    try:
        requests.post(url, json = {"content": message}, timeout = 5)
    except requests.RequestException:
        pass


def list_locations():
    """Return every location as a dict (id, slug, name, shelf_count), sorted by name."""

    sql = (
        "SELECT id, slug, name, shelf_count "
        "FROM locations "
        "ORDER BY name"
    )
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()

def get_location(slug):
    """Return one location dict by its slug, or None if there isn't one."""
    if slug:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, slug, name, shelf_count FROM locations WHERE slug = %s",
                    (slug,),
                )

                return cur.fetchone()
    else:
        return None

def create_location(slug, name, shelf_count):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO locations (slug, name, shelf_count) "
                "VALUES (%s, %s, %s)",
                (slug, name, shelf_count)
            )
            conn.commit()
            return cur.lastrowid

def _ordinal(n):
    """1 -> '1st', 2 -> '2nd', 3 -> '3rd', 11 -> '11th'."""
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def _locations_by_id():
    """All locations keyed by id, loaded once per request."""
    if "locations_by_id" not in g:
        g.locations_by_id = {loc["id"]: loc for loc in (list_locations() or [])}
    return g.locations_by_id


def _location_label(item):
    """'Dining room fridge · 2nd shelf' for an item, or '' if it has no location."""
    loc = _locations_by_id().get(item.get("location_id"))
    if not loc:
        return ""
    if item.get("shelf"):
        return f"{loc['name']} · {_ordinal(item['shelf'])} shelf"
    return loc["name"]


@bp.app_context_processor
def _inject_location_helpers():
    """Templates (cards, item page) use these to show where an item is kept."""
    return {"location_label": _location_label, "ordinal": _ordinal}


def _slugify(name):
    """'Pink Room Fridge!' -> 'pink-room-fridge'."""
    slug = "".join(c if c.isalnum() else "-" for c in name.lower())
    slug = "-".join(part for part in slug.split("-") if part)
    return slug[:50] or "location"


def _read_item_form():
    """Validate the add/edit form. Returns (data, error)."""
    f = request.form
    data = {
        "name": f.get("name", "").strip()[:100],
        "brand": f.get("brand", "").strip()[:60] or None,
        "pack_size": f.get("pack_size", "").strip()[:30] or None,
        "category": f.get("category", ""),
        "quantity": f.get("quantity", type=int),
        "threshold": f.get("threshold", type=int),
        "location_id": f.get("location_id", type=int),
        "shelf": f.get("shelf", type=int),
        "expiry_date": f.get("expiry_date") or None,
        "size": f.get("size", "").strip()[:20] or None,
        "color": f.get("color", "").strip()[:30] or None,
        "season": f.get("season") if f.get("season") in SEASONS else None,
        "private": f.get("private") == "on",
    }

    loc = _locations_by_id().get(data["location_id"])
    if loc is None:
        data["location_id"] = None
        data["shelf"] = None
    elif not loc["shelf_count"] or data["shelf"] is None or not 1 <= data["shelf"] <= loc["shelf_count"]:
        data["shelf"] = None

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
        data["pack_size"] = None
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


def _back_url(item_id):
    """Where to go after a +/- tap: the list, a location page, or the item page."""
    back = request.form.get("back")
    if back == "list":
        return url_for("inventory.dashboard")
    if back == "location":
        loc = get_location(request.form.get("slug", ""))
        if loc:
            return url_for("inventory.location_page", slug=loc["slug"])
    return url_for("inventory.item_page", item_id=item_id)


def _form_context():
    """Everything item_form.html needs besides the item itself."""
    return {"categories": CATEGORIES, "seasons": SEASONS,
            "locations": list_locations() or [], "max_shelves": MAX_SHELVES}


@bp.route("/")
def dashboard():
    filters = _filters_from_args()
    items = list_items(g.user["id"], **filters)
    return render_template("dashboard.html", items=items, filters=filters,
                           categories=CATEGORIES, sorts=SORTS)


@bp.route("/item/<int:item_id>")
def item_page(item_id):
    item = get_item(item_id, g.user["id"])
    if item is None:
        abort(404)
    location = _locations_by_id().get(item.get("location_id"))
    return render_template("item.html", item=item, location=location, categories=CATEGORIES)


@bp.route("/item/<int:item_id>/use", methods=["POST"])
def use_item(item_id):
    amount = max(request.form.get("amount", 1, type=int) or 1, 1)
    change_quantity(item_id, g.user["id"], -amount)
    return redirect(_back_url(item_id))


@bp.route("/item/<int:item_id>/restock", methods=["POST"])
def restock_item(item_id):
    amount = max(request.form.get("amount", 1, type=int) or 1, 1)
    change_quantity(item_id, g.user["id"], amount)
    return redirect(_back_url(item_id))


@bp.route("/add", methods=["GET", "POST"])
def add_item():
    data = {"category": request.args.get("category", "products"), "quantity": 1, "threshold": 0,
            "location_id": request.args.get("location_id", type=int),
            "shelf": request.args.get("shelf", type=int)}
    if request.method == "POST":
        data, error = _read_item_form()
        if error is None:
            new_id = create_item(data, g.user["id"])
            flash(f"Added {data['name']}.", "success")
            loc = _locations_by_id().get(data["location_id"])
            if loc:
                return redirect(url_for("inventory.location_page", slug=loc["slug"]))
            if new_id:
                return redirect(url_for("inventory.item_page", item_id=new_id))
            return redirect(url_for("inventory.dashboard"))
        flash(error, "error")
    return render_template("item_form.html", item=data, mode="add", **_form_context())


@bp.route("/item/<int:item_id>/edit", methods=["GET", "POST"])
def edit_item(item_id):
    item = get_item(item_id, g.user["id"])
    if item is None:
        abort(404)
    if request.method == "POST":
        data, error = _read_item_form()
        if error is None:
            update_item(item["id"], data, g.user["id"])
            flash("Saved.", "success")
            return redirect(url_for("inventory.item_page", item_id=item_id))
        flash(error, "error")
        item = {**item, **data}
    else:
        item = {**item, "private": item["owner_id"] is not None}
    return render_template("item_form.html", item=item, mode="edit", **_form_context())


@bp.route("/item/<int:item_id>/delete", methods=["POST"])
def remove_item(item_id):
    item = get_item(item_id, g.user["id"])
    if item is None:
        abort(404)
    delete_item(item["id"], g.user["id"])
    flash(f"Deleted {item['name']}.", "success")
    loc = _locations_by_id().get(item.get("location_id"))
    if loc:
        return redirect(url_for("inventory.location_page", slug=loc["slug"]))
    return redirect(url_for("inventory.dashboard"))


@bp.route("/locations", methods=["GET", "POST"])
def locations():
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:60]
        shelf_count = request.form.get("shelf_count", type=int)
        if shelf_count is not None and not 1 <= shelf_count <= MAX_SHELVES:
            shelf_count = None
        if not name:
            flash("Give the location a name.", "error")
        else:
            base = _slugify(name)
            slug, n = base, 2
            while get_location(slug):
                slug, n = f"{base}-{n}", n + 1
            create_location(slug, name, shelf_count)
            flash(f"Added {name}.", "success")
            return redirect(url_for("inventory.locations"))
    return render_template("locations.html", locations=list_locations() or [],
                           max_shelves=MAX_SHELVES)


@bp.route("/location/<slug>")
def location_page(slug):
    loc = get_location(slug)
    if loc is None:
        abort(404)
    items = list_items(g.user["id"], location=loc["id"]) or []

    groups = []
    if loc["shelf_count"]:
        for n in range(1, loc["shelf_count"] + 1):
            on_shelf = [i for i in items if i.get("shelf") == n]
            groups.append((n, on_shelf))
        loose = [i for i in items if not i.get("shelf") or i["shelf"] > loc["shelf_count"]]
        if loose:
            groups.append((None, loose))
    else:
        groups.append((None, items))

    return render_template("location.html", location=loc, items=items, groups=groups,
                           categories=CATEGORIES)
