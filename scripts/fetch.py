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


def fetch_all():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for filename, url in SOURCES.items():
        dest = RAW_DIR / filename
        print(f"Downloading {filename}...")
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        print(f"  Saved to {dest} ({len(resp.content)} bytes)")


if __name__ == "__main__":
    fetch_all()
