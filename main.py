import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup
from discord_webhook import DiscordEmbed, DiscordWebhook
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()

import bluesky  # noqa: E402
import curator  # noqa: E402  (baca env AREAANIME_* setelah .env dimuat)
import digest  # noqa: E402
import history_store  # noqa: E402
import telegram_channels  # noqa: E402
import x_accounts  # noqa: E402
import x_trends  # noqa: E402
from translator import GeminiTranslator, TranslationUnavailable  # noqa: E402
from sources import TARGETS, parse_date, parse_rss  # noqa: E402

# --- KONFIGURASI ---
WH_AREAANIME = os.getenv("DISCORD_WEBHOOK_AREAANIME")
WH_DIGEST = os.getenv("DISCORD_WEBHOOK_DIGEST")  # file teks berita baru untuk ChatGPT/Claude
HISTORY_FILE = "history.json"
DIGEST_PREVIEW = "digest-latest.txt"  # salinan lokal file digest saat --dry-run
DRY_RUN = "--dry-run" in sys.argv   # cek hasil tanpa kirim ke Discord & tanpa simpan history
# Berita kategori yang terbit lebih lama dari ini tidak dikirim (0 = tanpa batas), supaya jendela
# sumber yang lebar tidak mengirim ulang berita lama.
NEWS_MAX_AGE_HOURS = float(os.getenv("NEWS_MAX_AGE_HOURS") or 48)
# Berhenti mengirim berita baru setelah sekian menit (0 = tanpa batas), supaya run selesai
# sebelum timeout langkah GitHub Actions (40 menit) dan tidak tercatat gagal.
RUN_TIME_LIMIT_MINUTES = float(os.getenv("RUN_TIME_LIMIT_MINUTES") or 35)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
    'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8,id;q=0.7',
}


def make_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    retry = Retry(total=2, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504],
                  respect_retry_after_header=False)
    session.mount("http://", HTTPAdapter(max_retries=retry))
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


SESSION = make_session()
TRANSLATOR = GeminiTranslator()


# --- FUNGSI HELPER ---
def load_history():
    return history_store.load(HISTORY_FILE)


def save_history(history):
    history_store.save(HISTORY_FILE, history)


def translate_item(item):
    """Terjemahkan judul + ringkasan dalam satu request, tanpa kirim judul asing saat gagal."""
    if 'title_id' in item:
        return item
    if item.get('_translation_error'):
        raise TranslationUnavailable(item['_translation_error'])
    title, summary = item['title'], clip(item.get('summary'), 350)
    social = is_social(item.get('site') or {})
    if social:
        # Teks postingan panjang: kirim baris pertama sebagai judul dan sisanya sebagai ringkasan,
        # supaya model tidak meringkas seluruh postingan menjadi satu judul.
        title, _, rest = title.partition("\n")
        summary = rest.strip()
    try:
        title_id, summary_id = TRANSLATOR.translate(title, summary, item['lang'])
    except TranslationUnavailable as error:
        item['_translation_error'] = str(error)
        raise
    if social:
        title_id, summary_id = (f"{title_id}\n\n{summary_id}" if summary_id else title_id), ""
    item['title_id'], item['summary_id'] = title_id, summary_id
    return item


def is_social(site):
    """Postingan X / Telegram: teks lengkap ada di "title", ditampilkan dengan embed sosial."""
    return 'x' in site or 'telegram' in site
    return item


def clip(text, limit):
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def favicon(url):
    return f"https://www.google.com/s2/favicons?domain={url.split('/')[2]}&sz=64"


def fetch_items(site):
    if 'x' in site or 'telegram' in site or 'bsky' in site:
        if 'x' in site:
            items = x_accounts.fetch(SESSION, site, parse_rss)
        elif 'telegram' in site:
            items = telegram_channels.fetch(SESSION, site)
        else:
            items = bluesky.fetch(SESSION, site)
        for item in items:
            # Postingan sudah membawa teks & gambar; halaman x.com / t.me tidak bisa di-scrape.
            item.update(lang=site['lang'], site=site, _enriched=True)
        return items

    response = SESSION.get(site['url'], timeout=20)
    response.raise_for_status()
    if 'rss' in site:
        items = parse_rss(response.content, site['rss'], site['limit'])
    else:
        response.encoding = response.apparent_encoding
        items = site['parser'](BeautifulSoup(response.text, 'html.parser'))[:site['limit']]

    for item in items:
        item['link'] = urljoin(site['url'], item['link'] or "")
        img = item.get('img') or ""
        item['img'] = urljoin(site['url'], img) if img and not img.startswith('data:') else ""
        item['lang'] = site['lang']
        item['site'] = site
    return [i for i in items if i['link'].startswith('http')]


def enrich(item):
    """Ambil ringkasan, gambar resolusi penuh & tanggal terbit dari meta artikel (sekali per berita)."""
    if item.get('_enriched'):
        return item
    item['_enriched'] = True
    try:
        response = SESSION.get(item['link'], timeout=12)
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html.parser')

        def meta(*names):
            for name in names:
                tag = (soup.find('meta', attrs={'property': name}) or soup.find('meta', attrs={'name': name})
                       or soup.find('meta', attrs={'itemprop': name}))
                if tag and tag.get('content'):
                    return tag['content'].strip()
            return ""

        og_image = meta('og:image', 'twitter:image')
        if og_image.startswith(('http', '//', '/')) and ' ' not in og_image:
            item['img'] = urljoin(item['link'], og_image)
        if not item.get('summary'):
            item['summary'] = meta('og:description', 'description', 'twitter:description')
        if not item.get('published'):
            # Urutan: meta artikel, JSON-LD, lalu <time datetime> pertama (blog Livedoor, Oricon).
            json_ld = re.search(r'"datePublished"\s*:\s*"([^"]+)"', response.text)
            time_tag = soup.find('time', attrs={'datetime': True})
            item['published'] = parse_date(
                meta('article:published_time', 'datePublished', 'pubdate', 'aja:published_date')
                or (json_ld.group(1) if json_ld else None)
                or (time_tag['datetime'] if time_tag else None))
    except Exception as e:
        print(f"    (meta artikel tidak terbaca: {type(e).__name__})")
    return item


def is_stale(item, now=None):
    published = item.get('published')
    if not published or NEWS_MAX_AGE_HOURS <= 0:
        return False
    return published < (now or datetime.now(timezone.utc)) - timedelta(hours=NEWS_MAX_AGE_HOURS)


def send_webhook(url, embed, username=None, extra_images=(), files=()):
    """Kirim embed. extra_images (maks. 3) tampil sebagai galeri: Discord menggabungkan embed
    dengan url yang sama menjadi satu postingan berisi beberapa gambar. files = [(nama, bytes)]
    dilampirkan sebagai file."""
    if DRY_RUN:
        gallery = f" (+{len(extra_images[:3])} gambar)" if extra_images else ""
        attached = f" (+file {', '.join(name for name, _ in files)})" if files else ""
        print(f"    [DRY-RUN] {embed.title}{gallery}{attached}")
        return True
    webhook = DiscordWebhook(url=url, username=username, rate_limit_retry=False, timeout=60 if files else 20)
    webhook.add_embed(embed)
    for name, content in files:
        webhook.add_file(file=content, filename=name)
    if embed.url:
        for image in extra_images[:3]:
            extra = DiscordEmbed(url=embed.url)
            extra.set_image(url=image)
            webhook.add_embed(extra)
    try:
        for attempt in range(3):
            # Panggilan transport menghindari retry 429 tanpa batas milik library.
            with webhook.api_post_request() as response:
                if response.status_code in (200, 204):
                    return True
                if attempt < 2 and response.status_code == 400 and webhook.embeds[0].get('image'):
                    print("    Gagal kirim (400). Mencoba kirim tanpa gambar...")
                    webhook.embeds = webhook.embeds[:1]
                    webhook.embeds[0].pop('image')
                    continue
                if attempt < 2 and response.status_code == 429:
                    delay = float(response.json().get('retry_after', 1))
                    if 0 <= delay <= 30:
                        print(f"    Discord rate limit, tunggu {delay:g} detik...")
                        time.sleep(delay + 0.15)
                        continue
                print(f"    Webhook gagal ({response.status_code}); akan dicoba pada run berikutnya.")
                return False
    except Exception as err:
        # Pesan exception requests dapat memuat token URL webhook.
        print(f"    Webhook error ({type(err).__name__}); akan dicoba pada run berikutnya.")
    return False


def build_digest_embed(ranked, filename):
    top = "\n".join(f"`{score:g}/10` [{clip(item['title'].split(chr(10))[0], 90)}]({item['link']}) · {item['source']}"
                    for item, score, *_ in ranked[:5])
    embed = DiscordEmbed(
        title=f"🧠 Digest {len(ranked)} berita baru untuk ChatGPT/Claude",
        description=clip(f"Unduh **{filename}**, lalu kirim ke ChatGPT/Claude dengan pesan:\n"
                         "> Baca file ini dan kerjakan bagian \"Tugas untukmu\".\n\n"
                         f"**Skor awal tertinggi (heuristik bot):**\n{top}", 4000),
        color="7c4dff",
    )
    embed.set_footer(text="Digest otomatis • Bot Berita")
    embed.set_timestamp()
    return embed


def run_digest(history, all_items, trends):
    """Kirim satu file berisi berita baru sejak digest sebelumnya (lihat digest.py), setelah
    terkumpul digest.MIN_ITEMS berita atau digest.INTERVAL_HOURS jam sejak digest terakhir."""
    print("--> Digest untuk ChatGPT/Claude")
    now = datetime.now(timezone.utc)
    last = history["digest_last"]
    due = not last or now - datetime.fromisoformat(last) >= timedelta(hours=digest.INTERVAL_HOURS)
    seen, links, fresh = set(history["digest_seen"]), set(), []
    for item in all_items:
        if item['link'] not in seen and item['link'] not in links:
            links.add(item['link'])
            fresh.append(item)
    waiting = (f"    {{}} berita baru terkumpul; digest dikirim setelah {digest.MIN_ITEMS} berita "
               f"atau {digest.INTERVAL_HOURS:g} jam sejak digest terakhir.")
    if not fresh or (not due and len(fresh) < digest.MIN_ITEMS):  # cek murah sebelum enrich
        print(waiting.format(len(fresh)))
        return
    # shortcut: berita yang menunggu tidak disimpan; yang keburu keluar dari jendela sumber
    # (SOURCE_LIMIT) sebelum digest terkirim hilang. Simpan item ke history kalau run jadi sering.
    # Ringkasan & tanggal terbit dari meta artikel: konteks untuk AI dan penyaring berita lama.
    # Hasilnya juga dipakai ulang saat kiriman kategori (enrich hanya sekali per berita).
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(enrich, fresh))
    ranked = digest.rank([item for item in fresh if not is_stale(item)], all_items, trends)
    if not due and len(ranked) < digest.MIN_ITEMS:
        print(waiting.format(len(ranked)))
        return
    if ranked:
        cutoff = now - timedelta(hours=curator.RECENT_HOURS)
        recent = [p['title'] for p in history["areaanime_posts"] if datetime.fromisoformat(p['ts']) >= cutoff]
        text = digest.build(ranked, trends, recent[-30:], now)
        filename = f"digest-{now.astimezone(digest.WIB):%Y%m%d-%H%M}.txt"
        print(f"    {len(ranked)} berita masuk digest ({len(text.encode('utf-8')) // 1024} KB)")
        if DRY_RUN:
            Path(DIGEST_PREVIEW).write_text(text, encoding="utf-8")
            print(f"    [DRY-RUN] isi digest disimpan ke {DIGEST_PREVIEW}")
        if not send_webhook(WH_DIGEST, build_digest_embed(ranked, filename), username="Digest Berita",
                            files=[(filename, text.encode("utf-8"))]):
            return  # coba lagi run berikutnya dengan berita yang sama
        history["digest_last"] = now.isoformat(timespec="seconds")
    history["digest_seen"].extend(item['link'] for item in fresh)
    if not DRY_RUN:
        save_history(history)


# --- TAMPILAN EMBED ---
def gallery(item):
    """Gambar tambahan selain gambar utama, untuk send_webhook(extra_images=...)."""
    return [url for url in item.get('images') or [] if url != item.get('img')]


# platform: (nama di footer, situs untuk ikon, label tombol link)
PLATFORMS = {
    "x": ("X (Twitter)", "https://x.com/", "X"),
    "telegram": ("Telegram", "https://t.me/", "Telegram"),
}


def build_social_embed(item):
    """Embed postingan X / Telegram: teks terjemahan lengkap + teks asli."""
    site = item['site']
    platform = "x" if 'x' in site else "telegram"
    footer, platform_home, label = PLATFORMS[platform]
    translate_item(item)
    text, original = item['title_id'], item['title']
    handle = item['source'].removeprefix('X ') if platform == "x" else f"t.me/{site['telegram']}"

    # Baris pertama jadi judul embed, sisanya deskripsi (supaya teks tidak tampil dua kali).
    first, _, rest = text.partition("\n")
    if len(first) > 250:
        first, rest = handle, text
    parts = []
    if site.get('leak'):
        parts.append("⚠️ *Bocoran (leak): belum tentu resmi dan bisa berisi spoiler.*")
    if rest.strip():
        parts.append(clip(rest.strip(), 3000))
    if text != original:
        parts.append("> 📝 " + clip(original, 700).replace("\n", "\n> "))
    links = [f"👉 **[Lihat postingan di {label}]({item['link']})**"]
    if item.get('x_link'):
        links.append(f"🐦 [Postingan X]({item['x_link']})")
    parts.append(" · ".join(links))

    embed = DiscordEmbed(
        title=clip(f"{site.get('emoji', '🐦')} {first or handle}", 256),
        description="\n\n".join(parts),
        color=site.get('color', '1d9bf0'),
        url=item['link'],
    )
    embed.set_author(name=f"{item.get('author_name') or handle} ({handle})", url=site.get('home'),
                     icon_url=item.get('author_avatar') or favicon(platform_home))
    embed.set_footer(text=f"{footer} • Bot Berita", icon_url=favicon(platform_home))
    if item.get('published'):
        embed.set_timestamp(item['published'].timestamp())
    else:
        embed.set_timestamp()
    if item.get('img'):
        embed.set_image(url=item['img'])
    return embed


def build_news_embed(item):
    if is_social(item['site']):
        return build_social_embed(item)
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
    if info.get('x'):
        trends = ", ".join(f"[{t['term']}]({x_search(t['term'])}) ({t['region']} #{t['rank']})" for t in info['x'])
        embed.add_embed_field(name="🐦 Trending di X", value=clip(trends, 1024), inline=False)
    embed.set_footer(text=f"Dikurasi otomatis ({info['mode']}) • Bot Berita")
    embed.set_timestamp()
    if item.get('img'):
        embed.set_image(url=item['img'])
    return embed


def x_search(term):
    return f"https://x.com/search?q={quote(term)}"


def build_x_watch_embed(watch):
    lines = [f"**[{w['term']}]({x_search(w['term'])})** · X {w['region']} #{w['rank']}\n`{w['tag']}` {w['reason']}"
             for w in watch]
    embed = DiscordEmbed(
        title="📈 Lagi trending di X, belum ada beritanya",
        description=clip("\n\n".join(lines), 4000),
        color="1d9bf0",
    )
    embed.set_author(name="Areaanime Radar • Trending X")
    embed.set_footer(text="Cek dulu konteksnya di X sebelum diposting • Bot Berita")
    embed.set_timestamp()
    return embed


def record_area_post(history, link, key, title):
    history["areaanime_posts"].append({
        "link": link, "key": key, "title": title,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    if not DRY_RUN:
        save_history(history)


# --- MAIN LOOP ---
def mark_sent(history, sent, link):
    sent.add(link)
    history["sent"].append(link)
    if not DRY_RUN:
        save_history(history)


def main():
    print("Memulai pengecekan multi-website..." + (" (DRY-RUN)" if DRY_RUN else ""))
    deadline = time.monotonic() + RUN_TIME_LIMIT_MINUTES * 60 if RUN_TIME_LIMIT_MINUTES > 0 else None
    if not TRANSLATOR.api_key:
        print("GEMINI_API_KEY belum diatur; berita asing ditunda, berita Indonesia tetap dikirim.")
    history = load_history()
    sent = set(history["sent"])
    all_items = []
    category_batches = []

    # 1. Ambil semua sumber dahulu, supaya Areaanime tidak menunggu seluruh kiriman kategori.
    for site in TARGETS:
        # Sumber radar (channel None) hanya dipakai kurasi Areaanime & digest
        webhook_url = os.getenv(f"DISCORD_WEBHOOK_{site['channel']}") if site['channel'] else None
        if not webhook_url and not (WH_AREAANIME or WH_DIGEST):
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
        if webhook_url:
            category_batches.append((webhook_url, items, bool(site.get('leak'))))

    trends = []
    if WH_AREAANIME or WH_DIGEST:
        trends = x_trends.fetch(SESSION)
        print(f"    {len(trends)} topik trending X terbaca")

    # 2. Kurasi berita berpotensi viral untuk channel Areaanime
    if WH_AREAANIME:
        print("--> Kurasi Areaanime")
        seen = set(history["areaanime_seen"])
        candidates, links = [], set()
        for item in all_items:
            if item['link'] not in seen and item['link'] not in links:
                links.add(item['link'])
                candidates.append(item)

        picks, watch = curator.select(candidates, all_items, history["areaanime_posts"], trends)
        if not picks:
            print(f"    Tidak ada berita yang cukup menarik dari {len(candidates)} kandidat.")
        # Kandidat yang tidak dipilih sudah selesai dinilai. Pilihan tetap bisa dicoba ulang
        # jika pengiriman gagal atau proses berhenti sebelum sempat mengirimnya.
        selected = {item['link'] for item, _ in picks}
        history["areaanime_seen"].extend(c['link'] for c in candidates if c['link'] not in selected)
        if not DRY_RUN:
            save_history(history)
        for item, info in picks:
            print(f"    [AREAANIME {info['score']:g}/10] {item['source']}: {item['title'][:40]}...")
            try:
                embed = build_areaanime_embed(enrich(item), info)
            except TranslationUnavailable as error:
                print(f"    Areaanime ditunda: {error}")
                continue
            if send_webhook(WH_AREAANIME, embed, username="Areaanime Radar", extra_images=gallery(item)):
                history["areaanime_seen"].append(item['link'])
                record_area_post(history, item['link'], info['key'], item['title'])
            time.sleep(1.5)

        if watch:
            print(f"    [AREAANIME X] {', '.join(w['term'] for w in watch)}")
            if send_webhook(WH_AREAANIME, build_x_watch_embed(watch), username="Areaanime Radar"):
                for w in watch:
                    record_area_post(history, x_search(w['term']), w['key'], w['term'])
            time.sleep(1.5)

    # 2b. File digest untuk ChatGPT/Claude: semua berita baru beserta konteksnya
    if WH_DIGEST:
        run_digest(history, all_items, trends)

    # 3. Kirim kategori dari yang paling lama, simpan segera setelah setiap kiriman berhasil.
    #    Bocoran paling cepat basi, jadi channel LEAKS dikirim lebih dulu.
    category_batches.sort(key=lambda batch: not batch[2])
    for webhook_url, items, _ in category_batches:
        for item in reversed(items):
            if item['link'] in sent:
                continue
            if deadline and time.monotonic() > deadline:
                break
            enrich(item)
            if is_stale(item):
                # Berita lama yang baru masuk jendela sumber: tandai saja, jangan kirim.
                print(f"    [LAMA] {item['source']}: {item['title'][:40]}... (terbit {item['published']:%Y-%m-%d})")
                mark_sent(history, sent, item['link'])
                continue
            print(f"    [NEW] {item['source']}: {item['title'][:40]}...")
            try:
                embed = build_news_embed(item)
            except TranslationUnavailable as error:
                print(f"    Berita ditunda: {error}")
                continue
            if send_webhook(webhook_url, embed, extra_images=gallery(item)):
                mark_sent(history, sent, item['link'])
            time.sleep(1.5)
        else:
            continue
        # Berhenti rapi sebelum timeout GitHub Actions; sisanya dicoba lagi pada run berikutnya.
        print(f"Batas waktu run ({RUN_TIME_LIMIT_MINUTES:g} menit) tercapai; sisa berita dikirim run berikutnya.")
        break

    if DRY_RUN:
        print("DRY-RUN: history tidak disimpan.")
    else:
        save_history(history)
    print("Selesai pengecekan semua web.")


if __name__ == "__main__":
    main()
