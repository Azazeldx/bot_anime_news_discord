"""Postingan terbaru akun X (Twitter) untuk channel TWITTER.

X tidak punya API baca gratis, jadi ada dua jalur:
  1. Bridge RSS milik sendiri (env X_RSS_URL, mis. RSSHub
     https://rsshub.domainmu.com/twitter/user/{account}). Paling stabil, dipakai kalau diisi.
  2. Timeline embed publik X (syndication.twitter.com) tanpa login. Gratis, tetapi tidak
     resmi: bisa kena rate limit atau mengembalikan timeline lama. Gagal = akun dilewati,
     bot tetap jalan.

Hasil berupa list dict seperti parser lain: {"title", "link", "img", "source", "summary",
"published"}. "title" berisi teks tweet lengkap supaya terjemahan & kurasi membaca semuanya.
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone
from html import unescape

from bs4 import BeautifulSoup

SYNDICATION_URL = "https://syndication.twitter.com/srv/timeline-profile/screen-name/{account}"

# Akun default channel TWITTER; ganti lewat env X_TWITTER_ACCOUNTS="akun:bahasa,akun:bahasa".
DEFAULT_ACCOUNTS = ("SomosKudasai:es,animetrends:en,Dexerto:en,animetv_jp:en,MangaMoguraRE:en,"
                    "WSJ_manga:en,AniNewsAndFacts:en,seiyuucorner:en,Seifukuanimehub:en")
MAX_AGE_HOURS = float(os.getenv("X_MAX_AGE_HOURS") or 24)  # tweet lebih lama tidak dikirim
TEXT_LIMIT = 1000


def accounts():
    """[(akun, bahasa)] dari env X_TWITTER_ACCOUNTS atau default."""
    result = []
    for entry in (os.getenv("X_TWITTER_ACCOUNTS") or DEFAULT_ACCOUNTS).split(","):
        account, _, lang = entry.strip().lstrip("@").partition(":")
        if re.fullmatch(r"\w{1,15}", account):
            result.append((account, lang.strip() or "en"))
    return result


def _clean(text):
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", unescape(text or ""))).strip()


def _tweet_date(text):
    try:
        return datetime.strptime(text, "%a %b %d %H:%M:%S %z %Y")
    except (TypeError, ValueError):
        return None


def _tweet_text(tweet):
    """Teks tweet dengan link t.co dibuka dan link media (gambar) dibuang."""
    text = tweet.get("full_text") or tweet.get("text") or ""
    entities = tweet.get("entities") or {}
    for url in entities.get("urls") or []:
        if url.get("url"):
            text = text.replace(url["url"], url.get("expanded_url") or url["url"])
    for media in (entities.get("media") or []) + ((tweet.get("extended_entities") or {}).get("media") or []):
        if media.get("url"):
            text = text.replace(media["url"], "")
    return _clean(text)


def _tweet_image(tweet):
    for media in ((tweet.get("extended_entities") or {}).get("media")
                  or (tweet.get("entities") or {}).get("media") or []):
        if media.get("media_url_https"):
            return media["media_url_https"]
    return ""


def _is_recent(published, now=None):
    if not published or MAX_AGE_HOURS <= 0:
        return True
    return published >= (now or datetime.now(timezone.utc)) - timedelta(hours=MAX_AGE_HOURS)


def parse_syndication(html, account, limit=5, now=None):
    """Tweet terbaru (tanpa retweet & balasan) dari halaman timeline embed X."""
    script = BeautifulSoup(html, "html.parser").find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        raise ValueError("timeline X tidak berisi data (diblokir / perlu login?)")
    data = json.loads(script.string)
    entries = (((data.get("props") or {}).get("pageProps") or {}).get("timeline") or {}).get("entries") or []

    tweets = []
    for entry in entries:
        tweet = ((entry or {}).get("content") or {}).get("tweet")
        if not tweet or not str(tweet.get("id_str", "")).isdigit():
            continue
        if tweet.get("retweeted_status") or tweet.get("in_reply_to_status_id_str"):
            continue
        tweets.append(tweet)
    tweets.sort(key=lambda t: int(t["id_str"]), reverse=True)  # tweet pin bisa muncul paling atas

    results = []
    for tweet in tweets:
        published = _tweet_date(tweet.get("created_at"))
        text = _tweet_text(tweet)
        if not text or not _is_recent(published, now):
            continue
        user = tweet.get("user") or {}
        screen_name = user.get("screen_name") or account
        results.append({
            "title": text[:TEXT_LIMIT],
            "link": f"https://x.com/{screen_name}/status/{tweet['id_str']}",
            "img": _tweet_image(tweet),
            "source": f"X @{screen_name}",
            "summary": "",
            "published": published,
            "x_name": user.get("name") or screen_name,
            "x_avatar": (user.get("profile_image_url_https") or "").replace("_normal.", "_bigger."),
        })
        if len(results) == limit:
            break
    return results


def normalize_rss(items, account, now=None):
    """Item dari bridge RSS -> format tweet (teks lengkap, link x.com, tanpa RT & tweet lama)."""
    results = []
    for item in items:
        text = _clean(item.get("summary") or "") or _clean(item.get("title"))
        title = _clean(item.get("title"))
        if title.startswith("RT ") or title.startswith("Re ") or title.startswith("R to @"):
            continue
        if not text or not _is_recent(item.get("published"), now):
            continue
        status = re.search(r"/status(?:es)?/(\d+)", item.get("link") or "")
        link = f"https://x.com/{account}/status/{status.group(1)}" if status else item.get("link")
        results.append(dict(item, title=text[:TEXT_LIMIT], link=link, summary="",
                            source=f"X @{account}", x_name=account, x_avatar=""))
    return results


def fetch(session, site, parse_rss):
    """Ambil tweet satu akun. parse_rss = parser RSS generik dari sources.py."""
    account, limit = site["x"], site.get("limit", 5)
    rss_template = os.getenv("X_RSS_URL", "")
    if "{account}" in rss_template:
        response = session.get(rss_template.format(account=account), timeout=20)
        response.raise_for_status()
        return normalize_rss(parse_rss(response.content, f"X @{account}", limit * 2), account)[:limit]

    response = session.get(SYNDICATION_URL.format(account=account), timeout=20,
                           headers={"Accept": "text/html"})
    response.raise_for_status()
    response.encoding = "utf-8"
    return parse_syndication(response.text, account, limit)
