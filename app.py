import os
from datetime import date, timedelta

from dotenv import load_dotenv
from flask import Flask, render_template

load_dotenv()  # reads secrets from the .env file into os.environ

import auth  # noqa: E402  (imported after load_dotenv so it sees .env)
import books  # noqa: E402
import browse  # noqa: E402
import inventory  # noqa: E402
import recipes  # noqa: E402

# Serve public/ at the site root, the same way Vercel does (/style.css)
app = Flask(__name__, static_folder="public", static_url_path="")

# --- Config ---
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY"),                    # signs the sign-in cookie
    HOUSE_INVITE_CODE=os.environ.get("HOUSE_INVITE_CODE", ""),  # needed to create a profile
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),              # "Keep me signed in" length
    SESSION_COOKIE_HTTPONLY=True,    # page JavaScript can't read the sign-in cookie
    SESSION_COOKIE_SAMESITE="Lax",   # other websites can't use your cookie in forms
    # true when the site uses https (Vercel, or `tailscale serve`)
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
)
if not app.config["SECRET_KEY"]:
    raise RuntimeError("SECRET_KEY is missing. Add it to your .env file (see .env.example).")

# auth MUST be registered first: it locks every page behind sign-in.
app.register_blueprint(auth.bp)
app.register_blueprint(inventory.bp)   # /, /item/..., /add
app.register_blueprint(browse.bp)      # /browse
app.register_blueprint(recipes.bp)     # /recipes
app.register_blueprint(books.bp)       # /books (only profiles with the 'books' feature)


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
    # 0.0.0.0 = reachable from other devices on the network
    app.run(host="0.0.0.0", port=5000, debug=True)
