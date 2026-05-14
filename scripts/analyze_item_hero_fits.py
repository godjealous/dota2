"""
Analyze which heroes benefit most from each item (good fit / recommended carriers).
Output: data/item_hero_fits.json  {item_key: [{hero: "short_key", reason: "..."}]}
"""
import json
import os
import re
from pathlib import Path
import anthropic

_ROOT = Path(__file__).parent.parent
OUT_FILE = _ROOT / "data/item_hero_fits.json"


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

    items = {
        k: v for k, v in items_data.items()
        if (v.get("description") or v.get("bonuses"))
        and not k.startswith("item_recipe")
        and v.get("name") and v.get("cost")
    }
    print(f"Analyzing {len(items)} items, {len(heroes_data)} heroes...")

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

        prompt = f"""你是Dota2专家，请分析以下物品最适合哪些英雄出装（即英雄从该物品中获益最大）。

适合标准：该物品的属性加成或主动/被动效果能显著增强该英雄的核心打法、关键技能或核心定位。
例：
- 闪烁匕首适合需要精准切入的英雄（斧王、撼地神牛等）
- 魔杖适合魔法值紧张的前期英雄
- 圣剑适合物理核心Carry
- BKB适合需要在团战中稳定输出的近战核心

所有英雄（key | 名称 | 定位 | 核心技能）：
{hero_summary}

所有物品参考（key | 名称 | 加成 | 效果）：
{item_summary}

需要分析的物品：
{target_list}

每个物品输出最多5个最适合出装的英雄，只选契合度最高的。
辅助类物品（奶酪、观察守卫等）适合所有英雄，则给空数组。
功能性消耗品给空数组。

英雄key使用短格式（不含npc_dota_hero_前缀），如 antimage, axe 等。
reason简洁，12字以内，说明为什么适合，不含引号逗号。

严格JSON输出（不含markdown）：
{{
  "item_xxx": [
    {{"hero": "axe", "reason": "跳刀切入配合战吼"}},
    {{"hero": "sand_king", "reason": "跳刀开团地震波"}},
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
