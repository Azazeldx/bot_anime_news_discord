"""Topik yang sedang trending di X (Twitter) Jepang & Indonesia, diambil dari trends24.in.

X tidak menyediakan API baca gratis, sedangkan trends24 mencatat daftar trending resmi X
tiap jam. Dipakai kurator Areaanime sebagai sinyal "topik ini lagi ramai di X".
"""
from bs4 import BeautifulSoup

REGIONS = {
    "Jepang": "https://trends24.in/japan/",
    "Indonesia": "https://trends24.in/indonesia/",
}
HOURS = 3  # trending dari 3 jam terakhir, supaya topik yang baru turun peringkat tetap terhitung


def parse(html, region):
    """Return [{"term", "region", "rank"}] dengan peringkat terbaik tiap istilah."""
    best = {}
    for card in BeautifulSoup(html, "html.parser").select(".list-container")[:HOURS]:
        for rank, link in enumerate(card.select("a.trend-link"), 1):
            term = link.get_text(strip=True)
            if term and rank < best.get(term, 99):
                best[term] = rank
    return [{"term": term, "region": region, "rank": rank} for term, rank in best.items()]


def fetch(session):
    """Trending semua region, urut dari yang paling ramai. Gagal = list kosong (bot tetap jalan)."""
    trends = []
    for region, url in REGIONS.items():
        try:
            response = session.get(url, timeout=15)
            response.raise_for_status()
            response.encoding = "utf-8"  # header tanpa charset, requests akan salah menebak latin-1
            trends += parse(response.text, region)
        except Exception as e:
            print(f"    Trending X {region} tidak terbaca: {type(e).__name__}")
    return sorted(trends, key=lambda t: t["rank"])
