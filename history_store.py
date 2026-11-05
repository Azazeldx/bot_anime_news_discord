"""Penyimpanan atomik dan penggabungan memori pengiriman bot."""
import argparse
import json
import os
import tempfile
from pathlib import Path

# Harus jauh lebih besar dari jumlah link yang terlihat di semua jendela sumber (SOURCE_LIMIT x
# jumlah sumber), supaya berita lama yang masih tampil di sumber lambat tidak dikirim ulang.
HISTORY_LIMIT = 6000
AREAANIME_SEEN_LIMIT = 6000
DIGEST_SEEN_LIMIT = 6000
AREAANIME_POSTS_LIMIT = 200
# Daftar link: "sent" = terkirim ke channel kategori, "areaanime_seen" = sudah dinilai kurasi,
# "digest_seen" = sudah masuk file digest.
LINK_LISTS = {"sent": HISTORY_LIMIT, "areaanime_seen": AREAANIME_SEEN_LIMIT, "digest_seen": DIGEST_SEEN_LIMIT}


def normalize(data):
    if isinstance(data, list):
        data = {"sent": data, "areaanime_seen": list(data), "areaanime_posts": []}
    if not isinstance(data, dict):
        raise ValueError("Format history tidak valid")
    result = {key: data.get(key, []) for key in (*LINK_LISTS, "areaanime_posts")}
    for key in LINK_LISTS:
        if not isinstance(result[key], list) or any(not isinstance(link, str) for link in result[key]):
            raise ValueError(f"Format history {key} tidak valid")
    posts = result["areaanime_posts"]
    if not isinstance(posts, list) or any(
        not isinstance(post, dict) or any(not isinstance(post.get(key), str)
                                         for key in ("link", "key", "title", "ts"))
        for post in posts
    ):
        raise ValueError("Format history areaanime_posts tidak valid")
    # Waktu kiriman digest terakhir (ISO 8601 UTC), "" kalau belum pernah.
    result["digest_last"] = data.get("digest_last", "")
    if not isinstance(result["digest_last"], str):
        raise ValueError("Format history digest_last tidak valid")
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
    for key, limit in LINK_LISTS.items():
        # Pertahankan kemunculan terakhir saat gabungan harus dipangkas.
        links = left[key] + right[key]
        result[key] = list(reversed(dict.fromkeys(reversed(links))))[-limit:]
    posts = {(p["link"], p["ts"]): p for p in left["areaanime_posts"] + right["areaanime_posts"]}
    result["areaanime_posts"] = sorted(posts.values(), key=lambda p: p["ts"])[-AREAANIME_POSTS_LIMIT:]
    result["digest_last"] = max(left["digest_last"], right["digest_last"])  # format ISO sama, urut = urut waktu
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
