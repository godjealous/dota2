"""
Analyze which heroes are countered by each item, using Claude API.
Output: data/item_hero_counters.json  {item_key: [{hero: "short_key", reason: "..."}]}
"""
import json
import os
import re
from pathlib import Path
import anthropic

_ROOT = Path(__file__).parent.parent
OUT_FILE = _ROOT / "data/item_hero_counters.json"


def build_hero_summary(heroes: dict) -> str:
    lines = []
    for key, h in heroes.items():
        short = key.replace("npc_dota_hero_", "")
        name = h.get("name", short)
        roles = "/".join(h.get("roles", [])[:3])
        abilities = ", ".join(a["name"] for a in h.get("abilities", [])[:4])
        lines.append(f"[{short}]{name} | {roles} | {abilities}")
    return "\n".join(lines)


def build_item_summary(items: dict) -> str:
    lines = []
    for key, v in items.items():
        name = v.get("name", key)
        bonuses = ", ".join(
            f"{b['sign']}{b['value']}{'%' if b['pct'] else ''}{b['label']}"
            for b in v.get("bonuses", [])
        )
        desc_raw = v.get("description", "")
        desc = re.sub(r"<[^>]+>", "", desc_raw)
        desc = re.sub(r"%[A-Za-z0-9_]+%{0,2}", "N", desc)
        desc = desc.replace("\\n", " ").replace("\n", " ").strip()[:100]
        parts = [f"[{key}]{name}"]
        if bonuses:
            parts.append(f"加成:{bonuses}")
        if desc:
            parts.append(f"效果:{desc}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def main():
    items_data = json.loads((_ROOT / "data/output/items.json").read_text())
    heroes_data = json.loads((_ROOT / "data/output/heroes.json").read_text())

    # Only meaningful items
    items = {
        k: v for k, v in items_data.items()
        if (v.get("description") or v.get("bonuses"))
        and not k.startswith("item_recipe")
        and v.get("name") and v.get("cost")
    }
    print(f"Analyzing {len(items)} items vs {len(heroes_data)} heroes...")

    # Load existing results
    existing: dict = {}
    if OUT_FILE.exists():
        existing = json.loads(OUT_FILE.read_text(encoding="utf-8"))
    print(f"Already done: {len(existing)}")

    to_analyze = {k: v for k, v in items.items() if k not in existing}
    print(f"To analyze: {len(to_analyze)}")
    if not to_analyze:
        print("Nothing to do.")
        return

    api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY", "")
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    model = os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "claude-sonnet-4-6")
    client = anthropic.Anthropic(api_key=api_key, base_url=base_url)

    hero_summary = build_hero_summary(heroes_data)
    item_summary = build_item_summary(items)

    batch_size = 15
    keys = list(to_analyze.keys())
    results = dict(existing)

    for batch_start in range(0, len(keys), batch_size):
        batch_keys = keys[batch_start:batch_start + batch_size]
        batch_names = [(k, items[k]["name"]) for k in batch_keys]
        print(f"Batch {batch_start//batch_size + 1}: {[n for _, n in batch_names[:5]]}...")

        target_list = "\n".join(f"- {key} ({name})" for key, name in batch_names)

        prompt = f"""你是Dota2专家，请分析以下物品能克制哪些英雄。

克制定义：该物品的主动/被动效果能直接压制或削弱该英雄的核心玩法/关键技能/核心属性。
例：
- 金箍棒穿刺克制蝴蝶（无视闪避），克制所有依赖闪避的英雄
- 驱散类物品克制依赖持续性buff增益的英雄（如冰女大招）
- 真实视野克制隐身核心英雄（蛮王、赏金猎人等）
- 沉默道具克制法力依赖型英雄
- BKB克制全程依赖法术技能压制的英雄

所有英雄（key | 名称 | 定位 | 核心技能）：
{hero_summary}

所有物品参考（key | 名称 | 加成 | 效果）：
{item_summary}

需要分析的物品：
{target_list}

每个物品输出最多5个被该物品克制的英雄，只选择克制关系明显且重要的。
如果物品对英雄没有明显克制关系，给空数组。

英雄key使用短格式（不含npc_dota_hero_前缀），如 antimage, axe 等。
reason简洁，10字以内，不含引号逗号。

严格JSON输出（不含markdown）：
{{
  "item_xxx": [
    {{"hero": "antimage", "reason": "穿刺无视闪避"}},
    {{"hero": "axe", "reason": "沉默限制技能"}}
  ]
}}

只输出JSON。"""

        message = client.messages.create(
            model=model,
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )

        response = message.content[0].text.strip()
        m = re.search(r'\{[\s\S]+\}', response)
        if not m:
            print(f"  Warning: could not parse JSON for batch {batch_start//batch_size + 1}")
            for k in batch_keys:
                results.setdefault(k, [])
            OUT_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            continue

        try:
            batch_result = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            print(f"  Warning: JSON parse error: {e}")
            for k in batch_keys:
                results.setdefault(k, [])
            OUT_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            continue

        valid_hero_keys = {k.replace("npc_dota_hero_", "") for k in heroes_data}

        for item_key, hero_list in batch_result.items():
            if isinstance(hero_list, list):
                parsed = []
                for entry in hero_list:
                    if isinstance(entry, dict):
                        hkey = entry.get("hero", "")
                        if hkey in valid_hero_keys:
                            parsed.append({"hero": hkey, "reason": entry.get("reason", "")})
                results[item_key] = parsed
            else:
                results[item_key] = []

        OUT_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  Saved {len(results)} total")

    print(f"Done. {len(results)} items → {OUT_FILE}")


if __name__ == "__main__":
    main()
