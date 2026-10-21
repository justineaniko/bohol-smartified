import os
from datetime import timedelta

import requests
from dotenv import load_dotenv
from flask import Flask, abort, redirect, render_template, request, url_for

from auth import bp as auth_bp
from db import get_db

load_dotenv()  # reads secrets from the .env file into os.environ

# Serve public/ at the site root, the same way Vercel does (/style.css)
app = Flask(__name__, static_folder="public", static_url_path="")

# --- Config ---
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY"),                    # signs the sign-in cookie
    HOUSE_INVITE_CODE=os.environ.get("HOUSE_INVITE_CODE", ""),  # needed to create a profile
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),              # "Keep me signed in" length
    SESSION_COOKIE_HTTPONLY=True,    # page JavaScript can't read the sign-in cookie
    SESSION_COOKIE_SAMESITE="Lax",   # other websites can't use your cookie in forms
    # true only when the site uses https (Vercel, or `tailscale serve`)
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
)
if not app.config["SECRET_KEY"]:
    raise RuntimeError("SECRET_KEY is missing. Add it to your .env file (see .env.example).")

# Sign-in pages. This also LOCKS EVERY OTHER PAGE behind sign-in (see auth.require_login).
app.register_blueprint(auth_bp)

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")


# --- Helpers ---
def get_item(qr_code_id):
    """Return one item as a dict, or None if not found."""
    # TODO: SELECT the item WHERE qr_code_id = %s  (use get_db())
    # Hint: always pass values as the 2nd argument to execute(), never f-strings
    pass


def send_discord_alert(message):
    """Post a message to the household Discord channel."""
    # TODO: requests.post to the webhook with a JSON body {"content": message}
    pass


def check_low_stock(item):
    """Send one alert when stock drops to/below threshold; reset when restocked."""
    # TODO: compare quantity to threshold
    # TODO: use low_stock_alert_sent so it only alerts once
    pass


# --- Routes ---
# Every route here requires sign-in automatically. The signed-in user is in g.user.
# To make a page public on purpose, add its endpoint name to PUBLIC_ENDPOINTS in auth.py.

@app.route("/")
def dashboard():
    # TEMP test data: replace with a real DB query later
    items = [
        {"name": "Rice", "quantity": 2, "threshold": 3, "qr_code_id": "rice", "is_low": True},
        {"name": "Soap", "quantity": 6, "threshold": 2, "qr_code_id": "soap", "is_low": False},
    ]
    return render_template("dashboard.html", items=items)


@app.route("/item/<qr_code_id>")
def item_page(qr_code_id):
    # GET only: viewing must never change data
    item = get_item(qr_code_id)
    if item is None:
        abort(404)
    return render_template("item.html", item=item)


@app.route("/item/<qr_code_id>/use", methods=["POST"])
def use_item(qr_code_id):
    # TODO: decrease quantity by 1 (don't let it go below 0)
    # TODO: call check_low_stock
    return redirect(url_for("item_page", qr_code_id=qr_code_id))


@app.route("/item/<qr_code_id>/restock", methods=["POST"])
def restock_item(qr_code_id):
    # TODO: increase quantity by the amount from request.form
    # TODO: reset low_stock_alert_sent if stock is back above threshold
    return redirect(url_for("item_page", qr_code_id=qr_code_id))


@app.route("/add", methods=["GET", "POST"])
def add_item():
    if request.method == "POST":
        # TODO: read fields from request.form, INSERT the new item
        return redirect(url_for("dashboard"))
    # TODO: render a form template for adding items
    pass


if __name__ == "__main__":
    # 0.0.0.0 = reachable from other devices on the network/Tailscale
    app.run(host="0.0.0.0", port=5000, debug=True)
