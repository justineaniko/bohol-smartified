
import re
import secrets
from datetime import datetime, timedelta, timezone

import click
import pymysql
from flask import (Blueprint, abort, current_app, flash, g, redirect,
                   render_template, request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db

bp = Blueprint("auth", __name__)

PUBLIC_ENDPOINTS = {"auth.login", "auth.register", "auth.recover", "static"}

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
RECOVERY_CODE_COUNT = 8
MIN_PASSWORD_LENGTH = 8
USERNAME_RE = re.compile(r"^[a-z0-9_]{3,30}$")

LOGIN_ERROR = "Wrong username or password."
RECOVER_ERROR = "That username and recovery code don't match."
LOCKED_ERROR = f"Too many wrong tries. Wait {LOCKOUT_MINUTES} minutes and try again."

_DUMMY_HASH = generate_password_hash(secrets.token_hex(16))


@bp.before_app_request
def load_logged_in_user():
    """Put the signed-in user (or None) in g.user."""
    g.user = None
    if request.endpoint == "static":
        return
    user_id = session.get("user_id")
    if user_id is None:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, display_name, session_version, is_admin FROM users WHERE id = %s",
                (user_id,),
            )
            user = cur.fetchone()
    if user is None or user["session_version"] != session.get("session_version"):
        session.clear()
        return
    g.user = user


@bp.before_app_request
def check_csrf():
    """Every form includes a secret token, so other websites can't submit forms as you."""
    if request.method != "POST":
        return
    sent = request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    if not expected or not secrets.compare_digest(sent.encode(), expected.encode()):
        abort(400, "This form expired. Go back, refresh the page and try again.")


@bp.before_app_request
def require_login():
    """Default-deny: any page not in PUBLIC_ENDPOINTS needs a signed-in user."""
    if g.user is not None or request.endpoint in PUBLIC_ENDPOINTS:
        return
    if request.endpoint is None:
        return
    next_page = request.path if request.method == "GET" else None
    return redirect(url_for("auth.login", next=next_page))


@bp.after_app_request
def no_caching(response):
    """Pages aren't stored in the browser cache, so Back after signing out shows nothing private."""
    if request.endpoint != "static":
        response.headers["Cache-Control"] = "no-store"
    return response


@bp.app_context_processor
def inject_csrf_token():
    """Lets templates write {{ csrf_token() }} inside forms."""
    def csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return session["csrf_token"]
    return {"csrf_token": csrf_token}


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _same(a, b):
    """Compare secrets in constant time."""
    return secrets.compare_digest(a.encode(), b.encode())


def _safe_next(target):
    """Only allow redirects to pages on this site (stops redirects to other websites)."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return url_for("inventory.dashboard")


def _start_session(user, remember):
    session.clear()
    session["user_id"] = user["id"]
    session["session_version"] = user["session_version"]
    session.permanent = remember


def _password_problem(password, confirm):
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if password != confirm:
        return "The two passwords don't match."
    return None


def _get_user(cur, username):
    cur.execute("SELECT * FROM users WHERE username = %s", (username,))
    return cur.fetchone()


def _is_locked(user):
    return user["locked_until"] is not None and user["locked_until"] > _now()


def _record_failure(cur, user):
    failures = user["failed_attempts"] + 1
    if failures >= MAX_FAILED_ATTEMPTS:
        cur.execute(
            "UPDATE users SET failed_attempts = 0, locked_until = %s WHERE id = %s",
            (_now() + timedelta(minutes=LOCKOUT_MINUTES), user["id"]),
        )
    else:
        cur.execute("UPDATE users SET failed_attempts = %s WHERE id = %s", (failures, user["id"]))


def _clear_failures(cur, user_id):
    cur.execute("UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = %s", (user_id,))


def _normalize_code(code):
    """'A1B2C3-D4E5F6', 'a1b2c3 d4e5f6' and 'a1b2c3d4e5f6' all count as the same code."""
    return re.sub(r"[^0-9a-f]", "", code.lower())


def _new_recovery_codes(cur, user_id):
    """Replace a user's recovery codes. Returns the plain codes, to show ONCE."""
    codes = [f"{secrets.token_hex(3)}-{secrets.token_hex(3)}" for _ in range(RECOVERY_CODE_COUNT)]
    cur.execute("DELETE FROM recovery_codes WHERE user_id = %s", (user_id,))
    cur.executemany(
        "INSERT INTO recovery_codes (user_id, code_hash) VALUES (%s, %s)",
        [(user_id, generate_password_hash(_normalize_code(c))) for c in codes],
    )
    return codes


def _codes_left(cur, user_id):
    cur.execute(
        "SELECT COUNT(*) AS n FROM recovery_codes WHERE user_id = %s AND used_at IS NULL",
        (user_id,),
    )
    return cur.fetchone()["n"]


@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("inventory.dashboard"))
    if request.method == "POST":
        invite_code = current_app.config["HOUSE_INVITE_CODE"]
        username = request.form.get("username", "").strip().lower()
        display_name = request.form.get("display_name", "").strip()[:50] or username
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        error = None
        if not invite_code:
            error = "Sign-ups are closed: HOUSE_INVITE_CODE isn't set in .env."
        elif not _same(request.form.get("invite_code", "").strip(), invite_code):
            error = "That house invite code is wrong."
        elif not USERNAME_RE.match(username):
            error = "Username: 3 to 30 characters, using letters, numbers or underscores."
        else:
            error = _password_problem(password, confirm)

        if error is None:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) AS n FROM users")
                    is_first = cur.fetchone()["n"] == 0
                    try:
                        cur.execute(
                            "INSERT INTO users (username, display_name, password_hash, is_admin) "
                            "VALUES (%s, %s, %s, %s)",
                            (username, display_name, generate_password_hash(password), is_first),
                        )
                    except pymysql.err.IntegrityError:
                        error = "That username is taken."
                    else:
                        user_id = cur.lastrowid
                        codes = _new_recovery_codes(cur, user_id)
                        conn.commit()
                        cur.execute(
                            "SELECT id, username, display_name, session_version, is_admin FROM users WHERE id = %s",
                            (user_id,),
                        )
                        user = cur.fetchone()
            if error is None:
                _start_session(user, remember=False)
                g.user = user
                return render_template("recovery_codes.html", codes=codes, first_time=True)
        flash(error, "error")
    return render_template("register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("inventory.dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"

        with get_db() as conn:
            with conn.cursor() as cur:
                user = _get_user(cur, username)
                if user is None:
                    check_password_hash(_DUMMY_HASH, password)
                    error = LOGIN_ERROR
                elif _is_locked(user):
                    error = LOCKED_ERROR
                elif not check_password_hash(user["password_hash"], password):
                    _record_failure(cur, user)
                    conn.commit()
                    error = LOGIN_ERROR
                else:
                    _clear_failures(cur, user["id"])
                    conn.commit()
                    _start_session(user, remember)
                    return redirect(_safe_next(request.args.get("next")))
        flash(error, "error")
    return render_template("login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You're signed out.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/recover", methods=["GET", "POST"])
def recover():
    """Forgot password: username + one unused recovery code -> set a new password."""
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        code = _normalize_code(request.form.get("code", ""))
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        error = _password_problem(password, confirm)
        if error is None:
            with get_db() as conn:
                with conn.cursor() as cur:
                    user = _get_user(cur, username)
                    if user is None:
                        check_password_hash(_DUMMY_HASH, code)
                        error = RECOVER_ERROR
                    elif _is_locked(user):
                        error = LOCKED_ERROR
                    else:
                        cur.execute(
                            "SELECT id, code_hash FROM recovery_codes WHERE user_id = %s AND used_at IS NULL",
                            (user["id"],),
                        )
                        match = next(
                            (row for row in cur.fetchall() if check_password_hash(row["code_hash"], code)),
                            None,
                        )
                        if match is None:
                            _record_failure(cur, user)
                            conn.commit()
                            error = RECOVER_ERROR
                        else:
                            cur.execute("UPDATE recovery_codes SET used_at = %s WHERE id = %s", (_now(), match["id"]))
                            cur.execute(
                                "UPDATE users SET password_hash = %s, session_version = session_version + 1, "
                                "failed_attempts = 0, locked_until = NULL WHERE id = %s",
                                (generate_password_hash(password), user["id"]),
                            )
                            left = _codes_left(cur, user["id"])
                            conn.commit()
                            flash(f"Password reset. That code is now used up: you have {left} left.", "success")
                            if left <= 2:
                                flash("You're running low on recovery codes. Make new ones from your account page.", "error")
                            return redirect(url_for("auth.login"))
        flash(error, "error")
    return render_template("recover.html")


@bp.route("/account", methods=["GET", "POST"])
def account():
    """Signed-in only (not in PUBLIC_ENDPOINTS): change password, make new recovery codes."""
    if request.method == "POST":
        action = request.form.get("action")
        current = request.form.get("current_password", "")
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT password_hash FROM users WHERE id = %s", (g.user["id"],))
                if not check_password_hash(cur.fetchone()["password_hash"], current):
                    flash("Your current password is wrong.", "error")
                    return redirect(url_for("auth.account"))

                if action == "change_password":
                    new = request.form.get("new_password", "")
                    problem = _password_problem(new, request.form.get("confirm", ""))
                    if problem:
                        flash(problem, "error")
                    else:
                        cur.execute(
                            "UPDATE users SET password_hash = %s, session_version = session_version + 1 WHERE id = %s",
                            (generate_password_hash(new), g.user["id"]),
                        )
                        conn.commit()
                        session["session_version"] = g.user["session_version"] + 1
                        flash("Password changed. Your other devices have been signed out.", "success")
                    return redirect(url_for("auth.account"))

                if action == "new_codes":
                    codes = _new_recovery_codes(cur, g.user["id"])
                    conn.commit()
                    return render_template("recovery_codes.html", codes=codes, first_time=False)
        abort(400)

    with get_db() as conn:
        with conn.cursor() as cur:
            left = _codes_left(cur, g.user["id"])
    return render_template("account.html", codes_left=left)


FEATURES = {"books": "Book tracker"}


def has_feature(feature):
    """True if the signed-in user has this feature switched on. Cached per request."""
    if g.user is None:
        return False
    if "features" not in g:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT feature FROM user_features WHERE user_id = %s", (g.user["id"],))
                g.features = {row["feature"] for row in cur.fetchall()}
    return feature in g.features


def require_feature(feature):
    """Call from a blueprint's before_request: blocks the whole section on the server (403)."""
    if not has_feature(feature):
        abort(403)


@bp.app_context_processor
def inject_feature_check():
    """Lets templates write {% if has_feature('books') %}."""
    return {"has_feature": has_feature, "FEATURES": FEATURES}


@bp.route("/admin/access", methods=["GET", "POST"])
def admin_access():
    """Admin only: choose which profiles get which features."""
    if not g.user["is_admin"]:
        abort(403)
    with get_db() as conn:
        with conn.cursor() as cur:
            if request.method == "POST":
                feature = request.form.get("feature")
                user_id = request.form.get("user_id", type=int)
                if feature not in FEATURES or user_id is None:
                    abort(400)
                if request.form.get("enabled") == "1":
                    cur.execute(
                        "INSERT IGNORE INTO user_features (user_id, feature) VALUES (%s, %s)",
                        (user_id, feature),
                    )
                else:
                    cur.execute(
                        "DELETE FROM user_features WHERE user_id = %s AND feature = %s",
                        (user_id, feature),
                    )
                conn.commit()
                flash("Access updated.", "success")
                return redirect(url_for("auth.admin_access"))

            cur.execute("SELECT id, username, display_name, is_admin FROM users ORDER BY display_name")
            users = cur.fetchall()
            cur.execute("SELECT user_id, feature FROM user_features")
            enabled = {(row["user_id"], row["feature"]) for row in cur.fetchall()}
    return render_template("admin_access.html", users=users, enabled=enabled)


@bp.cli.command("reset-password")
@click.argument("username")
def reset_password_command(username):
    """Set a new password for USERNAME and print fresh recovery codes."""
    password = click.prompt("New password", hide_input=True, confirmation_prompt=True)
    if len(password) < MIN_PASSWORD_LENGTH:
        raise click.ClickException(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    with get_db() as conn:
        with conn.cursor() as cur:
            user = _get_user(cur, username.strip().lower())
            if user is None:
                raise click.ClickException("No user with that username.")
            cur.execute(
                "UPDATE users SET password_hash = %s, session_version = session_version + 1, "
                "failed_attempts = 0, locked_until = NULL WHERE id = %s",
                (generate_password_hash(password), user["id"]),
            )
            codes = _new_recovery_codes(cur, user["id"])
        conn.commit()
    click.echo(f"Password reset for {user['username']}. Their new recovery codes:")
    for c in codes:
        click.echo(f"  {c}")
