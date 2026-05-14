"""
Re-analyze items where counters_of and counters have overlapping items (direction confusion).
Uses stricter prompt with concrete examples.
"""
import json
import os
import re
from pathlib import Path
import anthropic

_ROOT = Path(__file__).parent.parent
OUT_FILE = _ROOT / "data/item_counters.json"
ITEMS_FILE = _ROOT / "data/output/items.json"


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
        desc = desc.replace("\\n", " ").replace("\n", " ").strip()[:120]
        parts = [f"[{key}]{name}"]
        if bonuses:
            parts.append(f"加成:{bonuses}")
        if desc:
            parts.append(f"效果:{desc}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def find_bad_keys(counters: dict) -> list:
    bad = []
    for k, v in counters.items():
        of_keys = {e['counter'] for e in v.get('counters_of', []) if isinstance(e, dict)}
        cnt_keys = {e['counter'] for e in v.get('counters', []) if isinstance(e, dict)}
        if of_keys & cnt_keys:
            bad.append(k)
    return bad


def main():
    items_data = json.loads(ITEMS_FILE.read_text())
    items = {
        k: v for k, v in items_data.items()
        if (v.get("description") or v.get("bonuses"))
        and not k.startswith("item_recipe")
        and v.get("name") and v.get("cost")
    }

    existing = json.loads(OUT_FILE.read_text(encoding="utf-8"))
    bad_keys = find_bad_keys(existing)
    print(f"Found {len(bad_keys)} items with direction confusion: {bad_keys}")

    api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY", "")
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    model = os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "claude-sonnet-4-6")
    client = anthropic.Anthropic(api_key=api_key, base_url=base_url)

    item_summary = build_item_summary(items)
    results = dict(existing)

    batch_size = 10
    for batch_start in range(0, len(bad_keys), batch_size):
        batch_keys = bad_keys[batch_start:batch_start + batch_size]
        batch_names = [(k, items[k]["name"]) for k in batch_keys if k in items]
        print(f"Batch {batch_start//batch_size + 1}: {[n for _, n in batch_names]}")

        target_list = "\n".join(f"- {key} ({name})" for key, name in batch_names)

        prompt = f"""你是Dota2专家，分析以下目标物品的克制关系。

【关键概念区分】
- counters_of（目标物品克制什么）：目标物品的效果能削弱/压制/绕过哪些其他物品的核心功能
  例：金箍棒(item_monkey_king_bar) counters_of = [蝴蝶, 辉耀]，因为金箍棒穿刺能无视蝴蝶/辉耀的闪避
- counters（什么克制目标物品）：哪些其他物品的效果能削弱/压制/绕过目标物品的核心功能
  例：金箍棒(item_monkey_king_bar) counters = [刃甲, 幽魂权杖]，因为这些物品能克制金箍棒的使用者

【严格要求】
- counters_of 和 counters 中不能出现同一个物品key
- 每个列表最多3个，无明显关系则给空数组
- 原因10字以内，不含引号逗号

所有可用物品：
{item_summary}

需要分析的目标物品：
{target_list}

严格JSON输出（不含markdown）：
{{
  "item_xxx": {{
    "counters_of": [{{"counter": "item_aaa", "reason": "XXX克制原因"}}],
    "counters": [{{"counter": "item_bbb", "reason": "XXX克制原因"}}]
  }}
}}"""

        message = client.messages.create(
            model=model,
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )

        response = message.content[0].text.strip()
        m = re.search(r'\{[\s\S]+\}', response)
        if not m:
            print(f"  Warning: could not parse JSON for batch {batch_start//batch_size + 1}")
            continue

        try:
            batch_result = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            print(f"  Warning: JSON parse error: {e}")
            continue

        def parse_entries(lst):
            out = []
            for c in (lst or []):
                if isinstance(c, dict) and c.get("counter") in items:
                    out.append({"counter": c["counter"], "reason": c.get("reason", "")})
            return out

        fixed = 0
        for target_key, val in batch_result.items():
            if isinstance(val, dict):
                new_of = parse_entries(val.get("counters_of", []))
                new_cnt = parse_entries(val.get("counters", []))
                # Verify no overlap
                of_keys = {e['counter'] for e in new_of}
                cnt_keys = {e['counter'] for e in new_cnt}
                overlap = of_keys & cnt_keys
                if overlap:
                    print(f"  Still has overlap for {target_key}: {overlap}, removing from counters")
                    new_cnt = [e for e in new_cnt if e['counter'] not in overlap]
                results[target_key] = {"counters_of": new_of, "counters": new_cnt}
                fixed += 1

        OUT_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  Fixed {fixed} items, saved {len(results)} total")

    # Final check
    remaining_bad = find_bad_keys(results)
    print(f"\nDone. Remaining items with overlap: {len(remaining_bad)}")
    if remaining_bad:
        print(f"  {remaining_bad}")


if __name__ == "__main__":
    main()
