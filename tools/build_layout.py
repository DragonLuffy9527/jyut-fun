# -*- coding: utf-8 -*-
"""
build_layout.py — 生成「原版式」版面数据 app/content/layout.json
不展示原版图像：只取 OCR 文字层每行的坐标 / 字号 / 类型，
App 端按原页面版式（分栏、缩进、对齐、字号层级）还原排版。

输出结构（精简键名以控制体积）：
{ "source":…, "sections":[ { "chapter":1, "title":"介紹",
    "pages":[ { "n":24, "w":595.0, "h":842.0,
                "lines":[ {"x":72.0,"y":300.5,"w":210.0,"s":11.3,"k":"py","t":"Da2 din6 wa2"} ] } ] } ] }
"""
import pymupdf, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_text import (PDF_PATH, HAN, TONE, classify, clean, clean_py, OCR_FIX)
import build_book as bb

OUT = os.path.join(bb.ROOT, "app", "content", "layout.json")
ROW_TOL = 3.0        # 同一视觉行的 y 容差（pt）


def page_rows(pdf, p1):
    """抽取页内文本行，保留原始坐标；同一视觉行合并"""
    d = pdf[p1 - 1].get_text('dict')
    rows = []
    for b in d['blocks']:
        if b['type'] != 0:
            continue
        for l in b['lines']:
            spans = [[s['bbox'][0], s['bbox'][2], s['text'].strip(), s['size']]
                     for s in l['spans'] if s['text'].strip()]
            if spans:
                rows.append({'y': l['bbox'][1], 'y1': l['bbox'][3], 'spans': spans})
    rows.sort(key=lambda r: (r['y'], min(s[0] for s in r['spans'])))
    merged = []
    for r in rows:
        if merged and abs(r['y'] - merged[-1]['y']) < ROW_TOL:
            merged[-1]['spans'].extend(r['spans'])
            merged[-1]['y1'] = max(merged[-1]['y1'], r['y1'])
        else:
            merged.append(r)
    return merged


def page_layout(pdf, p1):
    page = pdf[p1 - 1]
    out = []
    for r in page_rows(pdf, p1):
        spans = sorted(r['spans'], key=lambda s: s[0])
        text = clean(' '.join(s[2] for s in spans))
        size = max(s[3] for s in spans)
        k = classify(text, size)
        if k is None:
            continue
        if k in ('py', 'p'):
            text = clean_py(text)
            if not text or (k == 'p' and len(TONE.findall(text)) < 2):
                continue
        elif k in ('yue', 'man'):
            for a, b in OCR_FIX:
                text = text.replace(a, b)
        x0 = min(s[0] for s in spans)
        x1 = max(s[1] for s in spans)
        out.append({'x': round(x0, 1), 'y': round(r['y'], 1),
                    'w': round(x1 - x0, 1), 's': round(size, 1),
                    'k': k, 't': text})
    return {'n': p1, 'w': round(page.rect.width, 1), 'h': round(page.rect.height, 1),
            'lines': out}


def main():
    pdf = pymupdf.open(PDF_PATH)
    sections = []

    def build(ch, title, a, b):
        pages = [page_layout(pdf, p) for p in range(a, b + 1)]
        pages = [p for p in pages if p['lines']]
        sections.append({'chapter': ch, 'title': title, 'pages': pages})

    build(-1, '前言與目錄', *bb.FRONT_PDF)
    build(0, '語音入門', *bb.CH0_PDF)
    for ch in range(1, 31):
        s = bb.BOOK_STARTS[ch]
        e = (bb.BOOK_STARTS[ch + 1] - 1) if ch < 30 else (bb.APPENDIX_BOOK - 1)
        build(ch, bb.LESSON_TITLES[ch], s + bb.OFFSET, e + bb.OFFSET)

    data = {'source': '粵語（香港話）教程（修訂版）', 'sections': sections}
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    npg = sum(len(s['pages']) for s in sections)
    nln = sum(len(p['lines']) for s in sections for p in s['pages'])
    print('DONE sections:', len(sections), '| pages:', npg, '| lines:', nln,
          '| {:.0f} KB'.format(os.path.getsize(OUT) / 1024))


if __name__ == '__main__':
    main()
