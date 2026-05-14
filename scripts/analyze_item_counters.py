"""
Analyze item counter relationships using Claude API.
For each item, find up to 3 items that counter it.
Output: data/item_counters.json  {item_key: [counter_item_key, ...]}
"""
import json
import os
import re
from pathlib import Path
import anthropic

_ROOT = Path(__file__).parent.parent
OUT_FILE = _ROOT / "data/item_counters.json"


def build_item_summary(items: dict) -> str:
    """Build a compact summary of all items for the prompt."""
    lines = []
    for key, v in items.items():
        name = v.get("name", key)
        bonuses = ", ".join(
            f"{b['sign']}{b['value']}{'%' if b['pct'] else ''}{b['label']}"
            for b in v.get("bonuses", [])
        )
        # Strip HTML tags from description
        desc_raw = v.get("description", "")
        desc = re.sub(r"<[^>]+>", "", desc_raw)
        desc = re.sub(r"%[A-Za-z0-9_]+%{0,2}", "N", desc)
        desc = desc.replace("\\n", " ").replace("\n", " ").strip()[:120]
        parts = [f"[{key}]{name}"]
        if bonuses:
            parts.append(f"加成:{bonuses}")
        if desc:
            parts.append(f"效果:{desc}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def main():
    items_data = json.loads((_ROOT / "data/output/items.json").read_text())

    # Only analyze meaningful items (have description or bonuses, no recipes)
    items = {
        k: v for k, v in items_data.items()
        if (v.get("description") or v.get("bonuses"))
        and not k.startswith("item_recipe")
        and v.get("name") and v.get("cost")
    }
    print(f"Analyzing {len(items)} items...")

    # Load existing results (resume-safe)
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

    item_summary = build_item_summary(items)

    # Process in batches of 15 to stay within token limits
    batch_size = 15
    keys = list(to_analyze.keys())
    results = dict(existing)

    for batch_start in range(0, len(keys), batch_size):
        batch_keys = keys[batch_start:batch_start + batch_size]
        batch_names = [(k, items[k]["name"]) for k in batch_keys]
        print(f"Batch {batch_start//batch_size + 1}: {[n for _, n in batch_names[:5]]}...")

        target_list = "\n".join(f"- {key} ({name})" for key, name in batch_names)

        prompt = f"""你是Dota2专家，请分析以下目标物品的克制关系，同时给出两个方向：
1. counters_of: 哪些物品克制目标物品（最多3个）
2. counters: 目标物品克制哪些物品（最多3个）

所有可用物品（key | 名称 | 属性 | 效果）：
{item_summary}

需要分析的目标物品：
{target_list}

克制定义：X克制Y = X的效果能削弱/压制/绕过Y的核心功能。
例：金箍棒穿刺克制蝴蝶闪避；驱散类克制依赖buff的物品；真实视野克制隐身物品

每条包含counter(物品key)和reason(中文，10字以内，不含引号逗号)。
无明显克制关系则给空数组。

严格JSON输出（不含markdown）：
{{
  "item_xxx": {{
    "counters_of": [{{"counter": "item_aaa", "reason": "克制我的原因"}}],
    "counters": [{{"counter": "item_bbb", "reason": "我克制它的原因"}}]
  }}
}}

只输出JSON。"""

        message = client.messages.create(
            model=model,
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )

        response = message.content[0].text.strip()
        # Extract JSON from response
        m = re.search(r'\{[\s\S]+\}', response)
        if not m:
            print(f"  Warning: could not parse JSON for batch {batch_start//batch_size + 1}")
            continue

        try:
            batch_result = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            print(f"  Warning: JSON parse error in batch {batch_start//batch_size + 1}: {e}")
            for k in batch_keys:
                results.setdefault(k, {"counters_of": [], "counters": []})
            OUT_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            continue

        def parse_entries(lst):
            out = []
            for c in (lst or []):
                if isinstance(c, dict) and c.get("counter") in items:
                    out.append({"counter": c["counter"], "reason": c.get("reason", "")})
            return out

        for target_key, val in batch_result.items():
            if isinstance(val, dict):
                results[target_key] = {
                    "counters_of": parse_entries(val.get("counters_of", [])),
                    "counters":    parse_entries(val.get("counters", [])),
                }
            else:
                results[target_key] = {"counters_of": [], "counters": []}

        # Save after each batch
        OUT_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  Saved {len(results)} total")

    print(f"Done. Total: {len(results)} items with counter data → {OUT_FILE}")


if __name__ == "__main__":
    main()
