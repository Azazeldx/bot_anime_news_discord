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
        return GoogleTranslator(source=source_lang, target='id').translate(text)
    except:
        return text

# --- BAGIAN PARSER (REVISI V2) ---

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
    # Revisi Selector Gamerwk: Cari langsung h3 dengan class entry-title
    articles = soup.find_all('h3', class_='entry-title')
    for item in articles[:5]:
        link_elm = item.find('a')
        if not link_elm: continue
        
        # Cari gambar dengan naik ke parent lalu cari img
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
    # Revisi Selector SomosKudasai
    articles = soup.select('.ar-main .ar-post') 
    for item in articles[:5]:
        title_elm = item.find('h2')
        if not title_elm: continue
        link_elm = title_elm.find('a')
        if not link_elm: continue
        
        img_src = ""
        img_elm = item.find('img')
        if img_elm:
            img_src = img_elm.get('src') or ""
            
        results.append({
            "title": title_elm.text.strip(),
            "link": link_elm.get('href'),
            "img": img_src,
            "source": "SomosKudasai"
        })
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
    # Revisi Selector Dengeki: Menangkap lebih banyak jenis list item
    articles = soup.find_all('li', class_=lambda x: x and ('ArticleList_listItem' in x or 'TopicList_listItem' in x or 'NewsList_listItem' in x))
    
    for item in articles[:5]:
        try:
            link_elm = item.find('a')
            title_elm = item.find('p', class_=lambda x: x and ('ArticleCard_title' in x or 'TopicCard_title' in x))
            
            # Fallback jika title ada di tempat lain
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

# --- DAFTAR WEBSITE ---
TARGETS = [
    # 1. ORICON
    {"url": "https://www.oricon.co.jp/category/anime/", "lang": "ja", "parser": parse_oricon, "webhook": WH_ORICON, "color": "e60033"},

    # 2. INDO NEWS
    {"url": "https://gamerwk.com/", "lang": "id", "parser": parse_gamerwk, "webhook": WH_INDO, "color": "ff6600"},
    {"url": "https://www.kaorinusantara.or.id/rubrik/aktual/anime", "lang": "id", "parser": parse_kaori, "webhook": WH_INDO, "color": "ff9900"},

    # 3. GAME & TECH
    {"url": "https://www.famitsu.com/category/pc-game/page/1", "lang": "ja", "parser": parse_famitsu, "webhook": WH_GAME, "color": "00ff00"},

    # 4. GOSIP/BUZZ
    {"url": "http://yaraon-blog.com/", "lang": "ja", "parser": parse_yaraon, "webhook": WH_BUZZ, "color": "ffd700"},
    {"url": "http://otakomu.jp/", "lang": "ja", "parser": parse_otakomu, "webhook": WH_BUZZ, "color": "ffd700"},
    {"url": "http://blog.esuteru.com/archives/cat_6292.html", "lang": "ja", "parser": parse_esuteru, "webhook": WH_BUZZ, "color": "ffd700"},

    # 5. GENERAL ANIME
    {"url": "https://natalie.mu/comic", "lang": "ja", "parser": parse_natalie_comic, "webhook": WH_GENERAL, "color": "0099ff"},
    {"url": "https://mantan-web.jp/anime/", "lang": "ja", "parser": parse_mantanweb, "webhook": WH_GENERAL, "color": "0099ff"},
    {"url": "https://somoskudasai.com/", "lang": "es", "parser": parse_somoskudasai, "webhook": WH_GENERAL, "color": "0099ff"},
    {"url": "https://www.famitsu.com/category/anime/page/1", "lang": "ja", "parser": parse_famitsu, "webhook": WH_GENERAL, "color": "0099ff"},
    {"url": "https://animeanime.jp/category/news/latest/latest/", "lang": "ja", "parser": parse_animeanime, "webhook": WH_GENERAL, "color": "0099ff"},
    {"url": "https://dengekionline.com/category/anime/page/1", "lang": "ja", "parser": parse_dengeki, "webhook": WH_GENERAL, "color": "0099ff"},

    # 6. LIGHT NOVEL & Manga
    {"url": "https://animeanime.jp/category/news/novel/latest/", "lang": "ja", "parser": parse_animeanime, "webhook": WH_LN, "color": "9900cc"},
    {"url": "http://otakomu.jp/archives/cat_325595.html", "lang": "ja", "parser": parse_otakomu, "webhook": WH_LN, "color": "9900cc"},
    {"url": "https://animeanime.jp/category/news/manga/latest/", "lang": "ja", "parser": parse_animeanime, "webhook": WH_LN, "color": "9900cc"},

    # 7. VTUBER
    {"url": "https://dengekionline.com/special/vtuber", "lang": "ja", "parser": parse_dengeki, "webhook": WH_VTUBER, "color": "00ced1"}, 
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
            
            # --- FIX: MOJIBAKE ---
            # Wajib memaksa UTF-8 untuk site Jepang jadul seperti MANTANWEB
            response.encoding = 'utf-8'
            
            # Gunakan .text karena encoding sudah dipaksa
            soup = BeautifulSoup(response.text, 'html.parser')
            
            news_items = site['parser'](soup)
            
            if not news_items:
                print("    Tidak ada berita ditemukan (Cek selector?)")
            
            for news in reversed(news_items):
                if news['link'] in history:
                    continue
                
                print(f"    [NEW] {news['source']}: {news['title'][:30]}...")
                
                translated_title = translate_text(news['title'], site['lang'])
                
                webhook = DiscordWebhook(url=site['webhook']) 
                embed_color = site.get('color', '03b2f8')
                
                # --- FIX: ERROR 400 ---
                # Potong Judul (Max 250) & Deskripsi (Max 2000) untuk keamanan Discord
                embed = DiscordEmbed(
                    title=translated_title[:250], 
                    description=news['title'][:500], # Potong deskripsi asli
                    color=embed_color
                )
                embed.set_author(name=news['source'], url=site['url'])
                embed.set_url(news['link'])
                embed.set_footer(text=f"Source: {news['source']}")
                embed.set_timestamp()
                
                if news['img'] and "base64" not in news['img'] and len(news['img']) > 10:
                    embed.set_image(url=news['img'])
                
                webhook.add_embed(embed)
                
                # Eksekusi Webhook dengan Error Handling
                try:
                    response_webhook = webhook.execute()
                    if response_webhook.status_code == 400:
                        print(f"    Gagal kirim (400). Mencoba kirim tanpa gambar...")
                        # Retry mechanism: Kadang gambar bikin error, coba kirim text aja
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