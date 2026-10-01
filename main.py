import json
import os
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from discord_webhook import DiscordEmbed, DiscordWebhook
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()

import curator  # noqa: E402  (baca env AREAANIME_* setelah .env dimuat)
from sources import TARGETS, parse_rss  # noqa: E402

# --- KONFIGURASI ---
WH_AREAANIME = os.getenv("DISCORD_WEBHOOK_AREAANIME")
HISTORY_FILE = "history.json"
HISTORY_LIMIT = 2000          # cukup untuk ±27 sumber x 5 berita x banyak run, supaya berita lama tidak terkirim ulang
AREAANIME_SEEN_LIMIT = 3000
AREAANIME_POSTS_LIMIT = 200
DRY_RUN = "--dry-run" in sys.argv   # cek hasil tanpa kirim ke Discord & tanpa simpan history

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
    'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8,id;q=0.7',
}


def make_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    retry = Retry(total=2, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("http://", HTTPAdapter(max_retries=retry))
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


SESSION = make_session()


# --- FUNGSI HELPER ---
def load_history():
    """Format: {"sent": [link], "areaanime_seen": [link], "areaanime_posts": [{link, key, title, ts}]}.
    Format lama (list link) otomatis dikonversi."""
    empty = {"sent": [], "areaanime_seen": [], "areaanime_posts": []}
    if not os.path.exists(HISTORY_FILE):
        return empty
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return empty
    if isinstance(data, list):
        # Migrasi: semua berita lama dianggap sudah dinilai, supaya Areaanime tidak memposting berita basi.
        return {"sent": data, "areaanime_seen": list(data), "areaanime_posts": []}
    return {**empty, **data}


def save_history(history):
    data = {
        "sent": history["sent"][-HISTORY_LIMIT:],
        "areaanime_seen": history["areaanime_seen"][-AREAANIME_SEEN_LIMIT:],
        "areaanime_posts": history["areaanime_posts"][-AREAANIME_POSTS_LIMIT:],
    }
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)


def translate_text(text, source_lang):
    if not text or source_lang == 'id': return text
    # Jp > En > Id (hasilnya lebih natural daripada Jp > Id langsung)
    steps = [('ja', 'en'), ('en', 'id')] if source_lang == 'ja' else [(source_lang, 'id')]
    for attempt in range(2):
        try:
            result = text
            for src, dst in steps:
                result = GoogleTranslator(source=src, target=dst).translate(result)
                time.sleep(0.3)  # batas Google Translate ±5 request/detik
            return result or text
        except Exception as e:
            if attempt == 0:
                time.sleep(5)
            else:
                print(f"    Gagal translate: {str(e)[:80]}")
    return text


def translate_item(item):
    """Terjemahkan judul + ringkasan dalam satu request, hasilnya disimpan di item supaya tidak diulang."""
    if 'title_id' in item:
        return item
    title, summary = item['title'], clip(item.get('summary'), 350)
    item['title_id'], item['summary_id'] = title, summary
    if item['lang'] == 'id':
        return item
    if summary:
        source_text = f"{title}\n\n{summary}"
        joined = translate_text(source_text, item['lang'])
        parts = joined.split("\n\n", 1)
        if joined != source_text and len(parts) == 2:
            item['title_id'], item['summary_id'] = parts[0].strip(), parts[1].strip()
            return item
    # Fallback: terjemahkan judul saja (ringkasan bahasa asing tanpa terjemahan tidak ditampilkan)
    item['title_id'], item['summary_id'] = translate_text(title, item['lang']), ""
    return item


def clip(text, limit):
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def favicon(url):
    return f"https://www.google.com/s2/favicons?domain={url.split('/')[2]}&sz=64"


def fetch_items(site):
    response = SESSION.get(site['url'], timeout=20)
    response.raise_for_status()
    if 'rss' in site:
        items = parse_rss(response.content, site['rss'])
    else:
        response.encoding = response.apparent_encoding
        items = site['parser'](BeautifulSoup(response.text, 'html.parser'))

    for item in items:
        item['link'] = urljoin(site['url'], item['link'] or "")
        img = item.get('img') or ""
        item['img'] = urljoin(site['url'], img) if img and not img.startswith('data:') else ""
        item['lang'] = site['lang']
        item['site'] = site
    return [i for i in items if i['link'].startswith('http')]


def enrich(item):
    """Ambil ringkasan & gambar resolusi penuh dari meta og: artikel (sekali per berita)."""
    if item.get('_enriched'):
        return item
    item['_enriched'] = True
    try:
        response = SESSION.get(item['link'], timeout=12)
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html.parser')

        def meta(*names):
            for name in names:
                tag = soup.find('meta', attrs={'property': name}) or soup.find('meta', attrs={'name': name})
                if tag and tag.get('content'):
                    return tag['content'].strip()
            return ""

        og_image = meta('og:image', 'twitter:image')
        if og_image.startswith(('http', '//', '/')) and ' ' not in og_image:
            item['img'] = urljoin(item['link'], og_image)
        if not item.get('summary'):
            item['summary'] = meta('og:description', 'description', 'twitter:description')
    except Exception as e:
        print(f"    (meta artikel tidak terbaca: {e})")
    return item


def send_webhook(url, embed, username=None):
    if DRY_RUN:
        print(f"    [DRY-RUN] {embed.title}")
        return True
    webhook = DiscordWebhook(url=url, username=username, rate_limit_retry=True, timeout=20)
    webhook.add_embed(embed)
    try:
        response = webhook.execute()
        if response.status_code == 400 and webhook.embeds[0].get('image'):
            print("    Gagal kirim (400). Mencoba kirim tanpa gambar...")
            webhook.embeds[0].pop('image')
            response = webhook.execute()
        if response.ok:
            return True
        print(f"    Webhook gagal ({response.status_code}): {response.text[:200]}")
    except Exception as err:
        print(f"    Webhook error: {err}")
    return False


# --- TAMPILAN EMBED ---
def build_news_embed(item):
    site = item['site']
    home = site.get('home', site['url'])
    icon = favicon(home)

    translate_item(item)
    title, summary = item['title_id'], item['summary_id']

    parts = []
    if summary:
        parts.append(clip(summary, 600))
    if title != item['title']:
        parts.append(f"> 📝 *{clip(item['title'], 250)}*")
    parts.append(f"👉 **[Baca selengkapnya]({item['link']})**")

    embed = DiscordEmbed(
        title=clip(f"{site.get('emoji', '📰')} {title}", 256),
        description="\n\n".join(parts),
        color=site.get('color', '03b2f8'),
        url=item['link'],
    )
    embed.set_author(name=item['source'], url=home, icon_url=icon)
    embed.set_footer(text=f"{item['source']} • Bot Berita", icon_url=icon)
    embed.set_timestamp()
    if item.get('img'):
        embed.set_image(url=item['img'])
    return embed


def highlight(headline):
    """Bagian [di dalam kurung siku] = highlight kuning di feed → tampilkan tebal di Discord."""
    return headline.replace('[', '**').replace(']', '**')


def build_areaanime_embed(item, info):
    translate_item(item)
    title_id, summary = item['title_id'], item['summary_id']
    score = info['score']

    lines = []
    if info.get('headline'):
        lines.append(f"**✍️ Saran judul feed**\n`{info['tag']}`\n> {highlight(info['headline'])}")
    if summary:
        lines.append(f"**📰 Ringkasan**\n{clip(summary, 600)}")
    if title_id != item['title']:
        lines.append(f"> 📝 *{clip(item['title'], 250)}*")
    lines.append(f"👉 **[Buka sumber berita]({item['link']})**")

    color = "ff1744" if score >= 9 else "ff6d00" if score >= 8 else "ffc400"
    embed = DiscordEmbed(
        title=clip(f"🔥 {title_id}", 256),
        description="\n\n".join(lines),
        color=color,
        url=item['link'],
    )
    embed.set_author(name=f"Areaanime Radar • Potensi viral {score:g}/10", icon_url=favicon(item['link']))
    embed.add_embed_field(name="💡 Kenapa berpotensi viral", value=clip(info['reason'], 1024), inline=False)
    embed.add_embed_field(name="📡 Diliput", value=f"{item.get('_coverage', 1)} media", inline=True)
    embed.add_embed_field(name="🏷️ Sumber", value=item['source'], inline=True)
    embed.set_footer(text=f"Dikurasi otomatis ({info['mode']}) • Bot Berita")
    embed.set_timestamp()
    if item.get('img'):
        embed.set_image(url=item['img'])
    return embed


# --- MAIN LOOP ---
def main():
    print("Memulai pengecekan multi-website..." + (" (DRY-RUN)" if DRY_RUN else ""))
    history = load_history()
    sent = set(history["sent"])
    all_items = []

    # 1. Ambil berita & kirim ke channel kategori masing-masing
    for site in TARGETS:
        webhook_url = os.getenv(f"DISCORD_WEBHOOK_{site['channel']}")
        if not webhook_url and not WH_AREAANIME:
            print(f"Skipping {site['url']} (Webhook not set)")
            continue

        print(f"--> Mengecek: {site['url']}")
        try:
            items = fetch_items(site)
        except Exception as e:
            print(f"    Error di {site['url']}: {e}")
            continue
        if not items:
            print("    Tidak ada berita ditemukan (Cek selector?)")
        all_items.extend(items)

        if not webhook_url:
            continue
        for item in reversed(items):  # kirim dari yang paling lama supaya urutan di Discord benar
            if item['link'] in sent:
                continue
            print(f"    [NEW] {item['source']}: {item['title'][:40]}...")
            if send_webhook(webhook_url, build_news_embed(enrich(item))):
                sent.add(item['link'])
                history["sent"].append(item['link'])
            time.sleep(1.5)

    # 2. Kurasi berita berpotensi viral untuk channel Areaanime
    if WH_AREAANIME:
        print("--> Kurasi Areaanime")
        seen = set(history["areaanime_seen"])
        candidates, links = [], set()
        for item in all_items:
            if item['link'] not in seen and item['link'] not in links:
                links.add(item['link'])
                candidates.append(item)

        picks = curator.select(candidates, all_items, history["areaanime_posts"])
        if not picks:
            print(f"    Tidak ada berita yang cukup menarik dari {len(candidates)} kandidat.")
        posted = set()
        for item, info in picks:
            print(f"    [AREAANIME {info['score']:g}/10] {item['source']}: {item['title'][:40]}...")
            if send_webhook(WH_AREAANIME, build_areaanime_embed(enrich(item), info), username="Areaanime Radar"):
                posted.add(item['link'])
                history["areaanime_posts"].append({
                    "link": item['link'], "key": info['key'], "title": item['title'],
                    "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                })
            time.sleep(1.5)

        # Kandidat yang sudah dinilai tidak dinilai ulang (hemat token Claude),
        # kecuali yang terpilih tapi gagal terkirim.
        failed = {item['link'] for item, _ in picks} - posted
        history["areaanime_seen"].extend(c['link'] for c in candidates if c['link'] not in failed)

    if DRY_RUN:
        print("DRY-RUN: history tidak disimpan.")
    else:
        save_history(history)
    print("Selesai pengecekan semua web.")


if __name__ == "__main__":
    main()
