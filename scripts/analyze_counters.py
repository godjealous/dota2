"""
Analyze hero counter relationships using Claude API.
Generates data/counters.json with counter info for each hero.
"""
import json
import os
import sys
import time
from pathlib import Path

import anthropic

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data" / "output"
COUNTERS_FILE = ROOT / "data" / "counters.json"


def build_hero_summary(hero: dict) -> str:
    lines = [
        f"英雄名: {hero['name']} ({hero['name_en']})",
        f"定位: {', '.join(hero.get('roles', []))}",
        f"攻击类型: {hero.get('attack_type', '')}",
        f"主属性: {hero.get('primary_attr', '')}",
        "技能:",
    ]
    for ab in hero.get("abilities", []):
        if ab.get("key", "").startswith("special_bonus"):
            continue
        name = ab.get("name", "")
        desc = ab.get("description", "").replace("<b>", "").replace("</b>", "").replace("<br>", " ")
        # Strip HTML tags
        import re
        desc = re.sub(r"<[^>]+>", "", desc)
        desc = desc[:120]
        scepter = ab.get("scepter_desc", "")
        shard = ab.get("shard_desc", "")
        line = f"  - {name}: {desc}"
        if scepter:
            line += f" [神杖: {scepter[:60]}]"
        if shard:
            line += f" [魔晶: {shard[:60]}]"
        lines.append(line)

    talents = hero.get("talents", [])
    if talents:
        lines.append("天赋(关键项):")
        for t in talents:
            lvl = t.get("game_level", "")
            left = (t.get("left") or {}).get("name", "")
            right = (t.get("right") or {}).get("name", "")
            lines.append(f"  Lv{lvl}: {left} | {right}")

    return "\n".join(lines)


def build_all_heroes_index(heroes: dict) -> str:
    """Build a compact list of all heroes for the model to reference."""
    lines = []
    for key, h in heroes.items():
        short_key = key.replace("npc_dota_hero_", "")
        roles = "/".join(h.get("roles", []))
        lines.append(f"{h['name']}({h['name_en']}) [{short_key}] - {roles}")
    return "\n".join(lines)


SYSTEM_PROMPT = """你是一位 Dota 2 专业分析师，精通英雄克制关系。
分析时请参考英雄的技能机制、定位特点，并结合职业赛事和高分段玩家的实际对局数据。
你的分析必须基于技能机制，给出具体、准确、有说服力的理由。"""

COUNTER_PROMPT_TEMPLATE = """以下是所有英雄的列表，供参考：
{all_heroes}

---
现在分析以下英雄的克制关系：

{hero_summary}

---
请输出 JSON 格式，分析克制该英雄的其他英雄。要求：
1. 列出 5-8 个最能克制该英雄的英雄
2. 每个克制英雄给出 2-4 句具体理由（说明用哪个技能/特点克制了目标英雄的什么弱点）
3. 给出每个克制关系的强度评级：strong（强力克制）/ moderate（一定程度克制）

输出格式（纯 JSON，不要 markdown 代码块）：
{{
  "hero_key": "{hero_key}",
  "hero_name": "{hero_name}",
  "countered_by": [
    {{
      "key": "英雄key（如 axe）",
      "name": "英雄中文名",
      "strength": "strong 或 moderate",
      "reasons": [
        "理由1：具体技能名 + 克制机制说明",
        "理由2：...",
        "理由3（可选）..."
      ]
    }}
  ]
}}"""


def analyze_hero(client: anthropic.Anthropic, hero_key: str, hero: dict, all_heroes_index: str) -> dict:
    short_key = hero_key.replace("npc_dota_hero_", "")
    hero_summary = build_hero_summary(hero)
    prompt = COUNTER_PROMPT_TEMPLATE.format(
        all_heroes=all_heroes_index,
        hero_summary=hero_summary,
        hero_key=short_key,
        hero_name=hero["name"],
    )

    response = client.messages.create(
        model=os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "claude-sonnet-4-5"),
        max_tokens=3000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    # Remove markdown code fences if present
    if "```" in text:
        import re
        match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
        if match:
            text = match.group(1).strip()
    # Extract the first complete JSON object, ignoring any trailing text
    import re
    if not text.startswith("{"):
        match = re.search(r"\{[\s\S]+\}", text)
        if match:
            text = match.group(0)
    # Use a brace-counter to extract only the first balanced JSON object
    depth, start = 0, None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                text = text[start:i + 1]
                break
    return json.loads(text)


def main():
    heroes = json.loads((DATA_DIR / "heroes.json").read_text(encoding="utf-8"))
    all_heroes_index = build_all_heroes_index(heroes)

    # Load existing counters if any
    existing = {}
    if COUNTERS_FILE.exists():
        existing = json.loads(COUNTERS_FILE.read_text(encoding="utf-8"))

    # Determine which heroes to analyze
    if len(sys.argv) > 1:
        targets = sys.argv[1:]  # e.g. "antimage axe crystal_maiden"
        keys = [f"npc_dota_hero_{t}" if not t.startswith("npc_") else t for t in targets]
    else:
        keys = list(heroes.keys())

    client = anthropic.Anthropic(
        base_url=os.environ.get("ANTHROPIC_BASE_URL"),
        auth_token=os.environ.get("ANTHROPIC_AUTH_TOKEN"),
    )

    results = dict(existing)
    total = len(keys)

    for i, key in enumerate(keys, 1):
        short_key = key.replace("npc_dota_hero_", "")
        if short_key in results:
            print(f"[{i}/{total}] Skip {short_key} (already analyzed)")
            continue

        hero = heroes.get(key)
        if not hero:
            print(f"[{i}/{total}] Hero not found: {key}")
            continue

        print(f"[{i}/{total}] Analyzing {hero['name']} ({short_key})...", end=" ", flush=True)
        try:
            data = analyze_hero(client, key, hero, all_heroes_index)
            results[short_key] = data
            # Save after each hero to preserve progress
            COUNTERS_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            print("OK")
        except Exception as e:
            print(f"ERROR: {e}")

        if i < total:
            time.sleep(0.5)

    print(f"\nDone. Saved to {COUNTERS_FILE}")
    print(f"Total heroes analyzed: {len(results)}")


if __name__ == "__main__":
    main()
