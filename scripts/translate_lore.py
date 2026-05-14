"""
Translate item lore texts to Chinese using Claude API.
Outputs data/lore_cn.json: {item_key: translated_cn_text}
"""
import json
import os
from pathlib import Path
import anthropic

_ROOT = Path(__file__).parent.parent
RAW   = _ROOT / "data/raw"
OUT   = _ROOT / "data"
LORE_CN_FILE = OUT / "lore_cn.json"


def main():
    raw = json.loads((RAW / "items_raw.json").read_text())
    items_out = json.loads((_ROOT / "data/output/items.json").read_text())

    # Load existing translations (resume-safe)
    lore_cn: dict = {}
    if LORE_CN_FILE.exists():
        lore_cn = json.loads(LORE_CN_FILE.read_text(encoding="utf-8"))

    # Collect items that need translation
    to_translate = []
    for item_key, item in items_out.items():
        if item.get("description"):
            continue
        raw_key = item_key.replace("item_", "", 1)
        lore = raw.get(raw_key, {}).get("lore", "").strip()
        if lore and item_key not in lore_cn:
            to_translate.append((item_key, item.get("name", item_key), lore))

    print(f"Need to translate: {len(to_translate)} items")
    if not to_translate:
        print("Nothing to do.")
        return

    api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY", "")
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    model = os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "claude-sonnet-4-6")
    client = anthropic.Anthropic(api_key=api_key, base_url=base_url)

    # Batch all lore texts in one request to save cost
    numbered = "\n".join(
        f"{i+1}. [{item_key}] {lore}"
        for i, (item_key, _, lore) in enumerate(to_translate)
    )

    prompt = f"""你是Dota2游戏的中文翻译专家。请将以下{len(to_translate)}条物品背景描述（lore）翻译成简体中文。

要求：
- 保持游戏风格，文字简洁有力
- 每条翻译单独一行，格式为：序号. [item_key] 翻译内容
- 不要添加任何解释

原文：
{numbered}"""

    print("Calling Claude API...")
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    response = message.content[0].text
    print("Response received, parsing...")

    # Parse response lines
    import re
    for line in response.strip().splitlines():
        m = re.match(r'^\d+\.\s*\[([^\]]+)\]\s*(.+)$', line.strip())
        if m:
            item_key = m.group(1)
            cn_text = m.group(2).strip()
            lore_cn[item_key] = cn_text

    LORE_CN_FILE.write_text(
        json.dumps(lore_cn, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Saved {len(lore_cn)} translations → {LORE_CN_FILE}")


if __name__ == "__main__":
    main()
