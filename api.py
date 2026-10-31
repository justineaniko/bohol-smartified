import hashlib
import re
import secrets

from flask import Blueprint, Response, g, request

from db import get_db
import grocery
import inventory

bp = Blueprint("api", __name__, url_prefix="/api")

NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "a dozen": 12, "dozen": 12,
}
LEAD_VERBS = re.compile(r"^(?:please\s+)?(?:i\s+)?(?:add(?:ed)?|put|bought|got|use[ds]?|ate|drank|finished|took)\s+", re.I)
UNIT_OF = re.compile(r"^(?:packs?|bottles?|cans?|boxes?|bags?|pieces?|pcs|cartons?|packets?|rolls?|sachets?)\s+of\s+", re.I)
PLACE_SPLIT = re.compile(r"\s+(?:in|into|to|at|on|from)\s+(?:the\s+|my\s+)?", re.I)
LIST_WORDS = re.compile(r"\s+(?:to|on)\s+(?:the\s+|my\s+)?(?:grocery\s+|shopping\s+)?list\s*$", re.I)


def hash_key(key):
    return hashlib.sha256(key.encode()).hexdigest()


def new_key(user_id):
    key = "bh_" + secrets.token_urlsafe(32)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM api_keys WHERE user_id = %s", (user_id,))
            cur.execute("INSERT INTO api_keys (user_id, key_hash) VALUES (%s, %s)", (user_id, hash_key(key)))
            conn.commit()
    return key


def revoke_key(user_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM api_keys WHERE user_id = %s", (user_id,))
            conn.commit()


def key_info(user_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT created_at, last_used_at FROM api_keys WHERE user_id = %s", (user_id,))
            return cur.fetchone()


def _say(text, status=200):
    return Response(text, status=status, mimetype="text/plain")


@bp.before_request
def authenticate():
    header = request.headers.get("Authorization", "")
    key = header[7:].strip() if header.lower().startswith("bearer ") else request.headers.get("X-Key", "").strip()
    if not key:
        return _say("Missing Siri key.", 401)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT users.id, users.username, users.display_name, users.session_version, users.is_admin "
                "FROM api_keys JOIN users ON api_keys.user_id = users.id "
                "WHERE api_keys.key_hash = %s AND users.is_admin = TRUE",
                (hash_key(key),),
            )
            user = cur.fetchone()
            if user:
                cur.execute("UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP WHERE user_id = %s", (user["id"],))
                conn.commit()
    if user is None:
        return _say("That Siri key isn't valid any more. Make a new one on your Account page.", 401)
    g.user = user


def _spoken_text():
    data = request.get_json(silent=True)
    if isinstance(data, dict):
        text = data.get("text", "")
    else:
        text = request.form.get("text") or request.get_data(as_text=True)
    return re.sub(r"[.!?]+$", "", (text or "").strip())[:200]


def _split_amount(text):
    words = text.split()
    if not words:
        return 1, ""
    if re.fullmatch(r"\d+", words[0]):
        return max(int(words[0]), 1), " ".join(words[1:])
    two = " ".join(words[:2]).lower()
    if two in NUMBER_WORDS:
        return NUMBER_WORDS[two], " ".join(words[2:])
    if words[0].lower() in NUMBER_WORDS:
        return NUMBER_WORDS[words[0].lower()], " ".join(words[1:])
    return 1, text


def _norm(name):
    name = re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()
    name = re.sub(r"\s+", " ", name)
    words = [w[:-2] if w.endswith("es") and len(w) > 4 else w[:-1] if w.endswith("s") and len(w) > 3 else w
             for w in name.split()]
    return " ".join(words)


def _match_place(phrase):
    want = _norm(phrase)
    if not want:
        return None
    best, best_score = None, 0
    for loc in inventory.list_locations() or []:
        full = _norm(f"{loc.get('room_name') or ''} {loc['name']}")
        name = _norm(loc["name"])
        if want in (name, full):
            score = 3
        elif want in full or name in want:
            score = 2
        elif set(want.split()) <= set(full.split()):
            score = 1
        else:
            score = 0
        if score > best_score:
            best, best_score = loc, score
    return best


def _parse(text):
    text = LEAD_VERBS.sub("", text.strip())
    place = None
    splits = list(PLACE_SPLIT.finditer(text))
    if splits:
        last = splits[-1]
        candidate = _match_place(text[last.end():])
        if candidate:
            place = candidate
            text = text[:last.start()]
    amount, name = _split_amount(text.strip())
    name = UNIT_OF.sub("", name.strip())
    return amount, name.strip(), place


def _find_item(name, place):
    want = _norm(name)
    if not want:
        return None
    best, best_score = None, 0
    for item in inventory.list_items(g.user["id"]) or []:
        have = _norm(item["name"])
        if have == want:
            score = 10
        elif want in have or have in want:
            score = 5
        else:
            continue
        if place and item.get("location_id") == place["id"]:
            score += 3
        if score > best_score or (score == best_score and best and item["quantity"] > best["quantity"]):
            best, best_score = item, score
    if best and place and best.get("link_id") and best.get("location_id") != place["id"]:
        for other in inventory.list_group(best["link_id"], g.user["id"]):
            if other.get("location_id") == place["id"]:
                return other
    return best


def _where(item):
    label = inventory._location_label(item).replace(" · ", ", ")
    return f" in the {label}" if label else ""


def _status(item):
    total = item.get("group_total")
    extra = f", {total} total" if item.get("place_count") and item["place_count"] > 1 else ""
    return f"{item['name']} is now {item['quantity']}{_where(item)}{extra}."


@bp.route("/add", methods=["POST"])
def add():
    text = _spoken_text()
    amount, name, place = _parse(text)
    if not name:
        return _say("I didn't catch what to add.")
    item = _find_item(name, place)
    if item:
        item = inventory.change_quantity(item["id"], g.user["id"], amount)
        return _say(_status(item))
    data = {
        "name": name[:1].upper() + name[1:100], "brand": None, "pack_size": None, "category": "other",
        "quantity": amount, "threshold": 0, "restock_to": None,
        "location_id": place["id"] if place else None, "shelf": None, "expiry_date": None,
        "place_min": None, "assigned_to": None, "private": False,
    }
    new_id = inventory.create_item(data, g.user["id"])
    item = inventory.get_item(new_id, g.user["id"])
    return _say(f"Added {amount} {item['name']}{_where(item)} as a new item. You can set its category later.")


@bp.route("/use", methods=["POST"])
def use():
    text = _spoken_text()
    amount, name, place = _parse(text)
    item = _find_item(name, place)
    if item is None:
        return _say(f"I couldn't find {name or 'that'} in the inventory.")
    item = inventory.change_quantity(item["id"], g.user["id"], -amount)
    return _say(_status(item))


@bp.route("/grocery", methods=["POST"])
def grocery_add():
    text = _spoken_text()
    private = bool(re.search(r"\b(?:to|on)\s+my\s+list\b", text, re.I))
    text = LIST_WORDS.sub("", text)
    text = re.sub(r"^(?:please\s+)?(?:add|put|we need|i need|buy|get)\s+", "", text, flags=re.I).strip()
    if not text:
        return _say("I didn't catch what to add to the list.")
    name = text[:1].upper() + text[1:100]
    grocery.create_entry(name, g.user["id"] if private else None)
    return _say(f"Added {name} to {'your' if private else 'the house'} grocery list.")
