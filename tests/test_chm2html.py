import base64
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import chm2html  # noqa: E402
import chm2md  # noqa: E402

PNG = base64.b64decode(  # 1x1 transparent PNG
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def make_raw(d: Path) -> Path:
    raw = d / "raw"
    (raw / "Base" / "Main").mkdir(parents=True)
    (raw / "Base" / "image").mkdir()
    (raw / "Base" / "image" / "check.gif").write_bytes(b"GIF89a")
    (raw / "Base" / "image" / "a b.png").write_bytes(PNG)
    (raw / "StyleSheet.css").write_text(
        'ul.c{list-style-image:url("Base/image/check.gif");}', encoding="cp932")
    (raw / "toc.hhc").write_text(
        '<UL><LI><OBJECT type="text/sitemap"><param name="Name" value="基本">'
        '</OBJECT><UL><LI><OBJECT type="text/sitemap"><param name="Name" value="画面">'
        '<param name="Local" value="Base/Main/a.htm"></OBJECT></UL></UL>', encoding="cp932")
    (raw / "toc.hhk").write_text(
        '<UL><LI><OBJECT type="text/sitemap"><param name="Name" value="がめん">'
        '<param name="Local" value="Base/Main/a.htm"></OBJECT></UL>', encoding="cp932")
    page = (
        '<html><head><title>画面&nbsp;説明</title>'
        '<link rel="stylesheet" type="text/css" href="../../StyleSheet.css">'
        '<link rel="stylesheet" type="text/css" href="MS-ITS:Base.chm::/StyleSheet.css">'
        '<link rel="stylesheet" type="text/css" href="MS-ITS:ArcB.chm::/StyleSheet.css">'
        '<meta http-equiv="Content-Type" content="text/html; charset=Shift_JIS">'
        '</head><body><script src="../../ehlpdhtm.js"></script>'
        '<p>用語<a class="popup" href="javascript:fPopup(\'../../Base/Main/b.htm\');" id="A1">'
        'オブジェクト</a><script>fPopupInit(\'A1\');</script>です。</p>'
        '<p><a href="MS-ITS:Base.chm::/Base/Main/b.htm#x">内部</a>'
        '<a href="MS-ITS:ArcB.chm::/Arc/z.htm">別ヘルプ</a>'
        '<a href="https://example.com/">外部</a></p>'
        '<img src="../image/a%20b.png" alt="図1"><img src="../image/none.png">'
        '<div class="acc_title">開く</div><div class="toggle_container">中身</div>'
        '<p style="background:url(../image/check.gif)">背景</p>'
        '<p><object id="RelatedTopic1" classid="clsid:x" type="application/x-oleobject">'
        '<param name="Command" value="ALink"></object>'
        '<a href="javascript:RelatedTopic1.Click()" class="related">'
        '<img src="../image/check.gif">&nbsp;関連項目</a></p>'
        '</body></html>')
    (raw / "Base" / "Main" / "a.htm").write_bytes(page.encode("cp932"))
    (raw / "Base" / "Main" / "b.htm").write_bytes(
        "<title>オブジェクト</title><p>説明</p>".encode("cp932"))
    return raw


class HtmlTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)
        self.raw = make_raw(self.d)
        self.out = self.d / "out"
        self.out.mkdir()
        self.chm = self.d / "Base.chm"
        self.chm.write_bytes(b"dummy")
        self.stats = chm2md._build(self.chm, self.raw, self.out, None, "X", False,
                                   chm2md.DEFAULT_CLASS_MAP, "html", "Base.chm")
        self.a_bytes = (self.out / "pages" / "Base" / "Main" / "a.html").read_bytes()
        self.a = self.a_bytes.decode("utf-8-sig")

    def tearDown(self):
        self._tmp.cleanup()

    def test_bom_and_charset(self):
        self.assertTrue(self.a_bytes.startswith(b"\xef\xbb\xbf"))
        self.assertIn('<meta charset="utf-8">', self.a)
        self.assertNotIn("Shift_JIS", self.a)
        self.assertIn("画面&nbsp;説明", self.a)

    def test_css_inlined_once_with_images(self):
        self.assertEqual(self.a.count("<style>"), 1)
        self.assertNotIn("<link", self.a)
        self.assertIn('list-style-image:url("data:image/gif;base64,', self.a)
        self.assertIn('style="background:url(&quot;data:image/gif;base64,', self.a)

    def test_images(self):
        self.assertIn('<img src="data:image/png;base64,', self.a)
        self.assertIn('alt="図1"', self.a)
        self.assertIn("<span>[図: none.png]</span>", self.a)
        self.assertEqual(self.stats["images_missing"], 1)

    def test_scripts_and_activex_removed(self):
        self.assertNotIn("<script", self.a)
        self.assertNotIn("fPopupInit", self.a)
        self.assertNotIn("<object", self.a)
        self.assertNotIn("関連項目", self.a)
        self.assertNotIn("javascript:", self.a)

    def test_links(self):
        self.assertIn('<a class="popup" href="b.html" id="A1">オブジェクト</a>', self.a)
        self.assertIn('<a href="b.html#x">内部</a>', self.a)
        self.assertIn("<a>別ヘルプ</a>", self.a)
        self.assertIn('<a href="https://example.com/">外部</a>', self.a)

    def test_accordion_content_visible(self):
        self.assertIn('<div class="toggle_container">中身</div>', self.a)

    def test_nav_and_index(self):
        self.assertIn('<a href="../../../index.html">目次</a> &gt; 基本 &gt; 画面', self.a)
        idx = (self.out / "index.html").read_bytes()
        self.assertTrue(idx.startswith(b"\xef\xbb\xbf"))
        idx = idx.decode("utf-8-sig")
        self.assertIn('<a href="pages/Base/Main/a.html">画面</a>', idx)
        self.assertIn('<a href="pages/Base/Main/b.html">オブジェクト</a>', idx)  # orphan
        kw = (self.out / "keywords.html").read_text(encoding="utf-8-sig")
        self.assertIn("がめん: <a href=\"pages/Base/Main/a.html\">画面 説明</a>", kw)
        self.assertFalse((self.out / "SKILL.md").exists())
        self.assertIn("HTML", (self.out / "SOURCE.md").read_text(encoding="utf-8"))

    def test_stats(self):
        self.assertEqual(self.stats["pages"], 2)
        self.assertEqual(self.stats["orphans"], 1)
        self.assertEqual(self.stats["keywords"], 1)

    def test_formats_do_not_share_a_folder(self):
        with self.assertRaises(SystemExit):
            chm2md._check_out(self.out, "md")
        md = self.d / "md"
        chm2md._build(self.chm, self.raw, md, "x-help", "X", False,
                      chm2md.DEFAULT_CLASS_MAP, "md", "Base.chm")
        with self.assertRaises(SystemExit):
            chm2md._check_out(md, "html")
        chm2md._check_out(self.out, "html")  # rebuilding the same format is fine

    def test_htm_and_html_name_clash(self):
        (self.raw / "Base" / "Main" / "a.html").write_bytes(b"<title>two</title>")
        names = chm2html.page_names(chm2md.load_help(self.raw))
        self.assertEqual(names["Base/Main/a.html"], "Base/Main/a.html")
        self.assertEqual(names["Base/Main/a.htm"], "Base/Main/a_htm.html")
        self.assertEqual(len({n.lower() for n in names.values()}), len(names))


if __name__ == "__main__":
    unittest.main()
