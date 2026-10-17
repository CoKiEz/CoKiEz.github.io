#!/usr/bin/env python3
"""将指定 Obsidian 文章的可达依赖转换为 Hugo 页面包，原始文件只读。"""

from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import html
import json
from pathlib import Path
import posixpath
import re
import unicodedata
from urllib.parse import quote, unquote, urlsplit


REPO = Path(__file__).resolve().parents[1]
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif"}
# 将代码先隔离，避免把示例代码中的链接当成待发布的依赖。
CODE = re.compile(r"(?m)^ {0,3}(`{3,}|~{3,})[^\n]*\n[\s\S]*?^ {0,3}\1[ \t]*(?=\n|$)|(`+)[^\n]*?\2")
WIKI = re.compile(r"(!?)\[\[([^\]\n]+)\]\]")
# 支持尖括号地址及一层嵌套括号；更深的 Markdown 地址应使用尖括号写法。
LINK = re.compile(r'(!?\[[^\]\n]*\]\()(<[^>\n]+>|(?:[^\s()]|\([^()]*\))+)([ \t]+["\'][^\n]*?["\'])?\)')
REFERENCE = re.compile(r"(?m)^( {0,3}\[[^\]\n]+\]:[ \t]*)(<[^>\n]+>|\S+)")
# 只识别非转义的成对双星号，跳过三重星号以及内容首尾的空白。
STRONG = re.compile(r"(?<![\\*])\*\*(?![\s*])(.+?)(?<![\s\\])\*\*(?!\*)")


def normalize_punctuation_strong(text: str) -> str:
    """消除中文引号等标点与相邻正文导致的 CommonMark 加粗歧义。

    Args:
        text: 已隔离代码并完成链接转换的 Markdown；链接地址使用尖括号包裹。
    Returns:
        将存在标点边界歧义的成对加粗转换成 strong 标签，其余内容保持不变。
    Raises:
        无预期异常。
    """
    protected_tags: list[str] = []

    def protect_tag(match: re.Match) -> str:
        """暂存 HTML 标签和尖括号地址，避免改动图片属性、链接 URL 等内容。"""
        protected_tags.append(match.group())
        return f"\x00TAG{len(protected_tags) - 1}\x00"

    def punctuation(character: str) -> bool:
        """按 CommonMark 使用的 Unicode 标点及符号类别判断边界字符。"""
        return bool(character) and unicodedata.category(character)[0] in {"P", "S"}

    def replace_strong(match: re.Match) -> str:
        """仅替换会被标点边界规则拒绝的完整加粗，不处理未闭合标记。"""
        content = match[1]
        previous = masked[match.start() - 1] if match.start() else ""
        following = masked[match.end()] if match.end() < len(masked) else ""
        # CommonMark 不允许此处的标点紧贴外侧文字作为加粗边界。
        # 使用原生 strong 保持引号及内部 Markdown，不引入可见空格或零宽字符。
        invalid_open = punctuation(content[0]) and bool(previous) and not previous.isspace() and not punctuation(previous)
        invalid_close = punctuation(content[-1]) and bool(following) and not following.isspace() and not punctuation(following)
        return f"<strong>{content}</strong>" if invalid_open or invalid_close else match.group()

    masked = re.sub(r"<[^>\n]+>", protect_tag, text)
    normalized = STRONG.sub(replace_strong, masked)
    return re.sub(r"\x00TAG(\d+)\x00", lambda match: protected_tags[int(match[1])], normalized)


def json_text(value: object) -> str:
    """序列化 UTF-8 JSON，同时用于合法的 TOML 字符串和数组。

    Args:
        value: 可以由 JSON 序列化的值。
    Returns:
        保留中文的 JSON 文本。
    Raises:
        TypeError: 值无法被 JSON 序列化时抛出。
    """
    return json.dumps(value, ensure_ascii=False)


def frontmatter(values: dict) -> str:
    """生成 Hugo TOML 元数据。

    Args:
        values: 字段名与标量或数组值的映射。
    Returns:
        包含起止分隔符和中文生成说明的 TOML 文本。
    Raises:
        TypeError: 字段值无法序列化时抛出。
    """
    lines = ["+++", "# 由 scripts/import_obsidian.py 生成，请修改导入源或发布配置。"]
    lines.extend(f"{key} = {json_text(value)}" for key, value in values.items())
    return "\n".join([*lines, "+++", "", ""])


class Publisher:
    """管理单篇公开文章的依赖闭包及输出，不扫描发布无关内容。

    Args:
        config: 含导入根目录、入口文件、slug 和文章元数据的配置。
    Attributes:
        outputs: 本次生成的文件及其 SHA-256，用于验收和审阅。
    Raises:
        ValueError: 配置越界、slug 非法或存在不安全引用时抛出。
        FileNotFoundError: 导入目录或入口文件不存在时抛出。
    """

    def __init__(self, config: dict):
        """初始化路径边界与依赖索引；参数、异常见类文档，无返回值。"""
        self.config = config
        self.root = (REPO / config["source_root"]).resolve(strict=True)
        if not self.root.is_relative_to(REPO / "imports" / "obsidian"):
            raise ValueError("导入源必须位于 imports/obsidian 下")
        self.slug = config["slug"]
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", self.slug):
            raise ValueError("slug 只允许小写英文、数字和短横线")
        self.entry = (self.root / config["entry"]).resolve(strict=True)
        if not self.entry.is_relative_to(self.root):
            raise ValueError("入口文件越过导入根目录")
        self.files = sorted(path.resolve() for path in self.root.rglob("*")
                            if path.is_file() and path.resolve().is_relative_to(self.root))
        self.pages: dict[Path, tuple[Path, str]] = {}
        self.outputs: dict[str, str] = {}
        self.sources: dict[str, str] = {}
        self.canvas_stats: dict[str, dict] = {}
        self.missing: set[str] = set()

    def _resolve(self, target: str, source: Path) -> tuple[Path, str]:
        """解析相对路径、库内路径或唯一文件名；歧义和缺失引用直接报错。"""
        decoded = unquote(target).replace("\\", "/")
        # 先匹配完整文件名，允许文件名自身包含 #、? 等特殊字符。
        for name, suffix in [(decoded, ""), *self._fragment_candidates(decoded)]:
            relative = name.removeprefix(self.root.name + "/").lstrip("/")
            candidates = [source.parent / name, self.root / relative]
            for candidate in candidates:
                for path in [candidate, candidate.with_suffix(".md") if not candidate.suffix else candidate]:
                    resolved = path.resolve()
                    if resolved.is_file() and resolved.is_relative_to(self.root):
                        return resolved, suffix
            # Obsidian 最短 WikiLink 可以省略所在目录，但不能静默选择同名文件。
            matches = [p for p in self.files if p.name == Path(name).name or (not Path(name).suffix and p.stem == Path(name).name)]
            if len(matches) == 1 and "/" not in name:
                return matches[0], suffix
            if len(matches) > 1 and "/" not in name:
                raise ValueError(f"引用存在歧义：{source.name} -> {target}")
        raise FileNotFoundError(f"找不到公开依赖：{source.relative_to(self.root)} -> {target}")

    @staticmethod
    def _fragment_candidates(target: str) -> list[tuple[str, str]]:
        """拆出标题或查询后缀；完整文件名查找优先于此回退逻辑。"""
        match = re.search(r"[?#]", target)
        return [(target[:match.start()], target[match.start():])] if match else []

    @staticmethod
    def _relative_url(target: str, current: str) -> str:
        """生成相对页面目录的编码 URL，适用于域名根目录和子路径部署。"""
        relative = posixpath.relpath(target, current)
        return quote(relative, safe="/-._~") + ("/" if target.endswith("/") and not relative.endswith("/") else "")

    def _write(self, path: Path, content: str | bytes) -> None:
        """记录生成文件的哈希并写入，拒绝覆盖手写的页面包。"""
        bundle_index = next((parent / "index.md" for parent in path.parents if parent.parent == REPO / "content" / "post" or parent.parent == REPO / "content" / "canvas" / self.slug), None)
        if bundle_index and bundle_index.exists() and "obsidian_generated = true" not in bundle_index.read_text(encoding="utf-8"):
            raise ValueError(f"拒绝覆盖非自动生成的页面包：{bundle_index}")
        data = content.encode("utf-8") if isinstance(content, str) else content
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.outputs[path.relative_to(REPO).as_posix()] = sha256(data).hexdigest()

    def _publish(self, source: Path) -> tuple[Path, str]:
        """按依赖递归生成页面；提前登记路径以终止循环引用。"""
        if source in self.pages:
            return self.pages[source]
        identity = sha256(source.relative_to(self.root).as_posix().encode("utf-8")).hexdigest()[:12]
        is_entry = source == self.entry
        if source.suffix.lower() == ".canvas":
            bundle = REPO / "content" / "canvas" / self.slug / identity
            uri = f"/canvas/{self.slug}/{identity}/"
        elif source.suffix.lower() == ".md":
            bundle = REPO / "content" / "post" / (self.slug if is_entry else f"{self.slug}-note-{identity}")
            uri = f"/p/{bundle.name}/"
        else:
            raise ValueError(f"不支持生成页面：{source}")
        self.pages[source] = (bundle, uri)
        self.sources[source.relative_to(self.root).as_posix()] = sha256(source.read_bytes()).hexdigest()
        if source.suffix.lower() == ".canvas":
            self._canvas(source, bundle, uri)
        else:
            raw = source.read_text(encoding="utf-8-sig")
            # Obsidian 元数据与 Hugo 字段不同；正文仅转换引用和有歧义的加粗标记。
            body = re.sub(r"\A---\n.*?\n---(?:\n|$)", "", raw, count=1, flags=re.S)
            meta = {"title": self.config["title"] if is_entry else source.stem,
                    "slug": bundle.name, "date": self.config["date"], "draft": False,
                    "obsidian_generated": True, "toc": True}
            if is_entry:
                meta.update({key: self.config[key] for key in ("description", "categories", "tags")})
            else:
                meta["_build"] = {"list": "never"}
            # 内部笔记使用独立字段，TOML 的嵌套 build 配置在下方显式输出。
            hidden = meta.pop("_build", None)
            header = frontmatter(meta)
            if hidden:
                header = header.replace("+++\n\n", '[build]\nlist = "never"\n+++\n\n')
            self._write(bundle / "index.md", header + self._markdown(body, source, bundle, uri))
        return bundle, uri

    def _target(self, target: str, source: Path, bundle: Path, uri: str) -> tuple[str, Path | None]:
        """保留外链和页内锚点，将本地依赖转换为可公开访问的 URL。"""
        if target.startswith("#") or urlsplit(target).scheme or target.startswith("//"):
            scheme = urlsplit(target).scheme.lower()
            if scheme and scheme not in {"https", "http", "mailto", "tel"}:
                raise ValueError(f"不支持的链接协议：{scheme}")
            return target, None
        resolved, suffix = self._resolve(target, source)
        if resolved.suffix.lower() in {".md", ".canvas"}:
            _, destination = self._publish(resolved)
            if suffix.startswith("#") and not suffix.startswith("#^"):
                # 与 Hugo 默认标题 ID 规则保持一致，保留中文标题。
                suffix = "#" + quote(re.sub(r"[^\w\- ]", "", suffix[1:]).lower().replace(" ", "-"))
            return self._relative_url(destination, uri) + suffix, resolved
        relative = resolved.relative_to(self.root).as_posix()
        identity = sha256(relative.encode("utf-8")).hexdigest()[:12]
        resource = Path("media") / identity / resolved.name
        self._write(bundle / resource, resolved.read_bytes())
        self.sources[relative] = sha256(resolved.read_bytes()).hexdigest()
        return quote(resource.as_posix(), safe="/-._~") + suffix, resolved

    def _markdown(self, text: str, source: Path, bundle: Path, uri: str) -> str:
        """转换引用、图片和标点边界加粗，代码片段逐字保留。"""
        protected: list[str] = []

        def protect(match: re.Match) -> str:
            """暂存代码片段并返回不会匹配 Markdown 链接的占位符。"""
            protected.append(match.group())
            return f"\x00CODE{len(protected) - 1}\x00"

        def wiki(match: re.Match) -> str:
            """将单个 WikiLink 或嵌入转换为标准 Markdown 或图片标签。"""
            embedded, inner = match.groups()
            target, _, alias = inner.partition("|")
            try:
                url, resolved = self._target(target, source, bundle, uri)
            except FileNotFoundError:
                # 只为配置中明确登记的已知缺图显示提示，其他缺失依赖继续阻止导入。
                if not embedded or target not in self.config.get("missing_assets", []):
                    raise
                self.missing.add(target)
                return f'<span class="obsidian-missing-asset" role="note">【原始导入缺少图片：{html.escape(target)}】</span>'
            label = alias or (resolved.stem if resolved else target)
            if embedded and resolved and resolved.suffix.lower() in IMAGE_TYPES:
                size = re.fullmatch(r"(\d+)(?:x(\d+))?", alias)
                if size:
                    dimensions = f' width="{size[1]}"' + (f' height="{size[2]}"' if size[2] else "")
                    return f'<img src="{html.escape(url, quote=True)}" alt="{html.escape(resolved.stem, quote=True)}"{dimensions} loading="lazy">'
                return f"![{label}](<{url}>)"
            return f"[{label}](<{url}>)"

        def ordinary(match: re.Match) -> str:
            """转换普通 Markdown 地址并保留原有标题与链接说明。"""
            prefix, target, title = match.groups()
            url, _ = self._target(target.strip("<>"), source, bundle, uri)
            return f"{prefix}<{url}>{title or ''})"

        def reference(match: re.Match) -> str:
            """转换引用式链接定义，其引用名称和可选标题保持原样。"""
            prefix, target = match.groups()
            url, _ = self._target(target.strip("<>"), source, bundle, uri)
            return f"{prefix}<{url}>"

        text = CODE.sub(protect, text)
        # 普通链接先处理，防止 WikiLink 的生成结果被重复解析。
        text = LINK.sub(ordinary, text)
        text = REFERENCE.sub(reference, text)
        text = WIKI.sub(wiki, text)
        text = normalize_punctuation_strong(text)
        return re.sub(r"\x00CODE(\d+)\x00", lambda m: protected[int(m[1])], text)

    def _canvas(self, source: Path, bundle: Path, uri: str) -> None:
        """保留 JSON Canvas 结构与坐标，只转换文件、背景及正文中的引用。"""
        data = json.loads(source.read_text(encoding="utf-8-sig"))
        for node in data.get("nodes", []):
            for field in ("file", "background"):
                if node.get(field):
                    target = node[field]
                    node[field], resolved = self._target(target, source, bundle, uri)
                    if field == "file" and resolved and resolved.suffix.lower() == ".md":
                        # 保留 .md 后缀供阅读器识别，并另存页面地址用于打开完整笔记。
                        identity = sha256(resolved.relative_to(self.root).as_posix().encode("utf-8")).hexdigest()[:12]
                        resource = Path("notes") / identity / resolved.name
                        raw = resolved.read_text(encoding="utf-8-sig")
                        body = re.sub(r"\A---\n.*?\n---(?:\n|$)", "", raw, count=1, flags=re.S)
                        self._write(bundle / resource, self._markdown(body, resolved, bundle, uri))
                        node["website"] = node[field]
                        node[field] = quote(resource.as_posix(), safe="/-._~")
            if node.get("text"):
                node["text"] = self._markdown(node["text"], source, bundle, uri)
            if node.get("url"):
                node["url"], _ = self._target(node["url"], source, bundle, uri)
        stats = {"nodes": dict(Counter(node["type"] for node in data.get("nodes", []))),
                 "edges": len(data.get("edges", [])), "uri": uri}
        self.canvas_stats[source.relative_to(self.root).as_posix()] = stats
        self._write(bundle / "data.canvas", json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        meta = {"title": source.stem, "date": self.config["date"], "draft": False,
                "obsidian_generated": True, "article_ref": f"/post/{self.slug}",
                "canvas_nodes": sum(stats["nodes"].values()), "canvas_edges": stats["edges"]}
        header = frontmatter(meta).replace("+++\n\n", '[build]\nlist = "never"\n+++\n\n')
        self._write(bundle / "index.md", header)

    def run(self) -> dict:
        """生成文章及可达资源并写入审阅清单。

        Returns:
            包含源文件、生成文件哈希及画布统计的清单。
        Raises:
            OSError: 文件读取或写入失败时抛出。
            ValueError: 存在歧义、不安全链接或非法 JSON 时抛出。
            FileNotFoundError: 某个被引用的本地资源不存在时抛出。
        """
        self._publish(self.entry)
        result = {"entry": self.config["entry"], "article": f"/p/{self.slug}/",
                  "sources": dict(sorted(self.sources.items())),
                  "outputs": dict(sorted(self.outputs.items())), "canvases": self.canvas_stats,
                  "missing_assets": sorted(self.missing)}
        manifest = REPO / "Docs" / "obsidian-publication-manifest.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result


def main() -> None:
    """读取发布配置并执行转换。

    Returns:
        无；在标准输出打印发布数量。
    Raises:
        OSError: 配置或依赖不可读、生成文件不可写时抛出。
        ValueError: 配置、路径、链接或 Canvas 数据不合法时抛出。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=REPO / "scripts" / "obsidian-publication.json", help="发布配置 JSON 路径")
    args = parser.parse_args()
    result = Publisher(json.loads(args.config.read_text(encoding="utf-8"))).run()
    print(f"Imported {len(result['sources'])} source files; generated {len(result['outputs'])} files; {len(result['canvases'])} canvases.")


if __name__ == "__main__":
    main()
