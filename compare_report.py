# -*- coding: utf-8 -*-
"""
Compare report PTR vs Report Production (Fee Engine / Merah Putih).
Menghasilkan satu file HTML mandiri berisi seluruh perbedaan.

Pemakaian:
    py compare_report.py
    py compare_report.py "<folder PTR>" "<folder Prod>" -o hasil.html
"""
import os, re, sys, json, hashlib, argparse
from collections import Counter
from datetime import datetime

MAX_FULL_READ = 200 * 1024 * 1024   # di atas ini hanya cek hash, tanpa detail baris
SAMPLE_POS    = 25                  # contoh baris beda pada posisi sama
SAMPLE_UNIQ   = 15                  # contoh baris yang hanya ada di satu sisi
LINE_TRUNC    = 400

META_PAT = [
    re.compile(r'^\s*F[HT]\s*\d+'),
    re.compile(r'\bHAL\s*:'),
    re.compile(r'\bTANGGAL\s*:'),
    re.compile(r'\bKODE\s+(BANK|REPORT)\s*:'),
    re.compile(r'\bJAM\s*:'),
    re.compile(r'\bWAKTU\s+CETAK\b'),
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


def trunc(s):
    return s[:LINE_TRUNC] + ' ...' if len(s) > LINE_TRUNC else s


KEYLEN = 64


def key_of(t):
    k = t[:KEYLEN]
    return k if len(k.replace(' ', '')) >= 12 else None


def pair_by_content(r, la, lb, only_a, only_b, sa, sb):
    """Pasangkan baris beda lewat kunci isi (awal baris), bukan lewat posisi,
    supaya transaksi yang sama yang disandingkan walau urutannya bergeser."""
    idx = {}
    for j, ln in enumerate(lb):
        if ln in only_b:
            k = key_of(ln)
            if k:
                idx.setdefault(k, []).append(j)
    pos, used_b, paired_a, paired_b = [], set(), set(), set()
    for i, ln in enumerate(la):
        if len(pos) >= SAMPLE_POS:
            break
        if ln not in only_a or ln in paired_a:
            continue
        k = key_of(ln)
        if not k or k not in idx:
            continue
        hit = next((j for j in idx[k] if j not in used_b), None)
        if hit is None:
            continue
        used_b.add(hit)
        paired_a.add(ln)
        paired_b.add(lb[hit])
        pos.append({'no': i + 1, 'noProd': hit + 1,
                    'ptr': trunc(ln), 'prod': trunc(lb[hit]),
                    'codeA': sa[i], 'codeB': sb[hit]})
    r['samplesPos'] = pos
    r['posDiff'] = len(pos)
    return paired_a, paired_b


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
        'orderOnly': False,
        'eolPtr': None, 'eolProd': None,
        'status': '', 'note': '',
    }


def analyse(rel, a, b):
    r = blank(rel)
    r['sizePtr'], r['sizeProd'] = a['size'], b['size']

    if a['md5'] == b['md5']:
        r['status'] = 'IDENTIK'
        r['note'] = 'Isi file sama persis (MD5 cocok).'
        return r

    if max(a['size'], b['size']) > MAX_FULL_READ:
        r['status'] = 'BEDA_DATA'
        r['note'] = 'File terlalu besar untuk dianalisa per baris; MD5 berbeda.'
        return r

    la, r['eolPtr'] = read_lines(a['abs'])
    lb, r['eolProd'] = read_lines(b['abs'])
    r['linesPtr'], r['linesProd'] = len(la), len(lb)
    A, B = section_scan(la), section_scan(lb)
    code_diff(r, A, B)
    sa, sb = A[0], B[0]

    if la == lb:
        r['status'] = 'BEDA_FORMAT'
        r['note'] = ('Isi baris identik. Beda hanya pada spasi di akhir baris '
                     'atau akhiran baris (CRLF vs LF).')
        return r

    ca, cb = Counter(la), Counter(lb)
    only_a, only_b = ca - cb, cb - ca
    r['onlyPtrRows'] = sum(only_a.values())
    r['onlyProdRows'] = sum(only_b.values())

    shifted = sum(1 for i in range(min(len(la), len(lb))) if la[i] != lb[i])

    if not only_a and not only_b:
        r['status'] = 'IDENTIK'
        r['orderOnly'] = True
        r['note'] = ('Isi report cocok. Seluruh baris sama persis, hanya urutan '
                     'barisnya yang berbeda (%d posisi bergeser).' % shifted)
        return r

    code_rows(r, la, lb, only_a, only_b, sa, sb, A[2], B[2])
    paired_a, paired_b = pair_by_content(r, la, lb, only_a, only_b, sa, sb)
    r['samplesPtr'] = pick_unique(la, only_a, sa, paired_a)
    r['samplesProd'] = pick_unique(lb, only_b, sb, paired_b)

    uniq = list(only_a.keys()) + list(only_b.keys())
    if uniq and len(uniq) <= 2 * SAMPLE_UNIQ and all(is_meta(x) for x in uniq):
        r['status'] = 'BEDA_HEADER'
        r['note'] = ('Beda hanya pada baris header/trailer (jam cetak, nomor halaman, '
                     'atau jumlah record). Baris data tidak berubah.')
    else:
        r['status'] = 'BEDA_DATA'
        r['note'] = 'Ada baris data yang isinya berbeda antara PTR dan Production.'
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
h1{font-size:22px;margin:0 0 4px;letter-spacing:-.01em;position:relative;padding-top:15px}
h1::before{content:"";position:absolute;top:0;left:0;width:46px;height:3px;
  background:var(--accent);border-radius:2px}
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
  <h1>Perbandingan Report PTR vs Report Production</h1>
  <div class="sub" id="subtitle"></div>
  <div class="roots">
    <div class="root"><b>Sumber PTR</b><span id="rootPtr"></span></div>
    <div class="root"><b>Sumber Production</b><span id="rootProd"></span></div>
  </div>
</header>

<div id="verdict"></div>
<div class="kpis" id="kpis"></div>

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
var SM = {
  IDENTIK:['Identik','ok'], BEDA_FORMAT:['Beda format baris','warn'],
  BEDA_HEADER:['Beda header/jam','warn'],
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
var nSoft=cnt('BEDA_HEADER')+cnt('BEDA_FORMAT');
var nOrder=rows.filter(function(r){ return r.orderOnly; }).length;
var orderTxt = nOrder ? ' Termasuk <b>'+nOrder+'</b> file yang isinya sudah cocok dan '
  + 'hanya berbeda urutan barisnya.' : '';
var blocking=nBad+nOnlyP+nOnlyD;
document.getElementById('verdict').innerHTML =
  (blocking===0 && nSoft===0)
  ? '<div class="verdict ok"><div class="ic">✓</div><div><h2>COCOK — Report PTR sama dengan Production</h2>'
    + '<p>Seluruh ' + rows.length + ' file cocok.' + orderTxt + '</p></div></div>'
  : '<div class="verdict ' + (blocking?'bad':'warn') + '"><div class="ic">' + (blocking?'✕':'!') + '</div><div>'
    + '<h2>' + (blocking ? 'TIDAK COCOK — ' + blocking + ' file wajib ditindaklanjuti'
                         : 'PERLU DICEK — ' + nSoft + ' file beda non-data') + '</h2>'
    + '<p>' + nBad + ' file beda isi data · ' + nOnlyP + ' file hanya ada di PTR · '
    + nOnlyD + ' file hanya ada di Production · ' + nSoft
    + ' file beda header/format saja · ' + cnt('IDENTIK') + ' file sudah cocok.'
    + orderTxt + '</p></div></div>';

var kpis=[['IDENTIK','Identik','ok'],['BEDA_DATA','Beda data','bad'],
  ['BEDA_HEADER','Beda header/jam','warn'],
  ['BEDA_FORMAT','Beda format baris','warn'],
  ['HANYA_PTR','Hanya di PTR','ptr'],['HANYA_PROD','Hanya di Prod','prod']];
document.getElementById('kpis').innerHTML = kpis.map(function(k){
  return '<div class="kpi '+k[2]+'"><div class="n">'+cnt(k[0])+'</div><div class="l">'+k[1]+'</div></div>';
}).join('');

var folders=[]; rows.forEach(function(r){if(folders.indexOf(r.folder)<0)folders.push(r.folder);});
folders.sort();
document.getElementById('byFolder').innerHTML =
 '<thead><tr><th>Folder</th><th class="num">Total</th><th class="num">Identik</th>'
 +'<th class="num">Beda data</th><th class="num">Beda header/format</th>'
 +'<th class="num">Hanya PTR</th><th class="num">Hanya Prod</th></tr></thead><tbody>'
 + folders.map(function(f){
   var g=rows.filter(function(r){return r.folder===f;});
   var c=function(s){return g.filter(function(r){return r.status===s;}).length;};
   var soft=c('BEDA_HEADER')+c('BEDA_FORMAT');
   return '<tr><td class="fname">'+esc(f)+'</td><td class="num">'+g.length+'</td>'
   +'<td class="num">'+c('IDENTIK')+'</td><td class="num">'+(c('BEDA_DATA')||'–')+'</td>'
   +'<td class="num">'+(soft||'–')+'</td><td class="num">'+(c('HANYA_PTR')||'–')+'</td>'
   +'<td class="num">'+(c('HANYA_PROD')||'–')+'</td></tr>';
 }).join('')+'</tbody>';

var fStatus='ALL', fQ='', fFolder='ALL';
var fdefs=[['ALL','Semua'],['BEDA_DATA','Beda data'],['HANYA_PTR','Hanya di PTR'],
  ['HANYA_PROD','Hanya di Prod'],['BEDA_HEADER','Beda header'],
  ['BEDA_FORMAT','Beda format'],['IDENTIK','Identik']];
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
      var sub = esc(r.folder) + (r.orderOnly ? ' &middot; beda urutan baris' : '');
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
