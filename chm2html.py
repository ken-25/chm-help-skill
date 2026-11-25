"""Decompiled CHM -> one self-contained HTML file per page.

Each page keeps its original markup. Stylesheets are inlined as <style>,
images (including ones a stylesheet refers to) become data: URIs, scripts and
HTML Help ActiveX controls are removed, and links between pages point at the
converted files. Files are written as UTF-8 with a BOM so that tools which do
not read <meta charset> still decode them correctly.

Output layout (OUT is the folder given with --out):
  OUT/index.html     table of contents (from the .hhc)
  OUT/keywords.html  keyword index (from the .hhk), only when it has entries
  OUT/pages/...      one .html per help page, same relative paths as in the CHM
  OUT/SOURCE.md      where the help came from (written by chm2md)
"""
from __future__ import annotations

import base64
import html
import posixpath
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, unquote

import chm2md

ENCODING = "utf-8-sig"  # UTF-8 with BOM
MIME = {
    ".png": "image/png", ".gif": "image/gif", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".bmp": "image/bmp", ".svg": "image/svg+xml", ".ico": "image/x-icon", ".webp": "image/webp",
    ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf", ".otf": "font/otf",
    ".eot": "application/vnd.ms-fontobject",
}
# frames would load another file, so they go too (help pages rarely use them)
DROP_TAGS = {"script", "object", "applet", "embed", "noscript", "base",
             "iframe", "frame", "frameset"}
URL_IN_CSS = re.compile(r"""url\(\s*(['"]?)([^'")]+)\1\s*\)""", re.I)
CSS_IMPORT = re.compile(r"""@import\s+(?:url\(\s*)?(['"]?)([^'")\s;]+)\1\s*\)?[^;]*;""", re.I)
INDEX_CSS = (
    "body{font-family:'Meiryo UI','Yu Gothic UI',sans-serif;background:#fff;color:#222;"
    "margin:24px;line-height:1.6}"
    "ul{list-style:none;padding-left:1.2em}a{color:#0b62c4}"
)


# ----------------------------------------------------------------- resources


class Resources:
    """Reads files from the decompiled folder once and caches the encoded form."""

    def __init__(self, data: chm2md.HelpData, own_chm: str | None):
        self.data = data
        self.own_chm = (own_chm or "").lower()
        self._uri: dict[str, str | None] = {}
        self._css: dict[str, str] = {}
        self.embedded = 0
        self.missing: set[str] = set()

    def find(self, ref: str, base_dir: str) -> str | None:
        """Resolve a reference from a page/stylesheet to a raw-folder key."""
        # cut "#anchor" / "?query" before decoding, so "%23" in a name stays part of it
        r = ref.strip().replace("\\", "/").split("#", 1)[0].split("?", 1)[0]
        if "::" in r:
            chm, _, inner = r.partition("::")
            chm = re.sub(r"(?i)^(ms-its|mk:@msitstore|its):", "", chm)
            if posixpath.basename(unquote(chm)).lower() != self.own_chm:
                return None  # another CHM: not part of this conversion
            key = posixpath.normpath(unquote(inner).lstrip("/"))
        else:
            if not r or re.match(r"(?i)^[a-z][a-z0-9+.-]*:", r):
                return None
            key = posixpath.normpath(posixpath.join(base_dir, unquote(r)))
        key = key.lower()
        return key if key in self.data.files else None

    def data_uri(self, ref: str, base_dir: str) -> str | None:
        if re.match(r"(?i)^\s*(data|https?):", ref):
            return ref.strip()  # already inline, or on the web: left as it is
        key = self.find(ref, base_dir)
        if key is None:
            self.missing.add(posixpath.normpath(posixpath.join(base_dir, unquote(ref))))
            return None
        if key not in self._uri:
            path = self.data.files[key]
            mime = MIME.get(path.suffix.lower())
            self._uri[key] = (f"data:{mime};base64,"
                              + base64.b64encode(path.read_bytes()).decode("ascii")
                              if mime else None)
        if self._uri[key]:
            self.embedded += 1
        return self._uri[key]

    def css_text(self, text: str, base_dir: str, _seen: frozenset = frozenset()) -> str:
        """Inline @import-ed stylesheets and every url(...) as a data: URI."""
        def imp(m):
            key = self.find(m.group(2), base_dir)
            if key is None or key in _seen:
                return ""  # another CHM, missing, or an import loop
            inner = re.sub(r"(?is)@charset[^;]*;", "", chm2md.read_text(self.data.files[key]))
            return self.css_text(inner, posixpath.dirname(key), _seen | {key})

        def repl(m):
            uri = self.data_uri(m.group(2), base_dir)
            return f'url("{uri}")' if uri else m.group(0)
        return URL_IN_CSS.sub(repl, CSS_IMPORT.sub(imp, text))

    def stylesheet(self, key: str) -> str:
        if key not in self._css:
            path = self.data.files[key]
            text = chm2md.read_text(path)
            text = re.sub(r"(?is)@charset[^;]*;", "", text)
            self._css[key] = self.css_text(text, posixpath.dirname(key), frozenset({key}))
        return self._css[key]


# --------------------------------------------------------------------- pages


def page_names(data: chm2md.HelpData) -> dict[str, str]:
    """raw page path -> output path under pages/ ('.htm' becomes '.html')."""
    names: dict[str, str] = {}
    rels = sorted(data.pages[k].relative_to(data.raw).as_posix() for k in data.pages)
    # pages already named .html keep their name; a clashing .htm gets "_htm"
    taken = {r.lower() for r in rels if r.lower().endswith(".html")}
    for rel in rels:
        root, ext = posixpath.splitext(rel)
        if ext.lower() == ".html":
            names[rel] = rel
            continue
        name = root + ".html"
        if name.lower() in taken:
            name = root + "_htm.html"
        taken.add(name.lower())
        names[rel] = name
    return names


class PageRewriter(HTMLParser):
    """Re-serialises one page, rewriting what a browser outside CHM cannot load."""

    def __init__(self, rel: str, res: Resources, names: dict[str, str], nav: str):
        super().__init__(convert_charrefs=True)
        self.rel = rel
        self.dir = posixpath.dirname(rel)
        self.out_dir = posixpath.dirname(names[rel])
        self.res = res
        self.names = names
        self.nav = nav
        self.out: list[str] = []
        self._skip: list[str] = []      # tag names whose content is being dropped
        self._css_done: set[str] = set()
        self._in_style = 0
        self._charset_done = False
        self._nav_done = False

    # -- helpers
    def _page_link(self, href: str) -> str | None:
        """Href to another converted page, or None when it cannot be followed."""
        h = href.strip()
        anchor = ""
        if "#" in h:
            h, anchor = h.split("#", 1)
            anchor = "#" + anchor
        key = self.res.find(h, self.dir)
        if key is None or key not in self.res.data.pages:
            return None
        target = self.names[self.res.data.pages[key].relative_to(self.res.data.raw).as_posix()]
        return quote(posixpath.relpath(target, self.out_dir or ".")) + anchor

    def _href(self, href: str) -> tuple[str | None, bool]:
        """(new href or None to remove the attribute, drop the whole element)."""
        h = href.strip()
        low = h.lower()
        if low.startswith("#") or re.match(r"(?i)^(https?|mailto|ftp):", h):
            return h, False
        if low.startswith("javascript:"):
            m = re.match(r"(?is)javascript:\s*fPopup\(\s*['\"]([^'\"]+)['\"]", h)
            if m:  # glossary popup -> a normal link to the popup page
                return self._page_link(m.group(1)), False
            if re.search(r"(?i)\.click\(\)", h):
                return None, True  # "related topics" button of an ActiveX control
            return None, False
        return self._page_link(h), False

    @staticmethod
    def _attrs(attrs) -> str:
        parts = []
        for k, v in attrs:
            parts.append(f" {k}" if v is None else f' {k}="{html.escape(v, quote=True)}"')
        return "".join(parts)

    def _ensure_charset(self) -> None:
        if not self._charset_done:
            self.out.append('<meta charset="utf-8">')
            self._charset_done = True

    def _emit_nav(self) -> None:
        if not self._nav_done and self.nav:
            self.out.append(self.nav)
            self._nav_done = True

    # -- parser callbacks
    def handle_starttag(self, tag, attrs, closed=False):
        if self._skip:
            if tag == self._skip[-1] and not closed:
                self._skip.append(tag)
            return
        a = dict(attrs)
        if tag in DROP_TAGS:
            if not closed and tag not in chm2md.VOID_TAGS:
                self._skip.append(tag)
            return
        if tag == "meta":
            if (a.get("http-equiv") or "").lower() == "content-type" or "charset" in a:
                self._ensure_charset()
                return
        elif tag == "link":
            if "stylesheet" in (a.get("rel") or "").lower():
                key = self.res.find(a.get("href") or "", self.dir)
                if key and key not in self._css_done:
                    self._css_done.add(key)
                    self.out.append("<style>\n" + self.res.stylesheet(key) + "\n</style>")
                return
        elif tag == "img" or (tag == "input" and (a.get("type") or "").lower() == "image"):
            uri = self.res.data_uri(a.get("src") or "", self.dir)
            if not uri:
                label = (a.get("alt") or "").strip() or posixpath.basename(
                    unquote((a.get("src") or "").replace("\\", "/"))) or "?"
                self.out.append(f"<span>[図: {html.escape(label)}]</span>")
                return
            attrs = [(k, uri if k == "src" else v) for k, v in attrs]
        elif tag in ("a", "area") and "href" in a:
            new, drop = self._href(a["href"] or "")
            if drop:
                if not closed:
                    self._skip.append(tag)
                return
            attrs = [(k, new if k == "href" else v) for k, v in attrs
                     if not (k == "href" and new is None)]
        if "background" in a and a["background"]:
            uri = self.res.data_uri(a["background"], self.dir)
            attrs = [(k, (uri or v) if k == "background" else v) for k, v in attrs]
        if "style" in a and a["style"] and "url(" in a["style"].lower():
            attrs = [(k, self.res.css_text(v, self.dir) if k == "style" else v)
                     for k, v in attrs]
        attrs = [(k, v) for k, v in attrs if not k.startswith("on")]  # event handlers
        self.out.append(f"<{tag}{self._attrs(attrs)}{' /' if closed else ''}>")
        if tag == "head":
            self._ensure_charset()
        elif tag == "body":
            self._emit_nav()
        elif tag == "style" and not closed:
            self._in_style += 1

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs, closed=True)

    def handle_endtag(self, tag):
        if self._skip:
            if tag == self._skip[-1]:
                self._skip.pop()
                return
            if tag not in ("body", "html"):
                return
            self._skip.clear()  # an element dropped but never closed: stop dropping here
        if tag in DROP_TAGS:
            return
        if tag == "style" and self._in_style:
            self._in_style -= 1
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_style:  # raw CSS: the parser does not decode it
            self.out.append(self.res.css_text(data, self.dir))
            return
        # the parser decoded the entities (convert_charrefs); write them back so that a
        # bare "R&D" stays "R&amp;D" instead of becoming the unknown entity "&D;"
        self.out.append(html.escape(data, quote=False).replace("\xa0", "&nbsp;"))

    def handle_comment(self, data):
        if not self._skip:
            self.out.append(f"<!--{data}-->")

    def handle_decl(self, decl):
        if not self._skip:
            self.out.append(f"<!{decl}>")

    def unknown_decl(self, data):
        if not self._skip:
            self.out.append(f"<![{data}]>")

    def handle_pi(self, data):
        pass  # <?xml ...?> would declare the old encoding

    def result(self) -> str:
        text = "".join(self.out)
        add = ("" if self._charset_done else '<meta charset="utf-8">\n') + \
              ("" if self._nav_done or not self.nav else self.nav + "\n")
        if add:  # no <head>/<body>: put it after <html> (or <!DOCTYPE>), never before
            m = (re.search(r"(?i)<html\b[^>]*>", text) or re.search(r"(?i)<!doctype[^>]*>", text))
            pos = m.end() if m else 0
            text = text[:pos] + ("\n" if pos else "") + add + text[pos:]
        return text


def _nav(rel: str, names: dict[str, str], crumbs: list[str] | None) -> str:
    up = posixpath.relpath("index.html", posixpath.join("pages", posixpath.dirname(names[rel])))
    items = [f'<a href="{html.escape(up)}">目次</a>']
    items += [html.escape(c) for c in (crumbs or [])]
    return ('<div style="font-size:small;color:#555;margin:0 0 8px 0">'
            + " &gt; ".join(items) + "</div>")


def convert_page(rel: str, res: Resources, names: dict[str, str], nav: str) -> str:
    p = PageRewriter(rel, res, names, nav)
    p.feed(chm2md.read_text(res.data.pages[rel.lower()]))
    p.close()
    return p.result()


# --------------------------------------------------------------------- write


def _doc(title: str, body: list[str]) -> str:
    return "\n".join([
        "<!DOCTYPE html>", chm2md.GENERATED_MARK, '<html lang="ja">', "<head>",
        '<meta charset="utf-8">', f"<title>{html.escape(title)}</title>",
        f"<style>{INDEX_CSS}</style>", "</head>", "<body>", *body, "</body>", "</html>", ""])


def write_html(data: chm2md.HelpData, out: Path, title: str, own_chm: str | None) -> dict:
    names = page_names(data)
    res = Resources(data, own_chm)
    pages_dir = out / "pages"
    if pages_dir.exists():
        shutil.rmtree(pages_dir)
    pages_dir.mkdir(parents=True)

    titles: dict[str, str] = {}
    sizes: dict[str, int] = {}
    for rel in sorted(names):
        text = convert_page(rel, res, names, _nav(rel, names, data.crumbs.get(rel)))
        m = re.search(r"(?is)<title[^>]*>(.*?)</title>", text)
        t = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))) if m else ""
        titles[rel] = re.sub(r"\s+", " ", t.replace("\xa0", " ")).strip() or posixpath.basename(rel)
        dst = pages_dir / names[rel]
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(text, encoding=ENCODING, newline="")
        sizes[rel] = dst.stat().st_size

    def link(rel: str, label: str) -> str:
        return f'<a href="pages/{html.escape(quote(names[rel]))}">{html.escape(label)}</a>'

    body = [f"<h1>{html.escape(title)} ヘルプ 目次</h1>"]

    def toc(node):
        if not node["children"]:
            return
        body.append("<ul>")
        for ch in node["children"]:
            rel = next((r for r in (data.resolve(l, data.hhc_dir) for l in ch["locals"]) if r),
                       None)
            label = ch["name"] or (titles.get(rel) if rel else "") or "(無題)"
            body.append("<li>" + (link(rel, label) if rel else html.escape(label)))
            toc(ch)
            body.append("</li>")
        body.append("</ul>")

    toc(data.toc)
    orphans = sorted(r for r in titles if r not in data.crumbs)
    if orphans:
        body += ["<h2>目次にないページ</h2>", "<ul>"]
        body += [f"<li>{link(r, titles[r])}</li>" for r in orphans]
        body.append("</ul>")
    (out / "index.html").write_text(_doc(f"{title} ヘルプ 目次", body),
                                    encoding=ENCODING, newline="\n")

    kw_items: list[str] = []

    def kw(node, trail):
        for ch in node["children"]:
            words = trail + [ch["name"]]
            targets = [r for r in (data.resolve(l, data.hhk_dir) for l in ch["locals"]) if r]
            if targets:
                links = ", ".join(link(r, titles.get(r, r)) for r in targets)
                kw_items.append(f"<li>{html.escape(' / '.join(words))}: {links}</li>")
            kw(ch, words)

    kw(data.kw, [])
    kw_path = out / "keywords.html"
    if kw_items:
        kw_path.write_text(_doc(f"{title} ヘルプ 索引",
                                [f"<h1>{html.escape(title)} ヘルプ 索引</h1>", "<ul>",
                                 *kw_items, "</ul>"]), encoding=ENCODING, newline="\n")
    elif kw_path.exists():
        kw_path.unlink()
    _write_markdown_index(data, out, title, names, titles, orphans)

    biggest = max(sizes, key=sizes.get) if sizes else ""
    return {
        "pages": len(titles), "toc_pages": len(data.crumbs), "orphans": len(orphans),
        "keywords": len(kw_items), "images_embedded": res.embedded,
        "images_missing": len(res.missing), "total_bytes": sum(sizes.values()),
        "largest_page": names.get(biggest, ""), "largest_bytes": sizes.get(biggest, 0),
    }


def _write_markdown_index(data, out: Path, title: str, names: dict[str, str],
                          titles: dict[str, str], orphans: list[str]) -> None:
    """index.md / keywords.md for an AI to search, linking to the HTML pages."""
    def target(rel: str) -> str:
        return "pages/" + quote(names[rel])

    lines = [chm2md.GENERATED_MARK, f"# {title} ヘルプ 目次", ""]

    def toc(node, depth):
        for ch in node["children"]:
            rel = next((r for r in (data.resolve(l, data.hhc_dir) for l in ch["locals"]) if r),
                       None)
            label = ch["name"] or (titles.get(rel) if rel else "") or "(無題)"
            lines.append("  " * depth + "- " + (f"[{label}]({target(rel)})" if rel else label))
            toc(ch, depth + 1)

    toc(data.toc, 0)
    if orphans:
        lines += ["", "## 目次にないページ", ""]
        lines += [f"- [{titles[r]}]({target(r)})" for r in orphans]
    (out / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    kw_lines: list[str] = []

    def kw(node, trail):
        for ch in node["children"]:
            words = trail + [ch["name"]]
            targets = [r for r in (data.resolve(l, data.hhk_dir) for l in ch["locals"]) if r]
            if targets:
                links = ", ".join(f"[{titles.get(r, r)}]({target(r)})" for r in targets)
                kw_lines.append(f"- {' / '.join(words)}: {links}")
            kw(ch, words)

    kw(data.kw, [])
    kw_path = out / "keywords.md"
    if kw_lines:
        kw_path.write_text("\n".join([chm2md.GENERATED_MARK, f"# {title} ヘルプ 索引", ""]
                                     + kw_lines) + "\n", encoding="utf-8", newline="\n")
    elif kw_path.exists():
        kw_path.unlink()


def summary(stats: dict) -> str:
    return (f"- 形式: HTML(1ページ1ファイル、CSS と画像を埋め込み、UTF-8 BOM 付き)\n"
            f"- ページ数: {stats['pages']}(目次に載るもの {stats['toc_pages']})"
            f" / 索引語: {stats['keywords']} / 埋め込んだ画像: {stats['images_embedded']}"
            f" / 見つからない画像: {stats['images_missing']}\n"
            f"- 合計: {stats['total_bytes']:,} bytes / 最大のページ: {stats['largest_page']}"
            f"({stats['largest_bytes']:,} bytes)")
