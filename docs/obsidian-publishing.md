# Obsidian 发布记录

当前完成阶段一及阶段二：文章导入、目录修复与独立 Canvas 阅读器。工作流的完整验收及最终部署准备属于阶段三，等待阶段二确认后继续。

## 文件与发布边界

- 导入源：`imports/obsidian/Git工作流/`，转换器只读，不修改原文。
- 配置：`scripts/obsidian-publication.json`，明确指定入口、URL、标题、日期、分类和标签。
- 转换器：`scripts/import_obsidian.py`，仅使用 Python 3.10+ 标准库，无 pip/npm 依赖。
- 文章：`content/post/git-sourcetree-teamwork/index.md`，地址为 `/p/git-sourcetree-teamwork/`。
- Canvas 页面包：`content/canvas/git-sourcetree-teamwork/<稳定标识>/`。
- 共用模板：`layouts/canvas/single.html`，独立全宽阅读页面，沿用 Stack 的配色与主题切换。
- 阅读器适配：`assets/js/canvas-reader.js` 与 `assets/scss/custom.scss`。
- 目录适配：`layouts/_partials/article/components/toc.html`，仅导入文章改为完整的无自动编号目录。
- 浏览器依赖：`package.json` 与 `package-lock.json`，固定 JSON Canvas Viewer 4.3.2 及其依赖。
- 开源许可：`static/licenses/canvas-reader/`，随站点输出上游组件许可。
- 审阅清单：`scripts/obsidian-publication-manifest.json`，记录公开源文件及生成文件的 SHA-256。

当前公开闭包为 1 篇 Markdown、4 个 Canvas、47 张图片，共 52 个现有源文件。生成 5 个页面、4 个 `data.canvas` 和 47 张图片，共 56 个文件。未引用的 `Canvas/Git工作流.canvas`（空画布）和 `_Images/图3-1系统功能结构图.png` 不发布。

`imports/obsidian/` 已加入 Git 忽略列表；只提交转换后实际需要的内容。Hugo 不会把导入目录或 scripts/docs 作为网站内容输出。现有 Actions 已有基于锁文件的 `npm ci` 步骤，Node 24 满足依赖要求；可直接构建已生成的 content 文件，不需要在发布服务器安装 Python。工作流失败处理及完整发布检查留到阶段三。

原文元数据使用 `data: 2026-4-12`，Hugo 需要 `date`。发布配置明确将其映射为 `2026-04-12T00:00:00+08:00`。正文标题级别与文本保留，仅转换资源引用。

## 重新生成与预览

在仓库根目录执行：

```powershell
# 首次使用或锁文件更新后，安装固定的阅读器依赖；无需单独运行前端构建。
npm ci --ignore-scripts
# 将被引用的公开笔记及附件转换为 Hugo 页面包。
python scripts/import_obsidian.py
# 验证链接、代码保留、特殊文件名及路径边界。
python -m unittest discover -s scripts -p test_import_obsidian.py -v
# 使用项目当前版本构建，生成结果位于 public。
$hugoExe = 'E:\Hugo\hugo_extended_0.167.0_windows-amd64\hugo.exe'
& $hugoExe --cleanDestinationDir --gc --minify
# 启动主题预览，文章无需 -D 或 -F。
& $hugoExe server
```

本阶段会话的预览地址为 <http://localhost:1313/p/git-sourcetree-teamwork/>。正式发布操作仍遵循 README；当前没有执行提交、推送或线上部署。

不要手工编辑生成页面包：再次导入会覆盖同名生成文件。更改源文件后需重新运行转换器；源文件的移动或删除目前不会自动删除历史生成文件，发布前应结合 manifest 和 Git 差异移除不再使用的生成内容，避免遗留旧公开资源。

## 引用处理

- 支持普通 Markdown 链接、引用式链接、WikiLinks、图片嵌入，以及 Canvas 引用。
- 支持相对目录、`../`、导入根目录前缀和唯一的短文件名；同名短链接有歧义时中止导入。
- 中文、空格、`&`、`#` 等文件名保留并进行 URL 编码；文件名自身的 `#` 优先按真实文件匹配。
- 图片 `|宽度` 和 `|宽度x高度` 转成 HTML 图片尺寸；普通图片继续使用 Stack 图片模板。
- 行内代码和围栏代码块中的链接示例不转换。外部 HTTP(S) 链接保留。
- 本地 Markdown 依赖会递归生成隐藏于列表的页面，Canvas 同样递归处理文件、背景、文本和 URL；当前真实 Canvas 只引用 PNG 图片。Markdown 文件节点会额外生成可加载的正文资源，并通过 `website` 扩展字段记录完整笔记页面地址。
- 普通 Markdown 含空格的地址应使用 `<路径>` 或百分号编码；多层括号的地址也应使用尖括号。Markdown 嵌入目前转换成阅读链接，尚未实现内嵌正文、Obsidian 块引用或特殊插件语法。
- 未明确登记的缺失依赖、越界路径或不支持的链接协议会阻止导入。

## Canvas 数据与阅读器调研

实际 Canvas 顶层为 `nodes` 和 `edges`；文件节点含 `file`，文本节点含 Markdown `text`，节点坐标与尺寸由 `x/y/width/height` 给出，分组由 `type: group` 表示。转换保留节点 ID、坐标、颜色、分组与连线，仅重写资源地址。

| Canvas | 图片节点 | 文字节点 | 分组 | 连线 |
| --- | ---: | ---: | ---: | ---: |
| Github仓库的创建&克隆 | 5 | 0 | 0 | 4 |
| Git网路配置 | 6 | 8 | 4 | 2 |
| Unity项目初始化配置 | 9 | 2 | 1 | 8 |
| Unity特殊文件的配置和管理 | 4 | 5 | 0 | 5 |

已采用 [JSON Canvas Viewer](https://github.com/Hesprs/JSON-Canvas-Viewer) 4.3.2 的原生 JavaScript 接口，由 Hugo 内置 esbuild 打包，仅在 Canvas 页面加载。无需迁移博客或引入其他站点框架，也不在运行时从 CDN 获取阅读器。Markdown 使用上游 Marked + DOMPurify 解析与净化。

阶段二补充了中文控件、滚轮缩放、拖拽、适应屏幕、100% 显示、全屏、返回文章、主题同步和原图链接。全屏优先使用浏览器 API，受限浏览器回退到铺满当前页面的模式。工具栏保留在全屏区域内。键盘聚焦画布后可使用 `+`/`-` 缩放、`0` 适应屏幕、`f` 切换全屏。

图片按完整比例显示，避免长截图被裁切。点击文字或 Markdown 节点后可滚动正文、选择文字和打开链接。文件节点中的 Markdown 会加载正文，并提供完整笔记链接；嵌套 Canvas、其他附件与 URL 节点显示为链接卡片，避免直接内嵌外部网页造成跨站限制。

下载的 JSON 已重写为网站相对资源地址，适用于在线使用；它不是包含全部附件的离线笔记库打包。

## 本地验收结果与待处理内容

- Hugo Extended 0.167.0 正式构建通过，使用 Stack v4.0.3，没有修改主题版本或部署工作流。
- 7 项转换兼容性测试通过，新增 Canvas Markdown 文件节点及跨画布引用测试。
- Chrome 无头浏览器检查文章 30 个正文标题、23 张正文图片、5 张带指定尺寸的图片和 4 个 Canvas 跳转；图片全部成功解码。
- 4 个 Canvas 入口页及数据返回 HTTP 200；24 个 Canvas 图片引用全部返回 HTTP 200，返回文章链接正确。
- 亮暗两种主题已截图检查；390px 宽移动页面没有横向溢出；页面 JavaScript 无未捕获异常。
- 本地截图及浏览器报告位于 `.artifacts/article-light.png`、`.artifacts/article-dark.png`、`.artifacts/article-mobile.png` 和 `.artifacts/browser-stage1.json`，不提交。
- 修复后的目录包含 30 个标题链接，与正文一一对应；没有额外自动编号、缺失标题或失效锚点。一级标题下直接出现三级标题时不显示空列表标记。普通文章继续使用原有目录配置。
- 四张实际画布共 44 个节点（24 图片、15 文字、5 分组）和 19 条连线已检查；24 张图片全部成功解码，初始适应视图中所有内容节点位于画布可见区域。
- 四张画布分别通过真实浏览器鼠标事件验证放大、缩小、滚轮缩放、拖拽、100% 显示、适应屏幕、原生全屏进入和退出，以及亮暗色同步。
- 390px 移动阅读页无横向溢出；没有页面 JavaScript 未捕获异常。
- 通过浏览器请求拦截提供独立样例，不向博客添加测试笔记：验证了 Markdown 文件正文、图片、代码块、完整笔记链接、外链、跨 Canvas 跳转、返回文章、空画布和 HTTP 503 错误提示。Markdown 中的脚本内容没有执行。
- 阶段二截图：`.artifacts/article-toc-fixed.png`、`.artifacts/canvas-<画布标识>.png`、`.artifacts/canvas-mobile.png`；报告为 `.artifacts/browser-stage2.json`，均不提交。

此前缺少的 `Pasted image 20261016012400.png` 与 `Pasted image 20261016012532.png` 已由用户补回导入目录并重新转换，当前没有缺图提示或缺图例外配置。

当前范围内没有阻断阶段二验收的问题。未实现 Obsidian 插件语法、块引用锚点和 Markdown 嵌入正文展开；分组背景图、复杂媒体附件及特殊连线端点样式不在本次真实画布中，尚未单独验证。浏览器兼容性实测为本机 Chrome，不代表所有移动浏览器均已实测。

阶段三待执行：模拟 GitHub Actions 的干净依赖安装、生产资源与链接检查、现有博客回归，以及整理最终部署操作；执行前等待用户确认。没有修改部署工作流、提交代码、推送或部署线上网站。
