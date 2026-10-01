"""Penyimpanan atomik dan penggabungan memori pengiriman bot."""
import argparse
import json
import os
import tempfile
from pathlib import Path

HISTORY_LIMIT = 2000
AREAANIME_SEEN_LIMIT = 3000
AREAANIME_POSTS_LIMIT = 200


def normalize(data):
    if isinstance(data, list):
        data = {"sent": data, "areaanime_seen": list(data), "areaanime_posts": []}
    if not isinstance(data, dict):
        raise ValueError("Format history tidak valid")
    result = {key: data.get(key, []) for key in ("sent", "areaanime_seen", "areaanime_posts")}
    for key in ("sent", "areaanime_seen"):
        if not isinstance(result[key], list) or any(not isinstance(link, str) for link in result[key]):
            raise ValueError(f"Format history {key} tidak valid")
    posts = result["areaanime_posts"]
    if not isinstance(posts, list) or any(
        not isinstance(post, dict) or any(not isinstance(post.get(key), str)
                                         for key in ("link", "key", "title", "ts"))
        for post in posts
    ):
        raise ValueError("Format history areaanime_posts tidak valid")
    return result


def load(path):
    path = Path(path)
    if not path.exists():
        return normalize({})
    # History rusak harus menghentikan bot, supaya berita lama tidak dikirim ulang.
    with path.open(encoding="utf-8") as handle:
        return normalize(json.load(handle))


def merge(left, right):
    left, right = normalize(left), normalize(right)
    result = {}
    for key, limit in (("sent", HISTORY_LIMIT), ("areaanime_seen", AREAANIME_SEEN_LIMIT)):
        # Pertahankan kemunculan terakhir saat gabungan harus dipangkas.
        links = left[key] + right[key]
        result[key] = list(reversed(dict.fromkeys(reversed(links))))[-limit:]
    posts = {(p["link"], p["ts"]): p for p in left["areaanime_posts"] + right["areaanime_posts"]}
    result["areaanime_posts"] = sorted(posts.values(), key=lambda p: p["ts"])[-AREAANIME_POSTS_LIMIT:]
    return result


def save(path, data):
    path = Path(path)
    data = merge({}, data)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gabungkan history JSON saat Git rebase/merge")
    parser.add_argument("--merge", nargs=2, metavar=("OURS", "THEIRS"), required=True)
    args = parser.parse_args()
    ours, theirs = args.merge
    save(ours, merge(load(ours), load(theirs)))
