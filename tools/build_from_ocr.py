# -*- coding: utf-8 -*-
"""
build_from_ocr.py — 用 PP-OCRv6 的识别结果重建两份数据：
  1) app/content/book.json   卡片式（重排：對話卡／表格／詞組芯片）
  2) app/content/layout.json 原版式（每行保留原書座標，逐行還原版面）
数据源：tools/ocr_raw/pNNN.json（由 ocr_pages.py 生成）
"""
import os, sys, json, re, unicodedata
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_book as bb
from extract_text import (HAN, TONE, classify, clean, clean_py, make_pairs, add_vocab,
                          is_multi_col, make_table, OCR_FIX, NUM_ORDER,
                          LATIN_CELL, CELL_FIX)

RAW_DIR = os.path.join(bb.ROOT, "tools", "ocr_raw")
BOOK_OUT = os.path.join(bb.ROOT, "app", "content", "book.json")
LAYOUT_OUT = os.path.join(bb.ROOT, "app", "content", "layout.json")

SIZE_FACTOR = 0.82      # OCR 框高 → 字號（pt）
LOW_CONF = 0.72         # 低於此信心度標記為待核對
SUP = str.maketrans('⁰¹²³⁴⁵⁶⁷⁸⁹', '0123456789')
MARKS = '·・‧•∙⋅\u02d9'  # OCR 常把粵字注音小符號讀成點
CJK_CH = re.compile(r'[\u2e80-\u9fff\u3000-\u303f\uff00-\uffef]')


def normalize(t):
    """上標聲調→數字、去重音符號、統一引號、清除注音裝飾點"""
    t = t.translate(SUP)
    t = unicodedata.normalize('NFD', t)
    t = ''.join(c for c in t if not unicodedata.combining(c))
    t = unicodedata.normalize('NFC', t)
    for m in MARKS:
        t = t.replace(m, ' ')
    t = t.replace('’', "'").replace('‘', "'").replace('ʻ', "'")
    t = t.replace('“', '「').replace('”', '」')
    t = re.sub(r'\s+', ' ', t).strip()
    for a, b in OCR_FIX:
        t = t.replace(a, b)
    return t


def load_page(p1):
    path = os.path.join(RAW_DIR, 'p%03d.json' % p1)
    if not os.path.exists(path):
        return None
    d = json.load(open(path, encoding='utf-8'))
    k = 72.0 / d['dpi']
    items = []
    for box, txt, sc in d['items']:
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        t = normalize(txt)
        if not t:
            continue
        items.append({'x0': min(xs) * k, 'x1': max(xs) * k, 'y0': min(ys) * k,
                      'y1': max(ys) * k, 't': t, 'sc': sc})
    items.sort(key=lambda a: (a['y0'], a['x0']))
    return {'n': p1, 'w': d['w'], 'h': d['h'], 'items': items}


MAN_WORDS = ('對譯', '譯文', '普通話')
# 欄目完整名稱（用於分辨「正文標題」與「目錄行」）
CANON = ['普通話對譯', '課文', '講解', '練習', '重點詞彙', '補充語彙', '粵語趣談', '傳意項目',
         '會話聆聽', '短文朗讀', '粵字辨認', '每課一句', '語音講解', '語法講解', '補充練習',
         '聲母', '韻母', '聲調', '入聲']


def zone_kind(k, text, st):
    """用章節上下文判定：對譯段（標題「普通話對譯」之下）才算 man，其餘小字仍屬正文"""
    hits = [w for w in CANON if w in text]
    head_like = (k == 'h') or (len(text) <= 14 and hits)   # 「課文 1-1」這類欄目行也算標題
    if head_like:
        if len(hits) >= 2:               # 一行列出多個欄目 → 是目錄行，不改狀態
            return 'h' if k == 'h' else k
        if any(w in text for w in MAN_WORDS):
            st['man'] = True             # 進入對譯區
            return 'h'
        if hits:
            st['man'] = False            # 其他欄目 → 退出對譯區
            return 'h'
    if k in ('yue', 'man'):
        return 'man' if st.get('man') else 'yue'
    return k


def group_rows(items):
    """把同一個視覺行的 OCR 框合併成行"""
    rows = []
    for it in items:
        placed = False
        for r in rows:
            ov = min(r['y1'], it['y1']) - max(r['y0'], it['y0'])
            hh = min(r['y1'] - r['y0'], it['y1'] - it['y0'])
            if hh > 0 and ov / hh > 0.55:
                r['items'].append(it)
                r['y0'] = min(r['y0'], it['y0'])
                r['y1'] = max(r['y1'], it['y1'])
                placed = True
                break
        if not placed:
            rows.append({'y0': it['y0'], 'y1': it['y1'], 'items': [it]})
    rows.sort(key=lambda r: r['y0'])
    for r in rows:
        r['items'].sort(key=lambda a: a['x0'])
        r['x0'] = r['items'][0]['x0']
        r['x1'] = max(a['x1'] for a in r['items'])
        r['t'] = clean(' '.join(a['t'] for a in r['items']))
        r['size'] = max((a['y1'] - a['y0']) for a in r['items']) * SIZE_FACTOR
        r['sc'] = min(a['sc'] for a in r['items'])
    return rows


def page_ref(rows):
    """頁內正文基準字號：含漢字行的 70 分位（對譯行偏小，不會拉低基準）"""
    hs = sorted(r['size'] for r in rows if len(HAN.findall(r['t'])) >= 4)
    if not hs:
        hs = sorted(r['size'] for r in rows)
    if not hs:
        return 10.0
    return hs[min(int(len(hs) * 0.7), len(hs) - 1)]


def line_kind(t, size, ref=None):
    """判定行類型：(kind, text)
    表格字母格（b／p／m／f／-i／-ng／z（j））優先保留——原書語音表大量使用單字母格"""
    if LATIN_CELL.match(t) and 5.5 <= size <= 20:
        return ('p', CELL_FIX.get(t, t))
    k = classify(t, size, ref)
    if k is None:
        return None
    if k in ('py', 'p'):
        c = clean_py(t)
        if not c:
            return None
        if k == 'p' and len(TONE.findall(c)) < 2:
            return None
        if k == 'py':                       # 剔除含大量雜符的碎片行（如 .::.yi6）
            good = sum(1 for ch in t if ch.isalpha() or ch.isdigit() or ch in " '’-'()")
            if good / max(len(t), 1) < 0.8:
                return None
        return (k, c)
    return (k, t)


def char_w(ch, size):
    """估算單字寬度（pt）：全形 1.0em，西文 0.55em，空格 0.33em"""
    if CJK_CH.match(ch):
        return size
    if ch == ' ':
        return size * 0.33
    if ch in "'-’":
        return size * 0.3
    return size * 0.55


def nat_width(t, size):
    return sum(char_w(c, size) for c in t)


SEG_BR = re.compile(r'（[^（）]{1,3}）')


def split_segments(t):
    """拆開被 OCR 併成一個框的多個表格格
    ① 重複括注（（監）（間）（耕））② 多個短空白分詞（≥3 段且每段 ≤4 字）"""
    groups = SEG_BR.findall(t)
    if len(groups) >= 2 and ''.join(groups) == t.replace(' ', ''):
        return groups
    parts = t.split()
    if len(parts) >= 3 and all(len(p) <= 4 for p in parts):
        return parts
    return None


def col_candidates(lines):
    """頁內列座標候選：短西文格（拼音／聲母／韻尾）的左緣，用於把拆出的格子吸回原列"""
    xs = sorted(l['x'] for l in lines
                if l['k'] in ('p', 'py') and l['w'] <= 34 and len(l['t']) <= 6)
    cols = []
    for x in xs:
        if not cols or x - cols[-1] > 6:
            cols.append(x)
    return cols


def snap_columns(lines):
    """把「拆出來的格子」對齊到最近的原列座標（同列內不重疊）"""
    cols = col_candidates(lines)
    if len(cols) < 3:
        return lines
    floor = {}
    for L in lines:
        if not L.get('m'):
            continue
        key = round(L['y'])
        f = floor.get(key, -1e9)
        best = min(cols, key=lambda c: abs(c - L['x']))
        if abs(best - L['x']) <= 18 and best >= f:
            L['x'] = round(best, 1)
        floor[key] = L['x'] + L['w'] * 0.6      # 允許少量重疊（括號比列寬）
    return lines


def norm_sizes(lines):
    """同頁同類字號向中位數收斂，消除 OCR 框高抖動造成的忽大忽小（標題不參與）"""
    from statistics import median
    for kind in ('yue', 'man', 'p', 'py'):
        vs = [l['s'] for l in lines if l['k'] == kind]
        if len(vs) < 4:
            continue
        m = median(vs)
        for l in lines:
            if l['k'] == kind:
                l['s'] = round(min(m * 1.1, max(m * 0.92, l['s'])), 1)
    return lines


def layout_lines(page, st=None):
    """原版式：逐個 OCR 框保留座標（最貼近原書版面）
    含一步「去合併」：被 OCR 併成一框的多列文字拆回各列並吸回原列座標"""
    ref = page_ref([{'t': it['t'], 'size': (it['y1'] - it['y0']) * SIZE_FACTOR}
                    for it in page['items']])
    out = []
    st = st if st is not None else {'man': False}
    for it in page['items']:
        size = (it['y1'] - it['y0']) * SIZE_FACTOR
        r = line_kind(it['t'], size, ref)
        if r is None:
            continue
        k, t = r
        k = zone_kind(k, t, st)
        base = {'y': round(it['y0'], 1), 's': round(size, 1), 'k': k}
        if it['sc'] < LOW_CONF:
            base['q'] = 1
        box_w = it['x1'] - it['x0']
        segs = None
        if k in ('yue', 'man') and len(t) >= 3 and box_w >= nat_width(t, size) * 0.6:
            segs = split_segments(t)
        if segs and len(segs) >= 2:
            slot = box_w / len(segs)
            for i, sg in enumerate(segs):
                L = dict(base)
                L['t'] = sg
                L['x'] = round(it['x0'] + i * slot, 1)
                L['w'] = round(nat_width(sg, size), 1)
                L['m'] = 1                    # 標記：拆出來的格，待吸回原列
                out.append(L)
        else:
            L = dict(base)
            L['t'] = t
            L['x'] = round(it['x0'], 1)
            L['w'] = round(box_w, 1)
            out.append(L)
    return norm_sizes(snap_columns(out))


def card_blocks(page, st=None):
    """卡片式：行 → 表格／對話卡／詞組芯片"""
    rows = group_rows(page['items'])
    ref = page_ref(rows)
    out = []
    pending = []
    st = st if st is not None else {'man': False}
    i = 0
    while i < len(rows):
        r = rows[i]
        spans = [[a['x0'], a['x1'], a['t'], (a['y1'] - a['y0']) * SIZE_FACTOR] for a in r['items']]
        if is_multi_col(spans):
            j = i
            group = [spans]
            while j + 1 < len(rows) and is_multi_col(
                    [[a['x0'], a['x1'], a['t'], (a['y1'] - a['y0']) * SIZE_FACTOR] for a in rows[j + 1]['items']]):
                j += 1
                group.append([[a['x0'], a['x1'], a['t'], (a['y1'] - a['y0']) * SIZE_FACTOR]
                              for a in rows[j]['items']])
            if len(group) >= 2:
                tab = make_table(group)
                out.append(tab)
                i = j + 1
                continue
        rk = line_kind(r['t'], r['size'], ref)
        if rk is None:
            i += 1
            continue
        k, text = rk
        k = zone_kind(k, text, st)
        if k in ('yue', 'man'):
            for a, b in OCR_FIX:
                text = text.replace(a, b)
            pr = make_pairs(text)
            if pr:
                add_vocab(out, pr, pending)
                i += 1
                continue
            if out and out[-1].get('k') == 'vocab' and all(h in NUM_ORDER for h, _ in out[-1]['pairs']):
                from extract_text import make_units, numeral_fix
                units = make_units(text)
                pr2 = numeral_fix(units) if units else None
                if pr2:
                    add_vocab(out, pr2, pending)
                    i += 1
                    continue
        if out and out[-1].get('k') == k and k == 'p':
            out[-1]['s'] += ' ' + text
        else:
            blk = {'k': k, 's': text}
            if r['sc'] < LOW_CONF:
                blk['q'] = 1
            out.append(blk)
        i += 1
    return out


FALLBACK = os.path.join(bb.ROOT, "tools", "layout_acro_backup.json")   # 缺页兜底（Acrobat 版面）


def load_fallback():
    if not os.path.exists(FALLBACK):
        return {}
    d = json.load(open(FALLBACK, encoding='utf-8'))
    return {p['n']: p for s in d['sections'] for p in s.get('pages', [])}


def main():
    fb = load_fallback()
    sections = []

    def build(ch, title, subtitle, tracks, a, b):
        blocks, pages = [], []
        st = {'man': False, 'carry': False}    # 對譯區狀態（跨頁需嚴格確認才延續）
        for p1 in range(a, b + 1):
            page = load_page(p1)
            if page is None or not page['items']:
                if p1 in fb:                  # OCR 未覆盖的页 → 沿用舊版面，保證不缺頁
                    pages.append(fb[p1])
                continue
            first = page['items'][0]['t']
            # 只有上一页确实停在对译区、且本页以 (n) 编号续行，才延续对译区
            st['man'] = bool(st.get('carry')) and bool(re.match(r'^[（(]\s*\d+\s*[）)]', first))
            lines = layout_lines(page, st)
            if lines:
                pages.append({'n': p1, 'w': page['w'], 'h': page['h'], 'lines': lines})
            blocks.extend(card_blocks(page, st))
            st['carry'] = st['man']
        sections.append({'chapter': ch, 'title': title, 'subtitle': subtitle,
                         'tracks': tracks, 'blocks': blocks, 'pages': pages})

    with open(os.path.join(bb.ROOT, "prototype", "lessons.json"), encoding='utf-8') as f:
        audio = json.load(f)
    tracks_by_ch = {c['chapter']: c['audioKeys'] for c in audio['chapters']}

    build(-1, '前言與目錄', '序 · 前言 · 每課學習重點', [], *bb.FRONT_PDF)
    build(0, '語音入門', '粵語語音系統 · 粵語常用字表', tracks_by_ch.get(0, []), *bb.CH0_PDF)
    for ch in range(1, 31):
        s = bb.BOOK_STARTS[ch]
        e = (bb.BOOK_STARTS[ch + 1] - 1) if ch < 30 else (bb.APPENDIX_BOOK - 1)
        build(ch, bb.LESSON_TITLES[ch], '第{}課'.format(ch),
              tracks_by_ch.get(ch, []), s + bb.OFFSET, e + bb.OFFSET)

    book = {
        'source': '粵語（香港話）教程（修訂版）（錄音掃碼即聽版）',
        'official': 'https://www.jointpublishing.com/?p=16107/',
        'pdfOffset': bb.OFFSET,
        'audioBaseUrl': '../粵語教程/',
        'sections': [{k: v for k, v in s.items() if k != 'pages'} for s in sections],
    }
    with open(BOOK_OUT, 'w', encoding='utf-8') as f:
        json.dump(book, f, ensure_ascii=False, separators=(',', ':'))

    layout = {'source': book['source'], 'sections': sections}
    with open(LAYOUT_OUT, 'w', encoding='utf-8') as f:
        json.dump(layout, f, ensure_ascii=False, separators=(',', ':'))

    ntab = sum(1 for s in sections for b in s['blocks'] if b['k'] == 'table')
    nvoc = sum(1 for s in sections for b in s['blocks'] if b['k'] == 'vocab')
    nln = sum(len(p['lines']) for s in sections for p in s['pages'])
    nq = sum(1 for s in sections for p in s['pages'] for l in p['lines'] if l.get('q'))
    # 版面坐标自检：行是否落在页内、字号是否合理
    out_of_bounds = 0
    bad_size = 0
    for s in sections:
        for p in s['pages']:
            for l in p['lines']:
                if l['x'] < -1 or l['y'] < -1 or l['x'] > p['w'] or l['y'] > p['h']:
                    out_of_bounds += 1
                if not (5 <= l['s'] <= 40):
                    bad_size += 1
    print('DONE sections:{} | blocks:{} (tables {} vocab {}) | pages:{} lines:{} (low-conf {})'
          .format(len(sections), sum(len(s['blocks']) for s in sections), ntab, nvoc,
                  sum(len(s['pages']) for s in sections), nln, nq))
    print('自检: 越界行 {} | 异常字号 {}'.format(out_of_bounds, bad_size))
    print('book.json {:.0f} KB | layout.json {:.0f} KB'.format(
        os.path.getsize(BOOK_OUT) / 1024, os.path.getsize(LAYOUT_OUT) / 1024))


if __name__ == '__main__':
    main()
