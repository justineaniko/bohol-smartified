from flask import Blueprint, Response, render_template, request

import api

bp = Blueprint("voice", __name__, url_prefix="/voice")

COMMANDS = {"add": api.run_add, "use": api.run_use, "grocery": api.run_grocery}


@bp.route("/")
def index():
    return render_template("voice.html")


@bp.route("/run", methods=["POST"])
def run():
    action = request.form.get("action")
    text = request.form.get("text", "").strip()[:200]
    if action not in COMMANDS:
        return Response("Pick add, use or grocery.", status=400, mimetype="text/plain")
    if not text:
        return Response("I didn't catch anything.", status=400, mimetype="text/plain")
    return Response(COMMANDS[action](text), mimetype="text/plain")