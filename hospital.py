from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from db import get_db
import inventory

bp = Blueprint("hospital", __name__, url_prefix="/hospital")

KINDS = {
    "wound": "Wound care",
    "syringes": "Syringes & needles",
    "iv": "IV & tubing",
    "ppe": "Gloves & PPE",
    "equipment": "Equipment",
    "other": "Other",
}
CONDITIONS = {"sealed": "Sealed", "opened": "Opened", "used": "Used"}
STATUSES = {"in_stock": "In stock", "donated": "Donated", "sold": "Sold", "disposed": "Disposed"}
UNITS = ["pcs", "boxes", "packs", "rolls", "bottles", "sets"]
SORTS = {"name": "Name", "expiry": "Expiry date", "quantity": "Quantity", "newest": "Newest"}
COLUMNS = ("name", "kind", "quantity", "unit", "size", "item_condition", "status",
           "expiry_date", "location_id", "shelf", "notes")

def list_supplies(status=None, q="", kind=None, condition=None, sort="name"):
    where = ["1 = 1"]
    params = []
    if status:
        where.append("status = %s")
        params.append(status)
    if kind:
        where.append("kind = %s")
        params.append(kind)
    if condition:
        where.append("item_condition = %s")
        params.append(condition)
    if q:
        where.append("(name LIKE %s OR size LIKE %s OR notes LIKE %s)")
        params.extend([f"%{q}%"] * 3)

    order_by = {
        "name": "name",
        "expiry": "expiry_date IS NULL, expiry_date",
        "quantity": "quantity DESC",
        "newest": "created_at DESC",
    }.get(sort, "name")

    sql = "SELECT * FROM hospital_supplies WHERE " + " AND ".join(where) + " ORDER BY " + order_by
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

def count_by_status():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status, COUNT(*) AS n FROM hospital_supplies GROUP BY status")
            return {row["status"]: row["n"] for row in cur.fetchall()}

def get_supply(supply_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM hospital_supplies WHERE id = %s", (supply_id,))
            return cur.fetchone()

def create_supply(data):
    cols = ", ".join(COLUMNS)
    marks = ", ".join(["%s"] * len(COLUMNS))
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"INSERT INTO hospital_supplies ({cols}) VALUES ({marks})",
                        [data[c] for c in COLUMNS])
            conn.commit()

def update_supply(supply_id, data):
    sets = ", ".join(f"{c} = %s" for c in COLUMNS)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE hospital_supplies SET {sets} WHERE id = %s",
                        [data[c] for c in COLUMNS] + [supply_id])
            conn.commit()

def delete_supply(supply_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM hospital_supplies WHERE id = %s", (supply_id,))
            conn.commit()

def change_quantity(supply_id, delta):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE hospital_supplies SET quantity = GREATEST(quantity + %s, 0) WHERE id = %s",
                        (delta, supply_id))
            conn.commit()

def read_form():
    f = request.form
    data = {
        "name": f.get("name", "").strip()[:100],
        "kind": f.get("kind", ""),
        "quantity": f.get("quantity", type=int),
        "unit": f.get("unit") if f.get("unit") in UNITS else None,
        "size": f.get("size", "").strip()[:30] or None,
        "item_condition": f.get("item_condition", ""),
        "status": f.get("status", ""),
        "expiry_date": f.get("expiry_date") or None,
        "location_id": f.get("location_id", type=int),
        "shelf": f.get("shelf", type=int),
        "notes": f.get("notes", "").strip()[:2000] or None,
    }

    loc = inventory._locations_by_id().get(data["location_id"])
    if loc is None:
        data["location_id"] = None
        data["shelf"] = None
    elif not loc["shelf_count"] or data["shelf"] is None or not 1 <= data["shelf"] <= loc["shelf_count"]:
        data["shelf"] = None

    if not data["name"]:
        return data, "Give the supply a name."
    if data["kind"] not in KINDS:
        return data, "Pick a type."
    if data["quantity"] is None or data["quantity"] < 0:
        return data, "Quantity must be 0 or more."
    if data["item_condition"] not in CONDITIONS:
        return data, "Pick a condition."
    if data["status"] not in STATUSES:
        return data, "Pick a status."
    return data, None

def _filters_from_args():
    a = request.args
    return {
        "status": a.get("status") if a.get("status") in STATUSES else None,
        "q": a.get("q", "").strip()[:100],
        "kind": a.get("kind") if a.get("kind") in KINDS else None,
        "condition": a.get("condition") if a.get("condition") in CONDITIONS else None,
        "sort": a.get("sort") if a.get("sort") in SORTS else "name",
    }

def _form_context():
    return {"kinds": KINDS, "conditions": CONDITIONS, "statuses": STATUSES, "units": UNITS,
            "locations": inventory.list_locations() or [], "max_shelves": inventory.MAX_SHELVES}

@bp.route("/")
def index():
    filters = _filters_from_args()
    return render_template("hospital.html", supplies=list_supplies(**filters), filters=filters,
                           counts=count_by_status(), kinds=KINDS, conditions=CONDITIONS,
                           statuses=STATUSES, sorts=SORTS)

@bp.route("/add", methods=["GET", "POST"])
def add():
    supply = {"quantity": 1, "unit": "pcs", "item_condition": "sealed",
              "status": "in_stock"}
    if request.method == "POST":
        supply, error = read_form()
        if error is None:
            create_supply(supply)
            flash(f"Added {supply['name']}.", "success")
            return redirect(url_for("hospital.index"))
        flash(error, "error")
    return render_template("hospital_form.html", supply=supply, mode="add", **_form_context())

@bp.route("/<int:supply_id>/edit", methods=["GET", "POST"])
def edit(supply_id):
    supply = get_supply(supply_id)
    if supply is None:
        abort(404)
    if request.method == "POST":
        data, error = read_form()
        if error is None:
            update_supply(supply_id, data)
            flash(f"Saved {data['name']}.", "success")
            return redirect(url_for("hospital.index"))
        flash(error, "error")
        supply = {**supply, **data}
    return render_template("hospital_form.html", supply=supply, mode="edit", **_form_context())

@bp.route("/<int:supply_id>/use", methods=["POST"])
def use(supply_id):
    change_quantity(supply_id, -1)
    return redirect(url_for("hospital.index", **request.args))

@bp.route("/<int:supply_id>/restock", methods=["POST"])
def restock(supply_id):
    amount = request.form.get("amount", 1, type=int) or 1
    change_quantity(supply_id, min(max(amount, 1), 99999))
    return redirect(url_for("hospital.index", **request.args))

@bp.route("/<int:supply_id>/delete", methods=["POST"])
def remove(supply_id):
    delete_supply(supply_id)
    flash("Deleted.", "success")
    return redirect(url_for("hospital.index"))
