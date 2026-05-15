"""
Data merge script for Dota2 Wiki pipeline.

Reads raw data files and produces:
  data/output/heroes.json  – keyed by npc name
  data/output/items.json   – keyed by item_<name>
"""

import json
import re
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).parent.parent
RAW = _ROOT / "data/raw"
OUT = _ROOT / "data/output"

NPC_HEROES_URL = "https://raw.githubusercontent.com/dotabuff/d2vpkr/master/dota/scripts/npc/npc_heroes.txt"
NPC_HERO_FILE_URL = "https://raw.githubusercontent.com/dotabuff/d2vpkr/master/dota/scripts/npc/heroes/{hero}.txt"
NPC_ABILITIES_URL = "https://raw.githubusercontent.com/spirit-bear-productions/dota_vpk_updates/main/scripts/npc/npc_abilities.txt"

# Hero nicknames (manually maintained, keyed by short hero name without npc_dota_hero_ prefix)
# Hero nicknames are loaded from data/nicknames.json (manually maintained, not auto-generated)
HERO_NICKNAMES: dict = json.loads((_ROOT / "data/nicknames.json").read_text(encoding="utf-8"))
ITEM_NICKNAMES: dict = json.loads((_ROOT / "data/item_nicknames.json").read_text(encoding="utf-8"))

_SUB_ABILITY_SUFFIXES = (
    "_end", "_release", "_cancel", "_stop", "_throw", "_channel",
    "_toggle", "_return", "_raze1", "_raze2", "_raze3",
    "_morph_str", "_morph_agi", "_morph_replicate", "_jaunt",
)


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
# Grant ability detection (scepter/shard new abilities)
# ---------------------------------------------------------------------------

def _build_grant_sets(abilities_raw: dict, ha_raw: dict, loc: dict):
    """
    Return (scepter_granted, shard_granted, hero_ability_order) where:
      - scepter_granted / shard_granted: sets of ability keys unlocked as new
        abilities by Aghanim's Scepter or Shard respectively.
      - hero_ability_order: dict mapping npc_hero_name -> ordered list of
        ability keys as they appear in Ability1-9 in npc_heroes.txt (the
        authoritative in-game order, including innate abilities).
    """
    try:
        req = urllib.request.Request(
            NPC_HEROES_URL, headers={"User-Agent": "Mozilla/5.0"}
        )
        content = urllib.request.urlopen(req, timeout=15).read().decode("utf-8")
    except Exception as e:
        print(f"  [warn] Could not fetch npc_heroes.txt: {e}. Skipping grant detection.")
        return set(), set(), {}

    def _parse_hero_abilities(block: str):
        # Ordered list from Ability1..Ability99 (outside AbilityDraftAbilities block)
        # Strip the draft block first to avoid double-counting
        draft_match = re.search(r'"AbilityDraftAbilities"\s*\{([^}]+)\}', block, re.DOTALL)
        draft_ab: set = set()
        if draft_match:
            draft_ab = {m.group(1) for m in re.finditer(r'"Ability\d+"\s+"([^"]+)"', draft_match.group(1))}
            block_no_draft = block[:draft_match.start()] + block[draft_match.end():]
        else:
            block_no_draft = block
        ordered = [m.group(2) for m in sorted(
            re.finditer(r'"Ability(\d+)"\s+"([^"]+)"', block_no_draft),
            key=lambda x: int(x.group(1))
        )]
        # Deduplicate while preserving order
        seen: set = set()
        deduped = []
        for k in ordered:
            if k not in seen:
                seen.add(k)
                deduped.append(k)
        return deduped, draft_ab

    hero_pattern = re.compile(r'"(npc_dota_hero_\w+)"\s*\{', re.MULTILINE)
    hero_matches = list(hero_pattern.finditer(content))

    hero_ability_order: dict = {}
    non_draft_map: dict = {}
    for i, m in enumerate(hero_matches):
        hero_name = m.group(1)
        end = hero_matches[i + 1].start() if i + 1 < len(hero_matches) else len(content)
        ordered, draft_ab = _parse_hero_abilities(content[m.start():end])
        hero_ability_order[hero_name] = ordered
        grants: set = set()
        for ab_key in ordered:
            if ab_key in draft_ab:
                continue
            if "generic_hidden" in ab_key or "special_bonus" in ab_key:
                continue
            ab = abilities_raw.get(ab_key, {})
            if ab.get("is_innate"):
                continue
            if any(ab_key.endswith(s) for s in _SUB_ABILITY_SUFFIXES):
                continue
            behavior = ab.get("behavior", "")
            behaviors = behavior if isinstance(behavior, list) else [behavior]
            if "Hidden" in behaviors:
                has_cd = bool(ab.get("cd") and ab.get("cd") != "0")
                has_mc = bool(ab.get("mc") and ab.get("mc") != "0")
                if not has_cd and not has_mc:
                    continue
            has_name = bool(loc.get(f"DOTA_Tooltip_ability_{ab_key}") or ab.get("dname"))
            has_desc = bool(loc.get(f"DOTA_Tooltip_ability_{ab_key}_Description") or ab.get("desc"))
            if has_name and has_desc:
                grants.add(ab_key)
        if grants:
            non_draft_map[hero_name] = grants

    # Distinguish shard-granted by checking if any existing ability's shard_desc
    # contains the new ability's Chinese name.
    shard_granted: set = set()
    for hero_name, grant_abs in non_draft_map.items():
        hero_data = ha_raw.get(hero_name, {})
        existing_keys = [k for k in hero_data.get("abilities", []) if isinstance(k, str)]
        for nd_key in grant_abs:
            nd_cn = loc.get(f"DOTA_Tooltip_ability_{nd_key}", "")
            if not nd_cn:
                continue
            for ab_key in existing_keys:
                shard_desc = (
                    loc.get(f"DOTA_Tooltip_ability_{ab_key}_shard_Description", "")
                    or loc.get(f"DOTA_Tooltip_ability_{ab_key}_shard_description", "")
                )
                if nd_cn in shard_desc:
                    shard_granted.add(nd_key)
                    break

    all_grants: set = set()
    for v in non_draft_map.values():
        all_grants.update(v)
    scepter_granted = all_grants - shard_granted

    print(f"  Grant abilities detected: {len(scepter_granted)} scepter, {len(shard_granted)} shard")
    return scepter_granted, shard_granted, hero_ability_order


# ---------------------------------------------------------------------------
# Talent value extraction
# ---------------------------------------------------------------------------

def _fetch_generic_talent_values() -> dict:
    """
    Parse npc_abilities.txt and return {talent_key: {'value': 'N'}} for all
    generic special_bonus_* abilities (those not hero-specific).
    """
    try:
        req = urllib.request.Request(NPC_ABILITIES_URL, headers={"User-Agent": "Mozilla/5.0"})
        content = urllib.request.urlopen(req, timeout=15).read().decode("utf-8")
    except Exception as e:
        print(f"  [warn] Could not fetch npc_abilities.txt: {e}")
        return {}

    result: dict = {}
    bonus_pat = re.compile(r'"(special_bonus[^"]+)"\s*\n\s*\{', re.MULTILINE)
    for m in bonus_pat.finditer(content):
        key = m.group(1)
        start = m.end()
        depth = 1
        pos = start
        while pos < len(content) and depth > 0:
            c = content[pos]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            pos += 1
        block = content[start:pos]
        v_match = re.search(r'"value"\s*\{\s*"value"\s*"([^"]+)"', block)
        if not v_match:
            v_match = re.search(r'"value"\s+"([^"]+)"', block)
        if v_match:
            result[key] = {"value": v_match.group(1).split()[0]}
    return result


def _fetch_hero_talent_values(hero_npc_name: str) -> dict:
    """
    Fetch the hero's per-ability file and extract talent bonus values.
    Returns {talent_key: {field_name: value_str}}.
    E.g. {'special_bonus_unique_antimage': {'AbilityCooldown': '-1'}, ...}
    """
    url = NPC_HERO_FILE_URL.format(hero=hero_npc_name)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        content = urllib.request.urlopen(req, timeout=10).read().decode("utf-8")
    except Exception:
        return {}

    lines = content.splitlines()
    talent_fields: dict = {}

    for i, line in enumerate(lines):
        m = re.search(r'"(special_bonus_unique_[^"]+)"\s+"([^"]+)"', line)
        if not m:
            continue
        talent_key = m.group(1)
        bonus_val = m.group(2)

        # Walk up to find the enclosing field name (the key before the '{' block)
        field_name = None
        for j in range(i - 1, max(0, i - 10), -1):
            prev = lines[j].strip()
            if prev in ("{", "}", ""):
                continue
            fm = re.match(r'^"([A-Za-z_0-9]+)"\s*(?:\{)?\s*$', prev)
            if fm:
                name = fm.group(1)
                if name not in ("AbilityValues", "AbilitySpecial", "Version", "DOTAAbilities"):
                    field_name = name
                    break

        entry = talent_fields.setdefault(talent_key, {})
        entry[field_name or "value"] = bonus_val

    return talent_fields


def _resolve_talent_name(text: str, fields: dict) -> str:
    """Replace {s:bonus_XXX} placeholders with actual values from fields dict."""
    def replace(m: re.Match) -> str:
        placeholder = m.group(1)  # e.g. "bonus_AbilityCooldown"
        field = placeholder[6:] if placeholder.startswith("bonus_") else placeholder
        for k, v in fields.items():
            if k.lower() == field.lower():
                return v
        return m.group(0)

    result = re.sub(r"\{s:([^}]+)\}", replace, text)
    # Clean up doubled signs produced by combining text prefix + value sign
    result = re.sub(r"\+\+", "+", result)
    result = re.sub(r"--", "-", result)
    result = re.sub(r"\+-", "-", result)
    result = re.sub(r"-\+", "-", result)
    return result


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

    counters_file = _ROOT / "data/counters.json"
    counters_data: dict = json.loads(counters_file.read_text(encoding="utf-8")) if counters_file.exists() else {}

    synergies_file = _ROOT / "data/synergies.json"
    synergies_data: dict = json.loads(synergies_file.read_text(encoding="utf-8")) if synergies_file.exists() else {}

    # abilities_schinese.txt carries BOTH hero names and ability names
    loc = _load_kv_tokens(RAW / "abilities_schinese.txt")
    # dota_schinese.txt carries hype/bio texts
    dota_loc = _load_kv_tokens(RAW / "dota_schinese.txt")

    # Generic talent values (fallback for non-hero-specific talents like special_bonus_hp_regen_3)
    print("Fetching generic talent values...")
    _generic_talent_vals = _fetch_generic_talent_values()
    print(f"  Generic talent values: {len(_generic_talent_vals)}")

    # Detect abilities granted as new skills by scepter/shard; also get
    # the authoritative in-game ability order from npc_heroes.txt.
    print("Detecting grant abilities...")
    _grant_scepter, _grant_shard, _hero_order = _build_grant_sets(abilities_raw, hero_abilities_raw, loc)

    result: dict = {}

    for _numeric_id, hero in heroes_raw.items():
        npc_name: str = hero.get("name", "")
        if not npc_name.startswith("npc_dota_hero_"):
            continue

        # Chinese / English hero names
        # Token keys: "npc_dota_hero_antimage:n" and "npc_dota_hero_antimage__en:n"
        cn_name = loc.get(f"{npc_name}:n") or hero.get("localized_name", npc_name)
        en_name = loc.get(f"{npc_name}__en:n") or hero.get("localized_name", npc_name)

        # Hero hype / bio (short description shown in hero selection)
        short_name = npc_name.replace("npc_dota_hero_", "")
        hype = dota_loc.get(f"{npc_name}_hype", "")
        nickname = HERO_NICKNAMES.get(short_name, {}).get("nicknames", [])

        # Alternate persona name (e.g. Anti-Mage (Wei))
        persona_cn = loc.get(f"{npc_name}_persona1:n", "")
        persona_en = loc.get(f"{npc_name}_persona1__en:n", "")

        # Use the ordered ability list from npc_heroes.txt when available (it
        # includes innates in their correct in-game position).  Fall back to
        # hero_abilities_raw order if npc_heroes.txt had no entry for this hero.
        npc_ordered = _hero_order.get(npc_name)
        if npc_ordered:
            # npc_heroes.txt only lists base-slot abilities (Ability1-9).
            # hero_abilities_raw may have extra keys (e.g. alternate-form lists)
            # not in npc_heroes.txt — append those at the end so nothing is lost.
            npc_ordered_set = set(npc_ordered)
            ha_keys = [k for k in hero_abilities_raw.get(npc_name, {}).get("abilities", [])
                       if isinstance(k, str) and k not in npc_ordered_set]
            ability_keys = npc_ordered + ha_keys
        else:
            ability_keys = hero_abilities_raw.get(npc_name, {}).get("abilities", [])
            # Append innate abilities that are missing from the list
            hero_prefix = npc_name.replace("npc_dota_hero_", "")
            existing_keys = {k for k in ability_keys if isinstance(k, str)}
            innate_keys = sorted(
                k for k, v in abilities_raw.items()
                if v.get("is_innate")
                and k.startswith(hero_prefix + "_")
                and k not in existing_keys
                and (v.get("dname") or loc.get(f"DOTA_Tooltip_ability_{k}"))
            )
            ability_keys = list(ability_keys) + innate_keys

        abilities = []
        for ab_key in ability_keys:
            # Skip nested lists (alternate forms), hidden placeholders, and talents
            if not isinstance(ab_key, str):
                continue
            if "generic_hidden" in ab_key or "special_bonus" in ab_key:
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
            scepter_desc = (
                loc.get(f"DOTA_Tooltip_ability_{ab_key}_scepter_Description")
                or loc.get(f"DOTA_Tooltip_ability_{ab_key}_scepter_description")
                or ""
            )
            shard_desc = (
                loc.get(f"DOTA_Tooltip_ability_{ab_key}_shard_Description")
                or loc.get(f"DOTA_Tooltip_ability_{ab_key}_shard_description")
                or ""
            )
            has_scepter = bool(scepter_desc)
            has_shard = bool(shard_desc)

            grant_scepter = ab_key in _grant_scepter
            grant_shard = ab_key in _grant_shard

            abilities.append({
                "key": ab_key,
                "name": ab_cn_name,
                "description": ab_desc,
                "cooldown": cooldown,
                "manacost": manacost,
                "attrib": attrib,
                "is_innate": is_innate,
                "has_scepter": has_scepter,
                "scepter_desc": scepter_desc,
                "has_shard": has_shard,
                "shard_desc": shard_desc,
                "grant_scepter": grant_scepter,
                "grant_shard": grant_shard,
            })

        img_path = hero.get("img", "")
        icon_path = hero.get("icon", "")
        cdn = "https://cdn.cloudflare.steamstatic.com"
        img = (cdn + img_path.split("?")[0]) if img_path else ""
        icon = (cdn + icon_path.split("?")[0]) if icon_path else ""

        # Build talents: 8 entries grouped into 4 levels (1-4), each level has left+right
        # level 1 = game level 10, level 2 = 15, level 3 = 20, level 4 = 25
        TALENT_LEVELS = {1: 10, 2: 15, 3: 20, 4: 25}
        raw_talents = hero_abilities_raw.get(npc_name, {}).get("talents", [])

        # Fetch per-hero talent bonus values to substitute {s:...} placeholders
        hero_talent_vals = _fetch_hero_talent_values(npc_name)

        talent_by_level: dict = {}
        for t in raw_talents:
            lv = t.get("level")
            t_key = t.get("name", "")
            if not lv or not t_key:
                continue
            t_data = abilities_raw.get(t_key, {})
            t_cn_raw = loc.get(f"DOTA_Tooltip_ability_{t_key}") or t_data.get("dname", t_key)
            fields = {**_generic_talent_vals.get(t_key, {}), **hero_talent_vals.get(t_key, {})}
            t_cn = _resolve_talent_name(t_cn_raw, fields)
            talent_by_level.setdefault(lv, []).append({"key": t_key, "name": t_cn})

        talents = []
        for lv in sorted(talent_by_level.keys()):
            pair = talent_by_level[lv]
            talents.append({
                "level": lv,
                "game_level": TALENT_LEVELS.get(lv, lv * 5 + 5),
                "left": pair[0] if len(pair) > 0 else None,
                "right": pair[1] if len(pair) > 1 else None,
            })

        result[npc_name] = {
            "id": hero.get("id"),
            "name": cn_name,
            "name_en": en_name,
            "nickname": nickname,
            "persona_cn": persona_cn,
            "persona_en": persona_en,
            "hype": hype,
            "primary_attr": hero.get("primary_attr", ""),
            "attack_type": hero.get("attack_type", ""),
            "roles": hero.get("roles", []),
            "move_speed": hero.get("move_speed"),
            "attack_range": hero.get("attack_range"),
            "img": img,
            "icon": icon,
            "abilities": abilities,
            "talents": talents,
            "countered_by": counters_data.get(short_name, {}).get("countered_by", []),
            "synergies": synergies_data.get(short_name, {}).get("synergies", []),
        }

    return result


_ATTRIB_DISPLAY_CN = {
    # Stats
    "Strength": "力量",
    "Agility": "敏捷",
    "Intelligence": "智力",
    "All Attributes": "全属性",
    "Primary Attribute": "主属性",
    "Selected Attribute": "选择属性",
    # Offense
    "Damage": "攻击力",
    "Damage (MELEE)": "攻击力（近战）",
    "Damage (RANGED)": "攻击力（远程）",
    "Attack Speed": "攻击速度",
    "Attack Range (Melee & Ranged)": "攻击距离",
    "Attack Range (Melee Only)": "攻击距离（近战）",
    "Attack Range (Ranged Only)": "攻击距离（远程）",
    "Magic Attack Damage": "魔法攻击伤害",
    "Magic Damage Attack": "魔法攻击伤害",
    # Defense
    "Armor": "护甲",
    "Magic Resistance": "魔法抗性",
    "Evasion": "闪避",
    "Status Resistance": "状态抗性",
    "Slow Resistance": "减速抗性",
    "Knockback Resistance": "击退抗性",
    # Mobility
    "Movement Speed": "移动速度",
    "Move Speed (Melee Heroes)": "移动速度（近战）",
    "Move Speed (Ranged Heroes)": "移动速度（远程）",
    # HP / MP
    "Health": "生命值",
    "Max Health Increase": "最大生命值",
    "Health Regeneration": "生命回复",
    "Mana": "魔法值",
    "Max Mana": "最大魔法值",
    "Mana Regeneration": "魔法回复",
    "Mana Cost/Mana Loss Reduction": "魔法消耗降低",
    "Mana Cost/Mana Loss Increase": "魔法消耗增加",
    "Manacost Reduction": "魔法消耗降低",
    # Spells
    "Spell Amplification": "法术强度",
    "Spell Lifesteal": "法术偷生",
    "Cooldown Reduction": "技能冷却缩减",
    "Cast Range": "施法距离",
    "Cast Speed Bonus": "施法速度",
    # Lifesteal / Regen amp
    "Lifesteal": "生命偷取",
    "Heal Amplification": "治疗强化",
    "Health Regen and Lifesteal Amp": "生命回复及偷取强化",
    "Mana Regen Amplification": "魔法回复强化",
    "Health Restoration": "生命恢复",
    # Vision
    "Bonus Vision": "视野范围",
    "Bonus Night Vision": "夜间视野",
    "Night Vision": "夜间视野",
    # Misc
    "GPM BONUS": "金币/分钟",
    "Base Attack Damage": "基础攻击力",
    "Base Attack Speed Percentage": "基础攻击速度",
    "Base Attack Time": "基础攻击时间",
    "Debuff Duration": "减益持续时间",
    "Incoming Damage": "受到伤害",
    "Model Scale": "模型大小",
    "Projectile Speed": "弹道速度",
    "Area of Effect": "影响范围",
    "Artifact Potency": "神器效能",
    "Attack Projectile Speed": "攻击弹道速度",
    "Attack Animation Speed": "攻击动画速度",
    "Max Health Regen": "最大生命值回复",
    "Max Mana": "最大魔法值",
}


def _translate_display(display: str) -> str:
    """Convert English attrib display string to Chinese."""
    # Strip leading/trailing spaces
    s = display.strip()
    # Determine prefix (+/-) and whether it's a percentage
    is_pct = "%" in s and "{value}%" not in s
    s_clean = s
    for pref in ("+ ", "- ", "+", "-"):
        if s_clean.startswith(pref):
            s_clean = s_clean[len(pref):]
            break
    # Remove {value}, {value}%, % markers to get the label
    for token in ("{value}%", "{value}", "%"):
        s_clean = s_clean.replace(token, "").strip()
    # Normalize ALL CAPS labels
    s_norm = s_clean.title() if s_clean.isupper() else s_clean
    cn = _ATTRIB_DISPLAY_CN.get(s_norm) or _ATTRIB_DISPLAY_CN.get(s_clean)
    return cn or s_clean


def merge_items() -> dict:
    """
    Return a dict keyed by "item_<name>" (e.g. "item_blink") with the
    merged item data.
    """
    items_raw = json.loads((RAW / "items_raw.json").read_text())

    # abilities_schinese.txt also carries item name tokens
    loc = _load_kv_tokens(RAW / "abilities_schinese.txt")

    # Chinese lore translations (pre-translated via translate_lore.py)
    lore_cn_file = _ROOT / "data/lore_cn.json"
    lore_cn: dict = json.loads(lore_cn_file.read_text(encoding="utf-8")) if lore_cn_file.exists() else {}

    # Item counter relationships (pre-analyzed via analyze_item_counters.py)
    item_counters_file = _ROOT / "data/item_counters.json"
    item_counters: dict = json.loads(item_counters_file.read_text(encoding="utf-8")) if item_counters_file.exists() else {}

    # Item vs hero counter relationships (pre-analyzed via analyze_item_hero_counters.py)
    item_hero_counters_file = _ROOT / "data/item_hero_counters.json"
    item_hero_counters: dict = json.loads(item_hero_counters_file.read_text(encoding="utf-8")) if item_hero_counters_file.exists() else {}

    # Item good-for-hero fits (pre-analyzed via analyze_item_hero_fits.py)
    item_hero_fits_file = _ROOT / "data/item_hero_fits.json"
    item_hero_fits: dict = json.loads(item_hero_fits_file.read_text(encoding="utf-8")) if item_hero_fits_file.exists() else {}

    # Neutral item tiers (fetched from Dota2 datafeed via fetch.py)
    neutral_tiers_file = RAW / "neutral_tiers.json"
    neutral_tiers: dict = json.loads(neutral_tiers_file.read_text(encoding="utf-8")) if neutral_tiers_file.exists() else {}

    cdn = "https://cdn.cloudflare.steamstatic.com"

    def loc_get(key: str) -> str:
        return loc.get(f"DOTA_Tooltip_Ability_{key}") or loc.get(f"DOTA_Tooltip_ability_{key}") or ""

    result: dict = {}

    for raw_key, item in items_raw.items():
        if not isinstance(item, dict) or not item:
            continue

        item_key = f"item_{raw_key}"

        # Neutral items may carry a ":n" suffix in the localization key
        cn_name = (
            loc_get(f"{item_key}:n")
            or loc_get(item_key)
            or item.get("dname", raw_key)
        )
        en_name = item.get("dname", raw_key)

        description = (
            loc.get(f"DOTA_Tooltip_ability_{item_key}_Description")
            or loc.get(f"DOTA_Tooltip_Ability_{item_key}_Description")
            or ""
        )

        # Lore: English original + Chinese translation (for items without ability description)
        lore_en = item.get("lore", "").strip() if not description else ""
        lore_zh = lore_cn.get(item_key, "") if lore_en else ""

        img_path = item.get("img", "")
        img = (cdn + img_path.split("?")[0]) if img_path else ""

        # Build attrib lookup: {key: value_string}
        attrib = {}
        # Build bonus list: [{label, value, is_pct}] for display in UI
        bonuses = []
        for a in item.get("attrib", []):
            ak = a.get("key", "")
            av = a.get("value")
            if ak and av is not None:
                val_str = "/".join(str(x) for x in av) if isinstance(av, list) else str(av)
                attrib[ak] = val_str
                display = a.get("display", "")
                if display and "{value}" in display:
                    label = _translate_display(display)
                    is_pct = "{value}%" in display or ("%" in display and display.index("%") < display.index("{value}") if "%" in display and "{value}" in display else False)
                    sign = "-" if display.strip().startswith("-") else "+"
                    bonuses.append({"label": label, "value": val_str, "sign": sign, "pct": is_pct})

        # Cooldown and mana cost
        cd_raw = item.get("cd")
        mc_raw = item.get("mc")
        cooldown = (
            "/".join(str(x) for x in cd_raw) if isinstance(cd_raw, list)
            else str(cd_raw) if cd_raw is not None else None
        )
        manacost = (
            "/".join(str(x) for x in mc_raw) if isinstance(mc_raw, list)
            else str(mc_raw) if mc_raw is not None else None
        )

        qual = item.get("qual")
        cost = item.get("cost")
        neutral_tier = neutral_tiers.get(item_key, -1)
        is_neutral = neutral_tier >= 0

        result[item_key] = {
            "id": item.get("id"),
            "name": cn_name,
            "name_en": en_name,
            "nickname": ITEM_NICKNAMES.get(raw_key, {}).get("nicknames", []),
            "cost": cost,
            "qual": qual,
            "is_neutral": is_neutral,
            "neutral_tier": neutral_tier if is_neutral else None,  # 0–4 = 一级–五级
            "description": description,
            "lore_en": lore_en,
            "lore_zh": lore_zh,
            "attrib": attrib,
            "bonuses": bonuses,
            "counters_of": item_counters.get(item_key, {}).get("counters_of", []),
            "counters": item_counters.get(item_key, {}).get("counters", []),
            "hero_counters": item_hero_counters.get(item_key, []),
            "hero_fits": item_hero_fits.get(item_key, []),
            "cooldown": cooldown,
            "manacost": manacost,
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
