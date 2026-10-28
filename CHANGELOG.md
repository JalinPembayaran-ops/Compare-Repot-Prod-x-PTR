# Riwayat versi

Nomor versi ditampilkan di kepala halaman. Klik lencana versinya untuk melihat
riwayat ini langsung dari dalam alatnya.

> Setiap ada penambahan atau perubahan: naikkan `APP_VERSION` dan tambahkan satu
> baris pada `CHANGELOG` di dalam `index.html` dan `compare_report.py`, lalu
> catat juga di berkas ini.

## 2.3 — 28 Oktober 2026

- Subtotal per halaman () dihitung sebagai **angka
  turunan**. Begitu baris berpindah halaman, subtotalnya ikut berubah walau
  isinya sama, sehingga report yang hanya beda posisi tidak lagi terbaca
  BEDA DATA. Terlihat pada  (3.062 baris subtotal
  halaman) dan  (18 baris).
- Pengamannya: **grand total** - baris  tanpa  - harus sama
  persis di kedua sisi. Selisih nominal sekecil apa pun, baik di grand total
  maupun di baris data, tetap dilaporkan sebagai beda data.

## 2.2 — 27 Oktober 2026

- Baris yang **bertukar posisi** dikenali sebagai **Beda Posisi Baris**, bukan
  beda data. Nomor urut di kolom pertama ikut tertukar sehingga barisnya tidak
  pernah sama persis — itu sebabnya selama ini terbaca BEDA DATA.
- Kolom pertama baru diabaikan kalau angkanya benar-benar berurutan naik
  satu-satu, supaya kolom jam atau nominal tidak ikut terbuang. Sisa baris yang
  masih berbeda hanya boleh berupa baris keterangan.
- Sebutan "beda urutan baris" disatukan menjadi **beda posisi baris**, karena
  keduanya persoalan yang sama.
- `Waktu Settlement :` dan sejenisnya dikenali sebagai baris keterangan.

## 2.1 — 26 Oktober 2026

- Beda yang **hanya terjadi pada tanggal data terakhir** dihitung cocok. Itu
  sidik jari report yang dibuat pada jam berbeda: hari-hari yang sudah selesai
  isinya sama persis, hanya hari yang masih berjalan yang belum lengkap.
- Dua pengaman supaya aturan ini tidak menutupi masalah nyata:
  (1) kalau ada tanggal lain ikut berbeda, berkasnya tetap BEDA DATA;
  (2) harus ada tanggal lampau yang isinya sudah cocok — berkas yang hanya
  memuat tanggal terakhir tidak ikut, karena tidak ada bukti kecocokan sama
  sekali (misalnya PTR kosong sementara Production berisi).
- Baris header dan trailer bergaya `RH;` dan `RT;` dikenali sebagai baris
  keterangan, bukan baris data — jumlah record pada trailer mengikuti data,
  jadi bukan perbedaan yang berdiri sendiri.

## 2.0 — 15 Oktober 2026

- Berkas `.xlsx` dibandingkan **per isi sel**, bukan sebagai teks mentah.
  Sebelumnya isinya tampil sebagai sampah biner (`PK`, `[Content_Types].xml`)
  karena `.xlsx` sebenarnya arsip ZIP berisi XML. Kini tiap sel dirender jadi
  baris `Sheet1 baris 28  B28=... | C28=...` sehingga bisa ditelusuri.
- Berkas biner lain — `.xls` lama, `.gz`, `.zip`, gambar — dilaporkan apa adanya
  dengan keterangan jelas, tanpa baris sampah.
- Pemasangan baris tiga tahap disamakan antara `index.html` dan
  `compare_report.py`; sebelumnya versi baris perintah masih satu tahap,
  sehingga contoh baris sering kosong dan beda jam cetak tidak terdeteksi.

## 1.9 — 15 Oktober 2026

- Beda jam atau tanggal cetak, beda header/trailer, dan beda format baris kini
  dihitung **cocok** dan tidak lagi ditampilkan sebagai perbedaan. Kartu dan
  filter untuk status tersebut dihapus; jumlahnya tetap disebut sekali di
  banner ringkasan dan ditandai halus di kolom File.
- Selisih waktu dikenali **per token**, bukan per potongan karakter, sehingga
  `...;20260903` lawan `...;20260902` terbaca utuh sebagai tanggal. Tanggal dan
  jam bertanda baca (`01/09/2026`, `10:25:47`) dibaca sebagai satu token, dan
  rangka baris di luar token harus sama persis supaya nominal tidak pernah
  disalahartikan sebagai waktu.

## 1.8 — 07 Oktober 2026

- Jenis report `NET_SETTLE_RNTS_YYMMDD` ditambahkan, melengkapi varian ALTO
  dan ARTA yang sudah ada. Daftar kelengkapan kini 42 jenis.
- Kode di depan pola boleh 3 atau 4 huruf. Sebelumnya `XXX` dipatok tepat tiga
  huruf, sehingga `REVENUE_HARIAN_JALN_XXX_YYMMDD` tidak pernah menemukan
  ALTO, ARTA maupun RNTS. Pola itu kini mencakup 39 berkas.

## 1.7 — 07 Oktober 2026

- Ekstensi pada pola tidak lagi dituntut persis. Pola `.xls` tetap menemukan
  berkas `.xlsx`, dan sebaliknya. Sebelumnya `NET_SETTLE_ALTO_YYMMDD.xls` dan
  `NET_SETTLE_ARTA_YYMMDD.xls` terbaca "Tidak ditemukan" padahal berkasnya ada,
  hanya berekstensi `.xlsx`.

## 1.6 — 07 Oktober 2026

- Jenis report `RECON_JALN_ALTO_YYMMDD` ditambahkan ke daftar kelengkapan,
  melengkapi `RECON_JALN_ARTA_YYMMDD` yang sudah ada.
- Lencana versi di halaman diisi dari `APP_VERSION`, bukan ditulis tangan,
  supaya angkanya tidak bisa lagi menyimpang dari nilai sebenarnya.

## 1.5 — 06 Oktober 2026

- Nomor versi ditampilkan di kepala halaman beserta riwayat perubahannya.

## 1.4 — 06 Oktober 2026

- Pemeriksaan kelengkapan 40 jenis report: Ada, Hanya di PTR, Hanya di Prod,
  atau Tidak ditemukan.
- Unduhan ringkasan jadi dua sheet: Ringkasan dan Kelengkapan Report.
- Keterangan berkas identik diringkas jadi "Sudah OK".

## 1.3 — 30 September 2026

- Logo Jalin dan nama unit dipasang di kepala halaman.

## 1.2 — 23 September 2026

- Hasil unduhan jadi berkas `.xlsx`, siap pakai di Excel: baris judul dibekukan,
  filter otomatis, lebar kolom disetel, kolom isi report memakai huruf rata.
- Pemasangan baris tiga tahap, sehingga semua jenis report bisa diunduh —
  termasuk Fee-Marketing, Netting, Detail-Settlement, Klaim-Lain dan
  Switching-Fee yang perbedaannya jatuh di dalam kunci pemasangan.

## 1.1 — 11 September 2026

- Baris beda dipasangkan lewat isinya, bukan lewat posisi, supaya transaksi yang
  sama yang disandingkan walau urutan barisnya bergeser.
- Tombol unduh rincian perbedaan per berkas.

## 1.0 — 02 September 2026

- Rilis awal: bandingkan satu berkas, banyak berkas, atau seluruh folder.
- Analisa per kode report, dan label kode report pada tiap baris yang berbeda.
- Beda urutan baris diperlakukan sebagai cocok.
