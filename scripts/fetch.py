import json
import requests
from pathlib import Path

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"

SOURCES = {
    "heroes.json": "https://cdn.jsdelivr.net/npm/dotaconstants@latest/build/heroes.json",
    "hero_abilities.json": "https://cdn.jsdelivr.net/npm/dotaconstants@latest/build/hero_abilities.json",
    "abilities.json": "https://cdn.jsdelivr.net/npm/dotaconstants@latest/build/abilities.json",
    "items_raw.json": "https://cdn.jsdelivr.net/npm/dotaconstants@latest/build/items.json",
    "patch.json": "https://cdn.jsdelivr.net/npm/dotaconstants@latest/build/patch.json",
    "dota_schinese.txt": "https://dotabase.dillerm.io/dota-vpk/resource/localization/dota_schinese.txt",
    "abilities_schinese.txt": "https://dotabase.dillerm.io/dota-vpk/resource/localization/abilities_schinese.txt",
}

NEUTRAL_TIER_URL = "https://www.dota2.com/datafeed/itemlist?language=schinese"


def fetch_neutral_tiers() -> None:
    """Fetch neutral item tier info from Dota2 datafeed and save to neutral_tiers.json."""
    dest = RAW_DIR / "neutral_tiers.json"
    print("Downloading neutral_tiers.json...")
    resp = requests.get(NEUTRAL_TIER_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    data = resp.json()
    items = data.get("result", {}).get("data", {}).get("itemabilities", [])
    # Keep only items with a real tier (tier > 0)
    tier_map = {
        i["name"]: i["neutral_item_tier"]
        for i in items
        if i.get("neutral_item_tier", -1) >= 0
    }
    dest.write_text(json.dumps(tier_map, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Saved {len(tier_map)} neutral tier entries → {dest}")


def fetch_all():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for filename, url in SOURCES.items():
        dest = RAW_DIR / filename
        print(f"Downloading {filename}...")
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        print(f"  Saved to {dest} ({len(resp.content)} bytes)")
    fetch_neutral_tiers()


if __name__ == "__main__":
    fetch_all()
