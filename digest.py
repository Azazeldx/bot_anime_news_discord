"""Digest berita untuk channel DIGEST: satu file teks berisi semua berita baru sejak digest
sebelumnya, lengkap dengan konteks (sumber, liputan lintas media, trending X, skor awal bot)
dan instruksi editor Areaanime. File ini diunggah ke ChatGPT/Claude supaya AI memilih berita
yang paling layak diposting dan menulis saran judul feed.

Berita tidak diterjemahkan di sini (hemat kuota Gemini); ChatGPT/Claude membaca bahasa aslinya.
"""
import os
import re
from datetime import datetime, timedelta, timezone

import curator

MAX_ITEMS = int(os.getenv("DIGEST_MAX_ITEMS") or 200)  # berita skor terendah dipotong
TEXT_LIMIT = 600
SUMMARY_LIMIT = 400
MAX_TRENDS = 40
WIB = timezone(timedelta(hours=7))

TASK = """## Tugas untukmu
Kamu adalah editor konten untuk akun Instagram @Areaanime.id: media jejepangan untuk audiens Indonesia (anime, manga, light novel, game Jepang, VTuber, J-pop/K-pop yang nyambung ke anime, film Jepang). File ini berisi berita terbaru yang dikumpulkan bot dari media Jepang, Inggris, Indonesia, Spanyol, serta postingan X/Telegram/Bluesky.

1. Baca SEMUA berita di bagian "Berita". Urutan & "skor awal" hanya tebakan heuristik bot; nilai sendiri.
2. Pilih 5-10 berita yang paling layak diposting hari ini. Gabungkan berita yang membahas cerita yang sama dan pakai sumber dengan info paling lengkap.
3. Untuk tiap pilihan, tulis:
   - Skor 1-10 dan alasan satu kalimat kenapa berpotensi viral.
   - Tag badge (1-4 kata HURUF KAPITAL).
   - Saran judul feed sesuai "Aturan judul feed Areaanime".
   - Ringkasan 2-3 kalimat untuk caption, hanya dari fakta di sumber.
   - Nomor berita [n] dan link sumber.
4. Berita bertanda BOCORAN belum resmi: sebutkan itu, dan sarankan menunggu konfirmasi kalau kabarnya besar.
5. Lewati cerita yang sudah ada di "Topik yang sudah diposting Areaanime".
6. Kalau ada istilah di "Trending X" yang jelas soal jejepangan tapi tidak ada beritanya, sebutkan di akhir (jangan mengarang penyebabnya).
Jawab dalam Bahasa Indonesia."""


def _flat(text, limit):
    text = re.sub(r"\s*\n\s*", " / ", (text or "").strip())
    text = re.sub(r"[ \t]+", " ", text)
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _when(published):
    return published.astimezone(WIB).strftime("%Y-%m-%d %H:%M WIB") if published else "tanggal tidak diketahui"


def rank(items, all_items, trends):
    """[(item, skor, liputan, trend)] urut skor awal tertinggi, lalu yang paling baru."""
    coverage = curator.coverage_map(all_items)
    ranked = []
    for item in items:
        hits = curator.x_matches(item, trends)
        score, _, covered = curator.heuristic_score(item, coverage, hits)
        ranked.append((item, score, covered, hits))
    oldest = datetime.min.replace(tzinfo=timezone.utc)
    ranked.sort(key=lambda r: (r[1], r[0].get("published") or oldest), reverse=True)
    return ranked


def _entry(number, item, score, covered, hits):
    site = item.get("site") or {}
    channel = site.get("channel") or "RADAR"
    label = " · BOCORAN (belum resmi)" if site.get("leak") else ""
    lines = [f"[{number}] skor awal {score:g}/10 · liputan {covered} media · {item['source']} "
             f"({channel}, {item.get('lang', '?')}){label} · {_when(item.get('published'))}",
             f"Judul: {_flat(item['title'], TEXT_LIMIT)}"]
    summary = _flat(item.get("summary"), SUMMARY_LIMIT)
    if summary and _flat(item["title"], 1000) not in summary:  # banyak blog mengulang judul sebagai deskripsi
        lines.append(f"Ringkasan: {summary}")
    if hits:
        lines.append("Trending X: " + ", ".join(f"{t['term']} ({t['region']} #{t['rank']})" for t in hits))
    lines.append(f"Link: {item['link']}")
    if item.get("x_link"):
        lines.append(f"Postingan X: {item['x_link']}")
    return "\n".join(lines)


def build(ranked, trends, recent_titles, now=None):
    """Teks digest lengkap (Markdown sederhana) dari hasil rank()."""
    now = now or datetime.now(timezone.utc)
    shown, hidden = ranked[:MAX_ITEMS], len(ranked) - MAX_ITEMS
    sources = len({item["source"] for item, *_ in ranked})
    parts = [
        f"# Digest Berita Areaanime · {_when(now)}",
        f"{len(ranked)} berita baru sejak digest sebelumnya, dari {sources} sumber."
        + (f" {hidden} berita dengan skor awal terendah tidak dicantumkan." if hidden > 0 else ""),
        TASK, curator.EDITORIAL_GUIDE, curator.HEADLINE_RULES,
        "## Topik yang sudah diposting Areaanime (72 jam terakhir)\n"
        + ("\n".join(f"- {title}" for title in recent_titles) or "- (belum ada)"),
        "## Trending X saat ini (rank kecil = lebih ramai)\n"
        + ("\n".join(f"- {t['term']} ({t['region']} #{t['rank']})" for t in trends[:MAX_TRENDS])
           or "- (tidak terbaca)"),
        "## Berita\n\n" + "\n\n".join(_entry(n, *row) for n, row in enumerate(shown, 1)),
        curator.DATA_NOTE,
    ]
    return "\n\n".join(parts) + "\n"
