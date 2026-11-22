# AINOOK 作者小屋

[打开作者小屋](http://127.0.0.1:7896/author)

从项目根目录启动本机预览。

```powershell
python outputs/prototypes/ainook-author-gallery/serve.py
```

「一些奇思妙想」并排展示[作者小屋](http://127.0.0.1:7896/author?room=tram)和[阿灿的小屋](http://127.0.0.1:7896/author?friend=acan)。作者小屋里有原来的七个方案。点房间里的「一些奇思妙想」回到共享目录。原朋友目录和情侣电竞房的旧地址仍可访问。

新朋友登记在 `friends/rooms.json`。每个朋友的目录以该条目的 `id` 命名，包含 `room.html`、`room.css`、`room.js`、`room.webp` 和缩略图 `thumb.webp`。登记后的房间和现有房间一起展示在「一些奇思妙想」。

这个预览复用原有的插画、页面和交互。首版书房的新夜景在 `art/classic-night.webp` 中，三个室内方案的校正记录在 `study-corrections.json` 中，另有几处按房间加载的样式调整。

已在桌面和 320、390 像素手机画幅检查日夜画面与互动。`screenshots/all-rooms.png` 是前六版的日夜对照，`screenshots/tram-day-night.png` 是山坡电车的日夜对照。

## 初版书房夜景生成提示

```text
Edit the attached AINOOK physical miniature illustration into its precise NIGHT lighting pass. Nearly exact pixel registration to the source is crucial for UI overlays. The transparent canvas is still 1536 x 1024, landscape 3:2. Preserve the camera, crop, miniature scale, plinth edges and the position, size and silhouette of EVERY object pixel-for-pixel, including window bars, lamp body and cap, screen, book, rug, vinyl record and pot. The same fine wood and upholstery textures. Change only illumination and window content. Use a serene very dark indigo-blue forest and hills beyond the existing panes, a little blue night sky and a few pinprick gold lights in the far distance, no leftover bright day sky. The cool blue outdoor light through the window traces the desk edge and softens around it. A very faint, warm bounce from out of frame on the right gently makes the existing rug, book and lounge-chair readable. All indoor lamps and screens OFF, including the yellow desk lamp which must be a softly legible ordinary unlit warm yellow material, no halo or bloom. The CRT screen likewise is dark, no lettering. Let the scene be clear and richly dim, with directional shadows and actual material definition. Do not add a lamp, window divider, curtains, characters, props, title, labels, frame overlays or effects. Preserve exact overall transparency outside the crisp physical miniature. No new background or backing plate. This must match the reference image as closely as possible in composition and fit while being a genuine relighting.
```
