# -*- coding: utf-8 -*-
"""生成 Android 原生各密度啟動圖示與啟動畫面。

背景：`@capacitor/assets` 在本機 npm 狀態不一致、裝不上，而它做的事其實很機械，
索性用 Pillow 直接產生，零外部依賴、結果可重現。

產出（android/app/src/main/res/）：
  values/ic_launcher_background.xml   品牌底色（自適應圖示背景層）
  mipmap-<density>/ic_launcher.png            傳統方形圖示  48/72/96/144/192
  mipmap-<density>/ic_launcher_round.png      圓形圖示      同上
  mipmap-<density>/ic_launcher_foreground.png 自適應前景層  108/162/216/324/432
  drawable*/splash.png                        啟動畫面（沿用原有各密度尺寸）

設計：品牌粉底 + 白色「粵」字。自適應前景按 108dp 畫布只保證中央 72dp 可見來留安全區。
"""
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "android", "app", "src", "main", "res")

PINK = (255, 143, 171)
CREAM = (255, 247, 238)
WHITE = (255, 255, 255)
GLYPH = "粵"

DENSITY = {"mdpi": 1.0, "hdpi": 1.5, "xhdpi": 2.0, "xxhdpi": 3.0, "xxxhdpi": 4.0}

FONTS = [
    ("C:/Windows/Fonts/msjhbd.ttc", 0),
    ("C:/Windows/Fonts/msjh.ttc", 0),
    ("C:/Windows/Fonts/msyhbd.ttc", 0),
    ("C:/Windows/Fonts/msyh.ttc", 0),
    ("C:/Windows/Fonts/simsun.ttc", 0),
]


def pick_font():
    for path, idx in FONTS:
        if not os.path.exists(path):
            continue
        try:
            ImageFont.truetype(path, 64, index=idx)
            return path, idx
        except Exception:
            continue
    raise RuntimeError("找不到可渲染「粵」的中文字型")


def glyph_layer(font_path, font_index, ch, target_h, color=WHITE):
    """渲染單字並裁到墨跡邊界後等比縮放 —— 視覺居中，而非字型度量居中。"""
    probe = 400
    f = ImageFont.truetype(font_path, probe, index=font_index)
    canvas = Image.new("RGBA", (probe * 2, probe * 2), (0, 0, 0, 0))
    ImageDraw.Draw(canvas).text((probe, probe), ch, font=f, fill=color + (255,), anchor="mm")
    bbox = canvas.getbbox()
    if not bbox:
        raise RuntimeError("字型無法渲染該字：%r" % ch)
    ink = canvas.crop(bbox)
    w = max(1, int(round(ink.width * target_h / ink.height)))
    return ink.resize((w, target_h), Image.LANCZOS)


def rounded_square(size, radius_ratio, bg, glyph_ratio, fp, fi):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(round(size * radius_ratio))
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=bg + (255,))
    g = glyph_layer(fp, fi, GLYPH, int(round(size * glyph_ratio)))
    img.paste(g, ((size - g.width) // 2, (size - g.height) // 2), g)
    return img


def circle_icon(size, bg, glyph_ratio, fp, fi, ss=4):
    """圓形圖示：用 4x 超取樣畫圓再縮小，避免鋸齒。"""
    big = size * ss
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse([0, 0, big - 1, big - 1], fill=bg + (255,))
    g = glyph_layer(fp, fi, GLYPH, int(round(big * glyph_ratio)))
    img.paste(g, ((big - g.width) // 2, (big - g.height) // 2), g)
    return img.resize((size, size), Image.LANCZOS)


def splash_img(w, h, fp, fi):
    """啟動畫面：米色底 + 置中品牌方塊。"""
    img = Image.new("RGB", (w, h), CREAM)
    d = ImageDraw.Draw(img)
    box = int(round(min(w, h) * 0.30))
    x0, y0 = (w - box) // 2, (h - box) // 2
    d.rounded_rectangle([x0, y0, x0 + box, y0 + box], radius=int(box * 0.24), fill=PINK)
    g = glyph_layer(fp, fi, GLYPH, int(box * 0.58))
    img.paste(g, ((w - g.width) // 2, (h - g.height) // 2), g)
    return img


def main():
    if not os.path.isdir(RES):
        print("找不到 Android res 目錄：", RES)
        return 1
    fp, fi = pick_font()
    print("字型：%s（index %d）" % (fp, fi))
    print()

    # 1) 自適應圖示背景色
    bg_xml = os.path.join(RES, "values", "ic_launcher_background.xml")
    if os.path.exists(bg_xml):
        s = open(bg_xml, encoding="utf-8").read()
        s2 = re.sub(r'(<color name="ic_launcher_background">)[^<]*(</color>)',
                    r"\g<1>#FF8FAB\g<2>", s)
        if s2 != s:
            open(bg_xml, "w", encoding="utf-8").write(s2)
            print("  values/ic_launcher_background.xml -> #FF8FAB")

    # 2) 各密度圖示
    print()
    for name, scale in DENSITY.items():
        d = os.path.join(RES, "mipmap-" + name)
        os.makedirs(d, exist_ok=True)

        legacy = int(round(48 * scale))
        rounded_square(legacy, 0.20, PINK, 0.60, fp, fi).save(
            os.path.join(d, "ic_launcher.png"), "PNG", optimize=True)
        circle_icon(legacy, PINK, 0.56, fp, fi).save(
            os.path.join(d, "ic_launcher_round.png"), "PNG", optimize=True)

        # 前景層：108dp 畫布。系統最少保證中央 66dp 直徑圓可見，
        # 內接正方形邊長 = 66/√2 ≈ 46.7dp → 取 0.44 畫布寬（47.5dp）剛好貼邊不切角。
        fgsz = int(round(108 * scale))
        fg = Image.new("RGBA", (fgsz, fgsz), (0, 0, 0, 0))
        g = glyph_layer(fp, fi, GLYPH, int(round(fgsz * 0.44)))
        fg.paste(g, ((fgsz - g.width) // 2, (fgsz - g.height) // 2), g)
        fg.save(os.path.join(d, "ic_launcher_foreground.png"), "PNG", optimize=True)

        print("  mipmap-%-9s legacy %3d  foreground %3d" % (name, legacy, fgsz))

    # 3) 啟動畫面（沿用原尺寸，只換設計）
    print()
    drawn = 0
    for entry in sorted(os.listdir(RES)):
        if not entry.startswith("drawable"):
            continue
        p = os.path.join(RES, entry, "splash.png")
        if not os.path.exists(p):
            continue
        w, h = Image.open(p).size
        splash_img(w, h, fp, fi).save(p, "PNG", optimize=True)
        drawn += 1
        print("  %-22s splash %dx%d" % (entry, w, h))
    print("\n完成：%d 個密度圖示 + %d 張啟動畫面" % (len(DENSITY), drawn))
    return 0


if __name__ == "__main__":
    sys.exit(main())
