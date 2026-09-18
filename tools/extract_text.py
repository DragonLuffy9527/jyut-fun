# -*- coding: utf-8 -*-
"""
extract_text.py — 把 PDF OCR 文字层识别为结构化课文数据（含表格重建）
分类规则：
  - Times-Roman 西文行 (~11.3)   → py    粤语拼音行
  - HiddenHorzOCR 中文 >= 9.9    → yue   粤语句子
  - HiddenHorzOCR 中文 < 9.9     → man   普通話對譯
  - 栏目关键词 / 大字号          → h     栏目标题
  - 横向多列且相邻行对齐         → table 重建行列
输出: app/content/book.json（含 blocks，供 App 原生渲染）
"""
import pymupdf, json, os, re

ROOT = r"D:/Code/cantonese-app"
PDF_PATH = os.path.join(ROOT, "粵語教程", "粵語（香港話）教程（修訂版）.pdf")
BOOK_JSON = os.path.join(ROOT, "app", "content", "book.json")

SECTION_WORDS = ["課文", "補充語彙", "重點詞彙", "講解", "練習", "傳意項目", "粵語趣談",
                 "會話聆聽", "短文朗讀", "粵字辨認", "每課一句", "語音講解", "語法講解",
                 "普通話對譯", "補充練習", "聲母", "韻母", "聲調", "入聲", "拼音方案"]
HAN = re.compile(r'[\u4e00-\u9fff]')
LATIN = re.compile(r'[A-Za-z]')
TONE = re.compile(r'[A-Za-z]+[1-6]')
LETGRP = re.compile(r'[A-Za-z]+')
PYTOK = re.compile(r"[A-Za-z]+[1-6](?:(?:'|’|-)?[A-Za-z]*[1-6])*")
COL_TOL = 22          # 列对齐容差
GAP_MIN = 40          # 行内判定为多列的最小横向间隙
# 表格內的字母格：單聲母（b／p／m／f）、韻尾（-i／-ng）、帶括注聲母（z（j））
LATIN_CELL = re.compile(r"^-?[A-Za-z][A-Za-z'\-()（）\s]{0,13}$")
CELL_FIX = {'n-': '-u'}          # OCR 誤讀的韻尾格（原書為 -u）

# 本书的数字读音（按书内自创拼音方案，非标准 jyutping；源自书中「數目字」表）
NUM_PY = {'零': 'ling4', '一': 'yed1', '二': 'yi6', '三': 'sam1', '四': 'sei3',
          '五': 'ng5', '六': 'lug6', '七': 'ced1', '八': 'bad3', '九': 'geo2',
          '十': 'seb6', '廿': 'ya6', '卅': 'saa1', '百': 'baak3', '千': 'cin1',
          '萬': 'maan6', '兩': 'leo5'}
NUM_PY_INV = {v: k for k, v in NUM_PY.items()}
NUM_ORDER = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十',
             '廿', '卅', '百', '千', '萬', '兩']
# 高置信 OCR 纠错（仅收确定性错误：粤语特有字被误认，且误认字本书几乎不出现）
OCR_FIX = [('電語', '電話'),
           ('我地', '我哋'), ('你地', '你哋'), ('佢地', '佢哋'),
           ('佰', '佢'), ('嶓', '噃'), ('喏', '啱'),
           ('話條唔條', '係唔係'), ('唔該你溫', '唔該你搵')]

def clean_py(text):
    """清洗拼音行：剔除混入的汉字，只保留带声调数字的音节；碎裂严重则整行丢弃"""
    m = re.match(r'^\(\s*\d+\s*\)', text)
    prefix = m.group(0) + ' ' if m else ''
    body = text[m.end():] if m else text
    toks = TONE.findall(body)
    groups = LETGRP.findall(body.replace(' ', ''))
    if not toks:
        return None
    if len(toks) < 0.5 * max(1, len(groups)):
        return None                      # 碎片过多，丢弃避免误导
    return prefix + ' '.join(toks)

def make_units(text):
    """把「字+拼音」混行拆成 [汉字|None, 音节] 单元序列"""
    ms = list(PYTOK.finditer(text))
    if not ms:
        return None
    units, pos = [], 0
    for m in ms:
        han = ''.join(HAN.findall(text[pos:m.start()])).strip('：:、，,。.（）()「」-/—·+ ')
        units.append([han or None, m.group(0)])
        pos = m.end()
    return units

def numeral_fix(units):
    """全为数字时按书内读音校准，并补回 OCR 吞掉的数字；否则返回 None"""
    hans = [u[0] for u in units if u[0]]
    if not hans or not all(h in NUM_PY for h in hans):
        # 允许首单元带栏目标签前缀（如「數目字零」→ 零）
        if len(hans) >= 2 and hans[0][-1] in NUM_PY and all(h in NUM_PY for h in hans[1:]):
            units = list(units)
            for u in units:
                if u[0] == hans[0]:
                    u[0] = hans[0][-1]
                    break
        else:
            return None
    out = []
    for han, py in units:
        if han:
            out.append([han, NUM_PY[han]])
        else:
            h = NUM_PY_INV.get(py)
            if not h:
                return None
            out.append([h, py])
    return out

def add_vocab(out, pairs, pending=None):
    """追加词组芯片；纯数字词组按书的数字顺序排列（OCR 行序不可靠），并回收挂起的孤立数字音节"""
    if out and out[-1].get('k') == 'vocab':
        blk = out[-1]
        blk['pairs'].extend(pairs)
    else:
        blk = {'k': 'vocab', 'pairs': list(pairs)}
        out.append(blk)
    if all(h in NUM_ORDER for h, _ in blk['pairs']):
        for py in list(pending or []):
            h = NUM_PY_INV.get(py)
            if h:
                blk['pairs'].append([h, py])
                pending.remove(py)
        blk['pairs'].sort(key=lambda hp: NUM_ORDER.index(hp[0]))

def make_pairs(text):
    """「字+拼音」混排行 → 词组配对；数字序列（含跨行碎片）按书内读音校准"""
    units = make_units(text)
    if not units:
        return None
    pr = numeral_fix(units)
    if pr:
        return pr
    pairs = [u for u in units if u[0]]
    return pairs if len(pairs) >= 3 else None

def clean(s):
    s = s.replace('\u200b', '').replace('\uf0b7', '').replace('\uf0d8', '')
    s = s.replace('｀｀', '「').replace("''", '」')
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def classify(text, size, ref=None):
    """ref = 頁內正文基準字號；給定時用它區分正文/對譯/標題（比絕對字號穩健）"""
    n = len(text)
    if n == 0 or re.fullmatch(r'[\d\s]{1,5}', text):
        return None
    han_n = len(HAN.findall(text))
    lat_n = len(LATIN.findall(text))
    tone_n = len(TONE.findall(text))
    if n <= 1 and han_n == 0:
        return None
    if any(text.startswith(w) and n <= len(w) + 2 for w in SECTION_WORDS) and han_n >= 2:
        return 'h'
    if n >= 13 and han_n == 0 and size >= 13:
        return 'h'
    if han_n == 0:
        if tone_n >= 2:
            return 'py'
        if lat_n >= 3 and lat_n / max(n, 1) > 0.55:
            return 'py'
        if lat_n >= 2:
            return 'p'
        return None
    if ref:
        if size >= ref * 1.4 and len(text) <= 16:
            return 'h'                     # 明顯大於正文 → 標題
        return 'yue' if size >= ref * 0.92 else 'man'
    # 含汉字：拼音音节占绝对多数才视作被污染的拼音行，否则一律按正文处理
    if tone_n >= 3 and tone_n > han_n:
        return 'py'
    return 'yue' if size >= 9.9 else 'man'

def page_lines(pdf, p1):
    """返回 [(y, spans)]，spans = [(x0, x1, text, size)] 按 x 排序"""
    d = pdf[p1 - 1].get_text('dict')
    lines = {}
    for b in d['blocks']:
        if b['type'] != 0:
            continue
        for l in b['lines']:
            spans = []
            for s in l['spans']:
                t = s['text'].strip()
                if t:
                    spans.append([s['bbox'][0], s['bbox'][2], t, s['size']])
            if not spans:
                continue
            spans.sort(key=lambda s: s[0])
            y = round(l['bbox'][1] / 3)
            lines.setdefault(y, []).extend(spans)
    out = []
    for y in sorted(lines):
        spans = sorted(lines[y], key=lambda s: s[0])
        out.append((y, spans))
    return out

def row_text(spans):
    return ' '.join(s[2] for s in spans)

def is_multi_col(spans):
    """行内是否存在足够大的横向间隙（>=2 个有效单元格）"""
    if len(spans) < 2:
        return False
    good = 0
    for a, b in zip(spans, spans[1:]):
        if b[0] - a[1] > GAP_MIN:
            good += 1
    valid_cells = sum(1 for s in spans if len(HAN.findall(s[2])) >= 1 or len(LATIN.findall(s[2])) >= 2)
    return good >= 1 and valid_cells >= 2

def make_table(group):
    """group: 连续多列行的 spans 列表 → 聚类列坐标，输出行列矩阵"""
    xs = sorted(x for spans in group for (x, x1, t, sz) in spans)
    cols = []
    for x in xs:
        if not cols or x - cols[-1] > COL_TOL:
            cols.append(x)
    rows = []
    for spans in group:
        row = [''] * len(cols)
        for (x, x1, t, sz) in spans:
            ci = min(range(len(cols)), key=lambda i: abs(cols[i] - x))
            row[ci] = (row[ci] + ' ' + t).strip() if row[ci] else t
        rows.append([clean(c) for c in row])
    ncol = max(len(r) for r in rows)
    rows = [r + [''] * (ncol - len(r)) for r in rows]
    return {'k': 'table', 'rows': rows}

def page_blocks(pdf, p1):
    lines = page_lines(pdf, p1)
    out = []
    pending = []                         # 本页挂起的孤立数字音节（OCR 碎片）
    i = 0
    while i < len(lines):
        y, spans = lines[i]
        if is_multi_col(spans):
            j = i
            group = [spans]
            while j + 1 < len(lines) and is_multi_col(lines[j + 1][1]):
                j += 1
                group.append(lines[j][1])
            if len(group) >= 2:
                out.append(make_table(group))
                i = j + 1
                continue
        text = clean(row_text(spans))
        k = classify(text, max(s[3] for s in spans))
        if k is None:
            i += 1
            continue
        if k == 'py':
            text = clean_py(text)
            if text is None:
                i += 1
                continue
        elif k == 'p':
            text = clean_py(text)            # 纯噪声碎片（如 .::.yi6）在此被丢弃
            toks1 = TONE.findall(text or '')
            if text is None or len(toks1) < 2:
                # 孤立数字音节先挂起，稍后由数字词组块回收（如 .::.yi6 → 二 yi6）
                if len(toks1) == 1 and toks1[0] in NUM_PY_INV:
                    pending.append(toks1[0])
                i += 1
                continue
        elif k in ('yue', 'man'):
            for a, b in OCR_FIX:
                text = text.replace(a, b)
            pr = make_pairs(text)            # 「字+拼音」混排行 → 词组芯片
            if pr:
                add_vocab(out, pr, pending)
                i += 1
                continue
            # 数字续行：上一块是数字词组、本行是数字碎片 → 并回去（如 九geo2 + seb6 → 九 十）
            if out and out[-1].get('k') == 'vocab' and all(h in NUM_ORDER for h, _ in out[-1]['pairs']):
                units = make_units(text)
                pr2 = numeral_fix(units) if units else None
                if pr2:
                    add_vocab(out, pr2, pending)
                    i += 1
                    continue
        if out and out[-1].get('k') == k and k == 'p':
            out[-1]['s'] += ' ' + text
        else:
            out.append({'k': k, 's': text})
        i += 1
    return out

def main():
    with open(BOOK_JSON, encoding='utf-8') as f:
        book = json.load(f)
    pdf = pymupdf.open(PDF_PATH)
    total_tables = 0
    for sec in book['sections']:
        blocks = []
        for fname in sec.get('pages', []):
            p1 = int(re.match(r'p(\d+)\.jpg', fname).group(1))
            blocks.extend(page_blocks(pdf, p1))
        sec['blocks'] = blocks
        sec.pop('pages', None)
        ntab = sum(1 for b in blocks if b['k'] == 'table')
        total_tables += ntab
        print('ch{:<3} blocks: {:<5} tables: {}'.format(sec['chapter'], len(blocks), ntab))
    with open(BOOK_JSON, 'w', encoding='utf-8') as f:
        json.dump(book, f, ensure_ascii=False, separators=(',', ':'))
    print('DONE book.json: {:.0f} KB | tables total: {}'.format(os.path.getsize(BOOK_JSON) / 1024, total_tables))

if __name__ == '__main__':
    main()
