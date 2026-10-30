from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from db import get_db
import inventory

bp = Blueprint("medicine", __name__, url_prefix="/medicine")

SORTS = {"name": "Name", "expiry": "Expiry date", "quantity": "Quantity", "newest": "Newest"}
VISIBLE = "(medicine.owner_id = %s OR medicine.owner_id IS NULL)"
EXPIRING_DAYS = 30
COLUMNS = ("name", "generic_name", "strength", "quantity", "threshold",
           "location_id", "shelf", "expiry_date", "opened_on")


def list_medicines(user_id, q="", owner="all", low_only=False, expiring=False, sort="name"):
    where = []
    params = []

    if owner == "mine":
        where.append("medicine.owner_id = %s")
        params.append(user_id)
    elif owner == "shared":
        where.append("medicine.owner_id IS NULL")
    else:
        where.append(VISIBLE)
        params.append(user_id)

    if q:
        where.append("(medicine.name LIKE %s OR medicine.generic_name LIKE %s)")
        params.extend([f"%{q}%", f"%{q}%"])
    if low_only:
        where.append("quantity <= threshold")
    if expiring:
        where.append("expiry_date <= CURDATE() + INTERVAL %s DAY")
        params.append(EXPIRING_DAYS)

    order_by = {
        "name": "medicine.name",
        "expiry": "medicine.expiry_date IS NULL, medicine.expiry_date",
        "quantity": "quantity",
        "newest": "medicine.created_at DESC",
    }.get(sort, "medicine.name")

    sql = (
        "SELECT medicine.*, users.display_name AS owner_name "
        "FROM medicine LEFT JOIN users ON medicine.owner_id = users.id "
        "WHERE " + " AND ".join(where) +
        " ORDER BY " + order_by
    )
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

def get_medicine(med_id, user_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM medicine WHERE id = %s AND " + VISIBLE, (med_id, user_id))
            return cur.fetchone()
        
def create_medicine(data, user_id):
    owner_id = user_id if data["private"] else None
    cols = ", ".join(COLUMNS) + ", owner_id"
    marks = ", ".join(["%s"] * (len(COLUMNS) + 1))
    values = [data[c] for c in COLUMNS] + [owner_id]
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"INSERT INTO medicine ({cols}) VALUES ({marks})", values)
            conn.commit()

def update_medicine(med_id, data, user_id):
    owner_id = user_id if data["private"] else None
    sets = ", ".join(f"{c} = %s" for c in COLUMNS) + ", owner_id = %s"
    values = [data[c] for c in COLUMNS] + [owner_id, med_id, user_id]
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE medicine SET {sets} WHERE id = %s AND " + VISIBLE, values)
            conn.commit()


def delete_medicine(med_id, user_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM medicine WHERE id = %s AND " + VISIBLE, (med_id, user_id))
            conn.commit()


def change_quantity(med_id, user_id, delta):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE medicine SET quantity = GREATEST(quantity + %s, med_id) WHERE id = %s AND " + VISIBLE,
                (delta, med_id, user_id),
            )
            conn.commit()
    med = get_medicine(med_id, user_id)
    check_low_stock(med)


def check_low_stock(med):
    if med is None:
        return
    is_low = med["quantity"] <= med["threshold"]
    if is_low and not med["low_stock_alert_sent"]:
        inventory.send_discord_alert(f"💊 {med['name']} is running low ({med['quantity']} left)")
        set_alert_flag(med["id"], True)
    elif not is_low and med["low_stock_alert_sent"]:
        set_alert_flag(med["id"], False)


def set_alert_flag(med_id, value):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE medicine SET low_stock_alert_sent = %s WHERE id = %s", (value, med_id))
            conn.commit()

def read_form():
    f = request.form
    data = {
        "name": f.get("name", "").strip()[:100],
        "generic_name": f.get("generic_name", "").strip()[:100],
        "strength": f.get("strength", "").strip()[:30] or None,
        "quantity": f.get("quantity", type=int),
        "threshold": f.get("threshold", type=int),
        "location_id": f.get("location_id", type=int),
        "shelf": f.get("shelf", type=int),
        "expiry_date": f.get("expiry_date") or None,
        "opened_on": f.get("opened_on") or None,
        "private": f.get("private") == "on",
    }

    loc = inventory._locations_by_id().get(data["location_id"])
    if loc is None:
        data["location_id"] = None
        data["shelf"] = None
    elif not loc["shelf_count"] or data["shelf"] is None or not 1 <= data["shelf"] <= loc["shelf_count"]:
        data["shelf"] = None

    if not data["name"]:
        return data, "Give the medicine a name."
    if not data["generic_name"]:
        return data, "Add the generic name, e.g. Paracetamol."
    if data["quantity"] is None or data["quantity"] < 0:
        return data, "Quantity must be 0 or more."
    if data["threshold"] is None or data["threshold"] < 0:
        return data, "Alert level must be 0 or more."
    return data, None

def _form_context():
    return {"locations": inventory.list_locations() or [], "max_shelves": inventory.MAX_SHELVES}

def _filters_from_args():
    return {
        "q": request.args.get("q", "").strip()[:100],
        "owner": request.args.get("owner") if request.args.get("owner") in ("all", "mine", "shared") else "all",
        "low_only": request.args.get("low") == "1",
        "expiring": request.args.get("expiring") == "1",
        "sort": request.args.get("sort") if request.args.get("sort") in SORTS else "name",
    }



@bp.route("/")
def index():
    filters = _filters_from_args()
    medicines = list_medicines(g.user["id"], **filters)
    return render_template("medicine.html", medicines=medicines, filters=filters, sorts=SORTS)

@bp.route("/add", methods=["GET", "POST"])
def add():
    med = {"quantity": 1, "threshold": 0}
    if request.method == "POST":
        med, error = read_form()
        if error is None:
            create_medicine(med, g.user["id"])
            flash(f"Added {med['name']}.", "success")
            return redirect(url_for("medicine.index"))
        flash(error, "error")
    return render_template("medicine_form.html", med=med, mode="add", **_form_context())


@bp.route("/<int:med_id>/edit", methods=["GET", "POST"])
def edit(med_id):
    med = get_medicine(med_id, g.user["id"])
    if med is None:
        abort(404)
    if request.method == "POST":
        data, error = read_form()
        if error is None:
            update_medicine(med_id, data, g.user["id"])
            flash(f"Saved {data['name']}.", "success")
            return redirect(url_for("medicine.index"))
        flash(error, "error")
        med = {**med, **data}
    return render_template("medicine_form.html", med=med, mode="edit", **_form_context())


@bp.route("/<int:med_id>/use", methods=["POST"])
def use(med_id):
    change_quantity(med_id, g.user["id"], -1)
    return redirect(url_for("medicine.index"))


@bp.route("/<int:med_id>/restock", methods=["POST"])
def restock(med_id):
    change_quantity(med_id, g.user["id"], 1)
    return redirect(url_for("medicine.index"))


@bp.route("/<int:med_id>/delete", methods=["POST"])
def remove(med_id):
    delete_medicine(med_id, g.user["id"])
    flash("Deleted.", "success")
    return redirect(url_for("medicine.index"))