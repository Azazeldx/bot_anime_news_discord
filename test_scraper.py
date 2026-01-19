import requests
from bs4 import BeautifulSoup

# Setup Headers (Penting biar tidak dianggap bot jahat)
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

url = "https://www.oricon.co.jp/category/anime/"

print("Sedang mengambil data dari Oricon...")

try:
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 1. Cari semua elemen <article> yang punya class "card"
        news_list = soup.select('article.card')
        
        print(f"Ditemukan {len(news_list)} artikel. Menampilkan 5 terbaru:\n")
        
        for item in news_list[:5]: # Ambil 5 berita pertama saja untuk test
            
            # Cari elemen judul (h2 class="title")
            title_elm = item.find('h2', class_='title')
            
            # Cari elemen link (tag a)
            link_elm = item.find('a')
            
            # Cari gambar (opsional, kadang ada berita tanpa gambar)
            img_elm = item.find('img')
            
            if title_elm and link_elm:
                title = title_elm.text.strip()
                link = "https://www.oricon.co.jp" + link_elm['href'] # Linknya relatif, jadi harus ditambah domain
                
                print(f"Judul: {title}")
                print(f"Link:  {link}")
                if img_elm:
                    print(f"Img:   {img_elm.get('src')}")
                print("-" * 50)
                
    else:
        print(f"Gagal akses. Status Code: {response.status_code}")

except Exception as e:
    print(f"Terjadi Error: {e}")