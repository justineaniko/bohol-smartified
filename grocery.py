from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from db import get_db
import inventory
bp = Blueprint("grocery", __name__, url_prefix="/grocery")

ENTRY_SELECT = (
    "SELECT g.id, g.name AS name, g.item_id, g.auto_added, "
    "COALESCE((SELECT SUM(x.quantity) FROM items x WHERE x.link_id = i.link_id), i.quantity) AS quantity, "
    "i.restock_to, i.brand, i.pack_size "
    "FROM grocery_entries g LEFT JOIN items i ON g.item_id = i.id "
)


def list_entries(where, params):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(ENTRY_SELECT + "WHERE " + where + " ORDER BY g.name", params)
            return cur.fetchall()
        
def get_entry(entry_id, user_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM grocery_entries WHERE id = %s AND (owner_id IS NULL OR owner_id = %s)",
                (entry_id, user_id)
            )
            return cur.fetchone()

def create_entry(name, owner_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO grocery_entries (name, owner_id) VALUES (%s, %s)",
                (name, owner_id),
            )
            conn.commit()

def delete_entry(entry_id, user_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM grocery_entries WHERE id = %s AND (owner_id IS NULL OR owner_id = %s)",
                (entry_id, user_id)
            )
        conn.commit()

def add_low_stock_entry(item):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT IGNORE INTO grocery_entries (name, owner_id, item_id, auto_added) "
                "VALUES (%s, %s, %s, %s)",
                (item["name"], item["owner_id"], item["id"], True),
            )
            conn.commit()

@bp.route("/")
def index():
    shared_list = list_entries("g.owner_id IS NULL", ())
    my_list = list_entries("g.owner_id = %s", (g.user["id"],))
    return render_template("grocery.html", shared_list=shared_list, my_list=my_list)


@bp.route("/add", methods=["POST"])
def add():
    name = request.form.get("name", "").strip()[:100]
    if not name:
        flash("Type something to add.", "error")
        return redirect(url_for("grocery.index"))
    owner_id = g.user["id"] if request.form.get("private") == "on" else None
    create_entry(name, owner_id)
    return redirect(url_for("grocery.index"))

@bp.route("/<int:id>/bought", methods=["POST"])
def bought(id):
    user_id = g.user["id"]
    entry = get_entry(id, user_id)
    if entry is None: 
        abort(404)
    
    if entry["item_id"]:
        item = inventory.get_item(entry["item_id"], user_id)
        amount = request.form.get("amount", type=int)
        if item and amount and amount > 0:
            delta = amount
        elif item and item["restock_to"] is not None:
            delta = item["restock_to"] - item["group_total"]
        else:
            delta = 1
        if delta > 0:
            inventory.change_quantity(entry["item_id"], user_id, delta)
    
    delete_entry(id, user_id)
    return redirect(url_for("grocery.index"))


@bp.route("/<int:id>/delete", methods=["POST"])
def remove(id):
    delete_entry(id, g.user["id"])
    return redirect(url_for("grocery.index"))