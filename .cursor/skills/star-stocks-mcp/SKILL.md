---
name: star-stocks-mcp
description: >-
  Guides use of the star-stocks MCP server (题材标志性个股): query theme/sub-direction/stock
  trees, create/update/delete via 12 tools. Use when maintaining 炒作方向、细分方向、辨识度个股,
  calling star-stocks MCP, or editing star_stocks data through MCP.
---

# star-stocks MCP 使用指南

MCP 名：`star-stocks`。每个 tool 返回 **JSON 字符串**；成功为数据对象/数组，失败为 `{"error": "消息"}`。

## 枚举

**role_type**：`main_line`（主线）| `rotation`（轮动）| `normal`（普通）

**stock_type**：`权重` | `身位股` | `人气股` | `中军` | `涨停个股`

## 数据与 ID

```
题材 theme_direction
  └── 细分 sub_direction
        └── 个股条目 theme_stock（code、name、type、score、remark 均在本行）
```

| ID 字段 | 用途 |
|---------|------|
| `theme_id` | 题材；`create_sub_direction`、题材直下挂股、`get_theme_tree` |
| `sub_direction_id` | 细分；向细分下挂股、`update_sub_direction` |
| `entry_id` | **个股条目** id（`theme_stock.id`）；`update_theme_stock`、`delete_theme_stock` |

树里 `stocks[].id` = `entry_id`。个股挂点：`theme_id` 与 `sub_direction_id` **二选一**非空。

## 返回结构

**StockItem**（树内个股）：
```json
{"id": 1001, "code": "300502", "name": "新易盛", "stock_type": "权重", "is_distinctive": true, "remark": "龙头", "score": 97}
```

**SubDirectionBrief**（列表查询中的细分）：
```json
{"id": 71, "name": "光纤", "score": 85}
```

**SubDirectionTree**（树内细分）：
```json
{"id": 71, "name": "光纤", "score": 85, "sort_order": 0, "stocks": [/* StockItem[] */]}
```

**ThemeTree**（完整题材树）：
```json
{
  "id": 1, "name": "科技", "role_type": "main_line", "rotation_rank": null,
  "summary": "强分化", "sort_order": 0,
  "direct_stocks": [/* 题材直下 StockItem[] */],
  "sub_directions": [/* SubDirectionTree[] */]
}
```

**ThemeWithSubs**（题材+细分，无个股）：
```json
{
  "id": 1, "name": "科技", "role_type": "main_line", "rotation_rank": null, "summary": "...",
  "sub_directions": [/* SubDirectionBrief[] */]
}
```

**Theme**（新增/更新题材返回）：
```json
{
  "id": 1, "name": "科技", "role_type": "main_line", "rotation_rank": null, "summary": "...",
  "sort_order": 0, "is_active": true, "created_at": "...", "updated_at": "..."
}
```

**SubDirection**（新增/更新细分返回）：
```json
{"id": 71, "theme_id": 1, "name": "光纤", "score": 85, "sort_order": 0}
```

**ThemeStock**（新增/更新个股返回）：
```json
{
  "id": 1001, "theme_id": null, "sub_direction_id": 71,
  "code": "300502", "name": "新易盛", "stock_type": "权重",
  "is_distinctive": true, "remark": "龙头", "score": 97, "sort_order": 0
}
```

**DeleteResult**：`{"deleted": true, "entry_id"|"sub_direction_id"|"theme_id": <id>}`

## 查询 tool 选型

| 需求 | Tool |
|------|------|
| 全部题材+细分，**不要个股** | `list_themes_with_sub_directions` |
| **主线+轮动**完整树（含个股） | `list_main_rotation_trees` |
| **指定题材**完整树 | `get_theme_tree(theme_id)` |

结果已排序，**勿再排序**。排序规则：题材 主线→轮动→普通；细分/个股按 `score` 降序，无评分最后。

勿对「只要列表」场景逐个 `get_theme_tree`。

---

## 工具清单（12 个）

### 查询

#### list_themes_with_sub_directions
- **参数**：无
- **返回**：`ThemeWithSubs[]`

#### list_main_rotation_trees
- **参数**：无
- **返回**：`ThemeTree[]`（仅 `main_line` / `rotation`）

#### get_theme_tree
- **参数**：`theme_id` int（必填）
- **返回**：`ThemeTree`；不存在 → `{"error": "题材 {id} 不存在"}`

---

### 新增

#### create_theme
| 参数 | 类型 | 必填 | 默认 |
|------|------|------|------|
| name | str | 是 | — |
| role_type | enum | 否 | normal |
| rotation_rank | int\|null | 否 | null |
| summary | str\|null | 否 | null |

- **返回**：`Theme`

#### create_sub_direction
| 参数 | 类型 | 必填 |
|------|------|------|
| theme_id | int | 是 |
| name | str | 是 |
| score | int\|null | 否（0–100） |

- **返回**：`SubDirection`

#### create_theme_stock
| 参数 | 类型 | 必填 | 默认 |
|------|------|------|------|
| stock_type | enum | 是 | — |
| code | str | 是 | — |
| name | str | 是 | — |
| theme_id | int\|null | 二选一 | null |
| sub_direction_id | int\|null | 二选一 | null |
| is_distinctive | bool | 否 | false |
| remark | str\|null | 否 | null |
| score | int\|null | 否 | null（0–100） |

- **约束**：`theme_id` XOR `sub_direction_id`；同组 `code` 不可重复
- **返回**：`ThemeStock`

---

### 更新（仅下列字段）

#### update_theme
| 参数 | 类型 | 必填 |
|------|------|------|
| theme_id | int | 是 |
| role_type | enum\|null | 至少其一 |
| summary | str\|null | 至少其一 |

- **返回**：`Theme`

#### update_sub_direction
| 参数 | 类型 | 必填 |
|------|------|------|
| sub_direction_id | int | 是 |
| score | int\|null | 是（0–100） |

- **返回**：`SubDirection`

#### update_theme_stock
| 参数 | 类型 | 必填 |
|------|------|------|
| entry_id | int | 是 |
| stock_type | enum\|null | 至少其一 |
| is_distinctive | bool\|null | 至少其一 |
| remark | str\|null | 至少其一 |
| score | int\|null | 至少其一 |

- **返回**：`ThemeStock`

---

### 删除

#### delete_theme_stock
- **参数**：`entry_id` int
- **返回**：`{"deleted": true, "entry_id": ...}`

#### delete_sub_direction
- **参数**：`sub_direction_id` int（级联删其下个股）
- **返回**：`{"deleted": true, "sub_direction_id": ...}`

#### delete_theme
- **参数**：`theme_id` int（级联删细分与个股）
- **返回**：`{"deleted": true, "theme_id": ...}`

---

## 工作流

**无 ID**：`list_themes_with_sub_directions` → 取 id → 需要个股时 `get_theme_tree` / `list_main_rotation_trees` → 写操作

**改个股评分/备注**：`get_theme_tree` → `stocks[].id` 作 `entry_id` → `update_theme_stock`

**向细分加股**：
```
create_theme_stock(sub_direction_id=71, code="600519", name="贵州茅台", stock_type="权重", score=90)
```

**题材直下加股**：
```
create_theme_stock(theme_id=1, code="...", name="...", stock_type="权重")
```

## 错误与边界

- 响应含 `"error"` → 说明原因，核对 ID 与约束
- 重复 code → 「该分组下已存在相同股票」
- **无** import、overview、移动/复制个股、题材排序等 tool；用户需要时说明 MCP 不支持
