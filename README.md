# Bot Berita Anime Discord

Bot yang mengambil berita anime, manga, game, dan VTuber dari ±30 sumber (Jepang, Inggris, Indonesia, Spanyol) plus trending X, menerjemahkan judul serta ringkasannya ke Bahasa Indonesia, lalu mengirimnya ke channel Discord lewat webhook. Bot dijalankan GitHub Actions secara terjadwal.

## Struktur

| File | Isi |
|---|---|
| `main.py` | Alur utama: ambil berita, terjemahkan, kirim embed, simpan history |
| `sources.py` | Daftar sumber (`TARGETS`) dan parser tiap website / RSS |
| `curator.py` | Kurasi berita berpotensi viral untuk channel Areaanime |
| `x_trends.py` | Trending X Jepang & Indonesia (trends24.in) untuk kurasi Areaanime |
| `history.json` | Memori berita yang sudah dikirim (di-commit otomatis oleh bot) |
| `history_store.py` | Simpan history secara atomik dan gabungkan history saat Git rebase |
| `translator.py` | Terjemahkan judul dan ringkasan menggunakan Gemini API |

## Channel & Secrets

Isi di **Settings → Secrets and variables → Actions** (atau di `.env` saat menjalankan bot di komputer sendiri):

| Secret | Channel |
|---|---|
| `DISCORD_WEBHOOK_ORICON` | Oricon anime |
| `DISCORD_WEBHOOK_INDO` | Berita Indonesia (KAORI) |
| `DISCORD_WEBHOOK_GAME` | Famitsu, Gamebrott, 4Gamer |
| `DISCORD_WEBHOOK_BUZZ` | Blog matome (Yaraon, Otakomu, Hachima) |
| `DISCORD_WEBHOOK_GENERAL` | Berita anime umum |
| `DISCORD_WEBHOOK_LN` | Light novel & manga |
| `DISCORD_WEBHOOK_VTUBER` | VTuber |
| `DISCORD_WEBHOOK_ANN` | Anime News Network |
| `DISCORD_WEBHOOK_CRUNCHYROLL` | Crunchyroll News |
| `DISCORD_WEBHOOK_JP_NEWS` | Yahoo! Japan (di `.env` lokal namanya `DISCORD_WEBHOOK_JPGENERAL`) |
| `DISCORD_WEBHOOK_AREAANIME` | Kurasi berita berpotensi viral untuk @Areaanime.id |
| `GEMINI_API_KEY` | Terjemahan Gemini; wajib untuk mengirim berita berbahasa asing |
| `ANTHROPIC_API_KEY` | *Opsional*: kurasi Areaanime dinilai Claude (default memakai Gemini) |
| `X_RSS_URL` | *Opsional*: bridge RSS untuk membaca akun X langsung (lihat Channel Areaanime) |

Channel yang webhook-nya kosong otomatis dilewati.

Areaanime diproses setelah pengambilan sumber, sebelum pengiriman ke channel kategori. Setiap kiriman yang berhasil langsung disimpan ke history. Jika proses terhenti, GitHub Actions tetap mencoba menyimpan history dan mencadangkannya sebagai artifact selama 7 hari.

Permintaan Gemini punya timeout dan cache selama satu run. Judul dan ringkasan diterjemahkan langsung ke Indonesia dalam satu permintaan JSON. Jika API key belum ada, kuota habis, atau terjemahan gagal, berita asing ditunda dan tidak dicatat sebagai terkirim. Berita Indonesia tetap berjalan. Setelah tiga kegagalan berturut-turut, permintaan Gemini dihentikan untuk sisa run. Retry rate limit Discord dibatasi; kiriman yang gagal tetap bisa dicoba pada run berikutnya. History yang rusak menghentikan bot agar berita lama tidak terkirim ulang.

## Mengaktifkan terjemahan Gemini

1. Buat API key di [Google AI Studio](https://aistudio.google.com/apikey).
2. Tambahkan GitHub Actions secret `GEMINI_API_KEY` pada repository ini. Untuk pemakaian lokal, isi `.env` dengan pengaturan dari `.env.example`.
3. Jalankan workflow secara manual untuk memeriksa hasil terjemahan. Centang `dry_run` untuk menguji tanpa kiriman Discord atau perubahan history.

Model default adalah `gemini-3.5-flash-lite`. Model dapat diganti lewat environment lokal atau GitHub Actions **variable** `GEMINI_MODEL`. Ketersediaan model dan kuota gratis mengikuti akun Google; lihat [daftar model](https://ai.google.dev/gemini-api/docs/models) dan [harga resmi](https://ai.google.dev/gemini-api/docs/pricing).

Jeda antarpermintaan default 6 detik untuk mengurangi rate limit. Bisa diubah lewat `GEMINI_REQUEST_INTERVAL` (environment lokal atau GitHub Actions variable). Key dikirim melalui header, dan pesan error di log tidak memuat key atau isi respons server. Integrasi menggunakan `requests`, tanpa tambahan SDK.

## Channel Areaanime

Setiap run, semua berita yang terambil dinilai potensi viralnya untuk audiens Indonesia. Hanya berita dengan skor ≥ 7/10 yang dikirim, maksimal 3 per run, dan topik yang sama tidak diposting ulang dalam 72 jam. Berita RSS yang lebih tua dari 48 jam dilewati.

**Sumber.** Selain semua sumber kategori, kurasi juga membaca sumber radar yang tidak dikirim ke channel lain (`RADAR` di `sources.py`): Anime Corner, MyAnimeList, Reddit r/anime (flair News), Anime!Anime!, AUTOMATON, dan Kincir. Makin banyak media yang memberitakan cerita yang sama, makin tinggi skornya.

**Trending X.** Daftar trending X Jepang & Indonesia (3 jam terakhir) diambil dari [trends24.in](https://trends24.in/japan/). Berita yang topiknya sedang trending mendapat skor tambahan, dan embed-nya menampilkan trend tersebut. Trending yang jelas terkait anime/game/VTuber tetapi belum ada beritanya dikirim sebagai embed **📈 Lagi trending di X** (maksimal 3 per run, tidak diulang dalam 72 jam).

X tidak menyediakan API baca gratis, dan instance Nitter publik sudah diblokir. Untuk membaca postingan akun X langsung, siapkan bridge RSS sendiri (mis. [RSSHub](https://docs.rsshub.app/) dengan cookie akun X). Lalu isi secret `X_RSS_URL` dengan template seperti `https://rsshub.domainmu.com/twitter/user/{account}`. Daftar akun bisa diganti lewat variable `X_ACCOUNTS` (format `akun:bahasa,akun:bahasa`); defaultnya MangaMoguraRE, animecorner_ac, AniTrendz, anime_natalie, comic_natalie, dan animatetimes.

**Penilaian.**
- **LLM (default: Gemini, memakai `GEMINI_API_KEY` yang sama dengan terjemahan)**: menilai kandidat seperti editor konten dan menulis saran **tag + judul feed** dengan gaya Areaanime (bagian `[kurung siku]` = highlight kuning, tampil tebal di Discord). Model default `gemini-flash-latest`. Kalau sibuk (503/429), bot mencoba ulang lalu pindah ke `gemini-flash-lite-latest`. Kalau `ANTHROPIC_API_KEY` diisi, Claude dipakai lebih dulu dan Gemini menjadi cadangan.
- **Heuristik** (kalau semua LLM gagal): franchise besar, jenis kejadian (adaptasi anime, season baru, tamat/hiatus, kontroversi, rekor, dll), liputan lintas media, trending X, kaitan dengan Indonesia, serta penalti untuk merch/diskon dan artikel rutin per episode.

Pengaturan opsional lewat env: `AREAANIME_MIN_SCORE` (default 7), `AREAANIME_MAX_PER_RUN` (default 3), `AREAANIME_GEMINI_MODEL` (default `gemini-flash-latest`), `AREAANIME_GEMINI_FALLBACK` (default `gemini-flash-lite-latest`), `AREAANIME_MODEL` (Claude, default `claude-opus-5-5`), `AREAANIME_EFFORT` (Claude, default `medium`).

## Menjalankan di komputer sendiri

```bash
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python main.py --dry-run   # cek hasil tanpa kirim ke Discord & tanpa ubah history
venv\Scripts\python main.py             # jalan sungguhan
```

Jika akan melakukan `git pull --rebase` pada history yang berubah secara lokal, aktifkan penggabungan JSON (sudah otomatis di GitHub Actions):

```bash
git config merge.news-history.driver 'python history_store.py --merge "%A" "%B"'
```

Uji regresi tanpa jaringan atau kiriman Discord: `python -m unittest discover -s tests`.

## Menambah sumber baru

Tambahkan entri di `TARGETS` (`sources.py`). Untuk situs yang punya RSS cukup isi `"rss": "<nama sumber>"`. Untuk situs biasa, tulis fungsi parser yang mengembalikan list `{"title", "link", "img", "source"}`. Link relatif otomatis dijadikan absolut.
