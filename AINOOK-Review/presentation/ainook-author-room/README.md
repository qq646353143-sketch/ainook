# AINOOK 作者小屋交互预览

在项目根目录用 Python 启动预览。

```powershell
python outputs/prototypes/ainook-author-room/serve.py
```

打开 [作者小屋](http://127.0.0.1:7892/author)，也可直接查看 [白天](http://127.0.0.1:7892/author?theme-preview=day) 和 [夜晚](http://127.0.0.1:7892/author?theme-preview=night)。停止这个预览进程即可退出。与 [现有作者小屋](http://127.0.0.1:7891/author) 可同时打开对照。

预览借用现有站点外壳及前沿资讯样式。额度追踪的「求重置」计数使用独立的本地副本，首次启动时从现有预览读取计数总额。房间内的互动状态随本次页面访问保留，刷新后恢复初始状态。

插画中的物件位置按原图宽高的百分比定位。更换画面构图时，在 `room.css` 里同步校准按钮和效果的位置。底部「作者手记」目前是占位。

## 插画来源

主图由 ImageGen 根据以下提示生成。预览采用保留透明通道的 WebP。

```text
Use case: stylized-concept.
Create the actual hero illustration asset for AINOOK's interactive author room. A complete small contemporary study / maker's living room as a single premium physical architectural miniature, open-front dollhouse cutaway, isolated on transparent background. Wide landscape canvas 3:2. Generously fill the frame (roughly 88% of width and 85% of height), show the entire cutaway and a small section of its beveled floor plinth, not cropped. Orthographic, gently elevated 2.5D view, broadly facing the front so individual objects stay easy to identify. Only rear wall and left return wall, other faces open. Composition is one coherent room, no panels. Hand-finished matte painted wood, pale chalky blue-grey plaster, faded teal shelving and window trim, European light oak, oatmeal upholstery and a few restrained burnt-orange accents; soft diffuse daylight and crisp contact shadows. Refined editorial model design, slightly illustrative, real texture at miniature scale, clean edges. Adult, quiet, inhabited; no people. Avoid pixel art, toy-like oversaturation, thick outlines, high gloss, clutter, harsh bloom or photographic life-size realism.
Scene layout for later click targets, keep objects distinct and enough space around them: on left side a narrow tall oak bookshelf with books and one little pot, and a single simple terracotta pot on the left front corner of the floor; in the central back wall one broad ribbed sage-trimmed window looking onto softly drawn misty hills, a long light-oak study desk underneath the window. On the clear LEFT half of this desk a distinctive small butter-yellow mushroom table lamp with dome shade and slender base, turned OFF so the illustration can be later illuminated via UI. On the RIGHT half of the desk one small chunky vintage teal computer with an unlit blue-grey CRT screen, keyboard and mouse visible. A single green chair tucked under the desk. Along the right side, separate from the desk, one light-oak low sideboard with two drawers, and one clear vintage record player with a black vinyl disc on top. A slightly rumpled oatmeal throw on a single low slate armchair near the right front, and a woven thin faded rust rug in the open center-front. Small details such as an open notebook and a mug, no logo, no legible lettering, no watermark, no overlays or interactive markers. Keep the lamp, CRT and black record easy to pick out. Dignified and beautifully composed. Transparent exterior including above and around room; everything outside the miniature must have alpha.
```
