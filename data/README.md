# 数据目录说明

| 文件 | 用途 |
|---|---|
| `data/sample.json` | 本地样例，用于跑通七栏导航和验证渲染。 |
| `scripts/sync_edition.py` | 从固定地址拉取并校验，通过才原子替换 `outputs/ainook/reader-edition.json`，失败保留旧文件。 |

## 完整数据在哪

以 `meta.counts` 为准，当前一期的实际条数以数据文件为准。比如 `meta.counts.total` 是精选简报总数，`meta.counts.byCategory["模型更新"]` 是模型更新条数，`meta.counts.gossip` 是小道消息条数。历史样例用 `meta.counts.nav` 表示总数。样例缺少分项统计时，按 `news[].c` 分组并核对 `gossip` 数组。

正式刊次由内容方交付，通过下面两种方式之一更新。

1. **手动**：内容方每天交付 `AI每日速递.json`，覆盖到 `outputs/ainook/reader-edition.json`。
2. **自动**：服务器跑 `scripts/sync_edition.py`，从固定的 `EDITION_URL` 拉取。

```bash
# 每天 08:10 执行一次
10 8 * * * EDITION_URL=https://你的稳定地址/latest.json python3 /path/to/scripts/sync_edition.py >> /var/log/ainook-edition.log 2>&1
```

## 校验规则（脚本内置）

- `meta.timezone` 省略时按 `Asia/Shanghai` 解析。显式填写时取值为 `Asia/Shanghai`。
- 总条数 ≥ 30（防止把样例误当线上数据）
- 每条资讯使用 `id`，缺少时使用 `k`，整期标识必须唯一。每条 `u` 必须是 http 或 https 链接。
- 任何一项不满足 → 不替换，退出码 1

## 样例怎么用

把 `data/sample.json` 复制到独立测试目录并命名为 `reader-edition.json`。用站点的 `--data-dir` 指向测试目录，即可查看七栏样例。
