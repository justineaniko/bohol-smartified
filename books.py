"""Book tracker: only for profiles with the 'books' feature (switched on at /admin/access).

Every book belongs to exactly one profile and only that profile sees it,
so every query below must include  WHERE owner_id = %s  with user_id.

ROUTES: done.  DATA LAYER: your TODOs (pages load empty until you write them).
"""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from auth import require_feature
from db import get_db  # noqa: F401

bp = Blueprint("books", __name__, url_prefix="/books")

STATUSES = {"reading": "Reading", "to_read": "To read", "finished": "Finished"}
SORTS = {"recent": "Recently added", "title": "Title", "author": "Author", "rating": "Rating"}


@bp.before_request
def books_access():
    """Locks the WHOLE /books section on the server for profiles without the feature."""
    require_feature("books")


# =============================================================================
# DATA LAYER: your TODOs
# Book dicts need: id, title, author, status, rating, pages, genre,
#                  started_on, finished_on (dates), notes
# =============================================================================

def list_books(user_id, status=None, q="", sort="recent"):
    """This user's books. status: a STATUSES key or None for all. q: search title/author.
    sort: recent -> created_at DESC, title, author, rating -> rating DESC."""
    # TODO
    return []


def book_counts(user_id):
    """Return {"reading": n, "to_read": n, "finished": n} for the tab badges.
    Hint: SELECT status, COUNT(*) ... GROUP BY status"""
    # TODO
    return {"reading": 0, "to_read": 0, "finished": 0}


def get_book(book_id, user_id):
    """One book dict, or None if it doesn't exist OR belongs to someone else."""
    # TODO
    return None


def create_book(data, user_id):
    """INSERT with owner_id = user_id. `data` comes from _read_book_form()."""
    # TODO
    pass


def update_book(book_id, data, user_id):
    """UPDATE ... WHERE id = %s AND owner_id = %s"""
    # TODO
    pass


def delete_book(book_id, user_id):
    """DELETE ... WHERE id = %s AND owner_id = %s"""
    # TODO
    pass


# =============================================================================
# ROUTES: done
# =============================================================================

def _read_book_form():
    f = request.form
    rating = f.get("rating", type=int)
    pages = f.get("pages", type=int)
    data = {
        "title": f.get("title", "").strip()[:200],
        "author": f.get("author", "").strip()[:120] or None,
        "status": f.get("status") if f.get("status") in STATUSES else "to_read",
        "rating": rating if rating in (1, 2, 3, 4, 5) else None,
        "pages": pages if pages and pages > 0 else None,
        "genre": f.get("genre", "").strip()[:60] or None,
        "started_on": f.get("started_on") or None,
        "finished_on": f.get("finished_on") or None,
        "notes": f.get("notes", "").strip()[:4000] or None,
    }
    if not data["title"]:
        return data, "Give the book a title."
    return data, None


@bp.route("/")
def index():
    status = request.args.get("status")
    status = status if status in STATUSES else None
    q = request.args.get("q", "").strip()[:100]
    sort = request.args.get("sort") if request.args.get("sort") in SORTS else "recent"
    books = list_books(g.user["id"], status=status, q=q, sort=sort)
    return render_template("books.html", books=books, counts=book_counts(g.user["id"]),
                           status=status, q=q, sort=sort, statuses=STATUSES, sorts=SORTS)


@bp.route("/add", methods=["GET", "POST"])
def add():
    book = {"status": request.args.get("status", "to_read")}
    if request.method == "POST":
        book, error = _read_book_form()
        if error is None:
            create_book(book, g.user["id"])
            flash(f"Added {book['title']}.", "success")
            return redirect(url_for("books.index"))
        flash(error, "error")
    return render_template("book_form.html", book=book, mode="add", statuses=STATUSES)


@bp.route("/<int:book_id>/edit", methods=["GET", "POST"])
def edit(book_id):
    book = get_book(book_id, g.user["id"])
    if book is None:
        abort(404)
    if request.method == "POST":
        data, error = _read_book_form()
        if error is None:
            update_book(book_id, data, g.user["id"])
            flash("Saved.", "success")
            return redirect(url_for("books.index"))
        flash(error, "error")
        book = {**book, **data}
    return render_template("book_form.html", book=book, mode="edit", statuses=STATUSES)


@bp.route("/<int:book_id>/delete", methods=["POST"])
def delete(book_id):
    book = get_book(book_id, g.user["id"])
    if book is None:
        abort(404)
    delete_book(book_id, g.user["id"])
    flash(f"Deleted {book['title']}.", "success")
    return redirect(url_for("books.index"))
