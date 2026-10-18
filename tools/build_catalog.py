#!/usr/bin/env python3
"""Build an OPDS 1.2 catalog for the EPUBs in books/.

Pocket Quraan readers open https://raw.githubusercontent.com/<repo>/main/catalog.xml
from Apps -> OPDS Library (or the Library tile on Home). This script writes:

  catalog.xml            root: "All books" plus one entry per folder in books/
  feeds/<slug>-<n>.xml   book lists, 20 per page (small pages keep the reader's
                         memory use low), linked with rel="next"/"previous"
  covers/<slug>.jpg      small cover thumbnails taken from each EPUB

Folders inside books/ become categories, e.g. books/Hadith/My Book.epub.
Title, author and description come from the EPUB's own metadata.

Run from the repository root:  python3 tools/build_catalog.py --repo OWNER/REPO
The GitHub Action in .github/workflows/catalog.yml runs it on every push to books/.
"""

import argparse
import hashlib
import html
import io
import os
import re
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree as ET

PAGE_SIZE = 20
COVER_MAX = (240, 360)
NS = {
    "c": "urn:oasis:names:tc:opendocument:xmlns:container",
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
}
NAV_TYPE = "application/atom+xml;profile=opds-catalog;kind=navigation"
ACQ_TYPE = "application/atom+xml;profile=opds-catalog;kind=acquisition"


def slugify(text):
    s = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return s or hashlib.sha1(text.encode()).hexdigest()[:8]


def read_epub(path):
    """Return title, author, description, language and cover bytes (or None)."""
    meta = {"title": path.stem, "author": "", "description": "", "language": "", "cover": None}
    try:
        with zipfile.ZipFile(path) as z:
            container = ET.fromstring(z.read("META-INF/container.xml"))
            opf_path = container.find(".//c:rootfile", NS).get("full-path")
            opf = ET.fromstring(z.read(opf_path))
            base = os.path.dirname(opf_path)

            def text(tag):
                el = opf.find(f".//dc:{tag}", NS)
                return (el.text or "").strip() if el is not None and el.text else ""

            meta["title"] = text("title") or meta["title"]
            meta["author"] = text("creator")
            meta["language"] = text("language")
            desc = re.sub(r"<[^>]+>", " ", text("description"))
            meta["description"] = re.sub(r"\s+", " ", html.unescape(desc)).strip()[:500]

            # Cover: EPUB3 properties="cover-image", else EPUB2 <meta name="cover">.
            href = None
            for item in opf.findall(".//opf:manifest/opf:item", NS):
                if "cover-image" in (item.get("properties") or ""):
                    href = item.get("href")
                    break
            if href is None:
                m = opf.find(".//opf:metadata/opf:meta[@name='cover']", NS)
                if m is not None:
                    cid = m.get("content")
                    for item in opf.findall(".//opf:manifest/opf:item", NS):
                        if item.get("id") == cid:
                            href = item.get("href")
                            break
            if href:
                full = os.path.normpath(os.path.join(base, href)).replace("\\", "/")
                try:
                    meta["cover"] = z.read(full)
                except KeyError:
                    pass
    except Exception as exc:  # a broken EPUB still gets listed, by file name
        print(f"warning: {path}: {exc}", file=sys.stderr)
    return meta


def make_thumbnail(data, out_path):
    try:
        from PIL import Image
    except ImportError:
        return False
    try:
        img = Image.open(io.BytesIO(data))
        img = img.convert("L")  # the reader shows covers in black and white anyway
        img.thumbnail(COVER_MAX)
        img.save(out_path, "JPEG", quality=80, progressive=False)
        return True
    except Exception as exc:
        print(f"warning: cover {out_path.name}: {exc}", file=sys.stderr)
        return False


def raw_url(repo, branch, rel_path):
    return f"https://raw.githubusercontent.com/{repo}/{branch}/" + quote(rel_path.as_posix())


def feed(feed_id, title, self_url, start_url, updated, entries, kind, prev_url=None, next_url=None):
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/terms/"'
        ' xmlns:opds="http://opds-spec.org/2010/catalog">',
        f"  <id>{html.escape(feed_id)}</id>",
        f"  <title>{html.escape(title)}</title>",
        f"  <updated>{updated}</updated>",
        f'  <link rel="self" href="{html.escape(self_url)}" type="{kind}"/>',
        f'  <link rel="start" href="{html.escape(start_url)}" type="{NAV_TYPE}"/>',
    ]
    if prev_url:
        out.append(f'  <link rel="previous" href="{html.escape(prev_url)}" type="{kind}"/>')
    if next_url:
        out.append(f'  <link rel="next" href="{html.escape(next_url)}" type="{kind}"/>')
    out.extend(entries)
    out.append("</feed>")
    return "\n".join(out) + "\n"


def nav_entry(entry_id, title, url, updated, content=""):
    return "\n".join(
        [
            "  <entry>",
            f"    <id>{html.escape(entry_id)}</id>",
            f"    <title>{html.escape(title)}</title>",
            f"    <updated>{updated}</updated>",
            f'    <content type="text">{html.escape(content)}</content>' if content else "",
            f'    <link rel="subsection" href="{html.escape(url)}" type="{ACQ_TYPE}"/>',
            "  </entry>",
        ]
    ).replace("\n\n", "\n")


def book_entry(book, updated):
    lines = [
        "  <entry>",
        f"    <id>urn:pocketquraan:{book['id']}</id>",
        f"    <title>{html.escape(book['title'])}</title>",
        f"    <updated>{updated}</updated>",
    ]
    if book["author"]:
        lines.append(f"    <author><name>{html.escape(book['author'])}</name></author>")
    if book["language"]:
        lines.append(f"    <dc:language>{html.escape(book['language'])}</dc:language>")
    if book["description"]:
        lines.append(f'    <summary type="text">{html.escape(book["description"])}</summary>')
    if book["cover_url"]:
        lines.append(
            f'    <link rel="http://opds-spec.org/image/thumbnail" href="{html.escape(book["cover_url"])}" type="image/jpeg"/>'
        )
        lines.append(f'    <link rel="http://opds-spec.org/image" href="{html.escape(book["cover_url"])}" type="image/jpeg"/>')
    lines.append(
        f'    <link rel="http://opds-spec.org/acquisition" href="{html.escape(book["url"])}" type="application/epub+zip"/>'
    )
    lines.append("  </entry>")
    return "\n".join(lines)


def write_paged(root, repo, branch, slug, title, books, updated, start_url):
    pages = [books[i : i + PAGE_SIZE] for i in range(0, len(books), PAGE_SIZE)] or [[]]
    urls = [raw_url(repo, branch, Path("feeds") / f"{slug}-{n + 1}.xml") for n in range(len(pages))]
    for n, page in enumerate(pages):
        page_title = title if len(pages) == 1 else f"{title} ({n + 1}/{len(pages)})"
        xml = feed(
            f"urn:pocketquraan:feed:{slug}:{n + 1}",
            page_title,
            urls[n],
            start_url,
            updated,
            [book_entry(b, updated) for b in page],
            ACQ_TYPE,
            prev_url=urls[n - 1] if n > 0 else None,
            next_url=urls[n + 1] if n + 1 < len(pages) else None,
        )
        (root / "feeds" / f"{slug}-{n + 1}.xml").write_text(xml, encoding="utf-8")
    return urls[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="OWNER/REPO on GitHub")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--title", default="Pocket Quraan Books")
    ap.add_argument("--root", default=".")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    books_dir = root / "books"
    for d in ("feeds", "covers"):
        shutil.rmtree(root / d, ignore_errors=True)
        (root / d).mkdir()

    updated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    start_url = raw_url(args.repo, args.branch, Path("catalog.xml"))

    books, categories = [], {}
    for path in sorted(books_dir.rglob("*.epub"), key=lambda p: p.as_posix().lower()):
        rel = path.relative_to(root)
        meta = read_epub(path)
        book_id = slugify(rel.as_posix())
        cover_url = None
        if meta["cover"]:
            cover_rel = Path("covers") / f"{book_id}.jpg"
            if make_thumbnail(meta["cover"], root / cover_rel):
                cover_url = raw_url(args.repo, args.branch, cover_rel)
        book = {
            "id": book_id,
            "title": meta["title"],
            "author": meta["author"],
            "description": meta["description"],
            "language": meta["language"],
            "url": raw_url(args.repo, args.branch, rel),
            "cover_url": cover_url,
        }
        books.append(book)
        parts = path.relative_to(books_dir).parts
        if len(parts) > 1:
            categories.setdefault(parts[0], []).append(book)

    books.sort(key=lambda b: b["title"].lower())
    nav = [
        nav_entry(
            "urn:pocketquraan:all",
            "All books",
            write_paged(root, args.repo, args.branch, "all", "All books", books, updated, start_url),
            updated,
            f"{len(books)} books",
        )
    ]
    for name in sorted(categories, key=str.lower):
        cat_books = sorted(categories[name], key=lambda b: b["title"].lower())
        slug = "cat-" + slugify(name)
        first = write_paged(root, args.repo, args.branch, slug, name, cat_books, updated, start_url)
        nav.append(nav_entry(f"urn:pocketquraan:{slug}", name, first, updated, f"{len(cat_books)} books"))

    (root / "catalog.xml").write_text(
        feed("urn:pocketquraan:root", args.title, start_url, start_url, updated, nav, NAV_TYPE), encoding="utf-8"
    )
    print(f"catalog.xml: {len(books)} books, {len(categories)} folders")


if __name__ == "__main__":
    main()
