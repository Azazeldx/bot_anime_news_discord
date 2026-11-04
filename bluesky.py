"""Postingan akun Bluesky lewat API publik resmi (tanpa login / API key).

Beberapa media yang websitenya memblokir bot tetap membagikan judul beritanya di Bluesky,
mis. Comic Natalie (natalie.mu memblokir dengan "Human Verification", tetapi akun
@comic.natalie.mu memposting setiap artikel). Postingan yang menautkan artikel memakai link
artikel itu, supaya dedupe & hitungan liputan lintas media tetap jalan seperti sumber RSS.
"""
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

FEED_URL = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
LINK_FACET = "app.bsky.richtext.facet#link"


def _strip_tracking(url):
    parts = urlparse(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not k.startswith("utm_")]
    return urlunparse(parts._replace(query=urlencode(query)))


def _links_and_text(record):
    """(link di teks, teks tanpa URL). URL dipotong lewat byte range facet karena Bluesky
    menampilkan URL yang disingkat di teks."""
    data = (record.get("text") or "").encode("utf-8")
    links, ranges = [], []
    for facet in record.get("facets") or []:
        for feature in facet.get("features") or []:
            if feature.get("$type") == LINK_FACET and feature.get("uri"):
                links.append(feature["uri"])
                index = facet.get("index") or {}
                ranges.append((index.get("byteStart", 0), index.get("byteEnd", 0)))
    for start, end in sorted(ranges, reverse=True):
        data = data[:start] + data[end:]
    return links, data.decode("utf-8", errors="ignore").strip()


def _media(embed):
    """(gambar, external) dari embed view postingan."""
    embed = embed or {}
    if embed.get("$type", "").startswith("app.bsky.embed.recordWithMedia"):
        embed = embed.get("media") or {}
    images = [image["fullsize"] for image in embed.get("images") or [] if image.get("fullsize")]
    external = embed.get("external") or {}
    if not images and external.get("thumb"):
        images = [external["thumb"]]
    return images, external


def parse(data, name, limit=10):
    """Postingan sendiri (tanpa repost & balasan), paling baru dulu."""
    results = []
    for entry in data.get("feed") or []:
        post = entry.get("post") or {}
        record = post.get("record") or {}
        if entry.get("reason") or record.get("reply") or not post.get("uri"):
            continue
        links, text = _links_and_text(record)
        images, external = _media(post.get("embed"))
        title = text or external.get("title") or ""
        if not title:
            continue
        handle = (post.get("author") or {}).get("handle", "")
        post_link = f"https://bsky.app/profile/{handle}/post/{post['uri'].rpartition('/')[2]}"
        article = external.get("uri") or (links[0] if links else "")
        try:
            published = datetime.fromisoformat(record.get("createdAt", "").replace("Z", "+00:00"))
        except ValueError:
            published = None
        results.append({
            "title": title,
            "link": _strip_tracking(article) if article.startswith("http") else post_link,
            "img": images[0] if images else "",
            "images": images[:4],
            "source": name,
            "summary": external.get("description") or "",
            "published": published,
        })
        if len(results) == limit:
            break
    return results


def fetch(session, site):
    """Ambil postingan satu akun Bluesky (site["bsky"] = handle)."""
    response = session.get(FEED_URL, timeout=20, params={
        "actor": site["bsky"], "limit": 50, "filter": "posts_no_replies"})
    response.raise_for_status()
    return parse(response.json(), site["name"], site.get("limit", 10))
