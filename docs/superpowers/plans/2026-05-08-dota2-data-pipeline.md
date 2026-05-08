# Dota2 Wiki 数据管道实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 Python 数据管道，从 dotaconstants 和 GameTracking-Dota2 拉取数据，合并中英文，输出 heroes.json 和 items.json。

**Architecture:** fetch.py 下载原始文件到 data/raw/；parse_kv.py 解析 Valve KeyValues 格式的 .txt 文件；build.py 将结构数据与中文文本合并，输出最终 JSON。

**Tech Stack:** Python 3.10+, requests, pytest

---

## 文件结构

```
dota2/
├── scripts/
│   ├── fetch.py          # 下载原始数据文件
│   ├── parse_kv.py       # 解析 Valve KeyValues 格式
│   └── build.py          # 合并数据，输出最终 JSON
├── data/
│   ├── raw/              # 原始下载文件（gitignore）
│   └── output/
│       ├── heroes.json
│       └── items.json
├── tests/
│   ├── test_parse_kv.py
│   └── test_build.py
└── requirements.txt
```

---

## Task 1: 初始化项目结构

**Files:**
- Create: `requirements.txt`
- Create: `scripts/__init__.py`
- Create: `tests/__init__.py`
- Create: `.gitignore`

- [ ] **Step 1: 创建目录结构**

```bash
cd /Users/hanyang030/Desktop/dota2
mkdir -p scripts data/raw data/output tests
touch scripts/__init__.py tests/__init__.py
```

- [ ] **Step 2: 写 requirements.txt**

```
requests==2.31.0
pytest==8.1.0
```

- [ ] **Step 3: 写 .gitignore**

```
data/raw/
data/output/
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 4: 安装依赖**

```bash
pip install -r requirements.txt
```

Expected: 无报错，requests 和 pytest 安装成功。

- [ ] **Step 5: Commit**

```bash
git init
git add requirements.txt .gitignore scripts/__init__.py tests/__init__.py
git commit -m "chore: init project structure"
```

---

## Task 2: 实现 Valve KeyValues 解析器

Valve 的 .txt 文件使用 KeyValues 格式，类似：
```
"DOTAAbilities"
{
  "Version" "1"
  "antimage_mana_break"
  {
    "AbilityName" "antimage_mana_break"
    "AbilityValues" { ... }
  }
}
```
需要解析成 Python dict。

**Files:**
- Create: `scripts/parse_kv.py`
- Create: `tests/test_parse_kv.py`

- [ ] **Step 1: 写失败测试**

文件 `tests/test_parse_kv.py`：

```python
from scripts.parse_kv import parse_kv


def test_simple_key_value():
    text = '"key" "value"'
    result = parse_kv(text)
    assert result == {"key": "value"}


def test_nested_block():
    text = '''
"root"
{
    "child" "hello"
}
'''
    result = parse_kv(text)
    assert result == {"root": {"child": "hello"}}


def test_multiple_keys():
    text = '''
"root"
{
    "a" "1"
    "b" "2"
}
'''
    result = parse_kv(text)
    assert result == {"root": {"a": "1", "b": "2"}}


def test_deeply_nested():
    text = '''
"outer"
{
    "inner"
    {
        "key" "val"
    }
}
'''
    result = parse_kv(text)
    assert result == {"outer": {"inner": {"key": "val"}}}


def test_comment_ignored():
    text = '''
// this is a comment
"key" "value"
'''
    result = parse_kv(text)
    assert result == {"key": "value"}
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/hanyang030/Desktop/dota2
python -m pytest tests/test_parse_kv.py -v
```

Expected: `ImportError` 或 `ModuleNotFoundError`，因为 parse_kv.py 还不存在。

- [ ] **Step 3: 实现 parse_kv.py**

文件 `scripts/parse_kv.py`：

```python
import re


def parse_kv(text: str) -> dict:
    tokens = _tokenize(text)
    result, _ = _parse_block(tokens, 0)
    return result


def _tokenize(text: str) -> list[str]:
    tokens = []
    for line in text.splitlines():
        line = line.split("//")[0].strip()
        for token in re.findall(r'"[^"]*"|\{|\}', line):
            tokens.append(token.strip('"') if token not in ("{", "}") else token)
    return tokens


def _parse_block(tokens: list[str], pos: int) -> tuple[dict, int]:
    result = {}
    while pos < len(tokens):
        token = tokens[pos]
        if token == "}":
            return result, pos + 1
        if token == "{":
            pos += 1
            continue
        key = token
        pos += 1
        if pos >= len(tokens):
            break
        next_token = tokens[pos]
        if next_token == "{":
            value, pos = _parse_block(tokens, pos + 1)
            result[key] = value
        else:
            result[key] = next_token
            pos += 1
    return result, pos
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/test_parse_kv.py -v
```

Expected: 5 passed。

- [ ] **Step 5: Commit**

```bash
git add scripts/parse_kv.py tests/test_parse_kv.py
git commit -m "feat: add Valve KeyValues parser"
```

---

## Task 3: 实现数据下载脚本

**Files:**
- Create: `scripts/fetch.py`

下载以下文件到 `data/raw/`：
| 文件 | 来源 |
|------|------|
| `heroes.json` | dotaconstants CDN |
| `hero_abilities.json` | dotaconstants CDN |
| `abilities.json` | dotaconstants CDN |
| `items.json` (dotaconstants) | dotaconstants CDN |
| `dota_schinese.txt` | GameTracking-Dota2 GitHub raw |
| `abilities_schinese.txt` | GameTracking-Dota2 GitHub raw |

- [ ] **Step 1: 写 fetch.py**

文件 `scripts/fetch.py`：

```python
import requests
from pathlib import Path

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"

SOURCES = {
    "heroes.json": "https://cdn.jsdelivr.net/npm/dotaconstants@latest/build/heroes.json",
    "hero_abilities.json": "https://cdn.jsdelivr.net/npm/dotaconstants@latest/build/hero_abilities.json",
    "abilities.json": "https://cdn.jsdelivr.net/npm/dotaconstants@latest/build/abilities.json",
    "items_raw.json": "https://cdn.jsdelivr.net/npm/dotaconstants@latest/build/items.json",
    "dota_schinese.txt": "https://raw.githubusercontent.com/SteamDatabase/GameTracking-Dota2/master/game/dota/pak01_dir/resource/localization/dota_schinese.txt",
    "abilities_schinese.txt": "https://raw.githubusercontent.com/SteamDatabase/GameTracking-Dota2/master/game/dota/pak01_dir/resource/localization/abilities_schinese.txt",
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
```

- [ ] **Step 2: 运行下载脚本**

```bash
cd /Users/hanyang030/Desktop/dota2
python scripts/fetch.py
```

Expected: 6 个文件下载成功，打印每个文件的大小。确认 `data/raw/` 下有：
```
heroes.json
hero_abilities.json
abilities.json
items_raw.json
dota_schinese.txt
abilities_schinese.txt
```

- [ ] **Step 3: 验证文件内容**

```bash
python3 -c "
import json
from pathlib import Path
heroes = json.loads(Path('data/raw/heroes.json').read_text())
print('英雄数量:', len(heroes))
first = next(iter(heroes.items()))
print('第一个英雄 key:', first[0])
print('字段:', list(first[1].keys()))
"
```

Expected: 打印英雄数量（约 124），以及字段名列表。

- [ ] **Step 4: Commit**

```bash
git add scripts/fetch.py
git commit -m "feat: add data fetch script"
```

---

## Task 4: 实现数据合并脚本，输出 heroes.json

**Files:**
- Create: `scripts/build.py`
- Create: `tests/test_build.py`

合并逻辑：
1. 读取 `data/raw/heroes.json`（英雄基础数据）
2. 读取 `data/raw/hero_abilities.json`（英雄 → 技能 key 映射）
3. 读取 `data/raw/abilities.json`（技能详情）
4. 读取 `data/raw/dota_schinese.txt`，用 parse_kv 解析，提取英雄中文名
5. 读取 `data/raw/abilities_schinese.txt`，提取技能中文名和描述
6. 合并输出

- [ ] **Step 1: 写失败测试**

文件 `tests/test_build.py`：

```python
import json
from scripts.build import merge_heroes, merge_items


def test_merge_heroes_has_required_fields():
    heroes = merge_heroes()
    assert len(heroes) > 100

    hero = heroes.get("npc_dota_hero_antimage")
    assert hero is not None
    assert "id" in hero
    assert "name" in hero           # 中文名
    assert "name_en" in hero        # 英文名
    assert "primary_attr" in hero
    assert "abilities" in hero
    assert len(hero["abilities"]) > 0

    ability = hero["abilities"][0]
    assert "key" in ability
    assert "name" in ability        # 技能中文名


def test_merge_items_has_required_fields():
    items = merge_items()
    assert len(items) > 100

    item = items.get("item_blink")
    assert item is not None
    assert "id" in item
    assert "name" in item           # 中文名
    assert "name_en" in item
    assert "cost" in item
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python -m pytest tests/test_build.py -v
```

Expected: `ImportError`，build.py 尚未存在。

- [ ] **Step 3: 实现 build.py**

文件 `scripts/build.py`：

```python
import json
from pathlib import Path
from scripts.parse_kv import parse_kv

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "output"


def _load_json(filename: str) -> dict:
    return json.loads((RAW_DIR / filename).read_text(encoding="utf-8"))


def _load_kv(filename: str) -> dict:
    text = (RAW_DIR / filename).read_text(encoding="utf-8")
    return parse_kv(text)


def _get_zh_heroes(kv: dict) -> dict:
    """从 dota_schinese.txt 提取英雄中文名，key 形如 npc_dota_hero_antimage"""
    lang = kv.get("lang", kv)
    tokens = lang.get("Tokens", lang)
    result = {}
    for k, v in tokens.items():
        if k.startswith("npc_dota_hero_"):
            result[k.lower()] = v
    return result


def _get_zh_abilities(kv: dict) -> dict:
    """从 abilities_schinese.txt 提取技能中文名和描述"""
    lang = kv.get("lang", kv)
    tokens = lang.get("Tokens", lang)
    names = {}
    descs = {}
    for k, v in tokens.items():
        kl = k.lower()
        if kl.endswith("_description"):
            ability_key = kl[: -len("_description")]
            descs[ability_key] = v
        else:
            names[kl] = v
    return names, descs


def merge_heroes() -> dict:
    heroes_raw = _load_json("heroes.json")
    hero_abilities_raw = _load_json("hero_abilities.json")
    abilities_raw = _load_json("abilities.json")

    zh_heroes = _get_zh_heroes(_load_kv("dota_schinese.txt"))
    zh_ability_names, zh_ability_descs = _get_zh_abilities(_load_kv("abilities_schinese.txt"))

    result = {}
    for hero_key, hero_data in heroes_raw.items():
        hero_key_lower = hero_key.lower()
        abilities = []
        ha = hero_abilities_raw.get(hero_key, {})
        for ability_key in ha.get("abilities", []):
            ability_key_lower = ability_key.lower()
            ab = abilities_raw.get(ability_key, {})
            abilities.append({
                "key": ability_key,
                "name": zh_ability_names.get(ability_key_lower, ability_key),
                "description": zh_ability_descs.get(ability_key_lower, ""),
                "cooldown": ab.get("cd", ""),
                "manacost": ab.get("mc", ""),
            })

        result[hero_key] = {
            "id": hero_data.get("id"),
            "name": zh_heroes.get(hero_key_lower, hero_data.get("localized_name", hero_key)),
            "name_en": hero_data.get("localized_name", ""),
            "primary_attr": hero_data.get("primary_attr", ""),
            "attack_type": hero_data.get("attack_type", ""),
            "roles": hero_data.get("roles", []),
            "abilities": abilities,
        }
    return result


def merge_items() -> dict:
    items_raw = _load_json("items_raw.json")
    zh_heroes_kv = _load_kv("dota_schinese.txt")
    lang = zh_heroes_kv.get("lang", zh_heroes_kv)
    tokens = lang.get("Tokens", lang)

    result = {}
    for item_key, item_data in items_raw.items():
        item_key_lower = item_key.lower()
        zh_name = tokens.get(item_key_lower, tokens.get(f"DOTA_Tooltip_ability_{item_key_lower}", ""))
        result[item_key] = {
            "id": item_data.get("id"),
            "name": zh_name or item_data.get("dname", item_key),
            "name_en": item_data.get("dname", ""),
            "cost": item_data.get("cost"),
            "description": item_data.get("desc", ""),
        }
    return result


def build_all():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Merging heroes...")
    heroes = merge_heroes()
    (OUTPUT_DIR / "heroes.json").write_text(
        json.dumps(heroes, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  heroes.json: {len(heroes)} heroes")

    print("Merging items...")
    items = merge_items()
    (OUTPUT_DIR / "items.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  items.json: {len(items)} items")


if __name__ == "__main__":
    build_all()
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/test_build.py -v
```

Expected: 2 passed。

- [ ] **Step 5: 运行完整构建**

```bash
python scripts/build.py
```

Expected:
```
Merging heroes...
  heroes.json: 124 heroes
Merging items...
  items.json: ... items
```

- [ ] **Step 6: 验证输出内容**

```bash
python3 -c "
import json
from pathlib import Path

heroes = json.loads(Path('data/output/heroes.json').read_text())
antimage = heroes['npc_dota_hero_antimage']
print('敌法师:', json.dumps(antimage, ensure_ascii=False, indent=2))
"
```

Expected: 打印敌法师数据，name 字段为中文"敌法师"，abilities 列表包含技能且有中文名称。

- [ ] **Step 7: Commit**

```bash
git add scripts/build.py tests/test_build.py
git commit -m "feat: add data merge and build script"
```

---

## Task 5: 验收检查

- [ ] **Step 1: 运行全部测试**

```bash
python -m pytest tests/ -v
```

Expected: 7 passed, 0 failed。

- [ ] **Step 2: 检查英雄数据完整性**

```bash
python3 -c "
import json
from pathlib import Path

heroes = json.loads(Path('data/output/heroes.json').read_text())
missing_name = [k for k, v in heroes.items() if not v['name'] or v['name'] == k]
missing_abilities = [k for k, v in heroes.items() if len(v['abilities']) == 0]
print(f'英雄总数: {len(heroes)}')
print(f'缺少中文名的英雄: {len(missing_name)}')
if missing_name:
    print('  示例:', missing_name[:5])
print(f'没有技能数据的英雄: {len(missing_abilities)}')
if missing_abilities:
    print('  示例:', missing_abilities[:5])
"
```

- [ ] **Step 3: 检查物品数据完整性**

```bash
python3 -c "
import json
from pathlib import Path

items = json.loads(Path('data/output/items.json').read_text())
with_name = [k for k, v in items.items() if v['name'] and v['name'] != k]
print(f'物品总数: {len(items)}')
print(f'有中文名的物品: {len(with_name)}')
blink = items.get('item_blink')
if blink:
    print('闪烁匕首:', json.dumps(blink, ensure_ascii=False))
"
```

- [ ] **Step 4: Final commit**

```bash
git add .
git commit -m "chore: complete data pipeline v1"
```
