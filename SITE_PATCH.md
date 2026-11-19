# site.py 需要手工合入的两处补丁

`site.py` 不要整文件覆盖（你那边可能已有其它改动），只改下面两处。

## 补丁 1：让旧链接能进资讯路由（约 315 行）

原：

```python
                if (news_route in news_views.PAGES or news_route.startswith('/article/')
                        or (isinstance(app.news, NewsEdition) and news_route in EDITIONS)):
```

改为：

```python
                if (news_route in news_views.PAGES or news_route.startswith('/article/')
                        or (isinstance(app.news, NewsEdition)
                            and (news_route in EDITIONS or news_route in LEGACY_SECTIONS))):
```

`LEGACY_SECTIONS` 已在 `site.py` 第 21 行随 `EDITIONS` 一起导入，无需新增 import。

## 补丁 2：`/models` 的重定向目标（约 250 行）

原：

```python
            elif route == '/models':
                if api:
                    return self.respond(200, {'status': 'not_configured', 'items': []})
                return self.respond(302, b'', 'text/plain', {'Location': '/updates'})
```

把 `'/updates'` 改成 `'/news/model'`。否则 `/models` → `/updates` → 二次跳转，且旧 `/updates` 在新表里已不是一级路由，会绕远。

## 为什么要补丁 1

`LEGACY_SECTIONS` 的键（`/news/ai`、`/updates`、`/official`、`/hot`）只在 `read_news()` 内部生效。但请求先要穿过 `dispatch()` 的路由判定，判定条件原来只看 `PAGES` 和 `EDITIONS`，所以这些旧地址会在进入 `read_news()` 之前就被判 404。补丁 1 把它们放进来，之后才会命中 `read_news()` 里的 302 跳转。
