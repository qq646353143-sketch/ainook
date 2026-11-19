# 数据目录说明

| 文件 | 用途 |
|---|---|
| `data/sample.json` | **17 条样例**（五类各 3 条 + 小道 2 条），用于跑通七栏导航、验证渲染。**不是线上数据。** |
| `scripts/sync_edition.py` | 从固定地址拉取并校验，通过才原子替换 `outputs/ainook/reader-edition.json`，失败保留旧文件。 |

## 完整数据在哪

完整一份约 78KB（83 条）。仓库不适合每天整份提交，所以线上数据走这两条路之一：

1. **手动**：内容方每天交付 `AI每日速递.json`，覆盖到 `outputs/ainook/reader-edition.json`。
2. **自动**：服务器跑 `scripts/sync_edition.py`，从固定的 `EDITION_URL` 拉取。

```bash
# 每天 08:10 执行一次
10 8 * * * EDITION_URL=https://你的稳定地址/latest.json python3 /path/to/scripts/sync_edition.py >> /var/log/ainook-edition.log 2>&1
```

## 校验规则（脚本内置）

- `meta.timezone` 必须是 `Asia/Shanghai`
- 总条数 ≥ 30（防止把样例误当线上数据）
- `id` 不重复、每条 `u` 必须是 http/https 链接
- 任何一项不满足 → 不替换，退出码 1

## 样例怎么用

把 `data/sample.json` 拷成 `outputs/ainook/reader-edition.json` 就能看到七栏效果，但条数只有 17，各栏会显示 3 条左右。上线前务必换回完整数据。
