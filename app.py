import os
from datetime import date, timedelta

from dotenv import load_dotenv
from flask import Flask, render_template

load_dotenv()

import auth
import books
import browse
import inventory
import grocery
import medicine
import recipes

app = Flask(__name__, static_folder="public", static_url_path="")

app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY"),
    HOUSE_INVITE_CODE=os.environ.get("HOUSE_INVITE_CODE", ""),
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
)
if not app.config["SECRET_KEY"]:
    raise RuntimeError("SECRET_KEY is missing. Add it to your .env file (see .env.example).")

app.register_blueprint(auth.bp)
app.register_blueprint(inventory.bp)
app.register_blueprint(browse.bp)
app.register_blueprint(recipes.bp)
app.register_blueprint(books.bp)
app.register_blueprint(grocery.bp)
app.register_blueprint(medicine.bp)

@app.context_processor
def inject_today():
    """Templates use `today` to show 'expires in 3 days'."""
    return {"today": date.today()}


@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403, title="Not for this profile",
                           message="Your profile doesn't have access to this page."), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, title="Not found",
                           message="That page or item doesn't exist, or it isn't yours to see."), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
