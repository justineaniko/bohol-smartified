"""Recipes database, shared by the whole house.

ROUTES: done.  DATA LAYER: your TODOs (pages load empty until you write them).
"""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from db import get_db

bp = Blueprint("recipes", __name__, url_prefix="/recipes")

MEAL_TYPES = {"breakfast": "Breakfast", "lunch": "Lunch", "dinner": "Dinner",
              "snack": "Snack", "dessert": "Dessert", "drink": "Drink"}
TIME_LIMITS = {15: "15 min or less", 30: "30 min or less", 60: "1 hour or less"}
SORTS = {"newest": "Newest", "title": "Title", "quickest": "Quickest"}


def list_recipes(q="", meal_type=None, max_minutes=None, tag=None, sort="newest"):
    """Filtered recipes.
    q: search title, ingredients and tags. meal_type: MEAL_TYPES key or None.
    max_minutes: prep_minutes <= this, or None. tag: one tag; match with
    FIND_IN_SET(%s, REPLACE(tags, ', ', ',')) or a LIKE. sort: newest/title/quickest."""
    return []


def all_tags():
    """Every distinct tag, sorted, for the tag chips. Easiest in Python:
    SELECT tags FROM recipes, then split each on ',' and strip() into a set."""
    return []


def get_recipe(recipe_id):
    """One recipe dict or None."""
    return None


def create_recipe(data, user_id):
    """INSERT with created_by = user_id. Return the new id (cur.lastrowid)."""
    return None


def update_recipe(recipe_id, data):
    pass


def delete_recipe(recipe_id):
    pass


def _read_recipe_form():
    f = request.form
    minutes = f.get("prep_minutes", type=int)
    servings = f.get("servings", type=int)
    tags = ", ".join(t.strip().lower() for t in f.get("tags", "").split(",") if t.strip())
    data = {
        "title": f.get("title", "").strip()[:150],
        "meal_type": f.get("meal_type", ""),
        "cuisine": f.get("cuisine", "").strip()[:50] or None,
        "prep_minutes": minutes if minutes and minutes > 0 else None,
        "servings": servings if servings and servings > 0 else None,
        "tags": tags[:255] or None,
        "ingredients": f.get("ingredients", "").strip()[:8000],
        "steps": f.get("steps", "").strip()[:12000],
    }
    if not data["title"]:
        return data, "Give the recipe a title."
    if data["meal_type"] not in MEAL_TYPES:
        return data, "Pick a meal type."
    if not data["ingredients"] or not data["steps"]:
        return data, "Add at least one ingredient and one step."
    return data, None


def filters_from_args():
    """Also used by the Browse page."""
    max_minutes = request.args.get("time", type=int)
    meal = request.args.get("meal")
    return {
        "q": request.args.get("q", "").strip()[:100],
        "meal_type": meal if meal in MEAL_TYPES else None,
        "max_minutes": max_minutes if max_minutes in TIME_LIMITS else None,
        "tag": request.args.get("tag", "").strip().lower()[:40] or None,
        "sort": request.args.get("sort") if request.args.get("sort") in SORTS else "newest",
    }


@bp.route("/")
def index():
    filters = filters_from_args()
    return render_template("recipes.html", recipes=list_recipes(**filters), tags=all_tags(),
                           filters=filters, meal_types=MEAL_TYPES, time_limits=TIME_LIMITS, sorts=SORTS)


@bp.route("/<int:recipe_id>")
def detail(recipe_id):
    recipe = get_recipe(recipe_id)
    if recipe is None:
        abort(404)
    return render_template("recipe.html", recipe=recipe, meal_types=MEAL_TYPES)


@bp.route("/add", methods=["GET", "POST"])
def add():
    recipe = {}
    if request.method == "POST":
        recipe, error = _read_recipe_form()
        if error is None:
            new_id = create_recipe(recipe, g.user["id"])
            flash(f"Added {recipe['title']}.", "success")
            return redirect(url_for("recipes.detail", recipe_id=new_id) if new_id else url_for("recipes.index"))
        flash(error, "error")
    return render_template("recipe_form.html", recipe=recipe, mode="add", meal_types=MEAL_TYPES)


@bp.route("/<int:recipe_id>/edit", methods=["GET", "POST"])
def edit(recipe_id):
    recipe = get_recipe(recipe_id)
    if recipe is None:
        abort(404)
    if request.method == "POST":
        data, error = _read_recipe_form()
        if error is None:
            update_recipe(recipe_id, data)
            flash("Saved.", "success")
            return redirect(url_for("recipes.detail", recipe_id=recipe_id))
        flash(error, "error")
        recipe = {**recipe, **data}
    return render_template("recipe_form.html", recipe=recipe, mode="edit", meal_types=MEAL_TYPES)


@bp.route("/<int:recipe_id>/delete", methods=["POST"])
def delete(recipe_id):
    recipe = get_recipe(recipe_id)
    if recipe is None:
        abort(404)
    delete_recipe(recipe_id)
    flash(f"Deleted {recipe['title']}.", "success")
    return redirect(url_for("recipes.index"))
