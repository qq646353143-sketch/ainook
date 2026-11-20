# AINOOK 资讯模块

[AINOOK-Review/](AINOOK-Review/README.md) 是现行站点源码和运行入口。仓库根目录提供 [维护约定](AGENTS.md)、[数据契约](DATA_CONTRACT.md) 和 [刊次更新方法](data/README.md)。

## 资讯栏目

| 路由 | 名称 | 内容 |
|---|---|---|
| `/news` | 精选简报 | 全部资讯，含小道消息 |
| `/news/model` | 模型更新 | 新模型发布 |
| `/news/official` | 官方公告 | 官方公告和额度福利 |
| `/news/hot` | 行业热点 | 行业事件和人物动态 |
| `/news/world` | 国际新闻 | 国际政治、安全和外交 |
| `/news/finance` | 全球财经 | 货币政策、监管和并购融资 |
| `/rumors` | 小道消息 | 公开平台言论和社区议题 |

`/news/sources` 提供数据来源说明。

## 刊次更新与验收

内容方每日提供 `outputs/ainook/reader-edition.json`。可以手动放置，也可以通过 `scripts/sync_edition.py` 拉取。同步校验失败时会保留已有刊次。

替换刊次后重启站点，检查七个栏目和来源页均返回 HTTP 200，并核对旧地址的跳转。

以 `meta.counts` 为准，当前一期的实际条数以数据文件为准。比如 `meta.counts.total` 是精选简报总数，`meta.counts.byCategory["模型更新"]` 是模型更新条数，`meta.counts.gossip` 是小道消息条数。历史样例用 `meta.counts.nav` 表示总数。样例缺少分项统计时，按 `news[].c` 分组并核对 `gossip` 数组。

在仓库的 `AINOOK-Review/` 目录运行测试。

```bash
python -m unittest discover -s tests -p test_ainook.py
```

## 历史补丁

[2026-11-18 归档](reference/legacy-patch-20261118/README.md) 保留早期的七栏补丁原件。维护和运行请使用 `AINOOK-Review/ainook/` 下的现行源码。
