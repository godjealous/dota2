import json
from functools import lru_cache
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request

app = Flask(__name__)

DATA_DIR = Path(__file__).parent / "data" / "output"


@lru_cache(maxsize=None)
def _load(filename: str) -> dict:
    path = DATA_DIR / filename
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


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
    heroes = _load("heroes.json")
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
    hero = _load("heroes.json").get(key)
    if hero is None:
        abort(404)
    return jsonify(hero)


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
