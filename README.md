# CoKiE_z 的游戏开发博客

记录 Unity 游戏开发、算法学习与项目实践。网站地址：<https://cokiez.github.io/>。

本站使用 Hugo + [Stack](https://github.com/CaiJimmy/hugo-theme-stack)，通过 GitHub Actions 部署到 GitHub Pages。文章写在 `content/post/`，每篇文章一个文件夹，正文使用 Markdown。

## 1. 新建文章

在仓库目录打开 PowerShell：

```powershell
# 进入仓库，后续命令均在这里执行。
Set-Location 'E:\CoKiEz Blog\CoKiEz.github.io'
# 如果当前终端找不到 hugo，使用本机已有程序的完整路径。
$hugoExe = 'E:\Hugo\hugo_extended_0.167.0_windows-amd64\hugo.exe'
# 使用中文注释的文章模板创建草稿，目录名建议使用英文和短横线。
& $hugoExe new content post/unity-movement/index.md
```

如果已经把 Hugo 加入 PATH，可将 `& $hugoExe` 换成 `hugo`。本地需要 Git、Go 和 Hugo Extended；当前部署使用 Hugo Extended 0.167.0。

打开生成的 `content/post/unity-movement/index.md`，修改标题、简介和正文。文件顶部两个 `---` 之间是文章配置，例如：

```yaml
---
title: "Unity 角色移动实践"
description: "记录角色移动的实现方法和遇到的问题。"
# slug 决定文章网址，发布后尽量不要修改，也不要与其他文章重复。
slug: "unity-movement"
# 改成实际发布日期；+08:00 表示北京时间。
date: 2026-10-05T20:00:00+08:00
# 写作期间保留 true，正式发布前改为 false。
draft: true
# 没有封面时留空；有封面时填写同目录内的文件名。
image: ""
categories: ["Unity"]
tags: ["C#", "角色控制"]
math: false
---
```

正文从第二个 `---` 后开始。使用 `## 小标题` 划分章节；代码块标明语言（例如 `csharp`），即可使用主题的代码高亮。

新文章模板为 `archetypes/post.md`，以后想调整默认字段或章节，修改这个文件即可。生成时自动填写标题、slug、日期，并默认设置为草稿。详见 [Hugo 文章模板文档](https://gohugo.io/content-management/archetypes/)。

## 2. 插入图片

图片和 `index.md` 放在同一文件夹：

```text
content/post/unity-movement/
├── index.md
├── cover.jpg
└── movement-demo.png
```

封面配置填写 `image: "cover.jpg"`；正文插图写成：

```markdown
![角色移动效果](movement-demo.png)
```

文章默认按发布日期从新到旧排序，不需要填写 `weight`。分类适合大方向，如 Unity、算法、项目实践；标签适合具体知识点，如对象池、动态规划。归档、分类、标签和搜索索引会在构建时自动更新，无需手工维护页面。

## 3. 本地预览

```powershell
# 显示草稿并启动本地服务，按 Ctrl+C 停止。
& $hugoExe server -D
```

访问终端显示的地址，通常是 <http://localhost:1313/>。保存文章后页面会自动刷新。

`-D` 只包含草稿；如果 `date` 或 `publishDate` 在未来，需要使用 `server -D -F` 才能预览。正式构建默认排除草稿和未来文章。详见 [Hugo 构建与预览说明](https://gohugo.io/getting-started/usage/)。

## 4. 正式发布

1. 将文章的 `draft` 改为 `false`，确认发布日期不晚于当前时间。
2. 检查标题、正文、图片、分类和标签。
3. 构建并推送源文件：

```powershell
# 清理输出中的旧文件并检查正式构建；public 仅用于生成结果，不要手动存放源文件。
& $hugoExe --cleanDestinationDir --minify
# 确认变更只包含计划发布的内容，再暂存文章及其图片。
git status --short
git add content/post/unity-movement
# 提交文章到本地仓库并推送；本仓库当前分支为 master。
git commit -m "新增：Unity 角色移动实践"
git push origin master
```

如果同时修改了配置或其他文件，需要将相应文件一起 `git add`。不要提交 `public/` 或 `resources/`，仓库已忽略这两个生成目录。

4. 打开仓库的 [Actions 页面](https://github.com/CoKiEz/CoKiEz.github.io/actions)，确认 **Build and deploy** 工作流的 `build` 和 `deploy` 均成功。
5. 访问文章地址，例如 `https://cokiez.github.io/p/unity-movement/`。

工作流在推送到 `master` 或 `main` 时构建和部署，也支持手动运行。它不会替你编写或提交本地文章；本地修改需要先提交、推送，网站才会更新。现有的 **Update theme** 工作流仅负责更新主题依赖。

未来日期文章不会到点自动上线：现有部署没有定时发布触发器，到时需重新推送或手动运行 **Build and deploy**。

## 5. 不使用命令行发布

也可以在 GitHub 仓库网页中选择 **Add file → Create new file**，输入 `content/post/文章英文名/index.md`，粘贴上面的文章配置和正文，将 `draft` 改为 `false`，再提交到 `master`。图片也上传到同一目录。提交会触发相同的部署流程。

## 6. 修改与删除文章

- 修改文章：编辑对应的 `index.md`，提交并推送。需要记录更新时间时可添加 `lastmod`，原始 `date` 可以保留。
- 删除文章：删除对应的文章文件夹，提交并推送，部署后归档和搜索会同步更新，旧文章地址将返回 404。
- 修改导航：`content/_index.md` 和 `content/page/` 下对应页面的 `menu` 配置。
- 修改个人链接：`content/page/links/index.md`。
- 修改博客名称：`config/_default/config.toml`。
- 修改头像、简介和侧栏：`assets/img/avatar.jpg`、`config/_default/params.toml`。

## 本次模板清理

已移除五篇示例文章及其图片、示例分类和未启用的英文站点配置；导航已改为中文，链接页已换成个人 GitHub。归档保留，2022/2023 示例年份会随示例文章一起消失。

尚无正式文章时，首页和归档显示提示，右侧自动隐藏空的归档、分类和标签。相关模板位于 `layouts/`，沿用 Stack 的列表与分页；更新主题后建议检查这些自定义模板的兼容性。没有额外创建占位博客。
