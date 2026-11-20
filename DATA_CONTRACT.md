# 资讯数据契约（reader-edition.json）

路径：`outputs/ainook/reader-edition.json`

## 顶层

文件包含 `meta` 对象、`news` 新闻数组和 `gossip` 小道消息数组。`meta` 可附带 `site`、`window` 和 `tabs`。

- `meta.updated` 为北京时间，格式为 `YYYY-MM-DD HH:MM`。
- `meta.timezone` 可以省略，省略时按 `Asia/Shanghai` 解析。显式填写时取值为 `Asia/Shanghai`。
- `meta.counts.news` 是新闻条数，`meta.counts.gossip` 是小道消息条数，`meta.counts.total` 是两者之和。`meta.counts.byCategory` 以分类名为键，记录各类新闻条数。

以 `meta.counts` 为准，当前一期的实际条数以数据文件为准。比如 `meta.counts.total` 是精选简报总数，`meta.counts.byCategory["模型更新"]` 是模型更新条数，`meta.counts.gossip` 是小道消息条数。历史样例用 `meta.counts.nav` 表示总数。样例缺少分项统计时，按 `news[].c` 分组并核对 `gossip` 数组。

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
| `k` | string | 稳定编号，格式为 `g` + 数字，例如 `g10`、`g6` |
| `id` | string，可省略 | `g` + 数字编号，与 `k` 字段同值 |
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

- 站点以 `c` 的取值选择新闻子栏。未登记的分类只在精选简报显示。
- 同步校验取 `id`，缺少时用 `k`。标识缺失或在整期重复会抛 `ValueError`。
- `d` 晚于 `meta.updated` 会抛 `ValueError`。
