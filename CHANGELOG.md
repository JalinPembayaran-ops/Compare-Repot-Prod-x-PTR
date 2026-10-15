# Riwayat versi

Nomor versi ditampilkan di kepala halaman. Klik lencana versinya untuk melihat
riwayat ini langsung dari dalam alatnya.

> Setiap ada penambahan atau perubahan: naikkan `APP_VERSION` dan tambahkan satu
> baris pada `CHANGELOG` di dalam `index.html` dan `compare_report.py`, lalu
> catat juga di berkas ini.

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
