# -*- coding: utf-8 -*-
"""
build_book.py — 一步重建 app/content/book.json（课程结构 + 识别文本 blocks 含表格）
自包含：不依赖旧的 book.json / 页面图。数据源 = 教材 PDF + prototype/lessons.json。
"""
import pymupdf, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_text import page_blocks

ROOT = r"D:/Code/cantonese-app"
PDF_PATH = os.path.join(ROOT, "粵語教程", "粵語（香港話）教程（修訂版）.pdf")
OUT = os.path.join(ROOT, "app", "content", "book.json")
OFFSET = 22

LESSON_TITLES = {
    1: "介紹", 2: "問候", 3: "打電話", 4: "約會", 5: "問路",
    6: "購物", 7: "交通", 8: "天氣", 9: "飲食", 10: "香港",
    11: "開戶口", 12: "買餸", 13: "外出旅遊", 14: "睇醫生", 15: "清潔香港",
    16: "搵學校", 17: "晨運", 18: "搵工跳槽", 19: "打「九九九」", 20: "香港話",
    21: "報紙", 22: "交通運輸", 23: "海洋公園", 24: "黃大仙", 25: "電視文化",
    26: "食在香港", 27: "「女人街」", 28: "「居者有其屋」", 29: "貪字變貧字", 30: "話説移民",
}
BOOK_STARTS = {
    1: 2, 2: 13, 3: 26, 4: 39, 5: 54, 6: 67, 7: 80, 8: 92, 9: 103, 10: 114,
    11: 128, 12: 139, 13: 150, 14: 161, 15: 173, 16: 184, 17: 196, 18: 209,
    19: 222, 20: 235, 21: 252, 22: 264, 23: 276, 24: 288, 25: 299, 26: 311,
    27: 323, 28: 335, 29: 346, 30: 358,
}
APPENDIX_BOOK = 372
CH0_PDF = (16, 23)
FRONT_PDF = (5, 15)

def main():
    with open(os.path.join(ROOT, "prototype", "lessons.json"), encoding="utf-8") as f:
        audio = json.load(f)
    tracks_by_ch = {c["chapter"]: c["audioKeys"] for c in audio["chapters"]}

    pdf = pymupdf.open(PDF_PATH)
    def build(ch, title, subtitle, tracks, a, b):
        blocks = []
        for p1 in range(a, b + 1):
            blocks.extend(page_blocks(pdf, p1))
        return {"chapter": ch, "title": title, "subtitle": subtitle,
                "tracks": tracks, "pageStart": a, "pageEnd": b, "blocks": blocks}

    sections = []
    sections.append(build(-1, "前言與目錄", "序 · 前言 · 每課學習重點", [], *FRONT_PDF))
    sections.append(build(0, "語音入門", "粵語語音系統 · 粵語常用字表", tracks_by_ch.get(0, []), *CH0_PDF))
    for ch in range(1, 31):
        s = BOOK_STARTS[ch]
        e = (BOOK_STARTS[ch + 1] - 1) if ch < 30 else (APPENDIX_BOOK - 1)
        sections.append(build(ch, LESSON_TITLES[ch], "第{}課".format(ch),
                              tracks_by_ch.get(ch, []), s + OFFSET, e + OFFSET))

    book = {
        "source": "粵語（香港話）教程（修訂版）（錄音掃碼即聽版）",
        "official": "https://www.jointpublishing.com/?p=16107/",
        "pdfOffset": OFFSET,
        "audioBaseUrl": "../粵語教程/",
        "sections": sections,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(book, f, ensure_ascii=False, separators=(',', ':'))
    ntab = sum(1 for s in sections for b in s["blocks"] if b["k"] == "table")
    print("DONE sections:", len(sections),
          "| blocks:", sum(len(s["blocks"]) for s in sections),
          "| tables:", ntab,
          "| {:.0f} KB".format(os.path.getsize(OUT) / 1024))

if __name__ == "__main__":
    main()
