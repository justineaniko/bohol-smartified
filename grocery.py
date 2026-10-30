from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from db import get_db

bp = Blueprint("grocery", __name__, url_prefix="/grocery")

ENTRY_SELECT = (
    "SELECT g.id, g.name AS name, g.item_id, g.auto_added, "
    "i.quantity, i.restock_to, i.brand, i.pack_size "
    "FROM grocery_entries g LEFT JOIN items i ON g.item_id = i.id "
)


def list_entries(where, params):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(ENTRY_SELECT + "WHERE " + where + " ORDER BY g.name", params)
            return cur.fetchall()


@bp.route("/")
def index():
    shared_list = list_entries("g.owner_id IS NULL", ())
    my_list = list_entries("g.owner_id = %s", (g.user["id"],))
    return render_template("grocery.html", shared_list=shared_list, my_list=my_list)


@bp.route("/add", methods=["POST"])
def add():
    return redirect(url_for("grocery.index"))


@bp.route("/<int:id>/bought", methods=["POST"])
def bought(id):
    return redirect(url_for("grocery.index"))


@bp.route("/<int:id>/delete", methods=["POST"])
def remove(id):
    return redirect(url_for("grocery.index"))