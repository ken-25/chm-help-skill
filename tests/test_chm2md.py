import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import chm2md  # noqa: E402


def conv(html, link=lambda h: None, img=lambda s, a: f"[図: {a or s}]"):
    c = chm2md.MarkdownConverter(link, img)
    c.feed(html)
    c.close()
    return c.title, c.markdown()


class SitemapTest(unittest.TestCase):
    def test_nested_toc(self):
        hhc = """<UL>
          <LI><OBJECT type="text/sitemap"><param name="Name" value="章"></OBJECT>
          <UL>
            <LI><OBJECT type="text/sitemap"><param name="Name" value="節A">
                <param name="Local" value="HTML/a.html"></OBJECT>
            <LI><OBJECT type="text/sitemap"><param name="Name" value="節B">
                <param name="Local" value="HTML\\b.html#x"></OBJECT>
          </UL>
          <LI><OBJECT type="text/sitemap"><param name="Name" value="付録">
              <param name="Local" value="c.htm"></OBJECT>
        </UL>"""
        root = chm2md.parse_sitemap(hhc)
        top = root["children"]
        self.assertEqual([n["name"] for n in top], ["章", "付録"])
        self.assertEqual([n["name"] for n in top[0]["children"]], ["節A", "節B"])
        self.assertEqual(chm2md.norm_local(top[0]["children"][1]["locals"][0]), "HTML/b.html")

    def test_norm_local_msits(self):
        self.assertEqual(chm2md.norm_local("MS-ITS:Base.chm::/Base/x.htm"), "Base/x.htm")

    def test_same_title_width(self):
        self.assertTrue(chm2md._same("ＣＧウィンドウ", "CGウィンドウ"))
        self.assertFalse(chm2md._same("ＣＧ", "CAD"))


class MarkdownTest(unittest.TestCase):
    def test_headings_lists_entities(self):
        title, md = conv("<html><head><title>T&nbsp;1</title><script>x()</script></head>"
                         "<body><h1>[&nbsp;検索&nbsp;] ダイアログ</h1><p>本文<br>次行</p>"
                         "<ul><li>a</li><li>b<ol><li>c</li></ol></li></ul></body></html>")
        self.assertEqual(title, "T\xa01")
        self.assertIn("# [ 検索 ] ダイアログ", md)
        self.assertIn("本文\n次行", md)
        self.assertIn("- a\n- b", md)
        self.assertIn("\n  1. c", md)
        self.assertNotIn("x()", md)

    def test_default_class_map(self):
        _, md = conv('<div class="title">配置</div><div class="operation">操作方法</div>'
                     '<div class="operation_step"><span class="operation_number">1</span>'
                     '<span>クリックします。</span></div>'
                     '<div class="operation_detail">補足です。</div>')
        self.assertIn("# 配置", md)
        self.assertIn("## 操作方法", md)
        self.assertIn("1. クリックします。", md)
        self.assertIn("   - 補足です。", md)

    def test_table_and_links_and_images(self):
        _, md = conv('<table><tr><th>項目</th><th>説明</th></tr>'
                     '<tr><td>[OK]</td><td>確定 | 閉じる</td></tr></table>'
                     '<p><a href="x.html">リンク</a> <a href="javascript:f()">JS</a>'
                     '<img src="img/p.png"></p>',
                     link=lambda h: "x.md" if h == "x.html" else None)
        self.assertIn("| 項目 | 説明 |\n|---|---|\n| [OK] | 確定 \\| 閉じる |", md)
        self.assertIn("[リンク](x.md)", md)
        self.assertIn("JS", md)
        self.assertIn("[図: img/p.png]", md)

    def test_unclosed_paragraphs(self):
        _, md = conv("<p>一<p>二<p>三")
        self.assertEqual(md, "一\n\n二\n\n三\n")


class BuildTest(unittest.TestCase):
    def test_build_from_raw(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            raw = d / "raw"
            (raw / "HTML").mkdir(parents=True)
            (raw / "toc.hhc").write_text(
                '<UL><LI><OBJECT type="text/sitemap"><param name="Name" value="ガイド">'
                '</OBJECT><UL><LI><OBJECT type="text/sitemap"><param name="Name" value="画面">'
                '<param name="Local" value="HTML/a.html"></OBJECT></UL></UL>', encoding="cp932")
            (raw / "HTML" / "a.html").write_bytes(
                '<meta charset="shift_jis"><title>画面</title><div class="title">画面</div>'
                '<p><a href="b.html">次へ</a></p>'.encode("cp932"))
            (raw / "HTML" / "b.html").write_bytes("<title>孤立</title><p>本文</p>".encode("cp932"))
            chm = d / "x.chm"
            chm.write_bytes(b"dummy")
            out = d / "skill"
            out.mkdir()
            stats = chm2md._build_from_raw(chm, raw, out, "x-help", "X", False,
                                           chm2md.DEFAULT_CLASS_MAP)
            self.assertEqual(stats["pages"], 2)
            self.assertEqual(stats["orphans"], 1)
            a = (out / "pages" / "HTML" / "a.md").read_text(encoding="utf-8")
            self.assertTrue(a.startswith("# 画面\n\n> 場所: ガイド > 画面\n> 元ファイル: HTML/a.html"))
            self.assertIn("[次へ](b.md)", a)
            self.assertEqual(a.count("# 画面"), 1)
            idx = (out / "index.md").read_text(encoding="utf-8")
            self.assertIn("- ガイド\n  - [画面](pages/HTML/a.md)", idx)
            self.assertIn("- [孤立](pages/HTML/b.md)", idx)
            self.assertIn("name: x-help", (out / "SKILL.md").read_text(encoding="utf-8"))
            self.assertTrue((out / "SOURCE.md").exists())


if __name__ == "__main__":
    unittest.main()
