# 资讯数据契约（reader-edition.json）

路径：`outputs/ainook/reader-edition.json`

## 顶层

```json
{
  "meta": {
    "site": "AI 每日速递",
    "updated": "2026-11-19 08:40",
    "window": "近 7 天",
    "timezone": "Asia/Shanghai",
    "tabs": ["精选简报", "模型更新", "官方公告", "行业热点", "国际新闻", "全球财经", "小道消息"],
    "counts": { "nav": 83, "byCategory": { "模型更新": 14, "官方公告": 12 } }
  },
  "news": [ ... ],
  "gossip": [ ... ]
}
```

`meta.timezone` 必须是 `Asia/Shanghai`，`meta.updated` 是北京时间，格式 `YYYY-MM-DD HH:MM`。

## news 每条

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 稳定标识，`n-` + 10 位哈希，全库唯一 |
| `c` | string | 分类，取值只能是：模型更新 / 官方公告 / 行业热点 / 国际新闻 / 全球财经 |
| `d` | string | `MM-DD HH:MM`，北京时间 |
| `o` | number | 排序键 `MMDDHHMM`，列表按它倒序 |
| `t` | string | 标题 |
| `s` | string | 一句话摘要 |
| `n` | string | 来源名称 |
| `u` | string | 原文链接，必须可访问 |
| `p` | string[] | 详情段落 2–3 段，每段 1–3 句，只写事实 |

## gossip 每条

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | `g-` 开头 |
| `kind` | string | 固定 `gossip` |
| `c` | string | 固定 `小道消息` |
| `tag` | string | 类型标签，如 `X 言论`、`评论区` |
| `d` | string | `MM-DD HH:MM` |
| `t` / `s` | string | 标题 / 一句话概括 |
| `q` | string | 说话人原话 |
| `who` | string | 姓名 + 身份 + 平台 + 时间 |
| `chat` | string[] | 评论区讨论摘要 2–3 条 |
| `u` / `n` | string | 原帖链接 / 来源名 |

## 代码侧约束

- `c` 的取值会直接查 `CATEGORIES`，出现未登记的分类会抛 `KeyError` 并导致 `/news` 返回 503。
- `id` 重复会抛 `ValueError`。
- `d` 晚于 `meta.updated` 会抛 `ValueError`。
