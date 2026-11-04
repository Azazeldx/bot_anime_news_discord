# Bot Berita Anime Discord

Bot yang mengambil berita anime, manga, game, dan VTuber dari ±40 sumber (Jepang, Inggris, Indonesia, Spanyol), postingan akun X, Bluesky, dan Telegram (termasuk bocoran Sugoi LITE), plus trending X, menerjemahkan judul serta ringkasannya ke Bahasa Indonesia, lalu mengirimnya ke channel Discord lewat webhook. Bot dijalankan GitHub Actions secara terjadwal.

## Struktur

| File | Isi |
|---|---|
| `main.py` | Alur utama: ambil berita, terjemahkan, kirim embed, simpan history |
| `sources.py` | Daftar sumber (`TARGETS`) dan parser tiap website / RSS |
| `curator.py` | Kurasi berita berpotensi viral untuk channel Areaanime |
| `x_accounts.py` | Postingan terbaru akun X pilihan untuk channel Twitter |
| `telegram_channels.py` | Postingan channel Telegram publik (`t.me/s/…`) untuk channel Leaks |
| `bluesky.py` | Postingan akun Bluesky lewat API publik (mis. Comic Natalie) |
| `x_trends.py` | Trending X Jepang & Indonesia (trends24.in) untuk kurasi Areaanime |
| `history.json` | Memori berita yang sudah dikirim (di-commit otomatis oleh bot) |
| `history_store.py` | Simpan history secara atomik dan gabungkan history saat Git rebase |
| `translator.py` | Terjemahkan judul dan ringkasan menggunakan Gemini API |

## Channel & Secrets

Isi di **Settings → Secrets and variables → Actions** (atau di `.env` saat menjalankan bot di komputer sendiri):

| Secret | Channel |
|---|---|
| `DISCORD_WEBHOOK_ORICON` | Oricon anime |
| `DISCORD_WEBHOOK_INDO` | Berita Indonesia (Gwigwi) |
| `DISCORD_WEBHOOK_GAME` | Famitsu, Gamebrott, 4Gamer |
| `DISCORD_WEBHOOK_BUZZ` | Blog matome (Yaraon, Otakomu, Hachima) |
| `DISCORD_WEBHOOK_GENERAL` | Berita anime umum |
| `DISCORD_WEBHOOK_LN` | Light novel & manga |
| `DISCORD_WEBHOOK_VTUBER` | VTuber |
| `DISCORD_WEBHOOK_ANN` | Anime News Network |
| `DISCORD_WEBHOOK_CRUNCHYROLL` | Crunchyroll News |
| `DISCORD_WEBHOOK_JP_NEWS` | Yahoo! Japan (di `.env` lokal namanya `DISCORD_WEBHOOK_JPGENERAL`) |
| `DISCORD_WEBHOOK_TWITTER` | Postingan akun X (lihat Channel Twitter) |
| `DISCORD_WEBHOOK_LEAKS` | Bocoran anime/manga dari Sugoi LITE (lihat Channel Leaks) |
| `DISCORD_WEBHOOK_AREAANIME` | Kurasi berita berpotensi viral untuk @Areaanime.id |
| `GEMINI_API_KEY` | Terjemahan Gemini; wajib untuk mengirim berita berbahasa asing |
| `ANTHROPIC_API_KEY` | *Opsional*: kurasi Areaanime dinilai Claude (default memakai Gemini) |
| `TWITTER_AUTH_TOKEN` | Cookie `auth_token` akun X untuk RSSHub di GitHub Actions (lihat Channel Twitter) |
| `X_RSS_URL` | *Opsional*: bridge RSS milik sendiri, menggantikan RSSHub bawaan workflow |

Channel yang webhook-nya kosong otomatis dilewati.

Areaanime diproses setelah pengambilan sumber, sebelum pengiriman ke channel kategori. Setiap kiriman yang berhasil langsung disimpan ke history. Jika proses terhenti, GitHub Actions tetap mencoba menyimpan history dan mencadangkannya sebagai artifact selama 7 hari.

Permintaan Gemini punya timeout dan cache selama satu run. Judul dan ringkasan diterjemahkan langsung ke Indonesia dalam satu permintaan JSON. Jika API key belum ada, kuota habis, atau terjemahan gagal, berita asing ditunda dan tidak dicatat sebagai terkirim. Berita Indonesia tetap berjalan. Setelah tiga kegagalan berturut-turut, permintaan Gemini dihentikan untuk sisa run. Retry rate limit Discord dibatasi; kiriman yang gagal tetap bisa dicoba pada run berikutnya. History yang rusak menghentikan bot agar berita lama tidak terkirim ulang.

## Mengaktifkan terjemahan Gemini

1. Buat API key di [Google AI Studio](https://aistudio.google.com/apikey).
2. Tambahkan GitHub Actions secret `GEMINI_API_KEY` pada repository ini. Untuk pemakaian lokal, isi `.env` dengan pengaturan dari `.env.example`.
3. Jalankan workflow secara manual untuk memeriksa hasil terjemahan. Centang `dry_run` untuk menguji tanpa kiriman Discord atau perubahan history.

Model default adalah `gemini-3.5-flash-lite`. Model dapat diganti lewat environment lokal atau GitHub Actions **variable** `GEMINI_MODEL`. Ketersediaan model dan kuota gratis mengikuti akun Google; lihat [daftar model](https://ai.google.dev/gemini-api/docs/models) dan [harga resmi](https://ai.google.dev/gemini-api/docs/pricing).

Jeda antarpermintaan default 6 detik untuk mengurangi rate limit. Bisa diubah lewat `GEMINI_REQUEST_INTERVAL` (environment lokal atau GitHub Actions variable). Key dikirim melalui header, dan pesan error di log tidak memuat key atau isi respons server. Integrasi menggunakan `requests`, tanpa tambahan SDK.

## Kelengkapan data

- Setiap sumber dibaca **15 berita terbaru** (`SOURCE_LIMIT`; radar Areaanime 10). Jadwal GitHub Actions di repo gratis sering tertunda berjam-jam, jadi jendela 5 berita membuat banyak artikel terlewat di antara dua run.
- Berita kategori yang terbit lebih dari **48 jam** lalu (`NEWS_MAX_AGE_HOURS`, 0 = tanpa batas) dicatat di history tanpa dikirim. Tanggal diambil dari RSS, atau dari meta artikel (`article:published_time`, JSON-LD `datePublished`, `<time datetime>`). Dengan begitu jendela yang lebih lebar tidak mengirim ulang artikel lama dari sumber yang jarang update.
- Postingan X/Telegram/Bluesky dengan beberapa gambar dikirim sebagai galeri (maks. 4 gambar).
- Cron memakai menit ganjil (`7,22,37,52`) karena GitHub paling sering menunda jadwal di awal jam. Kalau jeda masih terlalu panjang, picu workflow dari luar, mis. [cron-job.org](https://cron-job.org/) yang memanggil `POST https://api.github.com/repos/<owner>/<repo>/actions/workflows/run_bot.yml/dispatches` dengan body `{"ref":"main"}` dan fine-grained token berizin *Actions: write*.
- Jendela lebar berarti lebih banyak terjemahan Gemini per hari; pantau kuota di Google AI Studio. Kurangi `SOURCE_LIMIT` kalau kuota sering habis.

## Channel Twitter

Postingan terbaru dari akun X berikut dikirim ke channel `DISCORD_WEBHOOK_TWITTER`, diterjemahkan ke Bahasa Indonesia dengan teks asli tetap ditampilkan: SomosKudasai (Spanyol), animetrends, Dexerto, animetv_jp, MangaMoguraRE, WSJ_manga, AniNewsAndFacts, seiyuucorner, dan Seifukuanimehub.

- Maksimal `SOURCE_LIMIT` postingan per akun per run, hanya yang berumur ≤ 24 jam (`X_MAX_AGE_HOURS`). Retweet dan balasan dilewati.
- Daftar akun bisa diganti lewat variable `X_TWITTER_ACCOUNTS` (format `akun:bahasa,akun:bahasa`, mis. `Dexerto:en,SomosKudasai:es`).
- Postingan ini juga ikut dinilai kurasi Areaanime.

**Cara membaca X.** Di GitHub Actions, workflow menjalankan container [RSSHub](https://docs.rsshub.app/) yang login memakai secret `TWITTER_AUTH_TOKEN` (nilai cookie `auth_token` dari browser yang login ke X; sebaiknya akun cadangan karena X bisa membatasi akun yang dipakai bot). Kalau secret `X_RSS_URL` diisi, bridge itu yang dipakai. Tanpa keduanya (mis. saat dijalankan lokal), bot membaca timeline embed publik X (`syndication.twitter.com`) tanpa login; jalur ini sering kena rate limit (429). Akun yang gagal dibaca hanya dilewati, bot tetap jalan.

## Channel Leaks (Sugoi LITE)

[Sugoi LITE](https://x.com/SugoiLITE) adalah akun leak anime di X (jumlah episode dari listing Blu-ray, KV/PV sebelum rilis, kabar tamat/hiatus manga). Semua postingannya juga di-mirror ke channel Telegram publik [t.me/sugoileaks](https://t.me/s/sugoileaks). Bot membaca pratinjau web `t.me/s/sugoileaks` tanpa login, API key, atau cookie, lalu mengirimnya ke `DISCORD_WEBHOOK_LEAKS` dengan label ⚠️ bocoran.

- Teks lengkap diterjemahkan (judul + isi terpisah supaya daftar staf/pemeran tidak diringkas), teks asli tetap ditampilkan, album dikirim sebagai galeri.
- Balasan ke postingan sebelumnya (mis. "The Latest KV!!") disertai kutipan postingan yang dibalas sebagai konteks. Link ke postingan X-nya (fixupx/fxtwitter) diubah menjadi link x.com.
- Hanya postingan ≤ 24 jam (`TELEGRAM_MAX_AGE_HOURS`). Postingan gambar tanpa teks dilewati.
- Channel lain bisa ditambahkan lewat variable `TELEGRAM_CHANNELS` (format `channel:bahasa:Nama`, mis. `sugoileaks:en:Sugoi LITE`). Semua masuk channel Leaks dan ikut dinilai Areaanime.

**Jalur membaca data "Twitter" yang dipakai bot:**

| Jalur | Butuh login | Stabilitas | Dipakai untuk |
|---|---|---|---|
| Mirror Telegram (`t.me/s/<channel>`) | Tidak | Tinggi | Sugoi LITE |
| Bluesky API publik (`public.api.bsky.app`) | Tidak | Tinggi (resmi) | Comic Natalie |
| RSSHub + cookie X | Ya (`TWITTER_AUTH_TOKEN`) | Sedang, akun bisa dibatasi | Channel Twitter, radar X |
| Timeline embed X (`syndication.twitter.com`) | Tidak | Rendah, sering 429 | Cadangan lokal |

Sebelum menambah akun X baru, cek dulu apakah akun itu punya mirror Telegram atau Bluesky; jalur itu tidak bergantung pada cookie X.

## Channel Areaanime

Setiap run, semua berita yang terambil dinilai potensi viralnya untuk audiens Indonesia. Hanya berita dengan skor ≥ 7/10 yang dikirim, maksimal 3 per run, dan topik yang sama tidak diposting ulang dalam 72 jam. Berita RSS yang lebih tua dari 48 jam dilewati.

**Sumber.** Selain semua sumber kategori, kurasi juga membaca sumber radar yang tidak dikirim ke channel lain (`RADAR` di `sources.py`): Anime Corner, MyAnimeList, Reddit r/anime (flair News), Anime!Anime!, AUTOMATON, Kincir, Otaku USA, Siliconera, Gematsu, Inside Games, dan Google News Indonesia. Makin banyak media yang memberitakan cerita yang sama, makin tinggi skornya.

**Trending X.** Daftar trending X Jepang & Indonesia (3 jam terakhir) diambil dari [trends24.in](https://trends24.in/japan/). Berita yang topiknya sedang trending mendapat skor tambahan, dan embed-nya menampilkan trend tersebut. Trending yang jelas terkait anime/game/VTuber tetapi belum ada beritanya dikirim sebagai embed **📈 Lagi trending di X** (maksimal 3 per run, tidak diulang dalam 72 jam).

Akun X untuk radar dibaca lewat RSSHub yang sama (`X_RSS_URL`). Daftar akun bisa diganti lewat variable `X_ACCOUNTS` (format `akun:bahasa,akun:bahasa`); defaultnya MangaMoguraRE, animecorner_ac, AniTrendz, dan animatetimes. Comic Natalie dibaca lewat Bluesky, jadi tidak perlu akun X natalie.

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

Tambahkan entri di `TARGETS` (`sources.py`). Untuk situs yang punya RSS cukup isi `"rss": "<nama sumber>"`. Akun Bluesky: `"bsky": "<handle>", "name": "<nama>"`. Channel Telegram publik: tambahkan ke `TELEGRAM_CHANNELS`. Untuk situs biasa, tulis fungsi parser yang mengembalikan list `{"title", "link", "img", "source"}` (jumlahnya dipotong otomatis ke `limit`). Link relatif otomatis dijadikan absolut.
