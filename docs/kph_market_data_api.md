# 开盘红平台行情数据服务 - 接口文档

## 1. 概述

开盘红平台行情数据 MCP 服务（`kph-market-data`）封装开盘红平台的 6 个 HTTP 接口（3 个实时 + 3 个历史），对外提供大盘直播、涨停天梯、盘面亮点三类数据的查询能力。

| 数据类型 | 实时 MCP 工具 | 历史 MCP 工具 | 底层客户端方法 |
| --- | --- | --- | --- |
| 大盘直播（概念点） | `get_live_content` | `get_historical_live_content` | `fetch_live_content` / `fetch_historical_live_content` |
| 涨停天梯 | `get_limit_up_ladder` | `get_historical_limit_up_ladder` | `fetch_limit_up_ladder` / `fetch_historical_limit_up_ladder` |
| 盘面亮点 | `get_market_highlights` | `get_historical_market_highlights` | `fetch_market_highlights` / `fetch_historical_market_highlights` |

**项目路径**: `src/mcp_servers/kph_market_data/`

```
kph_market_data/
├── config.py      # API 域名与公共参数
├── client.py      # HTTP 客户端，封装 6 个接口
├── models.py      # 响应数据模型
├── service.py     # MCP 工具注册与文本格式化
└── main.py        # 启动入口
```

---

## 2. 公共配置

### 2.1 接口地址

| 环境 | 域名 | 说明 |
| --- | --- | --- |
| 实时 | `https://apphwshhq.kaipanhong.com/w1/api/index.php` | 获取当日实时数据 |
| 历史 | `https://apphis.kaipanhong.com/w1/api/index.php` | 获取指定交易日历史数据 |

**请求方式**: POST  
**Content-Type**: `application/x-www-form-urlencoded; charset=UTF-8`  
**超时**: 10 秒

### 2.2 公共请求头

| 参数名 | 值 |
| --- | --- |
| Content-Type | `application/x-www-form-urlencoded; charset=UTF-8` |
| User-Agent | `Dalvik/2.1.0 (Linux; U; Android 16; 23127PN0CC Build/BP2A.250605.031.A3)` |
| Host | 对应域名的主机名（实时: `apphwshhq.kaipanhong.com`，历史: `apphis.kaipanhong.com`） |

### 2.3 公共请求参数

| 参数名 | 类型 | 必填 | 示例值 | 说明 |
| --- | --- | --- | --- | --- |
| PhoneOSNew | Integer | 是 | 1 | 手机操作系统标识 |
| DeviceID | String | 是 | eae3d4b5dcb6437f | 设备唯一标识符 |
| VerSion | String | 是 | 6.1.6 | 应用版本号 |
| Red | Integer | 否 | 1 | 红色标识 |
| apiv | String | 是 | w46 | API 版本标识 |

### 2.4 公共响应字段

以下字段出现在多个接口的顶层响应中：

| 字段名 | 类型 | 说明 |
| --- | --- | --- |
| errcode | String | 错误码，`"0"` 表示成功 |
| ttag | Float | 服务器处理耗时（秒） |

### 2.5 错误码

| 错误码 | 说明 |
| --- | --- |
| 0 | 请求成功 |
| 其他 | 请求失败 |

---

## 3. 公共数据实体

以下实体在多个接口间复用。接口章节中通过「响应结构」引用，不再重复展开字段说明。

### 3.1 StockWithChange — 带涨跌幅的个股引用

用于大盘直播 `Stock` 字段，数组元素格式：

```
[股票代码, 股票名称, 涨跌幅百分比]
```

| 索引 | 类型 | 说明 |
| --- | --- | --- |
| 0 | String | 股票代码 |
| 1 | String | 股票名称 |
| 2 | Float | 涨跌幅（%） |

**Python 模型**: `LiveContentItem.stock` → `list[list]`

### 3.2 StockPair — 个股代码与名称

用于大盘直播 `DisStock`、盘面亮点 `StockList` 字段，数组元素格式：

```
[股票代码, 股票名称]
```

| 索引 | 类型 | 说明 |
| --- | --- | --- |
| 0 | String | 股票代码 |
| 1 | String | 股票名称 |

**Python 模型**: `LiveContentItem.dis_stock` → `list[list]`；`MarketHighlightItem.stock_list` → `list[list[str]]`

### 3.3 LiveContentItem — 单条直播内容

| 字段名（JSON） | 类型 | 说明 |
| --- | --- | --- |
| ID | String | 记录唯一标识 |
| UID | String | 用户 ID |
| Time | Integer | 发布时间戳（Unix 秒） |
| Comment | String | 直播内容/评论文本 |
| Type | String | 内容类型（`0` 普通，`3` 重点/涨停相关等） |
| PlateCode | String | 关联板块代码 |
| PlateName | String | 关联板块名称 |
| PlateJE | String | 板块资金净额 |
| PlateZDF | String | 板块涨跌幅（%） |
| ThemeInfo | Array | 主题信息数组 |
| Interpretation | String | 内容解读 |
| IsChart | String | 是否包含图表（`0` 否） |
| ShareData | Object | 分享数据对象 |
| UserName | String | 发布者用户名 |
| Image | String | 内容图片 URL |
| Stock | Array\<[StockWithChange](#31-stockwithchange--带涨跌幅的个股引用)\> | 关联个股 |
| DisStock | Array\<[StockPair](#32-stockpair--个股代码与名称)\> | 展示用个股 |
| ThemeClassInfo | Array | 主题分类信息 |
| styleIndex | Array | 风格指数 |
| BoomReason | String | 概念爆发原因 |

**Python 模型**: `LiveContentItem`

### 3.4 LiveContentResponse — 大盘直播完整响应

实时与历史接口返回结构相同。

| 字段名（JSON） | 类型 | 说明 |
| --- | --- | --- |
| list / List | Array\<[LiveContentItem](#33-livecontentitem--单条直播内容)\> | 直播内容列表 |
| errcode | String | 见 [公共响应字段](#24-公共响应字段) |
| Notice | String | 公告信息 |
| Status | Integer | 状态标识（`0` 正常） |
| Time | Integer | 服务器时间戳 |
| date | String | 日期（`YYYY-MM-DD`） |
| ttag | Float | 见 [公共响应字段](#24-公共响应字段) |

**Python 模型**: `LiveContentResponse`

### 3.5 LimitUpStock — 涨停个股

`StockList` 数组元素，按索引位置解析：

| 索引 | 类型 | 说明 |
| --- | --- | --- |
| 0 | String | 个股代码 |
| 1 | String | 个股名称 |
| 2 | Integer | 连板高度 |
| 3 | Integer | 涨停时间（Unix 时间戳） |
| 4 | String | 所属题材代码 |
| 5 | String | 所属题材名称 |
| 6-7 | Integer | 保留字段 |
| 8 | Integer | 所属题材涨停家数 |
| 9 | Integer | 资金流入（元） |
| 10 | Integer | 资金流出（元） |

> **注意**: 索引 6-7 在代码中跳过未解析，实际含义未知。

服务层在返回数据前会从 star_stocks 数据库查询个股标签，追加到 Python 模型的 `tags` 字段中（非 API 原始字段）：

| Python 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tags` | `str \| None` | 个股标签（如 `"白酒,消费"`），来自 stock_info 查询，无匹配时为 `None` |

**Python 模型**: `LimitUpStock`

### 3.6 LimitUpTheme — 涨停题材

`ZhuShuList` 数组元素，按索引位置解析：

| 索引 | 类型 | 说明 |
| --- | --- | --- |
| 0 | String | 题材代码 |
| 1 | String | 题材名称 |
| 2 | Integer | 题材涨停家数 |
| 3 | Integer | 成交额（元） |
| 4 | String | 涨停个股代码（逗号分隔） |

**Python 模型**: `LimitUpTheme`

### 3.7 LimitUpLadderResponse — 涨停天梯完整响应

实时与历史接口返回结构相同。

| 字段名（JSON） | 类型 | 说明 |
| --- | --- | --- |
| StockList | Array\<[LimitUpStock](#35-limitupstock--涨停个股)\> | 涨停个股列表 |
| ZhuShuList | Array\<[LimitUpTheme](#36-limituptheme--涨停题材)\> | 涨停题材列表 |
| Date / date | String | 日期（`YYYY-MM-DD`） |
| ttag | Float | 见 [公共响应字段](#24-公共响应字段) |
| errcode | String | 见 [公共响应字段](#24-公共响应字段) |

**Python 模型**: `LimitUpLadderResponse`

### 3.8 MarketHighlightItem — 单条盘面亮点

| 字段名（JSON） | 类型 | 说明 |
| --- | --- | --- |
| TimeMin | Integer | 时间（Unix 时间戳） |
| TagID | Integer | 标签 ID |
| ZSCode | String | 所属题材代码 |
| Detail | String | 亮点描述 |
| TagShuXing | Integer | 标签属性 |
| TagName | String | 标签名称 |
| StockList | Array\<[StockPair](#32-stockpair--个股代码与名称)\> | 关联个股 |
| ZSName | String | 所属题材名称 |

**Python 模型**: `MarketHighlightItem`

### 3.9 MarketHighlightsResponse — 盘面亮点完整响应

实时与历史接口返回结构相同。

| 字段名（JSON） | 类型 | 说明 |
| --- | --- | --- |
| List | Array\<[MarketHighlightItem](#38-markethighlightitem--单条盘面亮点)\> | 盘面亮点列表 |
| date | String | 日期（`YYYY-MM-DD`） |
| Time | Integer | 服务器时间戳 |
| ttag | Float | 见 [公共响应字段](#24-公共响应字段) |
| errcode | String | 见 [公共响应字段](#24-公共响应字段) |

**Python 模型**: `MarketHighlightsResponse`

---

## 4. 实时接口

### 4.1 大盘直播（概念点）

| 项 | 值 |
| --- | --- |
| 接口标识 | `a=ZhiBoContent`, `c=ConceptionPoint` |
| MCP 工具 | `get_live_content` |
| 客户端方法 | `KPHClient.fetch_live_content` |
| 响应结构 | [LiveContentResponse](#34-livecontentresponse--大盘直播完整响应) |

#### 请求参数（除公共参数外）

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| index | Integer | 是 | 0 | 分页起始位置 |

#### MCP 工具参数

| 参数名 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| index | int | 0 | 分页起始位置 |

---

### 4.2 涨停天梯

| 项 | 值 |
| --- | --- |
| 接口标识 | `a=GetZhangTingTianTi`, `c=FuPanLa` |
| MCP 工具 | `get_limit_up_ladder` |
| 客户端方法 | `KPHClient.fetch_limit_up_ladder` |
| 响应结构 | [LimitUpLadderResponse](#37-limitupladderresponse--涨停天梯完整响应) |

#### 请求参数（除公共参数外）

无额外参数。

#### MCP 工具参数

无参数。

---

### 4.3 盘面亮点

| 项 | 值 |
| --- | --- |
| 接口标识 | `a=GetPMSL_PMLD`, `c=FuPanLa` |
| MCP 工具 | `get_market_highlights` |
| 客户端方法 | `KPHClient.fetch_market_highlights` |
| 响应结构 | [MarketHighlightsResponse](#39-markethighlightsresponse--盘面亮点完整响应) |

#### 请求参数（除公共参数外）

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| Index | Integer | 是 | 0 | 分页起始位置 |
| st | Integer | 是 | 30 | 返回条数 |

#### MCP 工具参数

| 参数名 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| index | int | 0 | 分页起始位置 |
| limit | int | 30 | 返回条数 |

---

## 5. 历史接口

历史接口与对应实时接口的**响应结构完全相同**，区别如下：

| 差异项 | 实时 | 历史 |
| --- | --- | --- |
| 域名 | `apphwshhq.kaipanhong.com` | `apphis.kaipanhong.com` |
| 日期参数 | 无（默认当日） | 必须传入 `Date`（`YYYY-MM-DD`） |

### 5.1 历史大盘直播

| 项 | 值 |
| --- | --- |
| 接口标识 | `a=ZhiBoContent`, `c=HisConceptionPoint` |
| MCP 工具 | `get_historical_live_content` |
| 客户端方法 | `KPHClient.fetch_historical_live_content` |
| 响应结构 | [LiveContentResponse](#34-livecontentresponse--大盘直播完整响应) |

#### 请求参数（除公共参数外）

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| index | Integer | 是 | 0 | 分页起始位置 |
| st | Integer | 是 | 0 | 返回条数限制（`0` 表示不限制） |
| Date | String | 是 | — | 历史日期（`YYYY-MM-DD`） |

#### MCP 工具参数

| 参数名 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| date | str | — | 历史日期（`YYYY-MM-DD`） |
| index | int | 0 | 分页起始位置 |
| st | int | 0 | 返回条数限制（`0` 表示不限制） |

---

### 5.2 历史涨停天梯

| 项 | 值 |
| --- | --- |
| 接口标识 | `a=GetZhangTingTianTi`, `c=FuPanLa` |
| MCP 工具 | `get_historical_limit_up_ladder` |
| 客户端方法 | `KPHClient.fetch_historical_limit_up_ladder` |
| 响应结构 | [LimitUpLadderResponse](#37-limitupladderresponse--涨停天梯完整响应) |

#### 请求参数（除公共参数外）

| 参数名 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| Date | String | 是 | 历史日期（`YYYY-MM-DD`） |

#### MCP 工具参数

| 参数名 | 类型 | 说明 |
| --- | --- | --- |
| date | str | 历史日期（`YYYY-MM-DD`） |

---

### 5.3 历史盘面亮点

| 项 | 值 |
| --- | --- |
| 接口标识 | `a=GetPMSL_PMLD`, `c=FuPanLa` |
| MCP 工具 | `get_historical_market_highlights` |
| 客户端方法 | `KPHClient.fetch_historical_market_highlights` |
| 响应结构 | [MarketHighlightsResponse](#39-markethighlightsresponse--盘面亮点完整响应) |

#### 请求参数（除公共参数外）

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| Index | Integer | 是 | 0 | 分页起始位置 |
| st | Integer | 是 | 30 | 返回条数 |
| Date | String | 是 | — | 历史日期（`YYYY-MM-DD`） |

#### MCP 工具参数

| 参数名 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| date | str | — | 历史日期（`YYYY-MM-DD`） |
| index | int | 0 | 分页起始位置 |
| limit | int | 30 | 返回条数 |

---

## 6. MCP 资源

| URI | 说明 |
| --- | --- |
| `kph://service/info` | 返回服务名称、版本、功能列表和数据源信息（JSON） |

---

## 7. 响应示例

### 7.1 大盘直播

```json
{
  "list": [
    {
      "ID": "89253",
      "UID": "182",
      "Time": 1777516320,
      "Comment": "市场强势震荡，个股涨多跌少...",
      "Type": "0",
      "PlateCode": "",
      "PlateName": "",
      "PlateJE": "",
      "PlateZDF": "",
      "ThemeInfo": [],
      "Interpretation": "",
      "IsChart": "0",
      "ShareData": {},
      "UserName": "Livermore",
      "Image": "",
      "Stock": [["000066", "中国长城", 9.99]],
      "DisStock": [["000066", "中国长城"]],
      "ThemeClassInfo": [],
      "styleIndex": [],
      "BoomReason": ""
    }
  ],
  "Notice": "直播即将开始！！！",
  "Status": 0,
  "Time": 1777742596,
  "date": "2026-04-30",
  "ttag": 0.036,
  "errcode": "0"
}
```

### 7.2 涨停天梯

```json
{
  "StockList": [
    ["603045", "福达合金", 4, 1778203555, "801807", "算力", 1, 1, 9, 8416561932, 10536364016]
  ],
  "ZhuShuList": [
    ["801159", "机器人概念", 23, 21152635060, "000678,002009"]
  ],
  "Date": "2026-05-08",
  "ttag": 0.000814,
  "errcode": "0"
}
```

### 7.3 盘面亮点

```json
{
  "List": [
    {
      "TimeMin": 1778203500,
      "TagID": 11,
      "ZSCode": "801807",
      "Detail": "算力福达合金领先身位、连续加速，四连板",
      "TagShuXing": 2,
      "TagName": "领先身位",
      "StockList": [["603045", "福达合金"]],
      "ZSName": "算力"
    }
  ],
  "date": "2026-05-08",
  "Time": 1778246094,
  "ttag": 0.001352,
  "errcode": "0"
}
```

---

## 8. 注意事项

1. 所有请求参数均需 URL 编码。
2. `index` / `Index` 用于分页，从 `0` 开始。
3. 时间戳均为 Unix 秒级时间戳。
4. MCP 工具返回格式化后的可读文本；如需结构化数据，可直接调用 `KPHClient` 获取对应的 Python dataclass 对象。
5. 历史接口仅支持开盘红平台有记录的交易日。
