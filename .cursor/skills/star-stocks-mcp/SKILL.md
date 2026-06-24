---
name: star-stocks-mcp
description: >-
  Guides use of the star-stocks MCP server (题材标志性个股): query theme/sub-direction/stock
  trees, create/update/delete via 12 tools. Use when maintaining 炒作方向、细分方向、辨识度个股,
  calling star-stocks MCP, or editing star_stocks MySQL data through MCP.
---

# star-stocks MCP 使用指南

MCP 服务名：`star-stocks`（v2.0.0）。所有 tool 返回 **JSON 字符串**；失败时为 `{"error": "..."}`。

完整参数与返回 schema 见 [docs/star_stocks_architecture.md](../../../docs/star_stocks_architecture.md)。

## 数据模型（三层）

```
theme_direction（题材/炒作方向）
  └── sub_direction（细分方向）
        └── theme_stock（个股条目，含 code/name/type/score/remark）
```

- 无独立 `stock` 表；个股信息在 `theme_stock` 一行内。
- `theme_id` 与 `sub_direction_id` 在个股上**二选一**（题材直下 vs 挂细分）。

## ID 含义（勿混用）

| 字段 | 表 | 用于 |
|------|-----|------|
| `theme_id` | theme_direction | 题材 CRUD、查树、新增细分 |
| `sub_direction_id` | sub_direction | 细分 CRUD、向细分下挂股 |
| `entry_id` | theme_stock | 更新/删除**个股条目**（`update_theme_stock` / `delete_theme_stock`） |

树中个股的 `id` 即 `entry_id`。

## 查询：选哪个 tool

| 用户需求 | Tool | 返回 |
|----------|------|------|
| 全部题材 + 细分列表，**不要个股** | `list_themes_with_sub_directions` | 题材数组，细分按 score 降序 |
| **主线 + 轮动**完整树（含个股） | `list_main_rotation_trees` | `ThemeTreeOut[]`，主线在前 |
| **某一个**题材的完整树 | `get_theme_tree(theme_id)` | 单个 `ThemeTreeOut` |

不要对「只要列表」的场景调用 `get_theme_tree` 逐条拉取。  
查询结果已按业务规则排序，**无需再排序**。

`ThemeTreeOut` 含 `direct_stocks`（题材直下个股）和 `sub_directions[].stocks`。

## 写操作约束

### 新增

| Tool | 要点 |
|------|------|
| `create_theme` | `name` 必填；`role_type` 默认 `normal` |
| `create_sub_direction` | `theme_id` + `name` |
| `create_theme_stock` | `code`+`name`+`stock_type` 必填；`theme_id` **XOR** `sub_direction_id` |

`role_type`：`main_line` | `rotation` | `normal`（无 `new`）。  
`stock_type`：`权重` | `身位股` | `人气股` | `中军` | `涨停个股`。

### 更新（仅允许下列字段）

| Tool | 可改字段 |
|------|----------|
| `update_theme` | `role_type`, `summary`（摘要/备注） |
| `update_sub_direction` | `score`（必填） |
| `update_theme_stock` | `score`, `remark`, `stock_type`, `is_distinctive` |

不要传 `name`、`sort_order` 等未开放字段。

### 删除（均有级联）

| Tool | 级联 |
|------|------|
| `delete_theme_stock(entry_id)` | 仅删该个股条目 |
| `delete_sub_direction` | 删细分 + 其下全部个股 |
| `delete_theme` | 删题材 + 全部细分 + 全部个股 |

## 推荐工作流

**不知道 ID 时：**

1. `list_themes_with_sub_directions` → 拿 `theme_id`、`sub_direction_id`
2. 需要个股详情 → `get_theme_tree(theme_id)` 或 `list_main_rotation_trees`
3. 再 `create_*` / `update_*` / `delete_*`

**改某只个股评分/备注：**

1. `get_theme_tree` 找到 `stocks[].id`（即 `entry_id`）
2. `update_theme_stock(entry_id, score=..., remark=...)`

**向细分加股：**

```
create_theme_stock(
  sub_direction_id=<id>,
  code="600519",
  name="贵州茅台",
  stock_type="权重",
  score=90
)
```

**向题材直下加股（无细分）：**

```
create_theme_stock(theme_id=<id>, code=..., name=..., stock_type=...)
```

## 错误处理

- 返回含 `"error"` 键 → 向用户说明原因，先查 ID 或约束是否满足
- `create_theme_stock` 同组下重复 `code` → 「该分组下已存在相同股票」
- `get_theme_tree` 题材不存在 → 先用 `list_themes_with_sub_directions` 核对 ID

## 不要使用的接口

本 MCP **没有** overview/import、移动/复制个股、题材排序等 tool；需要时走 Web API 或告知用户不可用。

## 启动前提

`../star_stocks/.env` 已配置 `DB_PASSWORD`；MCP 配置见 `mcp_config.json` 中 `star-stocks`。
