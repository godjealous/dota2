import json
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request

app = Flask(__name__)

DATA_DIR = Path(__file__).parent / "data" / "output"
NICKNAMES_FILE = Path(__file__).parent / "data" / "nicknames.json"
COUNTERS_FILE = Path(__file__).parent / "data" / "counters.json"


def _load(filename: str) -> dict:
    path = DATA_DIR / filename
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_nicknames() -> dict:
    if not NICKNAMES_FILE.exists():
        return {}
    return json.loads(NICKNAMES_FILE.read_text(encoding="utf-8"))


def _apply_nicknames(heroes: dict) -> dict:
    nicknames = _load_nicknames()
    for key, hero in heroes.items():
        short_key = key.replace("npc_dota_hero_", "")
        entry = nicknames.get(short_key, {})
        nicks = entry.get("nicknames")
        if nicks is not None:
            hero["nickname"] = nicks
    return heroes


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.route("/api/meta")
def api_meta():
    return jsonify(_load("meta.json"))


@app.route("/api/heroes")
def api_heroes():
    heroes = _apply_nicknames(_load("heroes.json"))
    q = request.args.get("q", "").lower()
    attr = request.args.get("attr", "")

    result = {}
    for key, hero in heroes.items():
        if attr and hero.get("primary_attr") != attr:
            continue
        if q and q not in hero.get("name", "").lower() and q not in hero.get("name_en", "").lower():
            continue
        result[key] = hero
    return jsonify(result)


@app.route("/api/heroes/<key>")
def api_hero(key: str):
    heroes = _apply_nicknames(_load("heroes.json"))
    hero = heroes.get(key)
    if hero is None:
        abort(404)
    return jsonify(hero)


@app.route("/api/counters/<key>")
def api_counters(key: str):
    if not COUNTERS_FILE.exists():
        abort(404)
    counters = json.loads(COUNTERS_FILE.read_text(encoding="utf-8"))
    short_key = key.replace("npc_dota_hero_", "")
    data = counters.get(short_key)
    if data is None:
        abort(404)
    return jsonify(data)


@app.route("/api/items")
def api_items():
    items = _load("items.json")
    q = request.args.get("q", "").lower()

    if not q:
        return jsonify(items)

    result = {
        key: item for key, item in items.items()
        if q in item.get("name", "").lower() or q in item.get("name_en", "").lower()
    }
    return jsonify(result)


@app.route("/api/items/<key>")
def api_item(key: str):
    item = _load("items.json").get(key)
    if item is None:
        abort(404)
    return jsonify(item)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)
