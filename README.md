# hsb-device.github.io

Source for the HSB-Device blog — notes on the LanceX kernel, root, and low-level
work on the RMX1971 (Snapdragon 712).

Live site: <https://hsb-device.github.io>

## Layout

```
build.py              static site generator (python3 stdlib only)
content/posts/*.md    posts, one file per article with YAML-ish front matter
site/static/*         files copied verbatim into docs/ (css, robots.txt)
docs/                 build output — committed, served by GitHub Pages
```

## Writing a post

Create `content/posts/<slug>.md`:

```
---
title: "Post title"
date: 2026-10-21
summary: One sentence that shows up on the index and in the feed.
tags: kernel, arm64
---

Body in Markdown. Supported: headings, paragraphs, fenced code, bullet lists,
blockquotes, horizontal rules, and inline code/bold/italic/links.
```

Then rebuild and commit both the source and the output:

```sh
python3 build.py
git add -A && git commit -m "post: <slug>" && git push
```

`python3 build.py --serve` builds and serves `docs/` on <http://127.0.0.1:8080>
for local preview.

## Pages

GitHub Pages serves this repository from `main` / `/docs`. The `docs/` tree is
plain HTML with a `.nojekyll` marker, so no Actions workflow is involved.
