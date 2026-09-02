# Compare Report PTR vs Production — Fee Engine (Merah Putih)

Alat bantu untuk memastikan report yang dihasilkan lingkungan **PTR** sama dengan
report **Production**. Membandingkan berkas report Fee Engine baris per baris,
lalu melaporkan apa saja yang berbeda dan di **kode report** mana perbedaan itu berada.

> ⚠️ **Repositori ini hanya berisi kode.** Berkas report Fee Engine memuat data
> nasabah (nomor kartu, nomor rekening, nama, nominal transaksi) dan **tidak boleh**
> dimasukkan ke repositori ini. `.gitignore` sudah menutup pola berkas tersebut,
> tetapi tetap periksa `git status` sebelum commit.

---

## Isi

| Berkas | Kegunaan |
|---|---|
| `Compare-Report-Tool.html` | Alat interaktif. Buka di browser, unggah report kedua sisi, langsung dibandingkan. |
| `compare_report.py` | Versi baris perintah. Memindai dua folder dan menghasilkan satu berkas HTML laporan. |

Keduanya memakai logika perbandingan yang sama dan menghasilkan angka yang identik.

---

## 1. Alat interaktif (tanpa instalasi)

Dobel-klik `Compare-Report-Tool.html`. Tidak perlu Python, tidak perlu internet,
tidak perlu server — seluruh proses berjalan di dalam browser dan berkas asli
tidak pernah dikirim ke mana pun.

Isi dua kotak (PTR dan Production), lalu klik **Bandingkan**. Tiap kotak menerima:

- **Pilih File** — satu berkas atau banyak berkas sekaligus
- **Pilih Folder** — seluruh folder beserta subfoldernya
- **Drag & drop** — seret berkas atau folder langsung ke kotaknya

Berkas dipasangkan berdasarkan **nama berkas**, bukan struktur folder, sehingga
nama folder yang berbeda di kedua sisi tetap terpasang dengan benar. Jika tiap
sisi hanya berisi satu berkas, keduanya dibandingkan langsung walaupun namanya berbeda.

Batas rincian per baris bawaannya 100 MB (bisa dinaikkan sampai 250 MB). Berkas di
atas batas tetap dicek identik atau tidak, hanya saja tidak dibedah per baris.

## 2. Versi baris perintah

```bash
py compare_report.py
```

Otomatis mencari folder `*PTR*` dan `*Prod*` di direktori yang sama, lalu menulis
`Compare-Report-PTR-vs-Prod.html`. Untuk folder lain:

```bash
py compare_report.py "<folder PTR>" "<folder Prod>" -o hasil.html
```

Lebih cepat daripada versi browser untuk memproses folder besar (ratusan berkas /
lebih dari 1 GB). Hasilnya satu berkas HTML mandiri — **berisi cuplikan data asli,
jadi perlakukan seperti data produksi.**

---

## Cara alat ini menilai

Tiap pasang berkas diberi salah satu status berikut:

| Status | Arti |
|---|---|
| **Identik** | Isi sama. Termasuk berkas yang seluruh barisnya sama dan hanya berbeda urutan — dianggap cocok. |
| **Beda data** | Ada baris yang isinya benar-benar berbeda. |
| **Beda header/jam** | Beda hanya pada jam cetak, nomor halaman, atau jumlah record. |
| **Beda format baris** | Isi baris sama, beda pada spasi akhir baris atau akhiran baris (CRLF vs LF). |
| **Hanya di PTR** / **Hanya di Prod** | Berkas hanya diproduksi salah satu sisi. |

Beberapa keputusan yang sengaja diambil supaya laporannya tidak berisik:

- **Beda urutan baris dianggap cocok.** Jika seluruh baris sama dan hanya urutannya
  berbeda, berkas dihitung Identik. Baris yang sekadar bergeser posisinya juga tidak
  ditampilkan sebagai contoh perbedaan.
- **Selisih jumlah halaman bukan ketidakcocokan kode report.** Kode report yang ada
  di kedua sisi tetapi jumlah halamannya berbeda dicatat sebagai keterangan, bukan
  sebagai kode yang hilang — penyebabnya jumlah transaksi yang berbeda.
- **Pemisah baris hanya LF.** CR tunggal diperlakukan sebagai isi baris, agar kedua
  versi alat menghasilkan angka yang sama persis. Perbedaan konvensi akhiran baris
  antar-lingkungan dilaporkan tersendiri.

## Analisa per kode report

Untuk report yang memuat baris `KODE REPORT`, detail tiap berkas menampilkan:

- kode report yang **tidak diproduksi** di salah satu sisi, misalnya `10A, 10B, 13, 15`
- tabel **perbedaan per kode report** — seluruh kode yang terdampak beserta judul
  section dan jumlah baris yang berbeda di masing-masing sisi
- setiap baris contoh diberi label kode report dan nomor barisnya, sehingga terlihat
  saat kedua berkas mulai tidak sejajar (misalnya `KODE REPORT — PTR 11 / PROD 10A`)

Angka pada tabel per kode dijumlah tepat sama dengan total baris berbeda di
ringkasan, jadi bisa dipakai menelusuri tanpa khawatir ada yang terlewat.
