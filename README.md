# Bot Berita Anime Discord

Bot yang mengambil berita anime, manga, game, dan VTuber dari ±25 sumber (Jepang, Inggris, Indonesia, Spanyol), menerjemahkan judul serta ringkasannya ke Bahasa Indonesia, lalu mengirimnya ke channel Discord lewat webhook. Bot dijalankan GitHub Actions secara terjadwal.

## Struktur

| File | Isi |
|---|---|
| `main.py` | Alur utama: ambil berita, terjemahkan, kirim embed, simpan history |
| `sources.py` | Daftar sumber (`TARGETS`) dan parser tiap website / RSS |
| `curator.py` | Kurasi berita berpotensi viral untuk channel Areaanime |
| `history.json` | Memori berita yang sudah dikirim (di-commit otomatis oleh bot) |
| `history_store.py` | Simpan history secara atomik dan gabungkan history saat Git rebase |

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
| `ANTHROPIC_API_KEY` | *Opsional*: kurasi Areaanime dinilai Claude + saran judul feed |

Channel yang webhook-nya kosong otomatis dilewati.

Areaanime diproses setelah pengambilan sumber, sebelum pengiriman ke channel kategori. Setiap kiriman yang berhasil langsung disimpan ke history. Jika proses terhenti, GitHub Actions tetap mencoba menyimpan history dan mencadangkannya sebagai artifact selama 7 hari.

Permintaan terjemahan punya timeout dan cache selama satu run. Setelah tiga kegagalan berturut-turut, terjemahan dihentikan untuk sisa run dan judul asli dipakai. Retry rate limit Discord dibatasi; kiriman yang gagal tetap bisa dicoba pada run berikutnya. History yang rusak menghentikan bot agar berita lama tidak terkirim ulang.

## Channel Areaanime

Setiap run, semua berita yang terambil dinilai potensi viralnya untuk audiens Indonesia. Hanya berita dengan skor ≥ 7/10 yang dikirim, maksimal 3 per run, dan topik yang sama tidak diposting ulang dalam 72 jam.

- **Tanpa `ANTHROPIC_API_KEY`**: penilaian heuristik. Faktornya franchise besar, jenis kejadian (adaptasi anime, season baru, tamat/hiatus, kontroversi, rekor, dll), jumlah media yang memberitakan cerita yang sama, dan penalti untuk merch/diskon.
- **Dengan `ANTHROPIC_API_KEY`**: Claude menilai kandidat seperti editor konten dan menulis saran **tag + judul feed** dengan gaya Areaanime (bagian `[kurung siku]` = highlight kuning, tampil tebal di Discord). Kalau API gagal, otomatis kembali ke heuristik.

Pengaturan opsional lewat env: `AREAANIME_MIN_SCORE` (default 7), `AREAANIME_MAX_PER_RUN` (default 3), `AREAANIME_MODEL` (default `claude-opus-5-5`), `AREAANIME_EFFORT` (default `medium`; `low` lebih hemat).

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
