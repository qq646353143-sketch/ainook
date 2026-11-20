# 给维护 AI 的硬约束

本仓库同时承载两类东西，权限不同：

| 位置 | 内容 | 权限 |
|---|---|---|
| `AINOOK-Review/` | 站点源码（由你维护） | 可改 |
| 仓库根目录 | 内容方放的交接文档、数据样例、同步脚本 | **只读，不得删改** |

## 一、上传时必须排除的路径

```
outputs/ainook/reader-edition.json           外部数据源，内容方每天更新；覆盖会造成数据回退
outputs/prototypes/home-v1/wishes.sqlite3    访客留言数据库，含他人内容，不得公开
data/sample.json                             内容方放的样例，不是线上数据
__pycache__/  *.pyc                          临时文件
```

## 二、每次提交写清改动

提交说明格式：`本次改动：<一句话>`。
不要只写 "update"、"fix"、"sync"——内容方需要靠它判断这次动了什么。

## 三、分类映射不得回退

七栏口径必须保留：

| 路由 | 名称 | 数据里的 `c` 值 |
|---|---|---|
| `/news` | 精选简报 | （全部，不过滤） |
| `/news/model` | 模型更新 | 模型更新 |
| `/news/official` | 官方公告 | 官方公告 |
| `/news/hot` | 行业热点 | 行业热点 |
| `/news/world` | 国际新闻 | 国际新闻 |
| `/news/finance` | 全球财经 | 全球财经 |
| `/rumors` | 小道消息 | （gossip 数组） |

硬规定：

- `AINOOK-Review/ainook/news_edition.py` 的 `CATEGORIES` 必须包含上述五个键。
- **禁止在前端写死分类映射表**，分类一律以数据里的 `c` 字段为准。
- 未登记的分类只在精选简报显示。历史补丁保存在 [归档目录](reference/legacy-patch-20261118/README.md)。
- 改 UI 时只能用 JSON 里已有的字段；需要新字段，先列清单给内容方，不得在页面侧自己造。

## 四、被否决过的设计（不得重新引入）

- 把导航拆回旧三栏（AI科技 / 国际新闻 / 财经）。
- 把 `reader-edition.json` 的内容写进代码或模板。
- 在预览模式和实时模式各维护一套导航表（现在两处都是七项，必须保持一致）。

## 五、自检

```bash
cd AINOOK-Review
python -m unittest discover -s tests -p test_ainook.py
```

替换数据后确认七栏和 `/news/sources` 全部返回 HTTP 200。

以 `meta.counts` 为准，当前一期的实际条数以数据文件为准。比如 `meta.counts.total` 是精选简报总数，`meta.counts.byCategory["模型更新"]` 是模型更新条数，`meta.counts.gossip` 是小道消息条数。历史样例用 `meta.counts.nav` 表示总数。样例缺少分项统计时，按 `news[].c` 分组并核对 `gossip` 数组。
