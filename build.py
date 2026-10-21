#!/usr/bin/env python3
"""Static blog builder for hsb-device.github.io.

No dependencies: only the Python standard library.
Reads content/posts/*.md and site/static/*, writes docs/.

    python3 build.py            # build into docs/
    python3 build.py --serve    # build, then serve docs/ on :8080
"""

import html
import os
import re
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content" / "posts"
STATIC = ROOT / "site" / "static"
OUT = ROOT / "docs"

SITE_TITLE = "HSB-Device"
SITE_TAGLINE = "Kernel, root and low-level notes for the RMX1971 / Snapdragon 712"
SITE_URL = "https://hsb-device.github.io"
REPO_URL = "https://github.com/HSB-Device"

# ---------------------------------------------------------------- front matter

FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def parse_post(path):
    raw = path.read_text(encoding="utf-8")
    meta, body = {}, raw
    m = FM_RE.match(raw)
    if m:
        body = raw[m.end():]
        for line in m.group(1).splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip().strip('"').strip("'")
    slug = meta.get("slug") or path.stem
    meta.setdefault("title", slug)
    meta.setdefault("date", date.today().isoformat())
    meta.setdefault("summary", "")
    meta.setdefault("tags", "")
    meta["slug"] = slug
    meta["tags"] = [t.strip() for t in meta["tags"].split(",") if t.strip()]
    return meta, body


# ------------------------------------------------------------ markdown subset
# Deliberately small: headings, paragraphs, fenced code, lists, quotes, hr,
# inline code/bold/italic/links. Anything fancier does not belong in a blog
# that has to stay readable as plain text.

INLINE_CODE_RE = re.compile(r"`([^`]+)`")
BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
ITALIC_RE = re.compile(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def inline(text):
    stash = []

    def keep(fragment):
        stash.append(fragment)
        return "\x00%d\x00" % (len(stash) - 1)

    text = INLINE_CODE_RE.sub(lambda m: keep("<code>%s</code>" % html.escape(m.group(1))), text)
    text = html.escape(text, quote=False)
    text = LINK_RE.sub(
        lambda m: keep('<a href="%s">%s</a>' % (html.escape(m.group(2)), m.group(1))), text
    )
    text = BOLD_RE.sub(r"<strong>\1</strong>", text)
    text = ITALIC_RE.sub(r"<em>\1</em>", text)
    return re.sub("\x00(\\d+)\x00", lambda m: stash[int(m.group(1))], text)


def markdown(src):
    out, para, i = [], [], 0
    lines = src.split("\n")

    def flush():
        if para:
            out.append("<p>%s</p>" % inline(" ".join(p.strip() for p in para)))
            para.clear()

    while i < len(lines):
        line = lines[i]
        fence = re.match(r"^```(\w*)\s*$", line)
        if fence:
            flush()
            lang = fence.group(1)
            i += 1
            block = []
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            cls = ' class="language-%s"' % lang if lang else ""
            out.append("<pre><code%s>%s</code></pre>" % (cls, html.escape("\n".join(block))))
            i += 1
            continue
        if not line.strip():
            flush()
            i += 1
            continue
        heading = re.match(r"^(#{1,4})\s+(.*)$", line)
        if heading:
            flush()
            n = len(heading.group(1))
            body = inline(heading.group(2))
            anchor = re.sub(r"[^a-z0-9]+", "-", heading.group(2).lower()).strip("-")
            out.append('<h%d id="%s">%s</h%d>' % (n, anchor, body, n))
            i += 1
            continue
        if re.match(r"^\s*([-*_])\s*\1\s*\1[\s\1]*$", line):
            flush()
            out.append("<hr>")
            i += 1
            continue
        if "|" in line and i + 1 < len(lines) and re.match(
                r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$", lines[i + 1]):
            flush()

            def cells(row):
                row = row.strip()
                if row.startswith("|"):
                    row = row[1:]
                if row.endswith("|") and not row.endswith("\\|"):
                    row = row[:-1]
                parts = re.split(r"(?<!\\)\|", row)
                return [c.replace("\\|", "|").strip() for c in parts]

            head = cells(line)
            i += 2
            body_rows = []
            while i < len(lines) and lines[i].strip() and "|" in lines[i]:
                body_rows.append(cells(lines[i]))
                i += 1
            for _row in body_rows:
                if len(_row) != len(head):
                    raise SystemExit(
                        "table row width mismatch: header=%d row=%d -> %r"
                        % (len(head), len(_row), _row)
                    )
            out.append(
                '<div class="table-wrap"><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>'
                % (
                    "".join("<th>%s</th>" % inline(c) for c in head),
                    "".join(
                        "<tr>%s</tr>" % "".join("<td>%s</td>" % inline(c) for c in r)
                        for r in body_rows
                    ),
                )
            )
            continue

        if re.match(r"^\s*[-*]\s+", line):
            flush()
            items = []
            while i < len(lines) and re.match(r"^\s*[-*]\s+", lines[i]):
                items.append(re.sub(r"^\s*[-*]\s+", "", lines[i]))
                i += 1
            out.append("<ul>%s</ul>" % "".join("<li>%s</li>" % inline(x) for x in items))
            continue
        if line.startswith("> "):
            flush()
            quote = []
            while i < len(lines) and lines[i].startswith("> "):
                quote.append(lines[i][2:])
                i += 1
            out.append("<blockquote>%s</blockquote>" % markdown("\n".join(quote)))
            continue
        para.append(line)
        i += 1
    flush()
    return "\n".join(out)


# ------------------------------------------------------------------- templates

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="stylesheet" href="{root}style.css">
<link rel="alternate" type="application/atom+xml" title="{site}" href="{root}feed.xml">
</head>
<body>
<header class="top">
  <a class="brand" href="{root}index.html">{site}</a>
  <nav><a href="{root}index.html">posts</a><a href="{repo}">github</a><a href="{root}feed.xml">rss</a></nav>
</header>
<main>
{body}
</main>
<footer>
  <span>{site} — {tagline}</span>
</footer>
</body>
</html>
"""


def page(title, desc, body, root=""):
    return PAGE.format(
        title=html.escape(title), desc=html.escape(desc), body=body,
        root=root, site=SITE_TITLE, tagline=SITE_TAGLINE, repo=REPO_URL,
    )


INDEX_HEAD = '<h1 class="site-title">%s</h1>\n<p class="tagline">%s</p>\n' % (SITE_TITLE, SITE_TAGLINE)


def post_card(p):
    tags = " ".join('<span class="tag">%s</span>' % html.escape(t) for t in p["tags"])
    return (
        '<article class="card">\n'
        '  <h2><a href="posts/%s.html">%s</a></h2>\n'
        '  <p class="meta"><time datetime="%s">%s</time> %s</p>\n'
        '  <p>%s</p>\n'
        '</article>\n' % (p["slug"], html.escape(p["title"]), p["date"], p["date"], tags,
                          inline(p["summary"]))
    )


# ----------------------------------------------------------------------- build


def build():
    posts = []
    for path in sorted(CONTENT.glob("*.md")):
        meta, body = parse_post(path)
        meta["html"] = markdown(body)
        posts.append(meta)
    posts.sort(key=lambda p: p["date"], reverse=True)

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "posts").mkdir(parents=True)

    for f in STATIC.glob("*"):
        shutil.copy2(f, OUT / f.name)
    (OUT / ".nojekyll").write_text("", encoding="utf-8")

    cards = "".join(post_card(p) for p in posts) or "<p>No posts yet.</p>"
    (OUT / "index.html").write_text(
        page(SITE_TITLE, SITE_TAGLINE, INDEX_HEAD + cards), encoding="utf-8"
    )

    for p in posts:
        tags = " ".join('<span class="tag">%s</span>' % html.escape(t) for t in p["tags"])
        body = (
            '<article class="post">\n'
            '  <h1>%s</h1>\n'
            '  <p class="meta"><time datetime="%s">%s</time> %s</p>\n'
            '%s\n'
            '</article>\n<a class="back" href="../index.html">&larr; all posts</a>\n'
            % (html.escape(p["title"]), p["date"], p["date"], tags, p["html"])
        )
        (OUT / "posts" / (p["slug"] + ".html")).write_text(
            page(p["title"], p["summary"], body, root="../"), encoding="utf-8"
        )

    feed = ['<?xml version="1.0" encoding="utf-8"?>',
            '<feed xmlns="http://www.w3.org/2005/Atom">',
            '  <title>%s</title>' % SITE_TITLE,
            '  <subtitle>%s</subtitle>' % html.escape(SITE_TAGLINE),
            '  <link href="%s/feed.xml" rel="self"/>' % SITE_URL,
            '  <link href="%s/"/>' % SITE_URL,
            '  <id>%s/</id>' % SITE_URL,
            '  <updated>%sT00:00:00Z</updated>' % (posts[0]["date"] if posts else date.today().isoformat())]
    for p in posts:
        url = "%s/posts/%s.html" % (SITE_URL, p["slug"])
        feed += [
            '  <entry>',
            '    <title>%s</title>' % html.escape(p["title"]),
            '    <link href="%s"/>' % url,
            '    <id>%s</id>' % url,
            '    <updated>%sT00:00:00Z</updated>' % p["date"],
            '    <summary>%s</summary>' % html.escape(p["summary"]),
            '    <content type="html">%s</content>' % html.escape(p["html"]),
            '  </entry>',
        ]
    feed.append("</feed>")
    (OUT / "feed.xml").write_text("\n".join(feed) + "\n", encoding="utf-8")

    urls = ['  <url><loc>%s/</loc></url>' % SITE_URL]
    urls += ['  <url><loc>%s/posts/%s.html</loc><lastmod>%s</lastmod></url>'
             % (SITE_URL, p["slug"], p["date"]) for p in posts]
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n%s\n</urlset>\n'
        % "\n".join(urls), encoding="utf-8")

    print("built %d post(s) -> %s" % (len(posts), OUT))
    for f in sorted(OUT.rglob("*")):
        if f.is_file():
            print("  %-42s %6d B" % (f.relative_to(OUT), f.stat().st_size))


if __name__ == "__main__":
    build()
    if "--serve" in sys.argv:
        import http.server
        os.chdir(OUT)
        http.server.ThreadingHTTPServer(("127.0.0.1", 8080), http.server.SimpleHTTPRequestHandler).serve_forever()
