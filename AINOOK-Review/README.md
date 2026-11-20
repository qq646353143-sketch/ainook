# AINOOK 站点维护入口

先读仓库根目录的 [AGENTS.md](../AGENTS.md) 与 [DATA_CONTRACT.md](../DATA_CONTRACT.md)。根目录的交接文档、样例与内容同步脚本由内容方维护。网站维护在本目录进行。

AINOOK 有三个入口。`/` 为额度追踪，`/news` 为前沿资讯，`/author` 为作者小屋。服务端是 Python 标准库的 `ThreadingHTTPServer`，界面使用原生 HTML、CSS 和 JavaScript。

## 本地运行与测试

从完整仓库的 `AINOOK-Review/` 目录运行。Python 需 3.10 或更新版本。

```sh
python -m ainook.site --port 7889 --no-scheduler --data-dir ../outputs/ainook
python -m unittest discover -s tests -p test_ainook.py
```

首页 `http://127.0.0.1:7889/`，资讯 `http://127.0.0.1:7889/news`。Windows 的 `start-local.cmd` 默认读取本目录下的数据。读取仓库根目录同步的刊次时，使用上面的命令。

完整刊次由内容方提供。只审阅七栏布局时，可把根目录现有的 `data/sample.json` **原样复制到独立临时目录**，命名为 `reader-edition.json`，并用 `--data-dir` 指向临时目录。用 `--wish-db` 把预览点击库也放在临时目录。

以 `meta.counts` 为准，当前一期的实际条数以数据文件为准。比如 `meta.counts.total` 是精选简报总数，`meta.counts.byCategory["模型更新"]` 是模型更新条数，`meta.counts.gossip` 是小道消息条数。历史样例用 `meta.counts.nav` 表示总数。样例缺少分项统计时，按 `news[].c` 分组并核对 `gossip` 数组。

## 代码地图

| 维护范围 | 入口 |
| --- | --- |
| 路由、页面响应、本地服务 | `ainook/site.py` |
| 资讯读取和七栏的唯一配置 | `ainook/news_edition.py` |
| 资讯杂志版与全文页 | `ainook/news_views.py`、`ainook/static/news-editorial.css` |
| 额度公告、官方链接和历史规则 | `ainook/catalog.json`、`ainook/quota.py` |
| 首页、导航、作者小屋与日夜背景 | `ainook/views.py`、`ainook/static/layout.html`、`ainook/static/home.css`、`ainook/static/theme.js`、`ainook/static/author.html` |
| 求重置、彩蛋与本地累计 | `ainook/static/home.js`、`ainook/static/burst.js`、`ainook/static/corner.js`、`ainook/wishes.py` |
| 旧采集实现和兼容依赖 | `ainook/news.py`、`ainook/news_events.py`、`ainook/news_translate.py`、`easel/` 内的最小依赖 |
| 回归测试与资源许可 | `tests/test_ainook.py`、`LICENSE`、`ainook/AIHOT-LICENSE.txt` 及 `ainook/static/assets/` 中的许可文件 |

## 资讯行为

- 使用上面的命令时，站点从仓库根目录的 `outputs/ainook/reader-edition.json` 只读加载外部刊次。程序在启动时加载，进程重新启动后读取下一期。日常新闻编写和更新归内容方。
- 七栏顺序为精选简报、模型更新、官方公告、行业热点、国际新闻、全球财经、小道消息。精选简报显示全量，子栏按数据的 `c` 字段读取，小道消息从 `gossip` 数组读取。
- 旧标签或未登记的类别只在全量页显示，等待内容方提供合法分类。站点不会给旧稿件推断新类别。
- 旧地址 `/news/ai`、`/updates`、`/official`、`/hot` 由固定刊次模式跳转到对应新地址，`/models` 兼容跳转到模型更新。
- 精选简报首页提升当前排序中的第一条普通新闻为头条，之后展示三条速览和连续列表。分类、搜索、来源筛选、日期筛选及分页共用现有查询。
- 点击标题进入独立全文页，显示刊次提供的完整段落、引文、来源及发布时间。页面上的返回链接直达文章所属栏目，浏览器后退可回到原先的筛选结果。
- 阅读器兼容内容方交付的两种刊次写法。省略 `meta.timezone` 时按北京时间解析，小道消息缺少 `id` 时使用原有 `k`，显式提供的 `id` 仍优先使用。

## 交接约定

- 网站源码、公共静态素材和测试保存在本目录。正式刊次、访客点击数据库、运行日志和凭据都留在运行环境。
- 固定刊次模式使用外部 JSON。`/news/sources` 显示外部每日提供数据的说明。旧采集与数据库代码保留便于追溯。
- 更新时按根目录 `AGENTS.md` 的范围和提交说明格式操作。页面改动验收七个栏目、搜索筛选、分页、完整正文、旧链接和桌面／手机导航。
