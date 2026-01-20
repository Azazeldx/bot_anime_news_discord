import requests
from bs4 import BeautifulSoup
from discord_webhook import DiscordWebhook, DiscordEmbed
from deep_translator import GoogleTranslator
import json
import time
import os
from dotenv import load_dotenv

load_dotenv()

# --- KONFIGURASI WEBHOOK ---
WH_ORICON = os.getenv("DISCORD_WEBHOOK_ORICON")
WH_GAME = os.getenv("DISCORD_WEBHOOK_GAME")
WH_INDO = os.getenv("DISCORD_WEBHOOK_INDO")
WH_BUZZ = os.getenv("DISCORD_WEBHOOK_BUZZ")
WH_GENERAL = os.getenv("DISCORD_WEBHOOK_GENERAL")
WH_LN = os.getenv("DISCORD_WEBHOOK_LN")
WH_VTUBER = os.getenv("DISCORD_WEBHOOK_VTUBER")
WH_ANN = os.getenv("DISCORD_WEBHOOK_ANN")
WH_CRUNCHYROLL = os.getenv("DISCORD_WEBHOOK_CRUNCHYROLL")

HISTORY_FILE = "history.json"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# --- FUNGSI HELPER ---
def load_history():
    if not os.path.exists(HISTORY_FILE): return []
    try:
        with open(HISTORY_FILE, 'r') as f: return json.load(f)
    except: return []

def save_history(history_list):
    with open(HISTORY_FILE, 'w') as f: json.dump(history_list[-300:], f)

def translate_text(text, source_lang):
    if source_lang == 'id': return text
    try:
        # TRIK: Kalau aslinya Jepang, oper ke Inggris dulu biar bahasanya luwes
        if source_lang == 'ja':
            text_en = GoogleTranslator(source='ja', target='en').translate(text)
            return GoogleTranslator(source='en', target='id').translate(text_en)
        
        # Kalau bukan Jepang (misal Spanyol/Inggris), langsung ke Indo aja
        return GoogleTranslator(source=source_lang, target='id').translate(text)
    except:
        return text

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

def parse_gamerwk(soup):
    results = []
    articles = soup.find_all('h3', class_='entry-title')
    for item in articles[:5]:
        link_elm = item.find('a')
        if not link_elm: continue
        
        img_src = ""
        parent = item.find_parent('div')
        if parent:
            img_elm = parent.find('img')
            if img_elm:
                img_src = img_elm.get('data-img-url') or img_elm.get('src')
        
        results.append({
            "title": link_elm.get('title') or link_elm.text.strip(),
            "link": link_elm.get('href'),
            "img": img_src,
            "source": "Gamerwk"
        })
    return results

def parse_natalie_comic(soup):
    results = []
    articles = soup.select('.NA_card')
    for item in articles[:5]:
        link_elm = item.find('a')
        title_elm = item.find('p', class_='NA_card_title')
        img_elm = item.find('img')
        if title_elm and link_elm:
            results.append({
                "title": title_elm.text.strip(),
                "link": "https://natalie.mu" + link_elm['href'],
                "img": img_elm.get('data-src') or img_elm.get('src') if img_elm else "",
                "source": "Natalie Comic"
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
    # Selector: Ambil kotak berita (herald box) yang memiliki class 'news'
    # Kalau mau ambil review juga, hapus '.news' jadi 'div.herald.box'
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

def parse_crunchyroll(soup):
    results = []
    articles = soup.find_all('article')
    
    for item in articles[:5]:
        try:
            title_elm = item.find('h3')
            if not title_elm: continue
            title = title_elm.text.strip()
            
            link_elm = title_elm.find_parent('a')
            if not link_elm: continue
            
            link = link_elm.get('href')
            if link and not link.startswith('http'):
                link = "https://www.crunchyroll.com" + link

            img_elm = item.find('img')
            img_src = ""
            if img_elm:
                img_src = img_elm.get('src')

            results.append({
                "title": title,
                "link": link,
                "img": img_src,
                "source": "Crunchyroll"
            })
            
        except Exception as e:
            print(f"Error parsing Crunchyroll: {e}")
            continue

    return results

def parse_gamebrott(soup):
    results = []
    # Gamebrott membungkus artikelnya dalam tag <article> dengan class 'jeg_post'
    articles = soup.select('article.jeg_post')
    
    for item in articles[:5]:
        try:
            # 1. Ambil Judul & Link
            title_elm = item.select_one('.jeg_post_title a')
            if not title_elm: continue
            
            title = title_elm.text.strip()
            link = title_elm.get('href')

            # 2. Ambil Gambar (Hati-hati, Gamebrott pakai Lazy Load)
            img_elm = item.select_one('.jeg_thumb img')
            img_src = ""
            
            if img_elm:
                # Prioritaskan 'data-src' karena 'src' isinya cuma placeholder (gambar kosong/svg)
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
        title_elm = item.find('h4', class_='entrylist_title').find('a')
        img_elm = item.find('figure').find('img') if item.find('figure') else None
        if title_elm:
            results.append({
                "title": title_elm.text.strip(),
                "link": title_elm.get('href'),
                "img": img_elm.get('src') if img_elm else "",
                "source": "Yaraon!"
            })
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

def parse_kaori(soup):
    results = []
    articles = soup.select('.td_module_wrap')
    for item in articles[:5]:
        try:
            title_elm = item.find('h3', class_='entry-title')
            if not title_elm: continue
            link_elm = title_elm.find('a')
            if not link_elm: continue
            
            img_src = ""
            thumb_div = item.find('div', class_='td-module-thumb')
            if thumb_div:
                img_tag = thumb_div.find('img')
                if img_tag:
                    img_src = img_tag.get('data-img-url') or img_tag.get('src')
                if not img_src:
                    span_bg = thumb_div.find('span', class_='entry-thumb')
                    if span_bg and span_bg.has_attr('style') and "url(" in span_bg['style']:
                        try: img_src = span_bg['style'].split("url('")[1].split("')")[0]
                        except: pass
            
            results.append({
                "title": link_elm.get('title') or link_elm.text.strip(),
                "link": link_elm['href'],
                "img": img_src,
                "source": "KAORI Nusantara"
            })
        except: continue
    return results

def parse_dengeki(soup):
    results = []
    articles = soup.find_all('li', class_=lambda x: x and ('ArticleList_listItem' in x or 'TopicList_listItem' in x or 'NewsList_listItem' in x))
    for item in articles[:5]:
        try:
            link_elm = item.find('a')
            title_elm = item.find('p', class_=lambda x: x and ('ArticleCard_title' in x or 'TopicCard_title' in x))
            
            if not title_elm:
                title_elm = item.find('p', class_=lambda x: x and 'title' in x.lower())

            img_elm = item.find('img')
            
            if title_elm and link_elm:
                link = link_elm.get('href')
                if link and not link.startswith('http'): link = "https://dengekionline.com" + link
                img_src = img_elm.get('src') if img_elm else ""
                
                results.append({
                    "title": title_elm.text.strip(),
                    "link": link,
                    "img": img_src,
                    "source": "Dengeki Online"
                })
        except: continue
    return results

# --- DAFTAR WEBSITE & CONFIG TAMPILAN ---
TARGETS = [
    # 1. ORICON
    {"url": "https://www.oricon.co.jp/category/anime/", "lang": "ja", "parser": parse_oricon, "webhook": WH_ORICON, "color": "e60033", "emoji": "🇯🇵"},

    # 2. INDO NEWS
    {"url": "https://gamerwk.com/", "lang": "id", "parser": parse_gamerwk, "webhook": WH_INDO, "color": "ff6600", "emoji": "🇮🇩"},
    {"url": "https://www.kaorinusantara.or.id/rubrik/aktual/anime", "lang": "id", "parser": parse_kaori, "webhook": WH_INDO, "color": "ff9900", "emoji": "🇮🇩"},

    # 3. GAME & TECH
    {"url": "https://www.famitsu.com/category/pc-game/page/1", "lang": "ja", "parser": parse_famitsu, "webhook": WH_GAME, "color": "00ff00", "emoji": "🎮"},
    {"url": "https://gamebrott.com/", "lang": "id", "parser": parse_gamebrott, "webhook": WH_GAME, "color": "e15f41", "emoji": "🎮"},

    # 4. GOSIP/BUZZ
    {"url": "http://yaraon-blog.com/", "lang": "ja", "parser": parse_yaraon, "webhook": WH_BUZZ, "color": "ffd700", "emoji": "🔥"},
    {"url": "http://otakomu.jp/", "lang": "ja", "parser": parse_otakomu, "webhook": WH_BUZZ, "color": "ffd700", "emoji": "🔥"},
    {"url": "http://blog.esuteru.com/archives/cat_6292.html", "lang": "ja", "parser": parse_esuteru, "webhook": WH_BUZZ, "color": "ffd700", "emoji": "🔥"},

    # 5. GENERAL ANIME
    {"url": "https://natalie.mu/comic", "lang": "ja", "parser": parse_natalie_comic, "webhook": WH_GENERAL, "color": "0099ff", "emoji": "📺"},
    {"url": "https://mantan-web.jp/anime/", "lang": "ja", "parser": parse_mantanweb, "webhook": WH_GENERAL, "color": "0099ff", "emoji": "📺"},
    {"url": "https://somoskudasai.org/", "lang": "es", "parser": parse_somoskudasai, "webhook": WH_GENERAL, "color": "0099ff", "emoji": "🇪🇸"},
    {"url": "https://www.famitsu.com/category/anime/page/1", "lang": "ja", "parser": parse_famitsu, "webhook": WH_GENERAL, "color": "0099ff", "emoji": "📺"},
    {"url": "https://animeanime.jp/category/news/latest/latest/", "lang": "ja", "parser": parse_animeanime, "webhook": WH_GENERAL, "color": "0099ff", "emoji": "📺"},
    {"url": "https://dengekionline.com/category/anime/page/1", "lang": "ja", "parser": parse_dengeki, "webhook": WH_GENERAL, "color": "0099ff", "emoji": "📺"},

    # 6. LIGHT NOVEL & Manga
    {"url": "https://animeanime.jp/category/news/novel/latest/", "lang": "ja", "parser": parse_animeanime, "webhook": WH_LN, "color": "9900cc", "emoji": "📚"},
    {"url": "http://otakomu.jp/archives/cat_325595.html", "lang": "ja", "parser": parse_otakomu, "webhook": WH_LN, "color": "9900cc", "emoji": "📚"},
    {"url": "https://animeanime.jp/category/news/manga/latest/", "lang": "ja", "parser": parse_animeanime, "webhook": WH_LN, "color": "9900cc", "emoji": "📚"},

    # 7. VTUBER
    {"url": "https://dengekionline.com/special/vtuber", "lang": "ja", "parser": parse_dengeki, "webhook": WH_VTUBER, "color": "00ced1", "emoji": "🤖"}, 

    # 8. ANIME NEWS NETWORK (Official)
    {"url": "https://www.animenewsnetwork.com/", "lang": "en", "parser": parse_ann, "webhook": WH_ANN, "color": "1c3c74", "emoji": "🇺🇸"},

    # 9. CRUNCHYROLL (Official)
    {"url": "https://www.crunchyroll.com/news", "lang": "en", "parser": parse_crunchyroll, "webhook": WH_CRUNCHYROLL, "color": "f47521", "emoji": "🟠"},
]

# --- MAIN LOOP ---
def main():
    print("Memulai pengecekan multi-website...")
    history = load_history()
    
    for site in TARGETS:
        if not site['webhook']:
            print(f"Skipping {site['url']} (Webhook not set)")
            continue

        print(f"--> Mengecek: {site['url']}")
        try:
            response = requests.get(site['url'], headers=HEADERS, timeout=15)
            response.encoding = response.apparent_encoding
            
            soup = BeautifulSoup(response.text, 'html.parser')
            news_items = site['parser'](soup)
            
            if not news_items:
                print("    Tidak ada berita ditemukan (Cek selector?)")
            
            for news in reversed(news_items):
                if news['link'] in history:
                    continue
                
                print(f"    [NEW] {news['source']}: {news['title'][:30]}...")
                
                translated_title = translate_text(news['title'], site['lang'])
                
                prefix_emoji = site.get('emoji', '📰')
                clean_desc = news['title'][:250]
                desc_with_link = f"{clean_desc}...\n\n👉 **[Baca Selengkapnya di Website]({news['link']})**"
                
                icon_url = ""
                try:
                    domain = site['url'].split('/')[2]
                    icon_url = f"https://www.google.com/s2/favicons?domain={domain}&sz=64"
                except:
                    pass
                
                # --- DISCORD EMBED ---
                webhook = DiscordWebhook(url=site['webhook']) 
                embed_color = site.get('color', '03b2f8')
                
                embed = DiscordEmbed(
                    title=f"{prefix_emoji} {translated_title[:250]}",
                    description=desc_with_link,
                    color=embed_color
                )

                embed.set_author(name=news['source'], url=site['url'], icon_url=icon_url)
                embed.set_url(news['link'])
                embed.set_footer(text=f"Source: {news['source']} • Bot Berita", icon_url=icon_url)
                embed.set_timestamp()
                
                if news['img'] and "base64" not in news['img'] and len(news['img']) > 10:
                    embed.set_image(url=news['img'])
                
                webhook.add_embed(embed)
                
                try:
                    response_webhook = webhook.execute()
                    if response_webhook.status_code == 400:
                        print(f"    Gagal kirim (400). Mencoba kirim tanpa gambar...")
                        webhook.embeds[0].image = {} 
                        webhook.execute()
                except Exception as err:
                    print(f"    Webhook error: {err}")
                
                history.append(news['link'])
                time.sleep(2) 
                
        except Exception as e:
            print(f"    Error di {site['url']}: {e}")
            
    save_history(history)
    print("Selesai pengecekan semua web.")

if __name__ == "__main__":
    main()