"""Daftar sumber berita + parser untuk masing-masing website.

Setiap parser menerima BeautifulSoup (atau bytes XML untuk RSS) dan mengembalikan
list dict: {"title", "link", "img", "source"}. Link/gambar relatif boleh dikembalikan
apa adanya, main.py yang akan menjadikannya absolut.
"""
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape

from bs4 import BeautifulSoup
from defusedxml.ElementTree import fromstring as parse_xml  # aman dari XML bomb / XXE

# --- BAGIAN PARSER ---

def parse_oricon(soup):
    results = []
    articles = soup.select('article.card')
    for item in articles[:5]:
        title_elm = item.find('h2', class_='title')
        link_elm = item.find('a')
        img_elm = item.find('img')
        if title_elm and link_elm:
            img_src = img_elm.get('data-original') or img_elm.get('src') if img_elm else ""
            results.append({
                "title": title_elm.text.strip(),
                "link": "https://www.oricon.co.jp" + link_elm['href'],
                "img": img_src,
                "source": "Oricon News"
            })
    return results

def parse_somoskudasai(soup):
    results = []
    articles = soup.select('ul.ul li') 
    
    for item in articles[:5]:
        try:
            link_elm = item.find('a')
            if not link_elm: continue
            
            link = link_elm.get('href')
            if link and link.startswith('./'):
                link = link.replace('./', 'https://somoskudasai.org/', 1)
            elif link and not link.startswith('http'):
                link = 'https://somoskudasai.org/' + link.lstrip('/')

            title_elm = link_elm.find('span', class_='h3')
            
            if title_elm:
                title = title_elm.text.strip()
            else:
                title = link_elm.get('title', '').strip()

            if not title: continue

            img_elm = item.find('img')
            img_src = ""
            if img_elm:
                img_src = img_elm.get('src')
                if img_src and img_src.startswith('./'):
                    img_src = img_src.replace('./', 'https://somoskudasai.org/', 1)
            
            results.append({
                "title": title,
                "link": link,
                "img": img_src,
                "source": "SomosKudasai"
            })
        except Exception as e:
            continue
    return results

def parse_ann(soup):
    results = []
    articles = soup.select('div.herald.box.news') 
    
    for item in articles[:5]:
        try:
    
            title_elm = item.find('h3')
            if not title_elm: continue
            
            link_elm = title_elm.find('a')
            if not link_elm: continue

            title = link_elm.text.strip()
            
            link = link_elm.get('href')
            if link and not link.startswith('http'):
                link = "https://www.animenewsnetwork.com" + link

            img_src = ""
            thumb_div = item.find('div', class_='thumbnail')
            if thumb_div:
                img_src = thumb_div.get('data-src')
                if img_src and not img_src.startswith('http'):
                    img_src = "https://www.animenewsnetwork.com" + img_src

            results.append({
                "title": title,
                "link": link,
                "img": img_src,
                "source": "Anime News Network"
            })
            
        except Exception as e:
            print(f"Error parsing ANN: {e}")
            continue

    return results

def parse_gamebrott(soup):
    results = []
    articles = soup.select('article.jeg_post')
    
    for item in articles[:5]:
        try:
            title_elm = item.select_one('.jeg_post_title a')
            if not title_elm: continue
            
            title = title_elm.text.strip()
            link = title_elm.get('href')

            img_elm = item.select_one('.jeg_thumb img')
            img_src = ""
            
            if img_elm:
                img_src = img_elm.get('data-src') or img_elm.get('src')
            
            results.append({
                "title": title,
                "link": link,
                "img": img_src,
                "source": "Gamebrott"
            })
            
        except Exception as e:
            print(f"Error parsing Gamebrott: {e}")
            continue

    return results

def parse_yaraon(soup):
    results = []
    articles = soup.select('div.entrylist') 
    for item in articles[:5]:
        title_elm = item.select_one('h4.entrylist_title a')
        img_elm = item.select_one('figure img')
        if title_elm:
            results.append({
                "title": title_elm.text.strip(),
                "link": title_elm.get('href'),
                "img": img_elm.get('src') if img_elm else "",
                "source": "Yaraon!"
            })
    return results

def parse_animatetimes(soup):
    results = []
    articles = soup.select('.row--foritem .c-item')

    for item in articles[:5]:
        try:
            link_elm = item.find('a', class_='c-item-link')
            if not link_elm: continue
            
            link = link_elm.get('href')
            if link and not link.startswith('http'):
                link = "https://www.animatetimes.com" + link

            title_elm = item.find('div', class_='c-item-ttl__heading')
            if not title_elm: continue
            title = title_elm.text.strip()

            img_elm = item.find('img')
            img_src = ""
            if img_elm:
                img_src = img_elm.get('src')
            
            results.append({
                "title": title,
                "link": link,
                "img": img_src,
                "source": "Animate Times"
            })
            
        except Exception as e:
            print(f"Error parsing Animate Times: {e}")
            continue
    
    return results

def parse_otakomu(soup):
    results = []
    articles = soup.select('article')
    for item in articles[:5]:
        title_elm = None
        link_elm = None
        img_src = ""
        
        if item.find('h2', class_='articleTop-title'):
            title_elm = item.find('h2', class_='articleTop-title')
            link_elm = item.find('a', class_='articleTop-link')
            img_div = item.find('div', class_='articleTop-img')
        else:
            title_elm = item.find('h2', class_='articleBottom-title')
            if title_elm: link_elm = title_elm.find('a')
            img_div = item.find('a', class_='articleBottom-img-link')

        if img_div and img_div.has_attr('style'):
            style_text = img_div['style']
            if 'url(' in style_text:
                try: img_src = style_text.split('url(')[1].split(')')[0].strip("'").strip('"')
                except: pass

        if title_elm and link_elm:
            results.append({
                "title": title_elm.text.strip(),
                "link": link_elm['href'],
                "img": img_src,
                "source": "Otakomu"
            })
    return results

def parse_mantanweb(soup):
    results = []
    articles = soup.select('li.article-list_horizontal__item')
    for item in articles[:5]:
        link_elm = item.find('a', class_='article-list_horizontal__unit')
        title_elm = item.find('h3', class_='article-list_horizontal__title')
        img_elm = item.find('img')
        if title_elm and link_elm:
            img_src = img_elm.get('data-src') or img_elm.get('src') if img_elm else ""
            results.append({
                "title": title_elm.text.strip(),
                "link": "https://mantan-web.jp" + link_elm.get('href'),
                "img": img_src,
                "source": "MANTANWEB"
            })
    return results

def parse_esuteru(soup):
    results = []
    articles = soup.select('article')
    for item in articles[:5]:
        title_elm = None
        link_elm = None
        img_src = ""
        img_container = None
        classes = item.get('class', [])
        
        if 'articleTop' in classes:
            title_elm = item.find('h2', class_='articleTop-title')
            link_elm = item.find('a', class_='articleTop-link')
            img_container = item.find('div', class_='articleTop-img')
        elif 'articleBottom' in classes:
            title_elm = item.find('h2', class_='articleBottom-title')
            if title_elm: link_elm = title_elm.find('a')
            img_container = item.find('a', class_='articleBottom-img-link')

        if img_container and img_container.has_attr('style') and 'url(' in img_container['style']:
            try: img_src = img_container['style'].split('url(')[1].split(')')[0].strip("'").strip('"')
            except: pass

        if title_elm and link_elm:
            results.append({
                "title": title_elm.text.strip(),
                "link": link_elm['href'],
                "img": img_src,
                "source": "Hachima Kiko"
            })
    return results

def parse_famitsu(soup):
    results = []
    articles = soup.find_all('div', class_=lambda x: x and 'cardContainer' in x)
    for item in articles[:5]:
        try:
            title_elm = item.find('p', class_=lambda x: x and 'cardTitle' in x)
            link_elm = item.find('a')
            img_elm = item.find('img')
            
            if title_elm and link_elm:
                link = link_elm.get('href')
                if link and not link.startswith('http'): link = "https://www.famitsu.com" + link
                img_src = img_elm.get('src') if img_elm else ""
                results.append({
                    "title": title_elm.text.strip(),
                    "link": link,
                    "img": img_src,
                    "source": "Famitsu"
                })
        except: continue
    return results

def parse_animeanime(soup):
    results = []
    articles = soup.find_all('section', class_=lambda x: x and 'item--cate-news' in x)
    for item in articles[:5]:
        try:
            link_elm = item.find('a', class_='link')
            title_elm = item.find('h2', class_='title')
            img_elm = item.find('img', class_='figure')
            
            if title_elm and link_elm:
                link = link_elm.get('href')
                if link and not link.startswith('http'): link = "https://animeanime.jp" + link
                img_src = img_elm.get('src') if img_elm else ""
                if img_src and not img_src.startswith('http'): img_src = "https://animeanime.jp" + img_src
                
                results.append({
                    "title": title_elm.text.strip(),
                    "link": link,
                    "img": img_src,
                    "source": "Anime!Anime!"
                })
        except: continue
    return results

def parse_vtub0(soup):
    results = []
    articles = soup.select('article.post-list')
    
    for item in articles[:5]:
        try:
            
            link_elm = item.find('a')
            if not link_elm: continue
            link = link_elm.get('href')

            title_elm = item.find(class_='entry-title')
            if not title_elm: continue
            title = title_elm.text.strip()

            img_elm = item.find('img')
            img_src = ""
            if img_elm:
                img_src = img_elm.get('src')
            
            results.append({
                "title": title,
                "link": link,
                "img": img_src,
                "source": "V-Tuber ZERO"
            })
            
        except Exception as e:
            print(f"Error parsing V-Tuber ZERO: {e}")
            continue

    return results

def parse_moguravr(soup):
    results = []
    
    articles = soup.select('a.mg-hover-card-link')
    
    for item in articles[:5]:
        try:
            
            link = item.get('href')
            if not link: continue

            title_elm = item.find('h3', class_='card-title')
            if not title_elm: continue
            title = title_elm.text.strip()

            img_elm = item.find('img', class_='mg-img-cover')
            img_src = ""
            if img_elm:
                img_src = img_elm.get('src')
            
            results.append({
                "title": title,
                "link": link,
                "img": img_src,
                "source": "Mogura VR"
            })
            
        except Exception as e:
            print(f"Error parsing Mogura VR: {e}")
            continue

    return results

def parse_4gamer(soup):
    results = []
    articles = soup.select('div.V2_article_container')

    for item in articles[:5]:
        try:
            h2_elm = item.find('h2')
            if not h2_elm: continue
            
            link_elm = h2_elm.find('a')
            if not link_elm: continue

            title = link_elm.text.strip()
            link = link_elm.get('href')
            
            if link and not link.startswith('http'):
                link = "https://www.4gamer.net" + link

            img_elm = item.find('img', class_='img_right_top')
            img_src = ""
            if img_elm:
                img_src = img_elm.get('src')
                # Fix Relative Image
                if img_src and not img_src.startswith('http'):
                    img_src = "https://www.4gamer.net" + img_src

            results.append({
                "title": title,
                "link": link,
                "img": img_src,
                "source": "4Gamer.net"
            })

        except Exception as e:
            print(f"Error parsing 4Gamer: {e}")
            continue

    return results


def parse_dengeki(soup):
    # Dengeki pakai class CSS-module yang berubah tiap build (ArticleCard_title__xxx),
    # jadi cari semua link artikel lalu ambil judul dari elemen yang class-nya mengandung "title".
    results = []
    seen = set()
    is_title = lambda c: c and 'title' in c.lower()
    for link_elm in soup.select('a[href*="/article/"]'):
        link = link_elm.get('href')
        if link in seen: continue
        title_elm = link_elm if is_title(' '.join(link_elm.get('class', []))) else link_elm.find(class_=is_title)
        if not title_elm or not title_elm.text.strip(): continue
        seen.add(link)

        card = link_elm.find_parent('li') or link_elm.find_parent('div')
        img_elm = card.find('img') if card else None
        results.append({
            "title": title_elm.text.strip(),
            "link": link,
            "img": img_elm.get('src') if img_elm else "",
            "source": "Dengeki Online"
        })
        if len(results) == 5: break
    return results

def _strip_html(text):
    return re.sub(r'\s+', ' ', BeautifulSoup(text or '', 'html.parser').get_text(' ')).strip()

def _parse_date(text):
    """Tanggal RSS (RFC 822) atau Atom/RDF (ISO 8601) -> datetime UTC, None kalau tidak terbaca."""
    try:
        date = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        try:
            date = datetime.fromisoformat(text.replace('Z', '+00:00'))
        except (AttributeError, ValueError):
            return None
    return date if date.tzinfo else date.replace(tzinfo=timezone.utc)

def parse_rss(content, source, limit=5):
    """Parser generik RSS 2.0, RSS 1.0 (RDF) dan Atom (lebih awet daripada scraping HTML)."""
    results = []
    root = parse_xml(content)
    entries = [e for e in root.iter() if e.tag.split('}')[-1] in ('item', 'entry')]
    for item in entries[:limit]:
        fields, img = {}, ""
        for child in item:
            tag = child.tag.split('}')[-1]  # buang namespace (media:, content:, dc:)
            if child.get('url') and tag in ('thumbnail', 'content', 'enclosure'):
                img = img or child.get('url')
            elif tag == 'link' and child.get('href'):  # Atom
                fields.setdefault('link', child.get('href'))
            elif tag == 'image' and child.text:
                img = img or child.text.strip()
            elif child.text:
                fields.setdefault(tag, child.text.strip())

        if not fields.get('title') or not fields.get('link'): continue
        if not img:
            html = fields.get('encoded', '') + fields.get('description', '') + fields.get('content', '')
            match = re.search(r'<img[^>]+src="([^"]+)"', html)
            img = unescape(match.group(1)) if match else ""

        results.append({
            "title": unescape(fields['title']),
            "link": fields['link'],
            "img": img,
            "source": source,
            "summary": _strip_html(fields.get('description') or fields.get('summary'))[:500],
            "published": _parse_date(fields.get('pubDate') or fields.get('published')
                                     or fields.get('updated') or fields.get('date')),
        })
    return results

# --- DAFTAR WEBSITE & CONFIG TAMPILAN ---
# "channel" = nama webhook, dibaca dari env DISCORD_WEBHOOK_<channel>.
# Sumber RSS memakai "rss": "<nama sumber>" sebagai ganti "parser".
TARGETS = [
    # 1. ORICON
    {"url": "https://www.oricon.co.jp/category/anime/", "lang": "ja", "parser": parse_oricon, "channel": "ORICON", "color": "e60033", "emoji": "🇯🇵"},

    # 2. INDO NEWS - halaman HTML KAORI memblokir server GitHub (403), pakai RSS rubriknya
    {"url": "https://www.kaorinusantara.or.id/rubrik/aktual/anime/feed", "lang": "id", "rss": "KAORI Nusantara", "channel": "INDO", "color": "ff9900", "emoji": "🇮🇩", "home": "https://www.kaorinusantara.or.id/"},

    # 3. GAME & TECH
    {"url": "https://www.famitsu.com/category/pc-game/page/1", "lang": "ja", "parser": parse_famitsu, "channel": "GAME", "color": "00ff00", "emoji": "🎮"},
    {"url": "https://gamebrott.com/", "lang": "id", "parser": parse_gamebrott, "channel": "GAME", "color": "e15f41", "emoji": "🎮"},
    {"url": "https://www.4gamer.net/", "lang": "ja", "parser": parse_4gamer, "channel": "GAME", "color": "003b86", "emoji": "🎮"},

    # 4. GOSIP/BUZZ
    {"url": "http://yaraon-blog.com/", "lang": "ja", "parser": parse_yaraon, "channel": "BUZZ", "color": "ffd700", "emoji": "🔥"},
    {"url": "http://otakomu.jp/", "lang": "ja", "parser": parse_otakomu, "channel": "BUZZ", "color": "ffd700", "emoji": "🔥"},
    {"url": "http://blog.esuteru.com/archives/cat_6292.html", "lang": "ja", "parser": parse_esuteru, "channel": "BUZZ", "color": "ffd700", "emoji": "🔥"},

    # 5. GENERAL ANIME
    {"url": "https://mantan-web.jp/anime/", "lang": "ja", "parser": parse_mantanweb, "channel": "GENERAL", "color": "0099ff", "emoji": "📺"},
    {"url": "https://somoskudasai.org/", "lang": "es", "parser": parse_somoskudasai, "channel": "GENERAL", "color": "0099ff", "emoji": "🇪🇸"},
    {"url": "https://www.famitsu.com/category/anime/page/1", "lang": "ja", "parser": parse_famitsu, "channel": "GENERAL", "color": "0099ff", "emoji": "📺"},
    {"url": "https://animeanime.jp/category/news/latest/latest/", "lang": "ja", "parser": parse_animeanime, "channel": "GENERAL", "color": "0099ff", "emoji": "📺"},
    {"url": "https://dengekionline.com/category/anime/page/1", "lang": "ja", "parser": parse_dengeki, "channel": "GENERAL", "color": "0099ff", "emoji": "📺"},
    {"url": "https://www.animatetimes.com/anime/", "lang": "ja", "parser": parse_animatetimes, "channel": "GENERAL", "color": "003c86", "emoji": "🇯🇵"},

    # 6. LIGHT NOVEL & Manga
    {"url": "https://animeanime.jp/category/news/novel/latest/", "lang": "ja", "parser": parse_animeanime, "channel": "LN", "color": "9900cc", "emoji": "📚"},
    {"url": "http://otakomu.jp/archives/cat_325595.html", "lang": "ja", "parser": parse_otakomu, "channel": "LN", "color": "9900cc", "emoji": "📚"},
    {"url": "https://animeanime.jp/category/news/manga/latest/", "lang": "ja", "parser": parse_animeanime, "channel": "LN", "color": "9900cc", "emoji": "📚"},

    # 7. VTUBER
    {"url": "https://dengekionline.com/special/vtuber", "lang": "ja", "parser": parse_dengeki, "channel": "VTUBER", "color": "00ced1", "emoji": "🤖"},
    {"url": "https://vtub0.com/", "lang": "ja", "parser": parse_vtub0, "channel": "VTUBER", "color": "00ced1", "emoji": "🤖"},
    {"url": "https://www.oricon.co.jp/news/tag/id/vtuber/", "lang": "ja", "parser": parse_oricon, "channel": "VTUBER", "color": "00ced1", "emoji": "🤖"},
    {"url": "https://www.moguravr.com/category/virtual-youtuber/", "lang": "ja", "parser": parse_moguravr, "channel": "VTUBER", "color": "00ced1", "emoji": "🤖"},

    # 8. ANIME NEWS NETWORK (Official)
    {"url": "https://www.animenewsnetwork.com/", "lang": "en", "parser": parse_ann, "channel": "ANN", "color": "1c3c74", "emoji": "🇺🇸"},

    # 9. CRUNCHYROLL (Official) - halaman /news sekarang dirender JavaScript, pakai RSS resminya
    {"url": "https://cr-news-api-service.prd.crunchyrollsvc.com/v1/en-US/rss", "lang": "en", "rss": "Crunchyroll", "channel": "CRUNCHYROLL", "color": "f47521", "emoji": "🟠", "home": "https://www.crunchyroll.com/news"},

    # 10. JAPAN GENERAL NEWS - halaman /flash sudah berubah, pakai RSS Yahoo! News
    {"url": "https://news.yahoo.co.jp/rss/topics/top-picks.xml", "lang": "ja", "rss": "Yahoo! Japan News", "channel": "JPGENERAL", "color": "ff0033", "emoji": "🔴", "home": "https://news.yahoo.co.jp/"},
    {"url": "https://news.yahoo.co.jp/rss/categories/entertainment.xml", "lang": "ja", "rss": "Yahoo! Japan Entame", "channel": "JPGENERAL", "color": "ff0033", "emoji": "🔴", "home": "https://news.yahoo.co.jp/categories/entertainment"},
]

# Sumber khusus radar Areaanime ("channel": None): ikut dinilai & menambah hitungan liputan
# lintas media, tapi tidak dikirim ke channel kategori mana pun.
RADAR = [
    {"url": "https://animecorner.me/feed/", "lang": "en", "rss": "Anime Corner", "home": "https://animecorner.me/"},
    {"url": "https://myanimelist.net/rss/news.xml", "lang": "en", "rss": "MyAnimeList", "home": "https://myanimelist.net/news"},
    {"url": "https://www.reddit.com/r/anime/search.rss?q=flair_name%3A%22News%22&restrict_sr=1&sort=new", "lang": "en", "rss": "Reddit r/anime", "home": "https://www.reddit.com/r/anime/"},
    {"url": "https://animeanime.jp/rss/index.rdf", "lang": "ja", "rss": "Anime!Anime!", "home": "https://animeanime.jp/"},
    {"url": "https://automaton-media.com/feed/", "lang": "ja", "rss": "AUTOMATON", "home": "https://automaton-media.com/"},
    {"url": "https://kincir.com/feed/", "lang": "id", "rss": "Kincir", "home": "https://kincir.com/"},
]

# Akun X (opsional). X tidak punya RSS/API gratis, jadi isi env X_RSS_URL dengan bridge RSS
# milik sendiri, mis. RSSHub: https://rsshub.domainmu.com/twitter/user/{account}
# Daftar akun bisa diganti lewat env X_ACCOUNTS="akun:bahasa,akun:bahasa".
X_ACCOUNTS = os.getenv("X_ACCOUNTS") or (
    "MangaMoguraRE:en,animecorner_ac:en,AniTrendz:en,anime_natalie:ja,comic_natalie:ja,animatetimes:ja")
X_RSS_URL = os.getenv("X_RSS_URL", "")
if "{account}" in X_RSS_URL:
    for entry in X_ACCOUNTS.split(","):
        account, _, lang = entry.strip().partition(":")
        if account:
            RADAR.append({"url": X_RSS_URL.format(account=account), "lang": lang or "en",
                          "rss": f"X @{account}", "home": f"https://x.com/{account}"})

TARGETS += [{**site, "channel": None, "limit": 10} for site in RADAR]

# Dihapus karena memblokir bot (Cloudflare / human verification), juga dari server GitHub:
#   - https://gamerwk.com/        (403 "Just a moment...")
#   - https://natalie.mu/comic    (405 "Human Verification")
