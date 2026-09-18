# -*- coding: utf-8 -*-
"""
extract_pdf.py — 《粵語（香港話）教程（修訂版）》PDF 提取流水线
1) 按目录解析 30 课页码范围（书页码 + 22 = PDF 页码，已用页脚 OCR 数字验证）
2) 渲染课文页为 JPEG（app/pages/）
3) 生成结构化清单 app/content/book.json（课程 → 页面 → 音轨）
仅做本地内容加工，供个人学习 App 使用。
"""
import pymupdf, json, os, re, sys

ROOT = r"D:/Code/cantonese-app"
PDF_PATH = os.path.join(ROOT, "粵語教程", "粵語（香港話）教程（修訂版）.pdf")
PAGES_DIR = os.path.join(ROOT, "app", "pages")
OUT_JSON = os.path.join(ROOT, "app", "content", "book.json")
OFFSET = 22          # 书页码 -> PDF 页码（1-based）
ZOOM = 110 / 72      # 110 dpi
JPEG_QUALITY = 62

# 手工校对后的课名（OCR 目录噪声已修正）
LESSON_TITLES = {
    1: "介紹", 2: "問候", 3: "打電話", 4: "約會", 5: "問路",
    6: "購物", 7: "交通", 8: "天氣", 9: "飲食", 10: "香港",
    11: "開戶口", 12: "買餸", 13: "外出旅遊", 14: "睇醫生", 15: "清潔香港",
    16: "搵學校", 17: "晨運", 18: "搵工跳槽", 19: "打「九九九」", 20: "香港話",
    21: "報紙", 22: "交通運輸", 23: "海洋公園", 24: "黃大仙", 25: "電視文化",
    26: "食在香港", 27: "「女人街」", 28: "「居者有其屋」", 29: "貪字變貧字", 30: "話説移民",
}
# 目录解析出的每课起始书页码
BOOK_STARTS = {
    1: 2, 2: 13, 3: 26, 4: 39, 5: 54, 6: 67, 7: 80, 8: 92, 9: 103, 10: 114,
    11: 128, 12: 139, 13: 150, 14: 161, 15: 173, 16: 184, 17: 196, 18: 209,
    19: 222, 20: 235, 21: 252, 22: 264, 23: 276, 24: 288, 25: 299, 26: 311,
    27: 323, 28: 335, 29: 346, 30: 358,
}
APPENDIX_BOOK = 372       # 附錄起始书页
CH0_PDF = (16, 23)        # 第0课（語音入門）：粵語語音系統 + 粵語常用字表
FRONT_PDF = (5, 15)       # 序 / 前言 / 目錄 / 每課學習重點（不配音轨）

def main():
    os.makedirs(PAGES_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)

    with open(os.path.join(ROOT, "prototype", "lessons.json"), encoding="utf-8") as f:
        audio = json.load(f)
    tracks_by_ch = {c["chapter"]: c["audioKeys"] for c in audio["chapters"]}

    pdf = pymupdf.open(PDF_PATH)
    jobs = []   # (pdf_index_1based, )
    def add_range(a, b):
        for p in range(a, b + 1):
            jobs.append(p)

    add_range(*FRONT_PDF)
    add_range(*CH0_PDF)
    for ch in range(1, 31):
        start_book = BOOK_STARTS[ch]
        end_book = (BOOK_STARTS[ch + 1] - 1) if ch < 30 else (APPENDIX_BOOK - 1)
        add_range(start_book + OFFSET, end_book + OFFSET)

    print("pages to render:", len(jobs))
    rendered = []
    mat = pymupdf.Matrix(ZOOM, ZOOM)
    for n, p1 in enumerate(jobs):
        page = pdf[p1 - 1]
        name = "p{:03d}.jpg".format(p1)
        path = os.path.join(PAGES_DIR, name)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        pix.pil_save(path, format="JPEG", quality=JPEG_QUALITY) if hasattr(pix, "pil_save") else pix.save(path, jpg_quality=JPEG_QUALITY)
        rendered.append(name)
        if (n + 1) % 50 == 0:
            print("rendered", n + 1, "/", len(jobs))

    # ---- 结构化清单 ----
    lessons = []
    def pdf_range(a, b):
        return ["p{:03d}.jpg".format(p) for p in range(a, b + 1)]

    lessons.append({
        "chapter": 0, "title": "語音入門", "subtitle": "粵語語音系統 · 粵語常用字表",
        "tracks": tracks_by_ch.get(0, []),
        "pages": pdf_range(*CH0_PDF),
    })
    for ch in range(1, 31):
        start_book = BOOK_STARTS[ch]
        end_book = (BOOK_STARTS[ch + 1] - 1) if ch < 30 else (APPENDIX_BOOK - 1)
        lessons.append({
            "chapter": ch, "title": LESSON_TITLES[ch], "subtitle": "第{}課".format(ch),
            "tracks": tracks_by_ch.get(ch, []),
            "pages": pdf_range(start_book + OFFSET, end_book + OFFSET),
        })

    front = {
        "chapter": -1, "title": "前言與目錄", "subtitle": "序 · 前言 · 每課學習重點",
        "tracks": [], "pages": pdf_range(*FRONT_PDF),
    }
    book = {
        "source": "粵語（香港話）教程（修訂版）（錄音掃碼即聽版）",
        "pdfOffset": OFFSET,
        "audioBaseUrl": "../粵語教程/",
        "sections": [front] + lessons,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(book, f, ensure_ascii=False, indent=1)
    total = sum(os.path.getsize(os.path.join(PAGES_DIR, x)) for x in rendered)
    print("DONE. lessons:", len(lessons) + 1, "| pages:", len(rendered),
          "| images total: {:.1f} MB".format(total / 1048576))

if __name__ == "__main__":
    sys.exit(main())
