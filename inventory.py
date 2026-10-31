import os
import requests

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from db import get_db
import grocery

bp = Blueprint("inventory", __name__)

CATEGORIES = {"food": "Food", "drinks": "Drinks", "leftovers": "Leftovers", "toiletries": "Toiletries",
              "cleaning": "Cleaning", "household": "Household", "other": "Other"}
SORTS = {"name": "Name", "quantity": "Quantity", "expiry": "Expiry date", "newest": "Newest"}
VISIBLE = "(items.owner_id = %s OR items.owner_id IS NULL)"
GROUP_TOTAL = "COALESCE((SELECT SUM(x.quantity) FROM items x WHERE x.link_id = items.link_id), items.quantity)"
ITEM_SELECT = (
    "SELECT items.*, users.display_name AS owner_name, assignee.display_name AS assigned_name, "
    + GROUP_TOTAL + " AS group_total, "
    "(SELECT COUNT(*) FROM items x WHERE x.link_id = items.link_id) AS place_count, "
    "(" + GROUP_TOTAL + " <= items.threshold) AS is_low "
    "FROM items LEFT JOIN users ON items.owner_id = users.id "
    "LEFT JOIN users assignee ON items.assigned_to = assignee.id "
)
SHARED_FIELDS = ("name", "brand", "pack_size", "category", "threshold", "restock_to", "assigned_to")
MAX_SHELVES = 10


def list_items(user_id, category=None, q="", owner="all", location=None, low_only=False, sort="name", room=None):
    where = []
    params = []

    if owner == "mine":
        where.append("items.owner_id = %s")
        params.append(user_id)
    elif owner == "shared":
        where.append("items.owner_id IS NULL")
    elif owner == "assigned":
        where.append(VISIBLE + " AND items.assigned_to = %s")
        params.extend([user_id, user_id])
    else:
        where.append(VISIBLE)
        params.append(user_id)

    if location:
        where.append("location_id = %s")
        params.append(location)
    if room:
        where.append("location_id IN (SELECT id FROM locations WHERE room_id = %s)")
        params.append(room)
    if category:
        where.append("category = %s")
        params.append(category)
    if q:
        where.append("name LIKE %s")
        params.append(f"%{q}%")
    if low_only:
        where.append(GROUP_TOTAL + " <= items.threshold")

    order_by = {
        "name": "name",
        "quantity": "quantity",
        "expiry": "expiry_date",
        "newest": "items.created_at DESC"
    }.get(sort, "name")

    sql = ITEM_SELECT + "WHERE " + " AND ".join(where) + " ORDER BY " + order_by

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def get_item(item_id, user_id):
    sql = ITEM_SELECT + "WHERE items.id = %s AND " + VISIBLE
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
                "restock_to, location_id, shelf, expiry_date, place_min, assigned_to) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (data["name"], data["brand"], data["pack_size"], data["category"], owner_id,
                 data["quantity"], data["threshold"], data["restock_to"], data["location_id"], data["shelf"],
                 data["expiry_date"], data.get("place_min"), data.get("assigned_to")),
            )
            conn.commit()
            return cur.lastrowid


def update_item(item_id, data, user_id, link_id=None):
    owner_id = user_id if data["private"] else None
    sql = (
        "UPDATE items SET name = %s, brand = %s, pack_size = %s, category = %s, owner_id = %s, "
        "quantity = %s, threshold = %s, restock_to = %s, location_id = %s, shelf = %s, "
        "expiry_date = %s, place_min = %s, assigned_to = %s "
        "WHERE id = %s AND " + VISIBLE
    )
    params = (data["name"], data["brand"], data["pack_size"], data["category"], owner_id,
              data["quantity"], data["threshold"], data["restock_to"], data["location_id"], data["shelf"],
              data["expiry_date"], data.get("place_min"), data.get("assigned_to"),
              item_id, user_id)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if link_id:
                sets = ", ".join(f"{c} = %s" for c in SHARED_FIELDS) + ", owner_id = %s"
                cur.execute(
                    f"UPDATE items SET {sets} WHERE link_id = %s AND id <> %s",
                    [data[c] for c in SHARED_FIELDS] + [owner_id, link_id, item_id],
                )
            conn.commit()


def collapse_linked(items):
    items = list(items or [])
    links = sorted({i["link_id"] for i in items if i.get("link_id") and (i.get("place_count") or 0) > 1})
    if not links:
        return items
    marks = ", ".join(["%s"] * len(links))
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT id, link_id, location_id, shelf, quantity FROM items WHERE link_id IN ({marks}) ORDER BY id",
                links,
            )
            rows = cur.fetchall()
    places = {}
    for row in rows:
        places.setdefault(row["link_id"], []).append(row)
    out, seen = [], set()
    for item in items:
        link = item.get("link_id")
        if link in places and len(places[link]) > 1:
            if link in seen:
                continue
            seen.add(link)
            item = {**item, "places": places[link]}
        out.append(item)
    return out


def list_group(link_id, user_id):
    if not link_id:
        return []
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(ITEM_SELECT + "WHERE items.link_id = %s AND " + VISIBLE + " ORDER BY items.id",
                        (link_id, user_id))
            return cur.fetchall()


def add_to_place(item, location_id, shelf, quantity, place_min):
    link_id = item["link_id"] or item["id"]
    with get_db() as conn:
        with conn.cursor() as cur:
            if not item["link_id"]:
                cur.execute("UPDATE items SET link_id = %s WHERE id = %s", (link_id, item["id"]))
            cur.execute(
                "INSERT INTO items (name, brand, pack_size, category, owner_id, quantity, threshold, "
                "restock_to, location_id, shelf, expiry_date, link_id, place_min, low_stock_alert_sent, "
                "assigned_to) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (item["name"], item["brand"], item["pack_size"], item["category"], item["owner_id"],
                 quantity, item["threshold"], item["restock_to"], location_id, shelf,
                 item["expiry_date"], link_id, place_min, item["low_stock_alert_sent"],
                 item.get("assigned_to")),
            )
            conn.commit()
            return cur.lastrowid


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
    if item is None or item["category"] == "leftovers":
        return

    total = item.get("group_total")
    if total is None:
        total = item["quantity"]
    is_low = item["threshold"] is not None and total <= item["threshold"]

    if is_low and not item["low_stock_alert_sent"]:
        send_discord_alert(f"{item['name']} is running low ({total} left)")
        set_alert_flag(item["id"], True, item.get("link_id"))
        grocery.add_low_stock_entry(_group_head(item))

    elif not is_low and item["low_stock_alert_sent"]:
        set_alert_flag(item["id"], False, item.get("link_id"))

    check_move(item)


def _group_head(item):
    if not item.get("link_id"):
        return item
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM items WHERE link_id = %s ORDER BY id LIMIT 1", (item["link_id"],))
            return cur.fetchone() or item


def check_move(item):
    if not item.get("link_id") or item.get("place_min") is None:
        return
    short = item["quantity"] < item["place_min"]
    if short and not item["move_alert_sent"]:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM items WHERE link_id = %s AND id <> %s AND quantity > 0 "
                    "ORDER BY quantity DESC LIMIT 1",
                    (item["link_id"], item["id"]),
                )
                source = cur.fetchone()
        if source:
            here = _location_label(item) or "its usual spot"
            there = _location_label(source) or "the other spot"
            send_discord_alert(
                f"Move some {item['name']} from {there} to {here}: "
                f"only {item['quantity']} left there, {source['quantity']} available."
            )
            set_move_flag(item["id"], True)
    elif not short and item["move_alert_sent"]:
        set_move_flag(item["id"], False)


def set_move_flag(item_id, value):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE items SET move_alert_sent = %s WHERE id = %s", (value, item_id))
            conn.commit()

def set_alert_flag(item_id, value, link_id=None):
    with get_db() as conn:
        with conn.cursor() as cur:
            if link_id:
                cur.execute("UPDATE items SET low_stock_alert_sent = %s WHERE link_id = %s", (value, link_id))
            else:
                cur.execute("UPDATE items SET low_stock_alert_sent = %s WHERE id = %s", (value, item_id))
            conn.commit()


def send_discord_alert(message):
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        print("Discord alert skipped: DISCORD_WEBHOOK_URL is not set")
        return

    try:
        r = requests.post(url, json={"content": message, "allowed_mentions": {"parse": []}}, timeout=5)
        if r.status_code >= 300:
            print(f"Discord alert failed: {r.status_code} {r.text[:200]}")
    except requests.RequestException as e:
        print(f"Discord alert failed: {e}")


LOCATION_SELECT = (
    "SELECT locations.id, locations.slug, locations.name, locations.shelf_count, locations.room_id, "
    "rooms.name AS room_name, rooms.slug AS room_slug "
    "FROM locations LEFT JOIN rooms ON locations.room_id = rooms.id "
)


def list_locations(room_id=None):
    sql = LOCATION_SELECT
    params = []
    if room_id:
        sql += "WHERE locations.room_id = %s "
        params.append(room_id)
    sql += "ORDER BY rooms.name IS NULL, rooms.name, locations.name"
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def list_rooms():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, slug, name FROM rooms ORDER BY name")
            return cur.fetchall()


def get_room(slug):
    if not slug:
        return None
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, slug, name FROM rooms WHERE slug = %s", (slug,))
            return cur.fetchone()


def create_room(slug, name):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO rooms (slug, name) VALUES (%s, %s)", (slug, name))
            conn.commit()
            return cur.lastrowid


def rename_room(room_id, name):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE rooms SET name = %s WHERE id = %s", (name, room_id))
            conn.commit()


def delete_room(room_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE locations SET room_id = NULL WHERE room_id = %s", (room_id,))
            cur.execute("DELETE FROM rooms WHERE id = %s", (room_id,))
            conn.commit()


def update_location(location_id, name, shelf_count, room_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE locations SET name = %s, shelf_count = %s, room_id = %s WHERE id = %s",
                (name, shelf_count, room_id, location_id),
            )
            conn.commit()


def delete_location(location_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE items SET location_id = NULL, shelf = NULL WHERE location_id = %s", (location_id,))
            cur.execute("DELETE FROM locations WHERE id = %s", (location_id,))
            conn.commit()

def get_location(slug):
    """Return one location dict by its slug, or None if there isn't one."""
    if slug:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(LOCATION_SELECT + "WHERE locations.slug = %s", (slug,))

                return cur.fetchone()
    else:
        return None

def create_location(slug, name, shelf_count, room_id=None):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO locations (slug, name, shelf_count, room_id) "
                "VALUES (%s, %s, %s, %s)",
                (slug, name, shelf_count, room_id)
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
    parts = [loc["room_name"], loc["name"]] if loc.get("room_name") else [loc["name"]]
    if item.get("shelf"):
        parts.append(f"{_ordinal(item['shelf'])} shelf")
    return " · ".join(parts)


def _group_by_room(locations):
    groups = []
    for loc in locations or []:
        key = loc.get("room_name")
        if groups and groups[-1][0] == key:
            groups[-1][1].append(loc)
        else:
            groups.append((key, [loc]))
    return groups


@bp.app_context_processor
def _inject_location_helpers():
    """Templates (cards, item page) use these to show where an item is kept."""
    return {"location_label": _location_label, "ordinal": _ordinal, "group_by_room": _group_by_room}


def _slugify(name):
    """'Pink Room Fridge!' -> 'pink-room-fridge'."""
    slug = "".join(c if c.isalnum() else "-" for c in name.lower())
    slug = "-".join(part for part in slug.split("-") if part)
    return slug[:50] or "location"


def _unique_slug(name, exists):
    base = _slugify(name)
    slug, n = base, 2
    while exists(slug):
        slug, n = f"{base}-{n}", n + 1
    return slug


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
        "restock_to": f.get("restock_to", type=int),
        "location_id": f.get("location_id", type=int),
        "shelf": f.get("shelf", type=int),
        "expiry_date": f.get("expiry_date") or None,
        "place_min": f.get("place_min", type=int),
        "assigned_to": f.get("assigned_to", type=int),
        "private": f.get("private") == "on",
    }
    if data["assigned_to"] is not None and not any(u["id"] == data["assigned_to"] for u in list_users()):
        data["assigned_to"] = None
    if data["place_min"] is not None and data["place_min"] < 0:
        data["place_min"] = None

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
    if data["threshold"] is not None and data["threshold"] < 0:
        return data, "Alert level must be 0 or more."
    return data, None


def _filters_from_args():
    category = request.args.get("category")
    return {
        "category": category if category in CATEGORIES else None,
        "q": request.args.get("q", "").strip()[:100],
        "owner": request.args.get("owner") if request.args.get("owner") in ("all", "mine", "shared", "assigned") else "all",
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
    if back == "room":
        room = get_room(request.form.get("slug", ""))
        if room:
            return url_for("inventory.room_page", slug=room["slug"])
    return url_for("inventory.item_page", item_id=item_id)


def _form_context():
    """Everything item_form.html needs besides the item itself."""
    return {"categories": CATEGORIES, "users": list_users(),
            "locations": list_locations() or [], "max_shelves": MAX_SHELVES}


def list_users():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, display_name FROM users ORDER BY display_name")
            return cur.fetchall() or []


@bp.route("/")
def dashboard():
    filters = _filters_from_args()
    items = collapse_linked(list_items(g.user["id"], **filters))
    return render_template("dashboard.html", items=items, filters=filters,
                           categories=CATEGORIES, sorts=SORTS)


@bp.route("/item/<int:item_id>")
def item_page(item_id):
    item = get_item(item_id, g.user["id"])
    if item is None:
        abort(404)
    location = _locations_by_id().get(item.get("location_id"))
    group = list_group(item["link_id"], g.user["id"])
    return render_template("item.html", item=item, location=location, categories=CATEGORIES,
                           group=group, locations=list_locations() or [], max_shelves=MAX_SHELVES)


@bp.route("/item/<int:item_id>/also", methods=["POST"])
def also_keep(item_id):
    item = get_item(item_id, g.user["id"])
    if item is None:
        abort(404)
    location_id = request.form.get("location_id", type=int)
    loc = _locations_by_id().get(location_id)
    if loc is None:
        flash("Pick where else it's kept.", "error")
        return redirect(url_for("inventory.item_page", item_id=item_id))
    shelf = request.form.get("shelf", type=int)
    if not loc["shelf_count"] or shelf is None or not 1 <= shelf <= loc["shelf_count"]:
        shelf = None
    quantity = max(request.form.get("quantity", 0, type=int) or 0, 0)
    place_min = request.form.get("place_min", type=int)
    if place_min is not None and place_min < 0:
        place_min = None
    new_id = add_to_place(item, location_id, shelf, quantity, place_min)
    check_low_stock(get_item(new_id, g.user["id"]))
    flash(f"{item['name']} is now also in {_location_label({'location_id': location_id, 'shelf': shelf})}.", "success")
    return redirect(url_for("inventory.item_page", item_id=item_id))


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
    data = {"category": request.args.get("category", "food"), "quantity": 1, "threshold": None,
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
            update_item(item["id"], data, g.user["id"], item.get("link_id"))
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


def _room_from_form():
    new_name = request.form.get("new_room", "").strip()[:60]
    if new_name:
        room = next((r for r in (list_rooms() or []) if r["name"].lower() == new_name.lower()), None)
        if room:
            return room["id"]
        return create_room(_unique_slug(new_name, get_room), new_name)
    room_id = request.form.get("room_id", type=int)
    return room_id if any(r["id"] == room_id for r in (list_rooms() or [])) else None


@bp.route("/locations", methods=["GET", "POST"])
def locations():
    if request.method == "POST":
        if request.form.get("form") == "room":
            name = request.form.get("name", "").strip()[:60]
            if not name:
                flash("Give the room a name.", "error")
            elif any(r["name"].lower() == name.lower() for r in (list_rooms() or [])):
                flash(f"{name} already exists.", "error")
            else:
                create_room(_unique_slug(name, get_room), name)
                flash(f"Added {name}.", "success")
                return redirect(url_for("inventory.locations"))
        else:
            name = request.form.get("name", "").strip()[:60]
            shelf_count = request.form.get("shelf_count", type=int)
            if shelf_count is not None and not 1 <= shelf_count <= MAX_SHELVES:
                shelf_count = None
            if not name:
                flash("Give the location a name.", "error")
            else:
                room_id = _room_from_form()
                create_location(_unique_slug(name, get_location), name, shelf_count, room_id)
                flash(f"Added {name}.", "success")
                return redirect(url_for("inventory.locations"))
    return render_template("locations.html", locations=list_locations() or [],
                           rooms=list_rooms() or [], max_shelves=MAX_SHELVES)


@bp.route("/room/<slug>")
def room_page(slug):
    room = get_room(slug)
    if room is None:
        abort(404)
    places = list_locations(room["id"]) or []
    items = list_items(g.user["id"], room=room["id"]) or []
    items = sorted(items, key=lambda i: (i.get("shelf") is None, i.get("shelf") or 0))
    groups = [(loc, [i for i in items if i.get("location_id") == loc["id"]]) for loc in places]
    return render_template("room.html", room=room, groups=groups, items=items,
                           categories=CATEGORIES)


@bp.route("/room/<slug>/rename", methods=["POST"])
def rename_room_page(slug):
    room = get_room(slug)
    if room is None:
        abort(404)
    name = request.form.get("name", "").strip()[:60]
    if not name:
        flash("Give the room a name.", "error")
    elif any(r["name"].lower() == name.lower() and r["id"] != room["id"] for r in (list_rooms() or [])):
        flash(f"{name} already exists.", "error")
    else:
        rename_room(room["id"], name)
        flash(f"Renamed to {name}.", "success")
    return redirect(url_for("inventory.room_page", slug=room["slug"]))


@bp.route("/room/<slug>/delete", methods=["POST"])
def delete_room_page(slug):
    room = get_room(slug)
    if room is None:
        abort(404)
    delete_room(room["id"])
    flash(f"Deleted {room['name']}. Its places are now under “No room yet”.", "success")
    return redirect(url_for("inventory.locations"))


@bp.route("/location/<slug>/edit", methods=["POST"])
def edit_location(slug):
    loc = get_location(slug)
    if loc is None:
        abort(404)
    name = request.form.get("name", "").strip()[:60]
    shelf_count = request.form.get("shelf_count", type=int)
    if shelf_count is not None and not 1 <= shelf_count <= MAX_SHELVES:
        shelf_count = None
    if not name:
        flash("Give the place a name.", "error")
    else:
        update_location(loc["id"], name, shelf_count, _room_from_form())
        flash(f"Saved {name}.", "success")
    return redirect(url_for("inventory.location_page", slug=loc["slug"]))


@bp.route("/location/<slug>/delete", methods=["POST"])
def delete_location_page(slug):
    loc = get_location(slug)
    if loc is None:
        abort(404)
    delete_location(loc["id"])
    flash(f"Deleted {loc['name']}. Its items are still in your inventory, just without a place.", "success")
    if loc.get("room_slug"):
        return redirect(url_for("inventory.room_page", slug=loc["room_slug"]))
    return redirect(url_for("inventory.locations"))


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
                           categories=CATEGORIES, rooms=list_rooms() or [], max_shelves=MAX_SHELVES)
