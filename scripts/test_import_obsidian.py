"""验证导入器的链接兼容性、代码保留和目录边界，不依赖第三方测试库。"""

import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import unquote

from import_obsidian import Publisher, REPO


class ImportCompatibilityTest(unittest.TestCase):
    """使用隔离的最小笔记库验证转换行为，不修改真实导入文件。"""

    def setUp(self) -> None:
        """建立临时笔记库、图片及已登记页面；无参数、返回值或预期异常。"""
        self.temp = tempfile.TemporaryDirectory(dir=REPO / "imports" / "obsidian", prefix="test-")
        self.root = Path(self.temp.name)
        self.source = self.root / "entry.md"
        self.source.write_text("# 入口\n", encoding="utf-8")
        self.image = self.root / "图片 空格&特殊#字符.png"
        self.image.write_bytes(b"image fixture")
        self.note = self.root / "参考 笔记.md"
        self.note.write_text("# 中文标题\n", encoding="utf-8")
        self.publisher = Publisher({"source_root": str(self.root.relative_to(REPO)), "entry": "entry.md", "slug": "test-import"})
        self.bundle = self.root / "output"
        self.publisher.pages[self.note] = (self.bundle, "/p/reference/")

    def tearDown(self) -> None:
        """清理本测试创建的临时目录；无参数、返回值或预期异常。"""
        self.temp.cleanup()

    def test_wiki_image_size_and_special_filename(self) -> None:
        """验证 Wiki 图片尺寸、中文、空格、& 和 # 字符均可正确转换。"""
        result = self.publisher._markdown(f"![[{self.image.name}|520]]", self.source, self.bundle, "/p/test-import/")
        self.assertIn('width="520"', result)
        self.assertIn('%20', result)
        self.assertIn('%23', result)
        self.assertEqual(len(self.publisher.outputs), 1)

    def test_markdown_links_and_reference_definitions(self) -> None:
        """验证编码地址、链接说明、引用式链接和中文标题锚点。"""
        text = '[正文](<参考%20笔记.md#中文标题> "说明")\n[笔记]: <参考 笔记.md> "说明"\n'
        result = self.publisher._markdown(text, self.source, self.bundle, "/p/test-import/")
        self.assertIn('../reference/#%E4%B8%AD%E6%96%87%E6%A0%87%E9%A2%98', result)
        self.assertIn('[笔记]: <../reference/> "说明"', result)

    def test_code_is_not_rewritten(self) -> None:
        """验证行内代码、反引号代码块和波浪号代码块逐字保留。"""
        text = '`[[不存在.md]]`\n\n```md\n![[不存在.png]]\n```\n\n~~~md\n[x](不存在.md)\n~~~\n'
        self.assertEqual(self.publisher._markdown(text, self.source, self.bundle, "/p/test-import/"), text)

    def test_vault_relative_and_parent_relative_paths(self) -> None:
        """验证笔记库前缀和相对于当前 Markdown 的父目录引用。"""
        child = self.root / "notes" / "child.md"
        child.parent.mkdir()
        child.write_text("", encoding="utf-8")
        self.assertEqual(self.publisher._resolve(f"{self.root.name}/{self.image.name}", child)[0], self.image)
        self.assertEqual(self.publisher._resolve(f"../{self.image.name}", child)[0], self.image)

    def test_missing_ambiguous_and_unsafe_paths_fail(self) -> None:
        """验证缺失资源、同名文件和越界路径不会被静默发布。"""
        with self.assertRaises(FileNotFoundError):
            self.publisher._resolve("missing.png", self.source)
        with self.assertRaises(FileNotFoundError):
            self.publisher._resolve("../../../README.md", self.source)
        other = self.root / "duplicate"
        other.mkdir()
        twin = self.root / "another"
        twin.mkdir()
        for directory in (other, twin):
            (directory / "collision.md").write_text("", encoding="utf-8")
            self.publisher.files.append(directory / "collision.md")
        # 根目录与当前目录都无法精确命中时，同名短链接必须报告歧义。
        with self.assertRaises(ValueError):
            self.publisher._resolve("collision.md", self.root / "unknown" / "child.md")

    def test_only_known_missing_images_get_notice(self) -> None:
        """验证缺图提示仅限明确登记的资源，意外缺图会中止导入。"""
        self.publisher.config["missing_assets"] = ["known.png"]
        result = self.publisher._markdown("![[known.png]]", self.source, self.bundle, "/p/test-import/")
        self.assertIn("原始导入缺少图片", result)
        self.assertNotIn("<img", result)
        with self.assertRaises(FileNotFoundError):
            self.publisher._markdown("![[unexpected.png]]", self.source, self.bundle, "/p/test-import/")

    def test_canvas_markdown_file_and_cross_canvas_links(self) -> None:
        """验证画布引用笔记时保留可加载的 Markdown、正文资源和完整笔记跳转。"""
        self.publisher.config["date"] = "2026-04-12T00:00:00+08:00"
        self.note.write_text(f"---\ntags: [测试]\n---\n# 中文标题\n![[{self.image.name}]]\n", encoding="utf-8")
        peer = self.root / "另一张画布.canvas"
        peer.write_text('{"nodes":[],"edges":[]}', encoding="utf-8")
        self.publisher.pages[peer] = (self.bundle, "/canvas/test-import/peer/")
        canvas = self.root / "sample.canvas"
        canvas.write_text(json.dumps({"nodes": [
            {"id": "note", "type": "file", "file": self.note.name, "subpath": "#中文标题", "x": 0, "y": 0, "width": 400, "height": 300},
            {"id": "peer", "type": "file", "file": peer.name, "x": 500, "y": 0, "width": 300, "height": 200}], "edges": []}), encoding="utf-8")
        self.publisher._canvas(canvas, self.bundle, "/canvas/test-import/current/")
        published = json.loads((self.bundle / "data.canvas").read_text(encoding="utf-8"))
        note, linked_canvas = published["nodes"]
        self.assertTrue(note["file"].endswith(".md"))
        self.assertIn("/p/reference/", note["website"])
        body = (self.bundle / unquote(note["file"])).read_text(encoding="utf-8")
        self.assertNotIn("tags:", body)
        self.assertIn("![", body)
        self.assertIn("%23", body)
        self.assertEqual(note["subpath"], "#中文标题")
        self.assertEqual(linked_canvas["file"], "../peer/")


if __name__ == "__main__":
    unittest.main()
