# -*- coding: utf-8 -*-
"""
Compare report PTR vs Report Production (Fee Engine / Merah Putih).
Menghasilkan satu file HTML mandiri berisi seluruh perbedaan.

Pemakaian:
    py compare_report.py
    py compare_report.py "<folder PTR>" "<folder Prod>" -o hasil.html
"""
import os, re, sys, json, hashlib, argparse, zipfile, io
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime

MAX_FULL_READ = 200 * 1024 * 1024   # di atas ini hanya cek hash, tanpa detail baris
SAMPLE_POS    = 25                  # contoh baris beda pada posisi sama
SAMPLE_UNIQ   = 15                  # contoh baris yang hanya ada di satu sisi
LINE_TRUNC    = 400

META_PAT = [
    re.compile(r'^\s*F[HT]\s*\d+'),
    re.compile(r'^\s*R[HT]\s*[;|]', re.IGNORECASE),
    re.compile(r'\bHAL\s*:'),
    re.compile(r'\bTANGGAL\s*:'),
    re.compile(r'\bKODE\s+(BANK|REPORT)\s*:'),
    re.compile(r'\bJAM\s*:'),
    re.compile(r'\bWAKTU\s+[A-Za-z]+\s*:', re.IGNORECASE),
]


RE_KODE = re.compile(r'KODE\s+REPORT\s*:\s*([0-9A-Za-z]+)\s*(.*)$')


def is_meta(line):
    return any(p.search(line) for p in META_PAT)


def tidy_title(t):
    t = re.sub(r'\s*(TANGGAL|HAL)\s*:.*$', '', t or '',
               flags=re.IGNORECASE).strip()
    if not t:
        return ''
    if re.match(r'^(\S )(\S )+', t):
        return ' '.join(w.replace(' ', '') for w in re.split(r'\s{2,}', t))
    return re.sub(r'\s{2,}', ' ', t)


def title_for(lines, i, inline):
    """Judul section: dari baris KODE REPORT itu sendiri, kalau kosong ambil
    baris pertama yang berisi di bawahnya (maksimal 4 baris ke bawah)."""
    t = tidy_title(inline)
    if t:
        return t
    for j in range(i + 1, min(i + 5, len(lines))):
        c = lines[j].strip()
        if not c or re.match(r'^[-=_*]+$', c):
            continue
        return tidy_title(c)
    return ''


def section_scan(lines):
    """Satu lintasan: kode report per baris, jumlah halaman per kode, dan judulnya."""
    sec, pages, titles, cur = [], Counter(), {}, ''
    for i, ln in enumerate(lines):
        m = RE_KODE.search(ln)
        if m:
            cur = m.group(1).upper()
            pages[cur] += 1
            if cur not in titles:
                titles[cur] = title_for(lines, i, m.group(2))
        sec.append(cur)
    return sec, pages, titles


def code_diff(r, A, B):
    """Hanya kode yang benar-benar absen di satu sisi yang dihitung tidak cocok.
    Selisih jumlah halaman dicatat terpisah - itu efek jumlah transaksi yang
    berbeda, bukan kode report yang hilang."""
    _, pa, ta = A
    _, pb, tb = B
    same = 0
    for c in sorted(set(pa) | set(pb)):
        a, b = pa.get(c, 0), pb.get(c, 0)
        if a and b:
            same += 1
            if a != b:
                r['codesPages'].append(c)
        else:
            r['codes'].append({
                'code': c, 'title': ta.get(c) or tb.get(c) or '',
                'status': 'HANYA_PTR' if b == 0 else 'HANYA_PROD',
            })
    r['codesSame'] = same


def md5_file(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def scan(root):
    out = {}
    for dp, _, fns in os.walk(root):
        for fn in fns:
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, root).replace('\\', '/')
            out[rel] = {'abs': p, 'size': os.path.getsize(p), 'md5': md5_file(p)}
    return out


def line_ending(data):
    """Tentukan konvensi akhiran baris sebuah file."""
    lf = data.count(b'\n')
    crlf = data.count(b'\r\n')
    if lf == 0:
        return 'CR' if b'\r' in data else '-'
    if crlf == 0:
        return 'LF'
    return 'CRLF' if crlf == lf else 'campuran (CRLF+LF)'


def read_lines(path):
    """Baca file menjadi daftar baris.

    Pemisah baris hanya LF; CR tunggal diperlakukan sebagai isi baris,
    bukan pemisah, supaya hasilnya sama persis dengan Compare-Report-Tool.html.
    """
    with open(path, 'rb') as f:
        data = f.read()
    eol = line_ending(data)
    lines = data.decode('latin-1').split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    return [ln.rstrip() for ln in lines], eol


NS_MAIN = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
NS_REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
BINER_EXT = ('.xls', '.gz', '.zip', '.png', '.jpg', '.jpeg', '.pdf')


def xlsx_to_text(data):
    """Ubah isi .xlsx jadi baris per baris sel.

    Berkas .xlsx sebenarnya arsip ZIP berisi XML, jadi membandingkannya
    sebagai teks biasa hanya menghasilkan sampah biner."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        nama = set(z.namelist())
        if 'xl/workbook.xml' not in nama:
            return None

        peta = {}
        if 'xl/_rels/workbook.xml.rels' in nama:
            for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels')):
                peta[r.get('Id')] = r.get('Target')

        ss = []
        if 'xl/sharedStrings.xml' in nama:
            for si in ET.fromstring(z.read('xl/sharedStrings.xml')):
                ss.append(''.join(t.text or '' for t in si.iter(NS_MAIN + 't')))

        out = []
        for sh in ET.fromstring(z.read('xl/workbook.xml')).iter(NS_MAIN + 'sheet'):
            nm = sh.get('name') or 'Sheet'
            tgt = peta.get(sh.get(NS_REL + 'id'), '')
            if not tgt:
                continue
            tgt = tgt[1:] if tgt.startswith('/') else (
                tgt if tgt.startswith('xl/') else 'xl/' + tgt)
            if tgt not in nama:
                continue
            out.append('=== %s ===' % nm)
            for row in ET.fromstring(z.read(tgt)).iter(NS_MAIN + 'row'):
                sel = []
                for c in row.iter(NS_MAIN + 'c'):
                    t = c.get('t')
                    if t == 'inlineStr':
                        e = c.find(NS_MAIN + 'is/' + NS_MAIN + 't')
                        v = e.text if e is not None else ''
                    else:
                        e = c.find(NS_MAIN + 'v')
                        v = e.text if e is not None else ''
                        if t == 's' and v is not None and v.isdigit():
                            v = ss[int(v)] if int(v) < len(ss) else ''
                    if v:
                        sel.append('%s=%s' % (c.get('r'), v))
                if sel:
                    out.append('%s baris %s  %s' % (nm, row.get('r'), '  |  '.join(sel)))
        return chr(10).join(out) if out else None
    except Exception:
        return None


def read_for_compare(path):
    """Baca berkas untuk dibandingkan: teks biasa, lembar kerja, atau biner."""
    with open(path, 'rb') as f:
        data = f.read()
    low = path.lower()
    if low.endswith(('.xlsx', '.xlsm')):
        teks = xlsx_to_text(data)
        if teks is None:
            return None, None, 'lembar kerja tidak terbaca'
        return teks.split(chr(10)), None, None
    if low.endswith(BINER_EXT) or b'\x00' in data[:8192]:
        ext = low.rsplit('.', 1)[-1] if '.' in low else '-'
        return None, None, 'format biner (%s)' % ext
    eol = line_ending(data)
    lines = data.decode('latin-1').split(chr(10))
    if lines and lines[-1] == '':
        lines.pop()
    return [ln.rstrip() for ln in lines], eol, None


def trunc(s):
    return s[:LINE_TRUNC] + ' ...' if len(s) > LINE_TRUNC else s


KEYLEN = 64


def key_of(t):
    k = t[:KEYLEN]
    return k if len(k.replace(' ', '')) >= 12 else None


def mask_key(t):
    k = re.sub(r'[0-9]', '#', t[:KEYLEN])
    return k if len(k.replace(' ', '')) >= 12 else None


def lcp_len(a, b):
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def pair_lines(la, lb, only_a, only_b):
    """Pasangkan baris beda antara kedua sisi. Tiga tahap, dari yang paling
    pasti ke yang paling longgar: kunci persis, kunci bertopeng angka (hanya
    diterima bila tidak ambigu), lalu kemiripan awalan untuk sisa yang sedikit.
    Sama persis dengan yang dipakai Compare-Report-Tool.html."""
    seen, idx_a = set(), []
    for i, ln in enumerate(la):
        if ln in only_a and ln not in seen:
            seen.add(ln)
            idx_a.append(i)
    seen, idx_b = set(), []
    for j, ln in enumerate(lb):
        if ln in only_b and ln not in seen:
            seen.add(ln)
            idx_b.append(j)

    pairs, taken_a, taken_b = [], set(), set()

    def tahap(keyfn, ketat):
        peta = {}
        for j in idx_b:
            if j in taken_b:
                continue
            k = keyfn(lb[j])
            if k:
                peta.setdefault(k, []).append(j)
        cnt_a = {}
        if ketat:
            for i in idx_a:
                if i in taken_a:
                    continue
                k = keyfn(la[i])
                if k:
                    cnt_a[k] = cnt_a.get(k, 0) + 1
        for i in idx_a:
            if i in taken_a:
                continue
            k = keyfn(la[i])
            if not k or k not in peta:
                continue
            cand = peta[k]
            if ketat and (len(cand) != 1 or cnt_a.get(k) != 1):
                continue
            hit = next((j for j in cand if j not in taken_b), None)
            if hit is None:
                continue
            taken_a.add(i)
            taken_b.add(hit)
            pairs.append((i, hit))

    tahap(key_of, False)
    tahap(mask_key, True)

    sisa_a = [i for i in idx_a if i not in taken_a]
    sisa_b = [j for j in idx_b if j not in taken_b]
    if sisa_a and sisa_b and len(sisa_a) <= 400 and len(sisa_b) <= 400:
        for i in sisa_a:
            best, best_len = -1, 7       # minimal 8 karakter awal harus sama
            for j in sisa_b:
                if j in taken_b:
                    continue
                L = lcp_len(la[i], lb[j])
                # awalan yang sama harus berisi, bukan sekadar deretan spasi
                if L > best_len and len(la[i][:L].replace(' ', '')) >= 6:
                    best, best_len = j, L
            if best >= 0:
                taken_a.add(i)
                taken_b.add(best)
                pairs.append((i, best))

    pairs.sort()
    return (pairs,
            [i for i in idx_a if i not in taken_a],
            [j for j in idx_b if j not in taken_b])


def pair_by_content(r, la, lb, only_a, only_b, sa, sb):
    """Contoh baris beda yang disandingkan, diambil dari hasil pemasangan."""
    pairs, _, _ = pair_lines(la, lb, only_a, only_b)
    r['samplesPos'] = [
        {'no': i + 1, 'noProd': j + 1, 'ptr': trunc(la[i]), 'prod': trunc(lb[j]),
         'codeA': sa[i], 'codeB': sb[j]}
        for i, j in pairs[:SAMPLE_POS]]
    r['posDiff'] = len(pairs)
    return {la[i] for i, _ in pairs}, {lb[j] for _, j in pairs}


# Tanggal dan jam bertanda baca dibaca sebagai satu token, bukan terpecah.
RE_TOKEN = re.compile(r'\d{2}[:.]\d{2}(?:[:.]\d{2})?|\d{2}[/-]\d{2}[/-]\d{4}'
                      r'|\d{4}[/-]\d{2}[/-]\d{2}|[0-9A-Za-z]+')


def _tgl(y, m, d):
    return 1 <= m <= 12 and 1 <= d <= 31


def _jam(h, mi, s=0):
    return h < 24 and mi < 60 and s < 60


def is_datetime_token(t):
    """Token berupa tanggal atau jam yang sah."""
    if re.match(r'^\d{2}[:.]\d{2}([:.]\d{2})?$', t):
        return True
    if re.match(r'^\d{2}[/-]\d{2}[/-]\d{4}$', t):
        return True
    if not t.isdigit():
        return False
    n = len(t)
    g = lambda a, b: int(t[a:b])
    if n == 6:
        return _tgl(g(0, 2), g(2, 4), g(4, 6)) or _jam(g(0, 2), g(2, 4), g(4, 6))
    if n == 8:
        return _tgl(g(0, 4), g(4, 6), g(6, 8))
    if n == 12:
        return _tgl(g(0, 2), g(2, 4), g(4, 6)) and _jam(g(6, 8), g(8, 10), g(10, 12))
    if n == 14:
        return _tgl(g(0, 4), g(4, 6), g(6, 8)) and _jam(g(8, 10), g(10, 12), g(12, 14))
    return False


def line_time_only(a, b):
    """Dua baris yang hanya berselisih pada token tanggal atau jam.

    Diperiksa per token, bukan per potongan karakter, supaya '...;20260903'
    lawan '...;20260902' terbaca utuh sebagai tanggal - bukan satu digit."""
    if a == b:
        return True
    # rangka baris - bagian selain token - harus sama persis
    if RE_TOKEN.sub('\x01', a) != RE_TOKEN.sub('\x01', b):
        return False
    ta, tb = RE_TOKEN.findall(a), RE_TOKEN.findall(b)
    if len(ta) != len(tb):
        return False
    beda = 0
    for x, y in zip(ta, tb):
        if x == y:
            continue
        if not (is_datetime_token(x) and is_datetime_token(y)):
            return False
        beda += 1
    return beda > 0


def norm_date(t):
    if not t.isdigit():
        return None
    if len(t) == 8:
        return t if is_datetime_token(t) else None
    if len(t) == 6:
        m, d = int(t[2:4]), int(t[4:6])
        return '20' + t if 1 <= m <= 12 and 1 <= d <= 31 else None
    return None


def dates_of(line):
    return [d for d in (norm_date(t) for t in RE_TOKEN.findall(line)) if d]


RE_SEQ = re.compile(r'^\s*(\d+)\s+')


def seq_nums(arr):
    return [int(m.group(1)) for m in (RE_SEQ.match(l) for l in arr) if m]


def seq_run(arr):
    """Kolom pertama baru dipercaya sebagai nomor urut kalau angkanya mulai
    dari 1 dan naik satu-satu tanpa putus. Tanpa syarat ini, kolom jam atau
    nominal bisa ikut terbuang."""
    v = seq_nums(arr)
    return len(v) >= 2 and all(x == i + 1 for i, x in enumerate(v))


RE_PAGE_SUB = re.compile(r'TOTAL[^:]*/\s*Page', re.IGNORECASE)


def grand_totals(arr):
    """Grand total - baris TOTAL yang bukan subtotal halaman. Inilah
    pengamannya: kalau angka ini bergeser sedikit saja, berkasnya tetap
    dihitung beda data."""
    return '\n'.join(
        re.sub(r'\s+', ' ', l).strip() for l in arr
        if re.search(r'TOTAL', l, re.IGNORECASE) and not RE_PAGE_SUB.search(l))


def position_only(la, lb):
    """Baris-barisnya sama, hanya posisinya bertukar sehingga nomor urut di
    kolom pertama dan subtotal per halaman ikut berubah."""
    if len(la) != len(lb) or not seq_run(la) or not seq_run(lb):
        return False
    if len(seq_nums(la)) != len(seq_nums(lb)):
        return False
    if grand_totals(la) != grand_totals(lb):
        return False
    ca = Counter(RE_SEQ.sub('', l, count=1) for l in la)
    cb = Counter(RE_SEQ.sub('', l, count=1) for l in lb)
    sisa = [k for k, v in ca.items() if v > cb.get(k, 0)]
    sisa += [k for k, v in cb.items() if v > ca.get(k, 0)]
    # sisa hanya boleh baris keterangan - judul, jam cetak, jam settlement -
    # atau subtotal halaman, yang angkanya mengikuti posisi baris
    return all(is_meta(k) or RE_PAGE_SUB.search(k) for k in sisa)


def latest_date_only(la, lb, only_a, only_b):
    """Beda yang hanya ada pada tanggal data terakhir.

    Report yang dibuat pada jam berbeda hanya berselisih pada hari yang masih
    berjalan; hari yang sudah selesai isinya sama persis. Kalau ada hari lain
    ikut berbeda, aturan ini gugur dan berkasnya tetap dihitung beda data."""
    if len(la) + len(lb) > 1000000:
        return False
    maks = ''
    for arr in (la, lb):
        for ln in arr:
            if is_meta(ln):
                continue
            for d in dates_of(ln):
                if d > maks:
                    maks = d
    if not maks:
        return False

    # Harus ada tanggal yang lebih lampau dan isinya memang sudah cocok. Kalau
    # seluruh berkas hanya memuat tanggal terakhir, tidak ada bukti apa pun
    # bahwa keduanya sejalan - misalnya PTR kosong sementara Prod berisi.
    if not any(d < maks
               for arr in (la, lb) for ln in arr if not is_meta(ln)
               for d in dates_of(ln)):
        return False

    ada = False
    for uniq in (only_a, only_b):
        for ln in uniq:
            if is_meta(ln):
                continue
            ds = dates_of(ln)
            if not ds or any(d != maks for d in ds):
                return False
            ada = True
    return ada


def time_only_diff(la, lb, only_a, only_b, sa, sb):
    """Seluruh beda hanya soal waktu: baris yang berpasangan cuma berselisih
    tanggal/jam, dan baris tanpa pasangan semuanya baris header/trailer."""
    pairs, solo_a, solo_b = pair_lines(la, lb, only_a, only_b)
    for i, j in pairs:
        if not line_time_only(la[i], lb[j]):
            return False
    for i in solo_a:
        if not is_meta(la[i]):
            return False
    for j in solo_b:
        if not is_meta(lb[j]):
            return False
    return True


def pick_unique(lines, uniq, sec, already=frozenset()):
    """Contoh baris yang benar-benar tidak punya pasangan di sisi lain,
    lengkap dengan nomor baris dan kode report tempat baris itu berada."""
    out, seen, per = [], set(), Counter()
    for i, ln in enumerate(lines):
        if len(out) >= SAMPLE_UNIQ:
            break
        if ln in uniq and ln not in seen and ln not in already:
            seen.add(ln)
            per[sec[i]] += 1
            if per[sec[i]] <= 2:
                out.append({'no': i + 1, 'code': sec[i], 'text': trunc(ln)})
    return out


def code_key(c):
    """Urutan alami kode report: 03 < 03A < 03B < 04."""
    m = re.match(r'^(\d+)(.*)$', c or '')
    return ('%04d%s' % (int(m.group(1)), m.group(2))) if m else ('zzzz' + (c or ''))


def code_rows(r, la, lb, only_a, only_b, sa, sb, ta, tb):
    """Jumlah baris beda per kode report. Tiap baris unik dihitung pada kode
    report tempat kemunculan pertamanya, jadi totalnya persis sama dengan
    angka onlyPtrRows / onlyProdRows."""
    tally = {}

    def add(lines, uniq, sec, key):
        seen = set()
        for i, ln in enumerate(lines):
            if ln in uniq and ln not in seen:
                seen.add(ln)
                e = tally.setdefault(sec[i], {'ptr': 0, 'prod': 0})
                e[key] += uniq[ln]

    add(la, only_a, sa, 'ptr')
    add(lb, only_b, sb, 'prod')

    absent = {c['code']: c['status'] for c in r['codes']}
    rows = [{'code': c, 'title': ta.get(c) or tb.get(c) or '',
             'ptr': v['ptr'], 'prod': v['prod'],
             'status': absent.get(c, 'BEDA')}
            for c, v in tally.items()]
    rows.sort(key=lambda x: code_key(x['code']))
    r['codeRows'] = rows


def blank(rel):
    return {
        'path': rel,
        'folder': rel.split('/')[0] if '/' in rel else '(root)',
        'name': rel.split('/')[-1],
        'sizePtr': None, 'sizeProd': None,
        'linesPtr': None, 'linesProd': None,
        'onlyPtrRows': 0, 'onlyProdRows': 0, 'posDiff': 0,
        'samplesPos': [], 'samplesPtr': [], 'samplesProd': [],
        'codes': [], 'codesSame': 0, 'codesPages': [], 'codeRows': [],
        'softReason': None, 'lembar': False,
        'eolPtr': None, 'eolProd': None,
        'status': '', 'note': '',
    }


def analyse(rel, a, b):
    r = blank(rel)
    r['sizePtr'], r['sizeProd'] = a['size'], b['size']

    if a['md5'] == b['md5']:
        r['status'] = 'IDENTIK'
        r['note'] = 'Sudah OK.'
        return r

    if max(a['size'], b['size']) > MAX_FULL_READ:
        r['status'] = 'BEDA_DATA'
        r['note'] = 'File terlalu besar untuk dianalisa per baris; MD5 berbeda.'
        return r

    la, r['eolPtr'], biner_a = read_for_compare(a['abs'])
    lb, r['eolProd'], biner_b = read_for_compare(b['abs'])
    if biner_a or biner_b:
        r['status'] = 'BEDA_DATA'
        r['note'] = ('Isinya berbeda, tetapi tidak bisa dirinci per baris karena %s.'
                     % (biner_a or biner_b))
        return r
    r['lembar'] = a['abs'].lower().endswith(('.xlsx', '.xlsm'))
    r['linesPtr'], r['linesProd'] = len(la), len(lb)
    A, B = section_scan(la), section_scan(lb)
    code_diff(r, A, B)
    sa, sb = A[0], B[0]

    if la == lb:
        r['status'] = 'IDENTIK'
        r['softReason'] = 'format'
        r['note'] = ('Isi report cocok. Beda hanya pada spasi di akhir baris '
                     'atau akhiran baris (CRLF vs LF).')
        return r

    ca, cb = Counter(la), Counter(lb)
    only_a, only_b = ca - cb, cb - ca
    r['onlyPtrRows'] = sum(only_a.values())
    r['onlyProdRows'] = sum(only_b.values())

    shifted = sum(1 for i in range(min(len(la), len(lb))) if la[i] != lb[i])

    if not only_a and not only_b:
        r['status'] = 'IDENTIK'
        r['softReason'] = 'posisi'
        r['note'] = ('Isi report cocok. Seluruh baris sama persis, hanya urutan '
                     'barisnya yang berbeda (%d posisi bergeser).' % shifted)
        return r

    code_rows(r, la, lb, only_a, only_b, sa, sb, A[2], B[2])
    paired_a, paired_b = pair_by_content(r, la, lb, only_a, only_b, sa, sb)
    r['samplesPtr'] = pick_unique(la, only_a, sa, paired_a)
    r['samplesProd'] = pick_unique(lb, only_b, sb, paired_b)

    if time_only_diff(la, lb, only_a, only_b, sa, sb):
        r['status'] = 'IDENTIK'
        r['softReason'] = 'jam'
        r['note'] = ('Isi report cocok. Beda hanya pada jam cetak, tanggal cetak, '
                     'nomor halaman, atau jumlah record di baris header/trailer.')
    elif position_only(la, lb):
        r['status'] = 'IDENTIK'
        r['softReason'] = 'posisi'
        r['note'] = ('Isi report cocok. Baris-barisnya sama, hanya posisinya bertukar '
                     'sehingga nomor urut di kolom pertama dan subtotal per halaman '
                     'ikut berubah. Grand total kedua report sama persis.')
    elif latest_date_only(la, lb, only_a, only_b):
        r['status'] = 'IDENTIK'
        r['softReason'] = 'generate'
        r['note'] = ('Isi report cocok. Seluruh tanggal yang sudah selesai sama persis; '
                     'yang berbeda hanya tanggal terakhir yang masih berjalan, karena '
                     'kedua report dibuat pada jam yang berbeda.')
    else:
        r['status'] = 'BEDA_DATA'
        r['note'] = ('Ada isi sel yang berbeda antara PTR dan Production. Berkas lembar '
                     'kerja dibandingkan per sel, bukan per baris teks.' if r['lembar']
                     else 'Ada baris data yang isinya berbeda antara PTR dan Production.')
    return r


# --------------------------------------------------------------------- HTML

HTML_TEMPLATE = r"""<!doctype html>
<html lang="id"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Compare PTR vs Prod</title>
<style>
:root{
  color-scheme:light;
  --bg:#f4f6f9; --panel:#ffffff; --panel2:#f8fafc; --line:#dde3ea;
  --tx:#101722; --tx2:#556173; --tx3:#7d8899;
  --ok:#0f7a4d; --okbg:#e7f7ee; --bad:#c0281f; --badbg:#fdecea;
  --warn:#8a5a00; --warnbg:#fdf4e3; --ptr:#1a5fbf; --ptrbg:#e9f1fd;
  --prod:#6a37b3; --prodbg:#f2ebfc; --accent:#1a5fbf; --mark:rgba(255,196,0,.42);
  --mono:ui-monospace,"Cascadia Mono",Consolas,"SFMono-Regular",Menlo,monospace;
  --sans:ui-sans-serif,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);font-family:var(--sans);
     font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased}
.wrap{max-width:1280px;margin:0 auto;padding:28px 20px 80px}
header.top{margin-bottom:22px}
h1{font-size:22px;margin:0 0 4px;letter-spacing:-.01em}
.brand{margin-bottom:22px;padding-bottom:16px;border-bottom:1px solid var(--line)}
.brand img{display:block;height:70px;width:auto}
.brand .unit{margin-top:9px;font-size:12px;font-weight:600;letter-spacing:.09em;
  text-transform:uppercase;color:var(--tx2)}
.verbtn{margin-left:10px;border:1px solid var(--line);background:var(--panel);
  color:var(--tx2);border-radius:20px;padding:1px 9px;font-size:11px;font-weight:600;
  cursor:pointer;font-family:var(--mono);vertical-align:1px}
.verbtn:hover{border-color:var(--accent);color:var(--accent)}
.vlog{margin:0 0 4px;padding-left:20px;font-size:12.5px;color:var(--tx2)}
.vlog li{margin:2px 0}
.sub{color:var(--tx2);font-size:13px}
.roots{margin-top:12px;display:grid;gap:6px;grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
.root{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:9px 12px;font-size:12px}
.root b{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--tx3);margin-bottom:2px}
.root span{font-family:var(--mono);color:var(--tx2);word-break:break-all}
.verdict{margin:20px 0;border-radius:10px;padding:16px 18px;border:1px solid;display:flex;gap:14px;align-items:flex-start}
.verdict.bad{background:var(--badbg);border-color:var(--bad);color:var(--bad)}
.verdict.ok{background:var(--okbg);border-color:var(--ok);color:var(--ok)}
.verdict.warn{background:var(--warnbg);border-color:var(--warn);color:var(--warn)}
.verdict .ic{font-size:22px;line-height:1.1}
.verdict h2{margin:0 0 3px;font-size:16px}
.verdict p{margin:0;font-size:13px;opacity:.92}
.kpis{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));margin-bottom:22px}
.kpi{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--line);
     border-radius:10px;padding:13px 14px}
.kpi.ok{border-left-color:var(--ok)} .kpi.bad{border-left-color:var(--bad)}
.kpi.warn{border-left-color:var(--warn)} .kpi.ptr{border-left-color:var(--ptr)}
.kpi.prod{border-left-color:var(--prod)}
.kpi .n{font-size:26px;font-weight:650;letter-spacing:-.02em;line-height:1.1}
.kpi .l{font-size:11.5px;color:var(--tx2);margin-top:3px}
.kpi.ok .n{color:var(--ok)} .kpi.bad .n{color:var(--bad)} .kpi.warn .n{color:var(--warn)}
.kpi.ptr .n{color:var(--ptr)} .kpi.prod .n{color:var(--prod)}
h3.sec{font-size:13px;text-transform:uppercase;letter-spacing:.07em;color:var(--tx3);
       margin:28px 0 10px;font-weight:600}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden;
      box-shadow:0 1px 2px rgba(16,23,34,.05)}
.tbl-scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px}
th{text-align:left;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.05em;
   color:var(--tx3);padding:9px 12px;border-bottom:1px solid var(--line);white-space:nowrap;
   background:var(--panel2);position:sticky;top:0;z-index:2}
td{padding:8px 12px;border-bottom:1px solid var(--line);vertical-align:top}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover td{background:var(--panel2)}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.fname{font-family:var(--mono);font-size:12px;word-break:break-all}
.fdir{color:var(--tx3);font-size:11px}
.badge{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:600;
       white-space:nowrap;border:1px solid currentColor}
.badge.ok{background:var(--okbg);color:var(--ok)}
.badge.bad{background:var(--badbg);color:var(--bad)}
.badge.warn{background:var(--warnbg);color:var(--warn)}
.badge.ptr{background:var(--ptrbg);color:var(--ptr)}
.badge.prod{background:var(--prodbg);color:var(--prod)}
.ctrls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 12px}
.chip{border:1px solid var(--line);background:var(--panel);color:var(--tx2);border-radius:20px;
      padding:5px 13px;font-size:12.5px;cursor:pointer;font-family:inherit}
.chip[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
input[type=search],select{border:1px solid var(--line);background:var(--panel);color:var(--tx);
      border-radius:8px;padding:6px 11px;font-size:13px;font-family:inherit;min-width:190px}
input[type=search]:focus,select:focus{outline:2px solid var(--accent);outline-offset:-1px}
.count{color:var(--tx3);font-size:12px;margin-left:auto}
.rowbtn{background:none;border:1px solid var(--line);border-radius:6px;color:var(--tx2);
        cursor:pointer;font-size:11px;padding:3px 9px;font-family:inherit;white-space:nowrap}
.rowbtn:hover{border-color:var(--accent);color:var(--accent)}
.modal{position:fixed;inset:0;z-index:50;display:flex;align-items:center;justify-content:center;
  background:rgba(16,23,34,.42);padding:20px}
.modal[hidden]{display:none}
.dlg{background:var(--panel);border:1px solid var(--line);border-radius:12px;
  width:min(1180px,96vw);max-height:88vh;display:flex;flex-direction:column;overflow:hidden;
  box-shadow:0 16px 44px rgba(16,23,34,.18)}
.dlg-hd{display:flex;gap:12px;align-items:center;padding:13px 16px;border-bottom:1px solid var(--line);
  background:var(--panel2)}
.dlg-hd .t{font-family:var(--mono);font-size:13px;word-break:break-all;flex:1;min-width:0}
.dlg-hd .t small{display:block;font-family:var(--sans);color:var(--tx3);font-size:11px}
.dlg-x{background:none;border:1px solid var(--line);border-radius:7px;color:var(--tx2);cursor:pointer;
  font-size:16px;line-height:1;padding:5px 10px;font-family:inherit}
.dlg-x:hover{border-color:var(--accent);color:var(--accent)}
#dlgBody{overflow:auto;min-height:0;flex:1}
.detail-in{padding:14px 16px}
.note{font-size:12.5px;color:var(--tx2);margin:0 0 10px}
.dhead{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--tx3);
       margin:14px 0 6px;font-weight:600}
pre.code{margin:0;background:var(--bg);border:1px solid var(--line);border-radius:7px;
   padding:9px 11px;font-family:var(--mono);font-size:11.5px;line-height:1.55;overflow-x:auto;
   white-space:pre;color:var(--tx)}
.pair{border:1px solid var(--line);border-radius:7px;overflow:hidden;margin-bottom:7px}
.pair .lbl{font-size:10.5px;font-weight:700;letter-spacing:.05em;padding:3px 9px;font-family:var(--sans)}
.pair .p-ptr .lbl{background:var(--ptrbg);color:var(--ptr)}
.pair .p-prod .lbl{background:var(--prodbg);color:var(--prod)}
.pair pre{margin:0;padding:6px 9px;font-family:var(--mono);font-size:11.5px;white-space:pre;
   overflow-x:auto;background:var(--panel);color:var(--tx)}
.pair .p-prod{border-top:1px solid var(--line)}
.lineno{font-size:11px;color:var(--tx3);margin:9px 0 3px;font-family:var(--mono)}
.ctbl{border:1px solid var(--line);border-radius:7px;overflow-x:auto;margin-bottom:6px}
.ctbl table{font-size:12px}
.ctbl th{padding:7px 10px;position:static}
.ctbl td{padding:6px 10px}
.note.cbad{color:var(--bad)}
.note.cbad b{font-family:var(--mono)}
.uline{display:flex;border:1px solid var(--line);border-radius:6px;margin-bottom:5px;overflow:hidden}
.uline .meta{flex:0 0 auto;min-width:96px;padding:6px 9px;background:var(--panel2);
  border-right:1px solid var(--line);font-family:var(--mono);font-size:10.5px;color:var(--tx3);
  white-space:nowrap;line-height:1.55}
.uline .meta b{color:var(--accent)}
.uline pre{flex:1;min-width:0;margin:0;padding:6px 9px;font-family:var(--mono);font-size:11.5px;
  white-space:pre;overflow-x:auto;background:var(--panel);color:var(--tx)}
mark{background:var(--mark);color:inherit;border-radius:2px;padding:0 1px}
.empty{padding:34px;text-align:center;color:var(--tx3);font-size:13px}
footer{margin-top:34px;color:var(--tx3);font-size:11.5px;text-align:center}
</style>
</head><body>

<div class="wrap">
<header class="top">
<div class="brand">
  <img src="data:image/png;base64,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"
       alt="Jalin, member of Danareksa" width="96" height="70">
  <div class="unit">Backoffice Business Operation<button class="verbtn" id="verBtn" title="Lihat riwayat versi"></button></div>
</div>
  <h1>Perbandingan Report PTR vs Report Production</h1>
  <div class="sub" id="subtitle"></div>
  <div class="roots">
    <div class="root"><b>Sumber PTR</b><span id="rootPtr"></span></div>
    <div class="root"><b>Sumber Production</b><span id="rootProd"></span></div>
  </div>
</header>

<div id="verdict"></div>
<div class="kpis" id="kpis"></div>

<h3 class="sec">Kelengkapan jenis report</h3>
<div class="note" id="typeNote"></div>
<div class="card tbl-scroll"><table id="byType"></table></div>

<h3 class="sec">Ringkasan per folder</h3>
<div class="card tbl-scroll"><table id="byFolder"></table></div>

<h3 class="sec">Rincian per file</h3>
<div class="ctrls" id="filters"></div>
<div class="ctrls">
  <input type="search" id="q" placeholder="Cari nama file / kode bank (mis. BRI)">
  <select id="folderSel"></select>
  <span class="count" id="count"></span>
</div>
<div class="card tbl-scroll"><table id="main"></table></div>

<footer id="foot"></footer>
</div>

<div class="modal" id="modal" hidden>
  <div class="dlg" role="dialog" aria-modal="true" aria-labelledby="dlgTitle">
    <div class="dlg-hd">
      <div class="t" id="dlgTitle"></div>
      <span id="dlgBadge"></span>
      <button class="dlg-x" id="dlgClose" aria-label="Tutup">&times;</button>
    </div>
    <div id="dlgBody"></div>
  </div>
</div>

<script>
/*__DATA__*/
(function(){
var D = window.__DATA__, rows = D.rows, meta = D.meta;
var lastFiles = {ptr: meta.filesPtr || [], prod: meta.filesProd || []};
/* Beda urutan baris, beda jam cetak dan beda format baris dihitung cocok;
   label ini dipakai banner ringkasan maupun tabel rincian. */
var SOFT_LABEL = {posisi:'beda posisi baris', jam:'beda jam cetak',
                  format:'beda format baris',
                  generate:'beda jam generate report'};
var SM = {
  IDENTIK:['Cocok','ok'],

  BEDA_DATA:['BEDA DATA','bad'], HANYA_PTR:['Hanya di PTR','ptr'],
  HANYA_PROD:['Hanya di Prod','prod']
};
function esc(s){return String(s).replace(/[&<>]/g,function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c];});}
function nf(n){return (n===null||n===undefined)?'–':n.toLocaleString('id-ID');}
function kb(n){return n<1024?n+' B':n<1048576?(n/1024).toFixed(1)+' KB':(n/1048576).toFixed(1)+' MB';}
function cnt(s){return rows.filter(function(r){return r.status===s;}).length;}

document.getElementById('subtitle').textContent =
  meta.label + ' · ' + rows.length + ' file diperiksa · dibuat ' + meta.generated;
document.getElementById('rootPtr').textContent  = meta.rootPtr;
document.getElementById('rootProd').textContent = meta.rootProd;

var nBad=cnt('BEDA_DATA'), nOnlyP=cnt('HANYA_PTR'), nOnlyD=cnt('HANYA_PROD');

var softCount = {};
rows.forEach(function(r){
  if(r.softReason) softCount[r.softReason] = (softCount[r.softReason]||0)+1; });
var softBits = Object.keys(softCount).map(function(k){
  return '<b>'+softCount[k]+'</b> '+SOFT_LABEL[k]; });
var orderTxt = softBits.length
  ? ' Termasuk file yang isinya sudah cocok dan hanya ' + softBits.join(', ') + '.' : '';

var blocking=nBad+nOnlyP+nOnlyD;
document.getElementById('verdict').innerHTML =
  (blocking===0)
  ? '<div class="verdict ok"><div class="ic">✓</div><div><h2>COCOK — Report PTR sama dengan Production</h2>'
    + '<p>Seluruh ' + rows.length + ' file cocok.' + orderTxt + '</p></div></div>'
  : '<div class="verdict bad"><div class="ic">✕</div><div>'
    + '<h2>TIDAK COCOK — ' + blocking + ' file wajib ditindaklanjuti</h2>'
    + '<p>' + nBad + ' file beda isi data · ' + nOnlyP + ' file hanya ada di PTR · '
    + nOnlyD + ' file hanya ada di Production · ' + cnt('IDENTIK') + ' file sudah cocok.'
    + orderTxt + '</p></div></div>';

var kpis=[['IDENTIK','Cocok','ok'],['BEDA_DATA','Beda data','bad'],
  ['HANYA_PTR','Hanya di PTR','ptr'],['HANYA_PROD','Hanya di Prod','prod']];
document.getElementById('kpis').innerHTML = kpis.map(function(k){
  return '<div class="kpi '+k[2]+'"><div class="n">'+cnt(k[0])+'</div><div class="l">'+k[1]+'</div></div>';
}).join('');

/* ---------------- kelengkapan jenis report ---------------- */
  var T = checkTypes(lastFiles.ptr, lastFiles.prod);
  var nAda = T.rows.filter(function(x){ return x.status === 'ADA'; }).length;
  var nHilang = T.rows.filter(function(x){ return x.status === 'TIDAK_ADA'; }).length;
  var nSebelah = T.rows.length - nAda - nHilang;

  document.getElementById('typeNote').innerHTML =
    '<b>' + nAda + '</b> dari <b>' + T.rows.length + '</b> jenis report ditemukan di kedua sisi'
    + (nSebelah ? ' &middot; <b>' + nSebelah + '</b> hanya ada di satu sisi' : '')
    + (nHilang ? ' &middot; <b>' + nHilang + '</b> tidak ditemukan sama sekali' : '')
    + '.';

  document.getElementById('byType').innerHTML =
    '<thead><tr><th>Jenis Report</th><th class="num">PTR</th><th class="num">Prod</th>'
    + '<th>Status</th><th>Contoh berkas</th></tr></thead><tbody>'
    + T.rows.map(function(x){
        var L = x.status === 'ADA'        ? ['Ada','ok']
              : x.status === 'HANYA_PTR'  ? ['Hanya di PTR','ptr']
              : x.status === 'HANYA_PROD' ? ['Hanya di Prod','prod']
              : ['Tidak ditemukan','bad'];
        return '<tr><td class="fname">' + esc(x.pat) + '</td>'
             + '<td class="num">' + (x.ptr || '–') + '</td>'
             + '<td class="num">' + (x.prod || '–') + '</td>'
             + '<td><span class="badge ' + L[1] + '">' + L[0] + '</span></td>'
             + '<td class="fdir">' + esc(x.contoh || '–') + '</td></tr>';
      }).join('') + '</tbody>';

var folders=[]; rows.forEach(function(r){if(folders.indexOf(r.folder)<0)folders.push(r.folder);});
folders.sort();
document.getElementById('byFolder').innerHTML =
 '<thead><tr><th>Folder</th><th class="num">Total</th><th class="num">Identik</th>'
 +'<th class="num">Beda data</th><th class="num">Cocok, beda non-data</th>'
 +'<th class="num">Hanya PTR</th><th class="num">Hanya Prod</th></tr></thead><tbody>'
 + folders.map(function(f){
   var g=rows.filter(function(r){return r.folder===f;});
   var c=function(s){return g.filter(function(r){return r.status===s;}).length;};
   var soft=g.filter(function(r){ return r.softReason; }).length;
   return '<tr><td class="fname">'+esc(f)+'</td><td class="num">'+g.length+'</td>'
   +'<td class="num">'+c('IDENTIK')+'</td><td class="num">'+(c('BEDA_DATA')||'–')+'</td>'
   +'<td class="num">'+(soft||'–')+'</td><td class="num">'+(c('HANYA_PTR')||'–')+'</td>'
   +'<td class="num">'+(c('HANYA_PROD')||'–')+'</td></tr>';
 }).join('')+'</tbody>';

var fStatus='ALL', fQ='', fFolder='ALL';
var fdefs=[['ALL','Semua'],['BEDA_DATA','Beda data'],['HANYA_PTR','Hanya di PTR'],
  ['HANYA_PROD','Hanya di Prod'],['IDENTIK','Cocok']];
document.getElementById('filters').innerHTML = fdefs.map(function(d){
  var n = d[0]==='ALL'?rows.length:cnt(d[0]);
  return '<button class="chip" data-v="'+d[0]+'" aria-pressed="'+(d[0]==='ALL')+'">'+d[1]+' ('+n+')</button>';
}).join('');
document.getElementById('filters').addEventListener('click',function(e){
  var b=e.target.closest('.chip'); if(!b) return;
  fStatus=b.dataset.v;
  Array.prototype.forEach.call(document.querySelectorAll('#filters .chip'),function(x){
    x.setAttribute('aria-pressed', x===b);});
  render();
});
document.getElementById('folderSel').innerHTML =
  '<option value="ALL">Semua folder</option>'+folders.map(function(f){
    return '<option>'+esc(f)+'</option>';}).join('');
document.getElementById('folderSel').onchange=function(e){fFolder=e.target.value;render();};
document.getElementById('q').oninput=function(e){fQ=e.target.value.toLowerCase();render();};

function hl(a,b){
  a=a||''; b=b||'';
  var m=Math.min(a.length,b.length), s=0, e=0;
  while(s<m && a.charAt(s)===b.charAt(s)) s++;
  while(e<m-s && a.charAt(a.length-1-e)===b.charAt(b.length-1-e)) e++;
  function wrap(t){
    return esc(t.slice(0,s))+'<mark>'+esc(t.slice(s,t.length-e))+'</mark>'+esc(t.slice(t.length-e));
  }
  return [wrap(a),wrap(b)];
}

/* ===================== daftar jenis report yang diharapkan =====================
   Pola ditulis seperti penamaan berkas: XXX = kode bank, YYMMDD = tanggal,
   YYMM = bulan. Sebagian pola ditulis tanpa '-MP' dan tanpa kode bank di
   depan, jadi keduanya diperlakukan opsional saat mencocokkan.            */
var REPORT_TYPES = [
  'XXX-Report-Harian-LINK-YYMMDD',
  'XXX-Report-Klaim-LINK-YYMMDD',
  'XXX-Transaction-Data-YYMMDD',
  'XXX-Transfer-Incomplete-YYMMDD',
  'XXX-Report-Clearing-LINK-MP-YYMMDD',
  'XXX-Report-ProAktif-Klaim-LINK-YYMMDD',
  'XXX-Report-Harian-LINK-YYMMDD-NEW',
  'XXX-Transaction-Data-YYMMDD-NEW',
  'XXX-Report-Revenue-Sharing-Jalin-MP-YYMMDD',
  'XXX-Report-Clearing-LINK-MP-Harian-YYMMDD',
  'BSM-Report-Harian-LINK-MP-AND-YYMMDD',
  'BSM-Transaction-Data-MP-AND-YYMMDD',
  'GPY-Transaction-Data-MP-YYMMDD-SUCCESS',
  'GPY-Transaction-Data-MP-YYMMDD-FAILED',
  'BCA-Klaim-Lain-MP-YYMMDD',
  'BCA-Switching-Fee-Harian-Data-MP-YYMMDD',
  'BCA-Netting-MP-YYMMDD',
  'BCA-Detail-Settlement-MP-YYMMDD',
  'Fee-Marketing-MP-YYMMDD',
  'Laporan-Fee-Marketing-MP-YYMMDD',
  'XXX-Report-Revenue-Sharing-Jalin-MP-YYMM',
  'XXX-Report-Revenue-Sharing-Jalin-MP-BNF-YYMM',
  'REVENUE_HARIAN_JALN_XXX_YYMMDD',
  'SETTLE_JALN_ALTO_YYMMDD_ACQ',
  'SETTLE_JALN_ALTO_YYMMDD_BNF',
  'SETTLE_JALN_ARTA_YYMMDD_ACQ',
  'SETTLE_JALN_ARTA_YYMMDD_BNF',
  'RECON_JALN_ALTO_YYMMDD',
  'RECON_JALN_ARTA_YYMMDD',
  'DISPUTE_JALN_ALTO_YYMMDD_BNF',
  'DISPUTE_JALN_ALTO_YYMMDD_ACQ',
  'DISPUTE_JALN_ARTA_YYMMDD_BNF',
  'DISPUTE_JALN_ARTA_YYMMDD_ACQ',
  'XXX-Report-Harian-LINK-MP-CLAIM-INTERKONEKSI-YYMMDD',
  'NET_SETTLE_ALTO_YYMMDD.xls',
  'NET_SETTLE_ARTA_YYMMDD.xls',
  'NET_SETTLE_RNTS_YYMMDD.xlsx',
  'XXX-Report-Revenue-Sharing-Jalin-MP-BNF-YYMMDD',
  'BTN-Report-Harian-LINK-MP-YYMMDD',
  'BTN-Transaction-Data-MP-YYMMDD',
  'BTN-Transfer-Incomplete-MP-YYMMDD',
  'ATMMP-Daily-Summary-YYMMDD.xls'
];

/* Kode di depan bisa kode bank 3 huruf (AGR, BCA) maupun nama switch
   4 huruf (ALTO, ARTA, RNTS), jadi keduanya diterima. */
var BANKRX = '[A-Za-z0-9]{3,4}';
function rxEsc(s){ return s.replace(/[.*+?^${}()|[\]\\\-]/g, '\\$&'); }

function typeRegex(pat){
  var p = pat, ext = '', m = /(\.[A-Za-z0-9]+)$/.exec(p);
  if(m){ ext = m[1]; p = p.slice(0, m.index); }
  var hasMp = (p.indexOf('-MP-') >= 0) || /-MP$/.test(p);
  var bankAwal = (p.indexOf('XXX') === 0) || /^[A-Z]{3}-/.test(p);
  var out = '', i = 0;
  while(i < p.length){
    if(!hasMp && p.substr(i, 7) === '-YYMMDD'){ out += '(?:\\-MP)?\\-\\d{6}'; i += 7; }
    else if(!hasMp && p.substr(i, 5) === '-YYMM'){ out += '(?:\\-MP)?\\-\\d{4}'; i += 5; }
    else if(p.substr(i, 6) === 'YYMMDD'){ out += '\\d{6}'; i += 6; }
    else if(p.substr(i, 4) === 'YYMM'){ out += '\\d{4}'; i += 4; }
    else if(p.substr(i, 3) === 'XXX'){ out += BANKRX; i += 3; }
    else { out += rxEsc(p.charAt(i)); i += 1; }
  }
  if(!bankAwal) out = '(?:' + BANKRX + '\\-)?' + out;
  /* Ekstensi yang ditulis di pola hanya petunjuk, tidak dituntut persis:
     pola '.xls' tetap menemukan berkas '.xlsx', dan sebaliknya. */
  var tail = '(?:\\.(?:txt|xls|xlsx|csv|gz|zip))?';
  return new RegExp('^' + out + tail + '$', 'i');
}

var TYPE_RX = null;
function typeRx(){
  if(!TYPE_RX) TYPE_RX = REPORT_TYPES.map(function(p){
    return {pat:p, rx:typeRegex(p)};
  });
  return TYPE_RX;
}

/* Periksa tiap jenis report: ada di PTR, ada di Production, atau tidak ada
   sama sekali. Berkas yang tidak tercakup pola mana pun juga dilaporkan,
   supaya tidak ada yang diam-diam terlewat. */
function checkTypes(namesPtr, namesProd){
  var defs = typeRx(), out = [];
  defs.forEach(function(d){
    var a = 0, b = 0, contoh = '';
    namesPtr.forEach(function(n){ if(d.rx.test(n)){ a++; if(!contoh) contoh = n; } });
    namesProd.forEach(function(n){ if(d.rx.test(n)){ b++; if(!contoh) contoh = n; } });
    out.push({pat:d.pat, ptr:a, prod:b, contoh:contoh,
              status: (a && b) ? 'ADA' : a ? 'HANYA_PTR' : b ? 'HANYA_PROD' : 'TIDAK_ADA'});
  });
  return {rows:out};
}

/* ============================ versi dan riwayat perubahan ============================
   Naikkan APP_VERSION dan tambahkan satu baris di CHANGELOG setiap ada
   penambahan atau perubahan, supaya pemakai tahu versi berapa yang dipegang. */
var APP_VERSION = '2.4';
var CHANGELOG = [
  ['2.4', '30 Okt 2026', [
    'Report pendek ikut dikenali sebagai beda posisi baris. Sebelumnya kolom nomor '
      + 'urut baru dipercaya kalau ada minimal 10 baris bernomor, sehingga report seperti '
      + 'DISPUTE yang hanya 8 baris tidak pernah lolos.',
    'Ambang itu diganti syarat yang lebih ketat sekaligus lebih longgar: nomornya harus '
      + 'mulai dari 1, berurutan naik satu-satu tanpa putus, dan jumlahnya sama di kedua sisi.'
  ]],
  ['2.3', '28 Okt 2026', [
    'Subtotal per halaman (SUB TOTAL ... /Page) dihitung sebagai angka turunan. '
      + 'Begitu baris berpindah halaman, subtotalnya ikut berubah walau isinya sama, '
      + 'sehingga report yang hanya beda posisi tidak lagi terbaca beda data.',
    'Pengamannya: grand total - baris TOTAL tanpa /Page - harus sama persis di kedua '
      + 'sisi. Selisih nominal sekecil apa pun tetap dilaporkan sebagai beda data.'
  ]],
  ['2.2', '27 Okt 2026', [
    'Baris yang bertukar posisi dikenali sebagai Beda Posisi Baris, bukan beda data. '
      + 'Nomor urut di kolom pertama ikut tertukar sehingga barisnya tidak pernah sama persis.',
    'Kolom pertama baru diabaikan kalau angkanya benar-benar berurutan naik satu-satu, '
      + 'supaya kolom jam atau nominal tidak ikut terbuang.'
  ]],
  ['2.1', '26 Okt 2026', [
    'Beda yang hanya terjadi pada tanggal data terakhir dihitung cocok: itu '
      + 'sidik jari report yang dibuat pada jam berbeda. Kalau ada tanggal lain '
      + 'ikut berbeda, berkasnya tetap dilaporkan sebagai beda data.',
    'Baris header dan trailer bergaya RH; dan RT; dikenali sebagai baris '
      + 'keterangan, bukan baris data.'
  ]],
  ['2.0', '15 Okt 2026', [
    'Berkas .xlsx dibandingkan per isi sel, bukan sebagai teks mentah. '
      + 'Sebelumnya isinya tampil sebagai sampah biner karena .xlsx '
      + 'sebenarnya arsip ZIP.',
    'Berkas biner lain - .xls lama, .gz, .zip, gambar - dilaporkan apa adanya '
      + 'tanpa rincian baris, tidak lagi memunculkan baris sampah.'
  ]],
  ['1.9', '15 Okt 2026', [
    'Beda jam atau tanggal cetak, beda header, dan beda format baris kini '
      + 'dihitung cocok dan tidak lagi ditampilkan sebagai perbedaan.',
    'Selisih waktu dikenali per token, sehingga tanggal yang berubah di tengah '
      + 'baris terbaca utuh dan nominal tidak ikut dianggap waktu.'
  ]],
  ['1.8', '07 Okt 2026', [
    'Jenis report NET_SETTLE_RNTS_YYMMDD ditambahkan.',
    'Kode di depan pola boleh 3 atau 4 huruf, sehingga '
      + 'REVENUE_HARIAN_JALN_XXX_YYMMDD kini menemukan ALTO, ARTA dan RNTS '
      + 'yang sebelumnya terlewat karena XXX dipatok tepat 3 huruf.'
  ]],
  ['1.7', '07 Okt 2026', [
    'Ekstensi pada pola tidak lagi dituntut persis, sehingga pola .xls tetap '
      + 'menemukan berkas .xlsx - sebelumnya NET_SETTLE_ALTO dan NET_SETTLE_ARTA '
      + 'terbaca Tidak ditemukan padahal berkasnya ada.'
  ]],
  ['1.6', '07 Okt 2026', [
    'Jenis report RECON_JALN_ALTO_YYMMDD ditambahkan ke daftar kelengkapan.'
  ]],
  ['1.5', '06 Okt 2026', [
    'Nomor versi ditampilkan di kepala halaman beserta riwayat perubahannya.'
  ]],
  ['1.4', '06 Okt 2026', [
    'Pemeriksaan kelengkapan 40 jenis report: Ada, Hanya di PTR, Hanya di Prod, atau Tidak ditemukan.',
    'Unduhan ringkasan jadi dua sheet: Ringkasan dan Kelengkapan Report.',
    'Keterangan berkas identik diringkas jadi "Sudah OK".'
  ]],
  ['1.3', '30 Sep 2026', [
    'Logo Jalin dan nama unit dipasang di kepala halaman.'
  ]],
  ['1.2', '23 Sep 2026', [
    'Hasil unduhan jadi berkas .xlsx, siap pakai di Excel.',
    'Pemasangan baris tiga tahap, sehingga semua jenis report bisa diunduh.'
  ]],
  ['1.1', '11 Sep 2026', [
    'Baris beda dipasangkan lewat isinya, bukan lewat posisi.',
    'Tombol unduh rincian perbedaan per berkas.'
  ]],
  ['1.0', '02 Sep 2026', [
    'Rilis awal: bandingkan satu berkas, banyak berkas, atau seluruh folder.',
    'Analisa per kode report dan label kode report pada tiap baris beda.',
    'Beda urutan baris diperlakukan sebagai cocok.'
  ]]
];

function changelogHTML(){
  return '<div class="detail-in">'
    + CHANGELOG.map(function(v){
        return '<div class="dhead">Versi ' + esc(v[0]) + ' &middot; ' + esc(v[1]) + '</div>'
             + '<ul class="vlog">'
             + v[2].map(function(t){ return '<li>' + esc(t) + '</li>'; }).join('')
             + '</ul>';
      }).join('')
    + '</div>';
}

/* ===================== pengenal selisih waktu =====================
   Dua baris dianggap hanya berselisih waktu bila seluruh token yang berbeda
   di antaranya berupa tanggal atau jam yang sah di KEDUA sisi. Pemeriksaan
   per token, bukan per potongan karakter, supaya '...;20260903' lawan
   '...;20260902' terbaca utuh sebagai tanggal - bukan sekadar satu digit. */
function isDateTimeToken(t){
  if(/^\d{2}[:.]\d{2}([:.]\d{2})?$/.test(t)) return true;          /* 10:25 / 10:25:47 */
  if(/^\d{2}[/-]\d{2}[/-]\d{4}$/.test(t)) return true;            /* 01/09/2026       */
  if(!/^\d+$/.test(t)) return false;
  function tgl(y, m, d){ return m >= 1 && m <= 12 && d >= 1 && d <= 31; }
  function jam(h, mi, s){ return h < 24 && mi < 60 && (s === undefined || s < 60); }
  var n = t.length;
  if(n === 6){                                                      /* YYMM\ / HHMMSS */
    return tgl(+t.slice(0,2), +t.slice(2,4), +t.slice(4,6))
        || jam(+t.slice(0,2), +t.slice(2,4), +t.slice(4,6));
  }
  if(n === 8) return tgl(+t.slice(0,4), +t.slice(4,6), +t.slice(6,8));
  if(n === 12) return tgl(+t.slice(0,2), +t.slice(2,4), +t.slice(4,6))
                   && jam(+t.slice(6,8), +t.slice(8,10), +t.slice(10,12));
  if(n === 14) return tgl(+t.slice(0,4), +t.slice(4,6), +t.slice(6,8))
                   && jam(+t.slice(8,10), +t.slice(10,12), +t.slice(12,14));
  return false;
}

/* Tanggal dan jam bertanda baca dibaca sebagai satu token, bukan terpecah. */
var RE_TOKEN = /\d{2}[:.]\d{2}(?:[:.]\d{2})?|\d{2}[/-]\d{2}[/-]\d{4}|\d{4}[/-]\d{2}[/-]\d{2}|[0-9A-Za-z]+/g;

function lineTimeOnly(a, b){
  if(a === b) return true;
  /* rangka baris - bagian selain token - harus sama persis */
  if(a.replace(RE_TOKEN, '\u0001') !== b.replace(RE_TOKEN, '\u0001')) return false;
  var ta = a.match(RE_TOKEN) || [], tb = b.match(RE_TOKEN) || [];
  if(ta.length !== tb.length) return false;
  var beda = 0, i;
  for(i = 0; i < ta.length; i++){
    if(ta[i] === tb[i]) continue;
    if(!isDateTimeToken(ta[i]) || !isDateTimeToken(tb[i])) return false;
    beda++;
  }
  return beda > 0;
}

function kodeTag(a,b){
  a = a || ''; b = (b===undefined) ? a : (b||'');
  if(!a && !b) return '';
  if(a === b) return '  &middot;  KODE REPORT ' + esc(a);
  return '  &middot;  KODE REPORT &mdash; PTR ' + esc(a||'-') + ' / PROD ' + esc(b||'-');
}
function ulines(list){
  return list.map(function(s){
    if(typeof s === 'string') s = {no:null, code:'', text:s};
    var meta = (s.code ? '<b>' + esc(s.code) + '</b> ' : '') + (s.no ? 'br.' + s.no : '');
    return '<div class="uline"><div class="meta">' + meta + '</div><pre>'
      + esc(s.text) + '</pre></div>';
  }).join('');
}
function detailHTML(r){
  var h='<div class="detail-in"><p class="note">'+esc(r.note)+'</p>';
  if(r.status==='HANYA_PTR'||r.status==='HANYA_PROD')
    return h+'<p class="note">Ukuran: '+kb(r.status==='HANYA_PTR'?r.sizePtr:r.sizeProd)+'</p></div>';

  if(r.onlyPtrRows || r.onlyProdRows)
    h+='<p class="note"><b>'+nf(r.onlyPtrRows)+'</b> baris hanya ada di PTR &middot; <b>'
      +nf(r.onlyProdRows)+'</b> baris hanya ada di Production</p>';

  if(r.eolPtr && r.eolProd && r.eolPtr !== r.eolProd)
    h+='<p class="note cbad">Akhiran baris berbeda: PTR memakai <b>'+esc(r.eolPtr)
      +'</b>, Production memakai <b>'+esc(r.eolProd)+'</b>.</p>';

  if(r.codes && r.codes.length){
    var mp=[], md=[];
    r.codes.forEach(function(c){
      if(c.status==='HANYA_PTR') mp.push(c.code); else md.push(c.code);
    });
    if(md.length) h+='<p class="note cbad">Kode report tidak diproduksi di PTR: <b>'
      +esc(md.join(', '))+'</b></p>';
    if(mp.length) h+='<p class="note cbad">Kode report tidak ada di Production: <b>'
      +esc(mp.join(', '))+'</b></p>';
  } else if(r.codesSame){
    h+='<p class="note">Seluruh <b>'+r.codesSame+'</b> kode report ada di kedua sisi'
      + ((r.codesPages && r.codesPages.length)
          ? '. Jumlah halaman berbeda pada <b>'+esc(r.codesPages.join(', '))
            +'</b> - ini akibat jumlah transaksinya berbeda, bukan kode report yang hilang.'
          : '.') + '</p>';
  }


  if(r.codeRows && r.codeRows.length){
    h+='<div class="dhead">Perbedaan per kode report ('+r.codeRows.length+' kode terdampak)</div>'
      +'<div class="ctbl"><table><thead><tr><th>Kode Report</th><th>Judul</th>'
      +'<th class="num">Baris beda PTR</th><th class="num">Baris beda Prod</th>'
      +'<th>Status</th></tr></thead><tbody>'
      + r.codeRows.map(function(c){
          var L = (c.status==='HANYA_PTR')  ? ['Hanya ada di PTR','ptr']
                : (c.status==='HANYA_PROD') ? ['Tidak ada di PTR','prod']
                : ['Beda isi','warn'];
          return '<tr><td class="fname">'+esc(c.code||'(sebelum header)')+'</td>'
           +'<td>'+esc(c.title||'-')+'</td>'
           +'<td class="num">'+nf(c.ptr)+'</td><td class="num">'+nf(c.prod)+'</td>'
           +'<td><span class="badge '+L[1]+'">'+L[0]+'</span></td></tr>';
        }).join('')+'</tbody></table></div>';
  }
  if(r.samplesPos.length){
    h+='<div class="dhead">Contoh baris yang isinya berbeda (transaksi yang sama, disandingkan)</div>';
    r.samplesPos.forEach(function(s){
      var p=hl(s.ptr,s.prod);
      var lbl = s.noProd && s.noProd !== s.no
        ? 'baris ' + s.no + ' (PTR) / ' + s.noProd + ' (PROD)'
        : 'baris ' + s.no;
      h+='<div class="lineno">'+lbl+kodeTag(s.codeA,s.codeB)+'</div><div class="pair">'
       +'<div class="p-ptr"><div class="lbl">PTR</div><pre>'+p[0]+'</pre></div>'
       +'<div class="p-prod"><div class="lbl">PROD</div><pre>'+p[1]+'</pre></div></div>';
    });
  }
  if(r.samplesPtr.length)
    h+='<div class="dhead">Baris yang tidak punya pasangan di Production</div>'+ulines(r.samplesPtr);
  if(r.samplesProd.length)
    h+='<div class="dhead">Baris yang tidak punya pasangan di PTR</div>'+ulines(r.samplesProd);
  return h+'</div>';
}

var tbl=document.getElementById('main');
function render(){
  var list=rows.filter(function(r){
    return (fStatus==='ALL'||r.status===fStatus)
        && (fFolder==='ALL'||r.folder===fFolder)
        && (!fQ||r.path.toLowerCase().indexOf(fQ)>=0);
  });
  document.getElementById('count').textContent=list.length+' dari '+rows.length+' file';
  if(!list.length){
    tbl.innerHTML='<tbody><tr><td class="empty">Tidak ada file yang cocok.</td></tr></tbody>';
    return;
  }
  tbl.innerHTML='<thead><tr><th>File</th><th>Status</th><th class="num">Ukuran PTR</th>'
   +'<th class="num">Ukuran Prod</th><th class="num">Baris PTR</th><th class="num">Baris Prod</th>'
   +'<th class="num">Baris beda</th><th></th></tr></thead><tbody>'
   + list.map(function(r,i){
      var sm=SM[r.status];
      var dif = (r.onlyPtrRows || r.onlyProdRows)
        ? nf(r.onlyPtrRows + r.onlyProdRows) : '–';
      var sub = esc(r.folder) + (r.softReason ? ' &middot; ' + SOFT_LABEL[r.softReason] : '');
      return '<tr><td><div class="fname">'+esc(r.name)+'</div><div class="fdir">'+sub+'</div></td>'
       +'<td><span class="badge '+sm[1]+'">'+sm[0]+'</span></td>'
       +'<td class="num">'+(r.sizePtr!=null?kb(r.sizePtr):'–')+'</td>'
       +'<td class="num">'+(r.sizeProd!=null?kb(r.sizeProd):'–')+'</td>'
       +'<td class="num">'+nf(r.linesPtr)+'</td><td class="num">'+nf(r.linesProd)+'</td>'
       +'<td class="num">'+dif+'</td>'
       +'<td>'+(r.status==='IDENTIK'?'':'<button class="rowbtn" data-i="'+i+'">Detail</button>')+'</td></tr>';
   }).join('')+'</tbody>';
  Array.prototype.forEach.call(tbl.querySelectorAll('.rowbtn'),function(b){
    b.onclick=function(){ openDlg(list[b.dataset.i]); };
  });
}

var modal=document.getElementById('modal');
function openDlg(r){
  var sm=SM[r.status];
  document.getElementById('dlgTitle').innerHTML=esc(r.name)+'<small>'+esc(r.folder)+'</small>';
  document.getElementById('dlgBadge').innerHTML='<span class="badge '+sm[1]+'">'+sm[0]+'</span>';
  document.getElementById('dlgBody').innerHTML=detailHTML(r);
  // geser kanan/kiri panel PTR & PROD secara bersamaan supaya kolom tetap sejajar
  Array.prototype.forEach.call(document.querySelectorAll('#dlgBody .pair'),function(p){
    var ps=p.querySelectorAll('pre'), lock=false;
    Array.prototype.forEach.call(ps,function(el){
      el.addEventListener('scroll',function(){
        if(lock) return; lock=true;
        Array.prototype.forEach.call(ps,function(o){ if(o!==el) o.scrollLeft=el.scrollLeft; });
        lock=false;
      });
    });
  });
  modal.hidden=false;
  document.body.style.overflow='hidden';
}
function closeDlg(){ modal.hidden=true; document.body.style.overflow=''; }
document.getElementById('verBtn').textContent = 'v' + APP_VERSION;
document.getElementById('verBtn').onclick = function(){
  document.getElementById('dlgTitle').innerHTML =
    'Riwayat versi<small>Compare Report PTR vs Production</small>';
  document.getElementById('dlgBadge').innerHTML =
    '<span class="badge ok">v' + esc(APP_VERSION) + '</span>';
  var dl = document.getElementById('dlPairs');
  if(dl) dl.hidden = true;
  document.getElementById('dlgBody').innerHTML = changelogHTML();
  modal.hidden = false;
  document.body.style.overflow = 'hidden';
};
document.getElementById('dlgClose').onclick=closeDlg;
modal.onclick=function(e){ if(e.target===modal) closeDlg(); };
document.addEventListener('keydown',function(e){ if(e.key==='Escape'&&!modal.hidden) closeDlg(); });

render();
document.getElementById('foot').textContent =
  'Dibuat otomatis oleh compare_report.py — ' + meta.generated;
})();
</script>
</body></html>
"""


def build_html(rows, meta):
    payload = json.dumps({'rows': rows, 'meta': meta}, ensure_ascii=False)
    payload = payload.replace('</', '<\\/')
    return HTML_TEMPLATE.replace('/*__DATA__*/', 'window.__DATA__ = ' + payload + ';')


def dive(p):
    """Turun ke dalam folder selama isinya hanya satu sub-folder."""
    while True:
        items = os.listdir(p)
        dirs = [x for x in items if os.path.isdir(os.path.join(p, x))]
        files = [x for x in items if os.path.isfile(os.path.join(p, x))]
        if files or len(dirs) != 1:
            return p
        p = os.path.join(p, dirs[0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ptr', nargs='?')
    ap.add_argument('prod', nargs='?')
    ap.add_argument('-o', '--out', default='Compare-Report-PTR-vs-Prod.html')
    ap.add_argument('--label', default='')
    a = ap.parse_args()

    base = os.path.dirname(os.path.abspath(__file__))
    ptr, prod = a.ptr, a.prod
    if not ptr or not prod:
        for d in sorted(os.listdir(base)):
            full = os.path.join(base, d)
            if not os.path.isdir(full):
                continue
            u = d.upper()
            if 'PTR' in u and not ptr:
                ptr = dive(full)
            elif 'PROD' in u and not prod:
                prod = dive(full)
    if not ptr or not prod:
        sys.exit('Folder PTR / Prod tidak ditemukan.\n'
                 'Jalankan: py compare_report.py "<folder PTR>" "<folder Prod>"')

    print('PTR  :', ptr)
    print('PROD :', prod)
    print('Memindai file...', flush=True)
    A, B = scan(ptr), scan(prod)
    keys = sorted(set(A) | set(B))
    rows = []
    n = len(keys)
    for i, k in enumerate(keys, 1):
        if k in A and k in B:
            rows.append(analyse(k, A[k], B[k]))
        elif k in A:
            r = blank(k)
            r['sizePtr'] = A[k]['size']
            r['status'] = 'HANYA_PTR'
            r['note'] = 'File ada di PTR tetapi tidak ada di Production.'
            rows.append(r)
        else:
            r = blank(k)
            r['sizeProd'] = B[k]['size']
            r['status'] = 'HANYA_PROD'
            r['note'] = 'File ada di Production tetapi tidak ada di PTR.'
            rows.append(r)
        if i % 25 == 0 or i == n:
            print('  %d/%d' % (i, n), flush=True)

    order = {'BEDA_DATA': 0, 'HANYA_PTR': 1, 'HANYA_PROD': 2, 'BEDA_URUTAN': 3,
             'BEDA_HEADER': 4, 'BEDA_FORMAT': 5, 'IDENTIK': 6}
    rows.sort(key=lambda r: (order[r['status']], r['path']))

    meta = {'rootPtr': ptr, 'rootProd': prod,
            'filesPtr': sorted(k.split('/')[-1] for k in A),
            'filesProd': sorted(k.split('/')[-1] for k in B),
            'label': a.label or os.path.basename(ptr.rstrip('\\/')),
            'generated': datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

    out = a.out if os.path.isabs(a.out) else os.path.join(base, a.out)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(build_html(rows, meta))

    print('\nSelesai -> ' + out)
    for s in order:
        c = sum(1 for r in rows if r['status'] == s)
        if c:
            print('  %-12s %d' % (s, c))


if __name__ == '__main__':
    main()
