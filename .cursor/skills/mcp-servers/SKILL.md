---
name: mcp-servers
description: >-
  stock-market-service、kph-market-data、star-stocks 三个 MCP 服务的使用指导，共 21 个工具。
  需要调用这三个 MCP 任意工具时使用；若上下文中已包含此 skill 内容，则无需重复读取。
---

# MCP Servers 综合使用指南

包含 3 个 MCP 服务，共 **21 个工具**。每个 tool 返回文本或 JSON 字符串；成功为数据，失败含 `"error"` 信息。

---

## 一、stock-market-service（A股行情数据服务）

基于 mootdx（通达信数据接口），提供 A 股行情数据查询。数据均做前复权处理。

### 工具清单（3 个）

#### get_minute_kline
获取 1 分钟 K 线数据，适用于观察单日分时走势与量能。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| stock_code | str | 与 name 二选一 | "" | 股票代码，如 "600519" |
| stock_name | str | 与 code 二选一 | "" | 股票名称，如 "贵州茅台" |
| count | int | 否 | 240 | 数据条数（约 1 个交易日） |

- **返回字段**：datetime、open、high、low、close、volume、amount

#### get_daily_kline
获取日 K 线数据，含均线、涨跌停价格。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| stock_code | str | 与 name 二选一 | "" | 股票代码 |
| stock_name | str | 与 code 二选一 | "" | 股票名称 |
| count | int | 否 | 120 | K 线条数 |

- **返回字段**：datetime、open、high、low、close、volume、amount、ma5、ma10、ma20、pre_close、limit_up、limit_down、is_limit_up、is_limit_down
- **涨跌停比例自动识别**：主板 ±10%、科创板(688)/创业板(300/301) ±20%、北交所(8开头) ±30%、ST ±5%

#### get_stock_quote
获取股票实时行情快照。

| 参数 | 类型 | 必填 | 默认 |
|------|------|------|------|
| stock_code | str | 与 name 二选一 | "" |
| stock_name | str | 与 code 二选一 | "" |

---

## 二、kph-market-data（开盘红平台行情数据服务）

对接开盘红平台，提供盘面数据的实时与历史查询。返回格式化文本。

### 工具清单（6 个）

#### get_live_content
获取当日大盘直播内容（概念点、盘面解读、关联个股、板块、概念爆发原因）。

| 参数 | 类型 | 必填 | 默认 |
|------|------|------|------|
| index | int | 否 | 0 |

#### get_limit_up_ladder
获取当日涨停天梯（题材排名、连板个股、涨停时间、个股标签）。

- **参数**：无

> **重要**：返回数据格式示例：`超声电子(000823): 2连板 | 涨停时间 09:32:15 | 题材 通信 | 标签 印制电路板,覆铜板,通信(印制电路板)`。其中"题材"表示个股所属的炒作题材，"标签"表示该股的涨停原因/辨识度。**二者结合**来判断个股所属的题材和细分方向，不可仅凭单一字段判断。

#### get_market_highlights
获取当日盘面亮点（时间节点、标签类型、关联题材、关联个股）。

| 参数 | 类型 | 必填 | 默认 |
|------|------|------|------|
| index | int | 否 | 0 |
| limit | int | 否 | 30 |

#### get_historical_live_content
获取指定日期的历史大盘直播内容。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| date | str | 是 | — | 日期，格式 YYYY-MM-DD |
| index | int | 否 | 0 | 分页起始位置 |
| st | int | 否 | 0 | 返回条数限制，0=不限制 |

#### get_historical_limit_up_ladder
获取指定日期的历史涨停天梯。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| date | str | 是 | 日期，格式 YYYY-MM-DD |

> **重要**：返回数据格式示例：`超声电子(000823): 2连板 | 涨停时间 09:32:15 | 题材 通信 | 标签 印制电路板,覆铜板,通信(印制电路板)`。其中"题材"表示个股所属的炒作题材，"标签"表示该股的涨停原因/辨识度。**二者结合**来判断个股所属的题材和细分方向，不可仅凭单一字段判断。

#### get_historical_market_highlights
获取指定日期的历史盘面亮点。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| date | str | 是 | — | 日期，格式 YYYY-MM-DD |
| index | int | 否 | 0 | 分页起始位置 |
| limit | int | 否 | 30 | 返回条数 |

---

## 三、star-stocks（题材个股管理服务）

基于数据库的题材与个股 CRUD 服务，用于维护炒作方向、细分方向及关联个股。

> **评分**：查询结果含只读 `score` 并按评分排序；MCP **不能**新增或修改评分（无 `update_sub_direction`）。

### 枚举

**role_type**：`main_line`（主线）| `rotation`（轮动）| `normal`（普通）

**stock_type**：`权重` | `身位股` | `人气股` | `中军` | `涨停个股`

### 数据层级与 ID

```
题材 theme
  ├── 细分 sub_direction
  │      └── 个股条目 theme_stock
  └── 个股条目 theme_stock（题材直下挂股）
```

| ID 字段 | 用途 |
|---------|------|
| `theme_id` | 题材标识；`create_sub_direction`、题材直下挂股、`get_theme_tree` 使用 |
| `sub_direction_id` | 细分标识；细分下挂股使用 |
| `entry_id` | 个股条目 id（`theme_stock.id`）；`update_theme_stock`、`delete_theme_stock` 使用 |

个股挂点规则：`theme_id` 与 `sub_direction_id` **二选一**非空。

### 查询工具（3 个）

| 需求 | Tool |
|------|------|
| 全部题材+细分，**不要个股** | `list_themes_with_sub_directions` |
| **主线+轮动**完整树（含个股） | `list_main_rotation_trees` |
| **指定题材**完整树 | `get_theme_tree(theme_id)` |

结果已排序，**勿再排序**。排序规则：题材 主线→轮动→普通；细分/个股按 `score` 降序，无评分最后。

#### list_themes_with_sub_directions
- **参数**：无
- **返回**：`ThemeWithSubs[]`

#### list_main_rotation_trees
- **参数**：无
- **返回**：`ThemeTree[]`（仅 `main_line` / `rotation`）

#### get_theme_tree
- **参数**：`theme_id` int（必填）
- **返回**：`ThemeTree`；不存在 → `{"error": "题材 {id} 不存在"}`

### 新增工具（3 个）

#### create_theme

| 参数 | 类型 | 必填 | 默认 |
|------|------|------|------|
| name | str | 是 | — |
| role_type | enum | 否 | normal |
| rotation_rank | int\|null | 否 | null |
| summary | str\|null | 否 | null |

#### create_sub_direction

| 参数 | 类型 | 必填 |
|------|------|------|
| theme_id | int | 是 |
| name | str | 是 |

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

- **约束**：`theme_id` XOR `sub_direction_id`；同组 `code` 不可重复

### 更新工具（2 个）

#### update_theme

| 参数 | 类型 | 必填 |
|------|------|------|
| theme_id | int | 是 |
| role_type | enum\|null | 至少其一 |
| summary | str\|null | 至少其一 |

#### update_theme_stock

| 参数 | 类型 | 必填 |
|------|------|------|
| entry_id | int | 是 |
| stock_type | enum\|null | 至少其一 |
| is_distinctive | bool\|null | 至少其一 |
| remark | str\|null | 至少其一 |

### 删除工具（3 个）

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

## 典型工作流

### 查询行情 → 关联题材

```
1. get_stock_quote(stock_code="600519") → 获取实时行情
2. get_daily_kline(stock_code="600519") → 了解K线形态与均线
3. list_main_rotation_trees → 查看当前主线题材中是否包含该股
```

### 复盘当日盘面

```
1. get_live_content → 大盘直播解读
2. get_limit_up_ladder → 涨停天梯（题材排名 + 连板个股）
3. get_market_highlights → 盘面亮点事件
```

### 复盘历史盘面

```
get_historical_limit_up_ladder(date="2026-06-24")
get_historical_market_highlights(date="2026-06-24")
get_historical_live_content(date="2026-06-24")
```

### 维护题材个股

```
1. list_themes_with_sub_directions → 取 theme_id / sub_direction_id
2. get_theme_tree(theme_id=1) → 查看完整树（含个股）
3. create_theme_stock / update_theme_stock / delete_theme_stock → 写操作
```

**改个股备注/类型/辨识度**：`get_theme_tree` → `stocks[].id` 作 `entry_id` → `update_theme_stock`

**向细分加股**：
```
create_theme_stock(sub_direction_id=71, code="600519", name="贵州茅台", stock_type="权重")
```

**题材直下加股**：
```
create_theme_stock(theme_id=1, code="300502", name="新易盛", stock_type="权重")
```

---

## 错误与边界

- 响应含 `"error"` → 核对参数、ID 与约束条件
- star-stocks 重复 code → 「该分组下已存在相同股票」
- star-stocks **无** `update_sub_direction`、**无** MCP 改评分、**无** import/overview、移动/复制个股、题材排序等 tool；需要时说明 MCP 不支持
- 股票查询 `stock_code` 与 `stock_name` 二选一，优先使用 `stock_code`
- kph-market-data 历史日期格式必须为 `YYYY-MM-DD`
