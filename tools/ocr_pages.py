# -*- coding: utf-8 -*-
"""
ocr_pages.py — 用 PP-OCRv6（RapidOCR，最新一代中文模型）重新识别全书页面
输出: tools/ocr_raw/pNNN.json  { n, w, h, dpi, items: [[box4, text, score], ...] }
支持断点续跑（已存在的页跳过）。坐标以像素计，pts = px / (dpi/72)。
"""
import os, sys, json, time, logging
import numpy as np, pymupdf
from PIL import Image
from io import BytesIO

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_book as bb

logging.disable(logging.INFO)
RAW_DIR = os.path.join(bb.ROOT, "tools", "ocr_raw")
DPI = 250                      # 约等于检测模型上限边长 2000px，质量/速度平衡


def page_list():
    pages = list(range(bb.FRONT_PDF[0], bb.FRONT_PDF[1] + 1))
    pages += list(range(bb.CH0_PDF[0], bb.CH0_PDF[1] + 1))
    for ch in range(1, 31):
        s = bb.BOOK_STARTS[ch] + bb.OFFSET
        e = ((bb.BOOK_STARTS[ch + 1] - 1) if ch < 30 else (bb.APPENDIX_BOOK - 1)) + bb.OFFSET
        pages += list(range(s, e + 1))
    return sorted(set(pages))


def main():
    from rapidocr import RapidOCR
    os.makedirs(RAW_DIR, exist_ok=True)
    engine = RapidOCR()
    pdf = pymupdf.open(bb.PDF_PATH)
    pages = page_list()
    todo = [p for p in pages if not os.path.exists(os.path.join(RAW_DIR, 'p%03d.json' % p))]
    print('pages total: %d | todo: %d' % (len(pages), len(todo)), flush=True)
    t_all = time.time()
    for k, p1 in enumerate(todo, 1):
        t0 = time.time()
        page = pdf[p1 - 1]
        img = np.asarray(Image.open(BytesIO(page.get_pixmap(dpi=DPI).tobytes('png'))).convert('RGB'))
        r = engine(img)
        items = []
        if r is not None and r.boxes is not None:
            for box, txt, sc in zip(r.boxes, r.txts, r.scores):
                items.append([[[round(float(x), 1), round(float(y), 1)] for x, y in box],
                              txt, round(float(sc), 3)])
        data = {'n': p1, 'w': round(page.rect.width, 1), 'h': round(page.rect.height, 1),
                'dpi': DPI, 'items': items}
        with open(os.path.join(RAW_DIR, 'p%03d.json' % p1), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
        if k % 10 == 0 or k == len(todo):
            el = time.time() - t_all
            print('[%d/%d] page %d | %.1fs/page | elapsed %.1f min | eta %.1f min'
                  % (k, len(todo), p1, el / k, el / 60, (len(todo) - k) * el / k / 60), flush=True)
    print('OCR DONE', flush=True)


if __name__ == '__main__':
    main()
