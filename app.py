import json
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request

app = Flask(__name__)

DATA_DIR = Path(__file__).parent / "data" / "output"
NICKNAMES_FILE = Path(__file__).parent / "data" / "nicknames.json"
COUNTERS_FILE = Path(__file__).parent / "data" / "counters.json"
SYNERGIES_FILE = Path(__file__).parent / "data" / "synergies.json"


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
    return render_template("home.html")


@app.route("/heroes")
def heroes_page():
    return render_template("heroes.html")


@app.route("/items")
def items_page():
    return render_template("items.html")


@app.route("/graph")
def graph_page():
    return render_template("graph.html")


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


@app.route("/api/synergies/<key>")
def api_synergies(key: str):
    if not SYNERGIES_FILE.exists():
        abort(404)
    synergies = json.loads(SYNERGIES_FILE.read_text(encoding="utf-8"))
    short_key = key.replace("npc_dota_hero_", "")
    data = synergies.get(short_key)
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


@app.route("/api/graph_synergies")
def api_graph_synergies():
    if not SYNERGIES_FILE.exists():
        return jsonify({})
    data = json.loads(SYNERGIES_FILE.read_text(encoding="utf-8"))
    result = {}
    for short_key, val in data.items():
        result[short_key] = {
            "synergies": [
                {"key": s["key"], "name": s.get("name", ""), "strength": s.get("strength", "moderate"),
                 "reasons": s.get("reasons", [])}
                for s in val.get("synergies", [])
            ]
        }
    return jsonify(result)


@app.route("/api/graph_data")
def api_graph_data():
    if not COUNTERS_FILE.exists():
        return jsonify({})
    data = json.loads(COUNTERS_FILE.read_text(encoding="utf-8"))
    # Return compact form: {shortKey: {countered_by: [{key, name, strength}]}}
    result = {}
    for short_key, val in data.items():
        result[short_key] = {
            "countered_by": [
                {"key": c["key"], "name": c.get("name", ""), "strength": c.get("strength", "moderate"),
                 "reasons": c.get("reasons", [])}
                for c in val.get("countered_by", [])
            ]
        }
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)
