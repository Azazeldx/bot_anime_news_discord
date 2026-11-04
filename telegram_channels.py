"""Postingan channel Telegram publik lewat pratinjau web t.me/s/<channel>.

Banyak akun leak/berita anime di X me-mirror postingannya ke channel Telegram, mis. Sugoi LITE
(@SugoiLITE di X) -> t.me/sugoileaks. Pratinjau t.me/s/ bisa dibaca tanpa login, API key, atau
cookie, jadi jauh lebih stabil daripada membaca X langsung.

Hasil berupa list dict seperti parser lain: {"title", "link", "img", "images", "source", "summary",
"published"}. "title" berisi teks postingan lengkap supaya terjemahan & kurasi membaca semuanya.
"""
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from bs4 import BeautifulSoup

PREVIEW_URL = "https://t.me/s/{channel}"
# Ganti lewat env TELEGRAM_CHANNELS="channel:bahasa:Nama,channel:bahasa:Nama".
DEFAULT_CHANNELS = "sugoileaks:en:Sugoi LITE"
MAX_AGE_HOURS = float(os.getenv("TELEGRAM_MAX_AGE_HOURS") or 24)
TEXT_LIMIT = 1500
MAX_IMAGES = 4  # galeri embed Discord menampilkan maksimal 4 gambar
_IMAGE_SELECTORS = (".tgme_widget_message_photo_wrap, .tgme_widget_message_video_thumb, "
                    ".link_preview_image, .link_preview_right_image, .link_preview_video_thumb")
_X_HOSTS = {"x.com", "twitter.com", "fixupx.com", "fxtwitter.com", "vxtwitter.com", "fixvx.com"}


def channels():
    """[(channel, bahasa, nama)] dari env TELEGRAM_CHANNELS atau default."""
    result = []
    for entry in (os.getenv("TELEGRAM_CHANNELS") or DEFAULT_CHANNELS).split(","):
        channel, _, rest = entry.strip().lstrip("@").partition(":")
        lang, _, name = rest.partition(":")
        if re.fullmatch(r"\w{5,32}", channel):
            result.append((channel, lang.strip() or "en", name.strip() or channel))
    return result


def _text(node):
    """Teks pesan dengan baris baru dipertahankan."""
    if node is None:
        return ""
    for br in node.find_all("br"):
        br.replace_with("\n")
    for quote in node.find_all("blockquote"):
        quote.insert_before("\n")
    text = re.sub(r"[ \t]+", " ", node.get_text())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(line.strip() for line in text.split("\n"))).strip()


def _background(node):
    match = re.search(r"background-image:url\('([^']+)'\)", node.get("style", ""))
    return match.group(1) if match else ""


def _x_link(node):
    """Link postingan X yang dibagikan (fixupx/fxtwitter -> x.com), kalau ada."""
    for a in node.select("a[href]"):
        url = urlparse(a["href"])
        if url.netloc.lower().removeprefix("www.") in _X_HOSTS and "/status/" in url.path:
            return f"https://x.com{url.path}"
    return ""


def _is_recent(published, now=None):
    if not published or MAX_AGE_HOURS <= 0:
        return True
    return published >= (now or datetime.now(timezone.utc)) - timedelta(hours=MAX_AGE_HOURS)


def parse(html, channel, name, limit=10, now=None):
    """Postingan terbaru (yang punya teks) dari halaman t.me/s/<channel>, paling baru dulu."""
    soup = BeautifulSoup(html, "html.parser")
    messages = soup.select(".tgme_widget_message[data-post]")
    if not messages:
        raise ValueError("pratinjau Telegram kosong (channel privat / tidak ada?)")
    header = soup.select_one(".tgme_channel_info_header_photo img, .tgme_widget_message_user_photo img")
    avatar = header.get("src", "") if header else ""

    results = []
    for message in sorted(messages, key=lambda m: int(m["data-post"].rpartition("/")[2] or 0), reverse=True):
        post = message["data-post"]
        reply = message.select_one(".tgme_widget_message_reply")
        for quoted in message.select(".tgme_widget_message_reply"):
            quoted.extract()  # kutipan pesan yang dibalas jangan ikut terbaca sebagai isi / gambar
        own = _text(message.select_one(".tgme_widget_message_text"))
        context = _text(reply.select_one(".js-message_reply_text")) if reply else ""
        if not own and not context:
            continue  # gambar tanpa keterangan: tidak ada yang bisa diterjemahkan / dinilai
        text = f"{own}\n\n» {context}" if own and context else own or context

        time_tag = message.select_one(".tgme_widget_message_date time[datetime]")
        published = datetime.fromisoformat(time_tag["datetime"]) if time_tag else None
        if not _is_recent(published, now):
            continue
        images = [url for url in (_background(n) for n in message.select(_IMAGE_SELECTORS)) if url]
        results.append({
            "title": text[:TEXT_LIMIT],
            "link": f"https://t.me/{post}",
            "img": images[0] if images else "",
            "images": images[:MAX_IMAGES],
            "source": name,
            "summary": "",
            "published": published,
            "author_name": name,
            "author_avatar": avatar,
            "x_link": _x_link(message),
        })
        if len(results) == limit:
            break
    return results


def fetch(session, site):
    """Ambil postingan satu channel Telegram."""
    response = session.get(PREVIEW_URL.format(channel=site["telegram"]), timeout=20)
    response.raise_for_status()
    response.encoding = "utf-8"
    return parse(response.text, site["telegram"], site["name"], site.get("limit", 10))
