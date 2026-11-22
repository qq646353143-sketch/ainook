# AINOOK 正式部署

Cloudflare 部署位于 `cloud/`。Python 常驻入口为 `presentation/ainook-author-gallery/serve.py`。两个入口共用现有页面、资讯与小屋素材。

## Cloudflare

使用 `python3 AINOOK-Review/cloud/build.py` 将现有页面和公开素材打包为静态资源。Cloudflare Worker 处理搜索和筛选、额度卡片及点击计数，D1 用来保存点击数和最后一次校验通过的额度快照。数据库结构见 `cloud/schema.sql`。现有本地 SQLite 文件、运行日志和工具凭据不属于部署资源。

从 `AINOOK-Review/cloud` 目录部署时先运行 `python3 build.py`，再运行 `npx wrangler deploy`。GitHub 自动构建使用相同的根目录和命令。Cloudflare 按每小时第 57 分钟从 GitHub 取额度快照。每日资讯任务在北京时间 08:45 校验和更新 `AINOOK-Review/published/reader-cloud.json`，随后由 Cloudflare 构建并发布。验证未通过时保留原来的数据。

在 Cloudflare 的「设置 → 构建」中，生产分支填 `main`，根目录填 `AINOOK-Review/cloud`，构建命令和部署命令使用上面的两条命令。「禁用构建」保持关闭，部署使用 Cloudflare 生成的构建令牌。连接后，下一次向 `main` 推送提交时会开始构建。在「部署」中核对构建结果和提交版本，再到公网首页检查。

运行时的 `DB` 绑定使用 `ainook-site` 保存点击计数和额度快照，`WISH_LIMIT` 限制过于频繁的点击请求。当前无需额外的运行时变量、构建密钥、部署挂钩、消息队列或邮件触发器。每天 08:45 的资讯任务由 GitHub Actions 触发，设置里的每小时第 57 分钟触发器负责读取额度快照。

## Python 常驻部署

用 Python 3.11 或更新版本启动。服务器需要系统时区数据和出站 HTTPS。站点可以在 Linux 主机上常驻，由反向代理处理公网 HTTPS。

## 持久目录

在源码目录之外准备一个持久目录。为运行网站的用户开启必要的读写权限。

- `reader-edition.json` 由内容方交付。用仓库根目录的同步脚本校验后导入正式目录。站点在启动时读取刊次，导入成功后重启服务即可显示新一期。
- `verified.json` 保存额度监测快照，`wishes.sqlite3` 保存求重置的累计次数。由正式站在持久目录中维护。
- `public-origin.json` 存放实际正式地址，格式如 `{"origin":"https://ainook.example","public_scope":"official"}`。部署时替换示例域名。凭据通过主机的环境变量管理。

## 启动

从仓库的 `AINOOK-Review/` 目录运行，示例持久目录为 `/var/lib/ainook`。

```sh
python3 presentation/ainook-author-gallery/serve.py \
  --production --port 7896 \
  --data-dir /var/lib/ainook \
  --wish-db /var/lib/ainook/wishes.sqlite3 \
  --origin-file /var/lib/ainook/public-origin.json
```

用主机的进程管理工具配置自动启动和故障重启。将域名的 HTTPS 请求转发至同机的 `127.0.0.1:7896`，并把原请求的 `Host` 传给应用。只开放反向代理的公网入口。发布前校验正式地址与 `public-origin.json` 一致。

正式模式要求有效刊次。额度监测由 GitHub Actions 每小时启动一次，计划在每小时的第 41 分钟运行。任务读取 `data/reset-watch.json` 中已有的编辑记录，检查 Codex 公开重置索引，以及 Anthropic 和 xAI 的公开发帖镜像。镜像用于找线索，只有能核对到官方原帖并明确识别预告或发放的消息才会写入 `AINOOK-Review/published/reset-watch-hourly.json`。该任务无需 X API 密钥，覆盖取决于公开索引和镜像的更新。

站点在启动时从 GitHub 下载额度快照，此后每小时再下载一次。下载或校验失败时沿用上次成功的数据。预告显示黄灯，确认发放的发卡和通用重置在北京时间当天显示绿灯。已经打开的页面会通过站内接口更新显示。做隔离检查时可加 `--no-quota-scheduler`；需要验证单独的快照地址时可使用 `--reset-feed-url`。

在真实公网地址打开首页、七个资讯栏目、资讯详情、作者小屋和两个朋友的小屋，测试日夜切换、求重置计数的写入与读取。随后从中国大陆不同线路测试首页和手机小屋素材。部署验证通过前保留上一版本的运行配置及持久数据备份。
