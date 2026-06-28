# 题材标志性个股 MCP 服务 - 架构文档

## 1. 概述

题材标志性个股（star_stocks）MCP 服务是一个基于 FastMCP 的 Model Context Protocol 服务，用于维护「炒作方向 → 细分方向 → 个股」三层数据，数据持久化在 MySQL。

### 核心功能

| 类别 | 工具数 | 说明 |
|------|--------|------|
| 查询 | 3 | 题材列表、主线+轮动树、单题材树 |
| 新增 | 3 | 题材、细分方向、个股 |
| 更新 | 2 | 题材角色/摘要；个股属性（备注/类型/辨识度，不含评分） |
| 删除 | 3 | 个股、细分方向、题材（均支持级联） |

服务版本：**2.1.0**（MCP 名称：`star-stocks`）

> **评分说明**：查询结果仍包含 `score` 字段并按评分排序；MCP 与 Web/API **不提供**手动设置或更新评分的接口。评分数据主要来自 Markdown 导入及细分方向下个股均分重算。

### 技术栈

- **Python**: 3.11+
- **MCP 框架**: FastMCP（`mcp[cli]`）
- **业务包**: `star_stocks`（editable 依赖，与 Web 共用 Service 层）
- **数据库**: MySQL（SQLAlchemy + PyMySQL）
- **配置**: `star_stocks/.env`（`DB_PASSWORD` 等）

## 2. 项目结构

```
mcpServers/
├── start_star_stocks_service.py     # 启动入口
├── mcp_config.json                  # Cursor MCP 配置
└── src/mcp_servers/
    ├── base.py                      # MCP 服务器基类
    └── star_stocks/
        ├── main.py                  # 进程入口
        ├── service.py               # MCP 工具注册（11 个 tool）
        ├── config.py                # .env 加载、项目根路径
        ├── db.py                    # 数据库 Session 上下文
        └── helpers.py               # ok / err JSON 序列化

star_stocks/                         # 业务项目（同级目录）
└── src/star_stocks/
    ├── models/                      # ORM：theme_direction, sub_direction, theme_stock
    ├── schemas/                     # Pydantic 入参/出参
    └── services/
        ├── __init__.py              # ThemeService, SubDirectionService, ThemeStockService
        └── mcp_query.py             # MCP 专用查询组装
```

## 3. 核心模块

### 3.1 BaseMCPServer（base.py）

MCP 服务器基类，提供：

- FastMCP 实例管理
- `register_tools()` 工具注册
- `run()` 启动 stdio 传输

### 3.2 StarStocksService（service.py）

MCP 服务定义类：

```
StarStocksService
├── register_tools()    # 注册 11 个 MCP tool
└── run()               # 启动服务
```

每个 tool 返回 **JSON 字符串**（非原生 MCP 结构化对象）：

- 成功：`ok(data)` → 业务数据的 JSON 数组或对象
- 失败：`err(message)` → `{"error": "..."}`

### 3.3 McpQueryService（star_stocks/services/mcp_query.py）

MCP 查询专用组装逻辑：

```
McpQueryService
├── list_themes_with_sub_directions()   # 全题材 + 细分（无个股）
├── list_main_rotation_trees()          # 主线 + 轮动完整树
├── get_theme_tree(theme_id)            # 单题材完整树
├── build_theme_tree()                  # 单题材树构建
└── _load_tree_maps()                   # 批量加载细分与个股
```

### 3.4 数据表（无 stock 主表）

| 表 | 说明 |
|----|------|
| `theme_direction` | 炒作方向（题材） |
| `sub_direction` | 细分方向 |
| `theme_stock` | 个股条目（`code`/`name` 直接存本表） |

表间无外键，关联由应用层维护。

## 4. 公共类型

### 4.1 枚举

**RoleType**（题材角色）：

| 值 | 含义 |
|----|------|
| `main_line` | 主线 |
| `rotation` | 轮动 |
| `normal` | 普通 |

**StockType**（个股类型）：

`权重` | `身位股` | `人气股` | `中军` | `涨停个股`

### 4.2 共享返回结构

**StockItemOut**（树中的个股节点）：

```json
{
  "id": 1001,
  "code": "300502",
  "name": "新易盛",
  "stock_type": "权重",
  "is_distinctive": true,
  "remark": "【最具辨识度】龙头",
  "score": 97
}
```

**SubDirectionTreeOut**（树中的细分方向节点）：

```json
{
  "id": 71,
  "name": "光纤",
  "score": 85,
  "sort_order": 0,
  "stocks": [ /* StockItemOut[]，按 score 降序 */ ]
}
```

**ThemeTreeOut**（完整题材树）：

```json
{
  "id": 1,
  "name": "科技",
  "role_type": "main_line",
  "rotation_rank": null,
  "summary": "强分化，PCB/光模块重灾区",
  "sort_order": 0,
  "direct_stocks": [ /* StockItemOut[]，题材直下个股，按 score 降序 */ ],
  "sub_directions": [ /* SubDirectionTreeOut[]，按 score 降序 */ ]
}
```

**ThemeOut**（题材详情，用于新增/更新返回）：

```json
{
  "id": 1,
  "name": "科技",
  "role_type": "main_line",
  "rotation_rank": null,
  "summary": "强分化",
  "sort_order": 0,
  "is_active": true,
  "created_at": "2026-06-01T10:00:00",
  "updated_at": "2026-06-24T14:30:00"
}
```

**SubDirectionOut**（细分方向详情）：

```json
{
  "id": 71,
  "theme_id": 1,
  "name": "光纤",
  "score": 85,
  "sort_order": 0
}
```

**ThemeStockOut**（个股条目详情）：

```json
{
  "id": 1001,
  "theme_id": null,
  "sub_direction_id": 71,
  "code": "300502",
  "name": "新易盛",
  "stock_type": "权重",
  "is_distinctive": true,
  "remark": "龙头",
  "score": 97,
  "sort_order": 0
}
```

> `theme_id` 与 `sub_direction_id` 二选一非空：挂题材直下时 `theme_id` 有值；挂细分时 `sub_direction_id` 有值。

**错误响应**（所有 tool 通用）：

```json
{
  "error": "题材 999 不存在"
}
```

## 5. MCP 工具接口

### 5.1 查询

#### 5.1.1 list_themes_with_sub_directions

查询所有题材及包含的细分方向（**不含个股**）。

**参数：** 无

**返回：** `ThemeWithSubDirectionsOut[]`

排序规则：

- 题材顺序：主线 → 轮动（按 `rotation_rank`）→ 普通（按 `sort_order`）
- 各题材内 `sub_directions`：按 `score` 降序，无评分排最后

```json
[
  {
    "id": 1,
    "name": "科技",
    "role_type": "main_line",
    "rotation_rank": null,
    "summary": "强分化",
    "sub_directions": [
      { "id": 71, "name": "光纤", "score": 85 },
      { "id": 72, "name": "AI硬件/通信", "score": 80 },
      { "id": 73, "name": "元器件", "score": null }
    ]
  },
  {
    "id": 2,
    "name": "有色金属",
    "role_type": "rotation",
    "rotation_rank": 1,
    "summary": null,
    "sub_directions": []
  }
]
```

---

#### 5.1.2 list_main_rotation_trees

查询主线与轮动题材的完整树（题材 → 细分 → 个股）。

**参数：** 无

**返回：** `ThemeTreeOut[]`（仅 `role_type` 为 `main_line` 或 `rotation` 的题材）

排序规则：

- 题材：主线在前，轮动在后（轮动按 `rotation_rank`）
- `sub_directions`、`direct_stocks`、各细分下 `stocks`：均按 `score` 降序

```json
[
  {
    "id": 1,
    "name": "科技",
    "role_type": "main_line",
    "rotation_rank": null,
    "summary": "强分化",
    "sort_order": 0,
    "direct_stocks": [],
    "sub_directions": [
      {
        "id": 71,
        "name": "光纤",
        "score": 85,
        "sort_order": 0,
        "stocks": [
          {
            "id": 1001,
            "code": "601869",
            "name": "长飞光纤",
            "stock_type": "权重",
            "is_distinctive": false,
            "remark": null,
            "score": 90
          }
        ]
      }
    ]
  }
]
```

---

#### 5.1.3 get_theme_tree

查询指定题材的完整树。

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `theme_id` | int | 是 | 题材 ID |

**返回：** `ThemeTreeOut`（结构同 5.1.2 单个元素）

**错误：** 题材不存在时返回 `{"error": "题材 {id} 不存在"}`

---

### 5.2 新增

#### 5.2.1 create_theme

新增炒作方向（题材）。

**参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `name` | str | 是 | — | 题材名称，最长 64 字符，全局唯一 |
| `role_type` | RoleType | 否 | `"normal"` | 角色类型 |
| `rotation_rank` | int \| null | 否 | `null` | 轮动序号，`role_type=rotation` 时填写 |
| `summary` | str \| null | 否 | `null` | 摘要/备注，最长 512 字符 |

**返回：** `ThemeOut`

---

#### 5.2.2 create_sub_direction

向指定题材下新增细分方向。

**参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `theme_id` | int | 是 | — | 所属题材 ID |
| `name` | str | 是 | — | 细分名称，最长 128 字符，同题材内唯一 |

**返回：** `SubDirectionOut`（`score` 为只读，新建时通常为 `null`）

---

#### 5.2.3 create_theme_stock

向题材或细分方向下新增个股。

**参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `stock_type` | StockType | 是 | — | 个股类型 |
| `code` | str | 是 | — | 证券代码，最长 10 字符 |
| `name` | str | 是 | — | 股票名称，最长 64 字符 |
| `theme_id` | int \| null | 否 | `null` | 挂题材直下（与 `sub_direction_id` 二选一） |
| `sub_direction_id` | int \| null | 否 | `null` | 挂细分方向（与 `theme_id` 二选一） |
| `is_distinctive` | bool | 否 | `false` | 是否最具辨识度 |
| `remark` | str \| null | 否 | `null` | 备注 |

**约束：**

- `theme_id` 与 `sub_direction_id` 必须**恰好一个**非空
- 同一题材或同一细分下 `code` 不可重复

**返回：** `ThemeStockOut`（`score` 为只读，新建时通常为 `null`）

---

### 5.3 更新

#### 5.3.1 update_theme

更新题材；**仅允许**修改角色与摘要。

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `theme_id` | int | 是 | 题材 ID |
| `role_type` | RoleType \| null | 否 | 新角色（至少提供 `role_type` 或 `summary` 之一） |
| `summary` | str \| null | 否 | 新摘要/备注 |

**返回：** `ThemeOut`

---

#### 5.3.2 update_theme_stock

更新个股条目；**仅允许**修改备注、类型、是否最具辨识度（**不可修改评分**）。

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `entry_id` | int | 是 | 个股条目 ID（`theme_stock.id`） |
| `stock_type` | StockType \| null | 否 | 个股类型 |
| `is_distinctive` | bool \| null | 否 | 是否最具辨识度 |
| `remark` | str \| null | 否 | 备注 |

至少提供一个可更新字段（除 `entry_id` 外）。

**返回：** `ThemeStockOut`（`score` 为只读）

---

### 5.4 删除

#### 5.4.1 delete_theme_stock

删除题材或细分下的指定个股条目。

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `entry_id` | int | 是 | 个股条目 ID |

**返回：**

```json
{
  "deleted": true,
  "entry_id": 1001
}
```

---

#### 5.4.2 delete_sub_direction

删除细分方向，**级联删除**其下所有个股条目。

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `sub_direction_id` | int | 是 | 细分方向 ID |

**返回：**

```json
{
  "deleted": true,
  "sub_direction_id": 71
}
```

---

#### 5.4.3 delete_theme

删除题材，**级联删除**其下所有细分方向与个股条目。

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `theme_id` | int | 是 | 题材 ID |

**返回：**

```json
{
  "deleted": true,
  "theme_id": 1
}
```

## 6. 数据流程

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────────────┐
│   MCP 客户端    │────▶│ StarStocks      │────▶│ star_stocks.services    │
│  (Cursor 等)    │     │ Service         │     │ Theme / Sub / Stock     │
└─────────────────┘     └─────────────────┘     └───────────┬─────────────┘
                                                          │
                        ┌─────────────────────────────────┤
                        ▼                                 ▼
               ┌─────────────────┐              ┌─────────────────┐
               │ McpQueryService │              │ SQLAlchemy ORM  │
               │ (查询组装)       │              │ + MySQL         │
               └─────────────────┘              └─────────────────┘
```

**查询类** tool → `McpQueryService` → 批量 SELECT + 内存排序组装  
**写操作** tool → `ThemeService` / `SubDirectionService` / `ThemeStockService` → 事务提交

### 6.1 与 star_stocks Web/API 的评分约定

| 能力 | MCP | REST API（`/api/v1`） |
|------|-----|------------------------|
| 查询 `score` | ✅ 只读 | ✅ 只读（展示/排序） |
| 新增时写入 `score` | ❌ | ❌（`SubDirectionCreate` / `ThemeStockCreate` 无 score 字段） |
| PATCH 更新 `score` | ❌（无 `update_sub_direction`） | ❌（`SubDirectionPatch` / `ThemeStockPatch` 无 score 字段） |
| Markdown 导入写入 `score` | ❌ MCP 无此 tool | ✅ `ImportService`（Web 导入入口） |

细分方向 `score` 仍可在导入后由「下属个股均分」脚本或 `SubDirectionService.recalculate_score` 自动回写，但**不能**通过 MCP 或日常 CRUD API 手工改分。

## 7. 排序规则汇总

| 场景 | 排序键 |
|------|--------|
| 题材列表（全量） | 主线 → 轮动（`rotation_rank`）→ 普通（`sort_order`） |
| 主线+轮动树 | 同上，且过滤掉 `normal` |
| 细分方向 | `score` 降序，无评分最后，同分按 `name` |
| 个股 | `score` 降序，无评分最后，同分按 `name` |

## 8. 启动与配置

### 8.1 启动

```bash
cd mcpServers
# 确保 ../star_stocks/.env 已配置 DB_PASSWORD
python start_star_stocks_service.py
```

### 8.2 Cursor MCP 配置（mcp_config.json）

```json
{
  "mcpServers": {
    "star-stocks": {
      "command": "python",
      "args": ["start_star_stocks_service.py"],
      "env": {}
    }
  }
}
```

### 8.3 环境变量

| 变量 | 说明 |
|------|------|
| `STAR_STOCKS_ROOT` | 可选，`star_stocks` 项目根目录，默认 `../star_stocks` |
| `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` | 从 `star_stocks/.env` 加载 |

## 9. 依赖说明

| 依赖 | 说明 |
|------|------|
| `star-stocks` | 本地 editable 包（`../star_stocks`） |
| `mcp[cli]` | MCP 框架 |
| `sqlalchemy` / `pymysql` | 数据库（由 star_stocks 传递） |
| `python-dotenv` | 加载 `.env` |

安装（mcpServers 目录）：

```bash
uv pip install -e ".[dev]"
```

## 10. 工具清单速查

| # | Tool | 类别 |
|---|------|------|
| 1 | `list_themes_with_sub_directions` | 查询 |
| 2 | `list_main_rotation_trees` | 查询 |
| 3 | `get_theme_tree` | 查询 |
| 4 | `create_theme` | 新增 |
| 5 | `create_sub_direction` | 新增 |
| 6 | `create_theme_stock` | 新增 |
| 7 | `update_theme` | 更新 |
| 8 | `update_theme_stock` | 更新 |
| 9 | `delete_theme_stock` | 删除 |
| 10 | `delete_sub_direction` | 删除 |
| 11 | `delete_theme` | 删除 |
