"""
Data merge script for Dota2 Wiki pipeline.

Reads raw data files and produces:
  data/output/heroes.json  – keyed by npc name
  data/output/items.json   – keyed by item_<name>
"""

import json
import re
from pathlib import Path

_ROOT = Path(__file__).parent.parent
RAW = _ROOT / "data/raw"
OUT = _ROOT / "data/output"


# ---------------------------------------------------------------------------
# Localization helpers
# ---------------------------------------------------------------------------

def _load_kv_tokens(filepath: Path) -> dict:
    """
    Parse a Valve KeyValues localization file and return a flat token dict.

    We use a line-by-line regex instead of the shared parse_kv() function
    because some values in these files contain escaped double-quotes (e.g.
    <span class=\"Footnote\">…</span>) which confuse parse_kv's tokeniser and
    cause the entire token stream to shift out of phase.

    The pattern matches:
        "KEY"   "VALUE"
    where both KEY and VALUE may contain backslash-escaped characters.
    """
    pattern = re.compile(
        r'^\s*"((?:[^"\\]|\\.)*)"[ \t]+"((?:[^"\\]|\\.)*)"\s*$'
    )
    tokens: dict = {}
    text = filepath.read_text(encoding="utf-8")
    for line in text.splitlines():
        m = pattern.match(line)
        if m:
            tokens[m.group(1)] = m.group(2)
    return tokens


# ---------------------------------------------------------------------------
# Public merge functions
# ---------------------------------------------------------------------------

def merge_heroes() -> dict:
    """
    Return a dict keyed by npc name (e.g. "npc_dota_hero_antimage") with
    the merged hero + abilities data.
    """
    heroes_raw = json.loads((RAW / "heroes.json").read_text())
    hero_abilities_raw = json.loads((RAW / "hero_abilities.json").read_text())
    abilities_raw = json.loads((RAW / "abilities.json").read_text())

    # abilities_schinese.txt carries BOTH hero names and ability names
    loc = _load_kv_tokens(RAW / "abilities_schinese.txt")

    result: dict = {}

    for _numeric_id, hero in heroes_raw.items():
        npc_name: str = hero.get("name", "")
        if not npc_name.startswith("npc_dota_hero_"):
            continue

        # Chinese / English hero names
        # Token keys: "npc_dota_hero_antimage:n" and "npc_dota_hero_antimage__en:n"
        cn_name = loc.get(f"{npc_name}:n") or hero.get("localized_name", npc_name)
        en_name = loc.get(f"{npc_name}__en:n") or hero.get("localized_name", npc_name)

        # Abilities
        ability_keys = hero_abilities_raw.get(npc_name, {}).get("abilities", [])

        # Collect innate abilities for this hero not already in the abilities list.
        # Only include those with a display name (dname or localization entry) to
        # exclude internal trigger/facet entries that have no tooltip.
        hero_prefix = npc_name.replace("npc_dota_hero_", "")
        existing_keys = {k for k in ability_keys if isinstance(k, str)}
        innate_keys = sorted(
            k for k, v in abilities_raw.items()
            if v.get("is_innate")
            and k.startswith(hero_prefix + "_")
            and k not in existing_keys
            and (v.get("dname") or loc.get(f"DOTA_Tooltip_ability_{k}"))
        )

        abilities = []
        for ab_key in list(ability_keys) + innate_keys:
            # Some ability entries are nested lists (alternate forms); skip them
            if not isinstance(ab_key, str):
                continue
            ab_data = abilities_raw.get(ab_key, {})
            if not ab_data:
                continue
            # Ability Chinese name: "DOTA_Tooltip_ability_<key>"
            ab_cn_name = loc.get(f"DOTA_Tooltip_ability_{ab_key}") or ab_data.get("dname", ab_key)
            # Ability description: "DOTA_Tooltip_ability_<key>_Description"
            ab_desc = loc.get(f"DOTA_Tooltip_ability_{ab_key}_Description") or ab_data.get("desc", "")

            # Cooldown and mana cost may be a list (per-level) or a single value
            cd_raw = ab_data.get("cd")
            mc_raw = ab_data.get("mc")
            cooldown = (
                "/".join(str(x) for x in cd_raw) if isinstance(cd_raw, list)
                else str(cd_raw) if cd_raw is not None
                else "0"
            )
            manacost = (
                "/".join(str(x) for x in mc_raw) if isinstance(mc_raw, list)
                else str(mc_raw) if mc_raw is not None
                else "0"
            )

            # Build attrib lookup: {key: value_string}
            attrib = {}
            for a in ab_data.get("attrib", []):
                ak = a.get("key", "")
                av = a.get("value")
                if ak and av is not None:
                    attrib[ak] = "/".join(str(x) for x in av) if isinstance(av, list) else str(av)

            # Special flags
            is_innate = bool(ab_data.get("is_innate"))
            has_scepter = bool(
                loc.get(f"DOTA_Tooltip_ability_{ab_key}_scepter_Description")
                or loc.get(f"DOTA_Tooltip_ability_{ab_key}_scepter_description")
            )
            has_shard = bool(
                loc.get(f"DOTA_Tooltip_ability_{ab_key}_shard_Description")
                or loc.get(f"DOTA_Tooltip_ability_{ab_key}_shard_description")
            )

            abilities.append({
                "key": ab_key,
                "name": ab_cn_name,
                "description": ab_desc,
                "cooldown": cooldown,
                "manacost": manacost,
                "attrib": attrib,
                "is_innate": is_innate,
                "has_scepter": has_scepter,
                "has_shard": has_shard,
            })

        img_path = hero.get("img", "")
        icon_path = hero.get("icon", "")
        cdn = "https://cdn.cloudflare.steamstatic.com"
        img = (cdn + img_path.split("?")[0]) if img_path else ""
        icon = (cdn + icon_path.split("?")[0]) if icon_path else ""

        result[npc_name] = {
            "id": hero.get("id"),
            "name": cn_name,
            "name_en": en_name,
            "primary_attr": hero.get("primary_attr", ""),
            "attack_type": hero.get("attack_type", ""),
            "roles": hero.get("roles", []),
            "img": img,
            "icon": icon,
            "abilities": abilities,
        }

    return result


def merge_items() -> dict:
    """
    Return a dict keyed by "item_<name>" (e.g. "item_blink") with the
    merged item data.
    """
    items_raw = json.loads((RAW / "items_raw.json").read_text())

    # abilities_schinese.txt also carries item name tokens
    loc = _load_kv_tokens(RAW / "abilities_schinese.txt")

    result: dict = {}

    for raw_key, item in items_raw.items():
        if not isinstance(item, dict) or not item:
            continue

        item_key = f"item_{raw_key}"

        # Chinese name: "DOTA_Tooltip_Ability_item_<raw_key>"  (capital A in Ability)
        # or lowercase variant: "DOTA_Tooltip_ability_item_<raw_key>"
        cn_name = (
            loc.get(f"DOTA_Tooltip_Ability_{item_key}")
            or loc.get(f"DOTA_Tooltip_ability_{item_key}")
            or item.get("dname", raw_key)
        )
        en_name = item.get("dname", raw_key)

        # Description (lowercase 'ability' variant used for most items)
        description = (
            loc.get(f"DOTA_Tooltip_ability_{item_key}_Description")
            or loc.get(f"DOTA_Tooltip_Ability_{item_key}_Description")
            or item.get("lore", "")
        )

        img_path = item.get("img", "")
        cdn = "https://cdn.cloudflare.steamstatic.com"
        img = (cdn + img_path.split("?")[0]) if img_path else ""

        result[item_key] = {
            "id": item.get("id"),
            "name": cn_name,
            "name_en": en_name,
            "cost": item.get("cost"),
            "description": description,
            "img": img,
        }

    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def build_meta() -> dict:
    patch_file = RAW / "patch.json"
    if patch_file.exists():
        patches = json.loads(patch_file.read_text())
        latest = patches[-1]
        return {"patch": latest["name"], "patch_date": latest["date"]}
    return {}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    heroes = merge_heroes()
    (OUT / "heroes.json").write_text(
        json.dumps(heroes, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Written {len(heroes)} heroes → {OUT / 'heroes.json'}")

    items = merge_items()
    (OUT / "items.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Written {len(items)} items → {OUT / 'items.json'}")

    meta = build_meta()
    (OUT / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Written meta → patch {meta.get('patch', 'unknown')}")


if __name__ == "__main__":
    main()
