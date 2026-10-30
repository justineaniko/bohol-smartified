"""Browse: one page with tabs (All, Products, Food, Clothes, Books, Recipes) and filters.

No new SQL here: it reuses the data-layer functions from inventory.py,
books.py and recipes.py. Once those work, this page works.
"""
from flask import Blueprint, g, render_template, request

import books
import inventory
import recipes
from auth import has_feature

bp = Blueprint("browse", __name__)


def _tabs():
    tabs = {"all": "All", **inventory.CATEGORIES}
    if has_feature("books"):
        tabs["books"] = "My books"
    tabs["recipes"] = "Recipes"
    return tabs


@bp.route("/browse")
def index():
    tabs = _tabs()
    tab = request.args.get("tab", "all")
    if tab not in tabs:
        tab = "all"
    user_id = g.user["id"]
    q = request.args.get("q", "").strip()[:100]
    ctx = {"tab": tab, "tabs": tabs, "q": q}

    if tab in inventory.CATEGORIES:
        filters = inventory._filters_from_args()
        filters["category"] = tab
        ctx.update(items=inventory.list_items(user_id, **filters), filters=filters,
                   sorts=inventory.SORTS)

    elif tab == "books":
        status = request.args.get("status")
        status = status if status in books.STATUSES else None
        ctx.update(books=books.list_books(user_id, status=status, q=q), status=status,
                   statuses=books.STATUSES)

    elif tab == "recipes":
        filters = recipes.filters_from_args()
        ctx.update(recipes=recipes.list_recipes(**filters), filters=filters,
                   meal_types=recipes.MEAL_TYPES, time_limits=recipes.TIME_LIMITS,
                   tags=recipes.all_tags())

    else:
        ctx["sections"] = []
        for key in inventory.CATEGORIES:
            found = inventory.list_items(user_id, category=key, q=q)
            ctx["sections"].append((key, tabs[key], "items", found))
        if has_feature("books"):
            ctx["sections"].append(("books", tabs["books"], "books", books.list_books(user_id, q=q)))
        ctx["sections"].append(("recipes", "Recipes", "recipes", recipes.list_recipes(q=q)))

    return render_template("browse.html", **ctx)
