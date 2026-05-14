# DOTA2 OldStack

基于 Flask 构建的 Dota2 英雄与物品百科，集成 Claude AI 分析克制关系、配合关系与物品推荐，并以 D3.js 力导向图可视化展示。

## 功能

### 英雄页
- 按力量 / 敏捷 / 智力 / 全属性筛选，支持中英文搜索
- 英雄详情：属性、技能描述（含 Lore）、昵称
- 克制该英雄的英雄列表（强度评级 + AI 分析原因）
- 与该英雄配合的英雄列表

### 物品页
- 分类网格展示所有物品（武器、防具、魔法道具等）
- 物品详情：费用、属性加成、效果描述、Lore
- 克制该物品的物品 / 该物品克制的物品
- 该物品克制哪些英雄（AI 分析）
- 推荐出该物品的英雄（AI 分析）

### 图谱页
- 搜索英雄后左右分屏展示：
  - **克制图谱**：哪些英雄/物品克制该英雄（红色边）
  - **配合图谱**：哪些英雄配合/哪些物品适合该英雄（绿色边）
- 搜索物品后展示该物品的克制关系图
- 节点悬停显示 AI 分析的详细原因
- 支持缩放、拖拽

## 项目结构

```
dota2/
├── app.py                          # Flask 应用入口，API 路由
├── templates/index.html            # 单页前端（HTML + CSS + JS）
├── requirements.txt
├── scripts/
│   ├── fetch.py                    # 从 dotaconstants / dotabase 拉取原始数据
│   ├── build.py                    # 合并原始数据，生成 output/heroes.json 和 items.json
│   ├── analyze_counters.py         # AI 分析英雄克制关系
│   ├── analyze_synergies.py        # AI 分析英雄配合关系
│   ├── analyze_item_counters.py    # AI 分析物品间克制关系
│   ├── analyze_item_hero_counters.py  # AI 分析物品克制哪些英雄
│   └── analyze_item_hero_fits.py   # AI 分析物品推荐哪些英雄出装
└── data/
    ├── raw/                        # fetch.py 拉取的原始 JSON / 本地化文件
    ├── output/
    │   ├── heroes.json             # 构建后的英雄数据（127 位）
    │   └── items.json              # 构建后的物品数据（501 件）
    ├── counters.json               # 英雄克制关系
    ├── synergies.json              # 英雄配合关系
    ├── item_counters.json          # 物品间克制关系
    ├── item_hero_counters.json     # 物品克制英雄
    ├── item_hero_fits.json         # 物品推荐英雄
    └── nicknames.json              # 英雄昵称（手动维护）
```

## 快速开始

### 环境要求

- Python 3.8+
- Anthropic API Key（用于 AI 分析脚本）

### 安装依赖

```bash
pip install -r requirements.txt
pip install anthropic
```

### 启动服务

如果已有构建好的数据（`data/output/` 下存在 `heroes.json` / `items.json`）：

```bash
python app.py
```

浏览器访问 [http://localhost:8000](http://localhost:8000)

## 数据更新

当 Dota2 版本更新、英雄或物品有改动时，按以下步骤刷新数据。

### 第一步：拉取最新原始数据

```bash
python scripts/fetch.py
```

从 dotaconstants 和 dotabase 下载最新的英雄、技能、物品、中文本地化文件到 `data/raw/`。

### 第二步：重新构建结构化数据

```bash
python scripts/build.py
```

将原始数据合并、翻译，输出 `data/output/heroes.json` 和 `data/output/items.json`。

### 第三步：重新运行 AI 分析（按需）

所有分析脚本均支持**增量更新**，已分析的条目会跳过，只补全新增或缺失的内容。

```bash
export ANTHROPIC_API_KEY=your_api_key_here

python scripts/analyze_counters.py
python scripts/analyze_synergies.py
python scripts/analyze_item_counters.py
python scripts/analyze_item_hero_counters.py
python scripts/analyze_item_hero_fits.py
```

### 强制全量重新分析

版本大改时，删除旧分析文件再运行：

```bash
rm data/counters.json data/synergies.json \
   data/item_counters.json data/item_hero_counters.json data/item_hero_fits.json

python scripts/analyze_counters.py
python scripts/analyze_synergies.py
python scripts/analyze_item_counters.py
python scripts/analyze_item_hero_counters.py
python scripts/analyze_item_hero_fits.py
```

### 重新分析单个英雄或物品

直接编辑对应 JSON 文件，删掉目标 key，再运行对应分析脚本即可：

```bash
# 例：重新分析敌法师的克制关系
# 编辑 data/counters.json，删除 "antimage" 那一项，然后：
python scripts/analyze_counters.py
```

## API

| 路由 | 说明 |
|------|------|
| `GET /api/heroes` | 英雄列表，支持 `?q=关键词&attr=str\|agi\|int\|all` |
| `GET /api/heroes/<key>` | 英雄详情 |
| `GET /api/counters/<key>` | 英雄克制数据 |
| `GET /api/synergies/<key>` | 英雄配合数据 |
| `GET /api/items` | 物品列表，支持 `?q=关键词` |
| `GET /api/items/<key>` | 物品详情（含 hero_counters / hero_fits）|
| `GET /api/graph_data` | 图谱用英雄克制数据（精简格式）|
| `GET /api/graph_synergies` | 图谱用英雄配合数据（精简格式）|

## 数据来源

- 英雄 / 技能 / 物品原始数据：[dotaconstants](https://github.com/odota/dotaconstants)
- 本地化文本（中文）：[dotabase](https://dotabase.dillerm.io/)
- NPC 属性数据：[d2vpkr](https://github.com/dotabuff/d2vpkr) / [dota_vpk_updates](https://github.com/spirit-bear-productions/dota_vpk_updates)
- AI 分析：[Anthropic Claude](https://www.anthropic.com/)
