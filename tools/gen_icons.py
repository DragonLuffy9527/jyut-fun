# -*- coding: utf-8 -*-
"""生成 PWA / 應用程式圖示與啟動畫面。

輸出：
  app/icons/icon-180.png            iOS apple-touch-icon
  app/icons/icon-192.png            PWA / Android
  app/icons/icon-512.png            PWA / Android
  app/icons/icon-maskable-512.png   Android 自適應圖示（安全區縮放）
  app/icons/icon-1024.png           商店素材 / Capacitor 來源
  resources/icon.png                @capacitor/assets 來源
  resources/splash.png              @capacitor/assets 啟動畫面來源

設計：品牌粉底 + 白色「粵」字，全出血方形（交由各平台自行遮罩）。
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON_DIR = os.path.join(ROOT, "app", "icons")
RES_DIR = os.path.join(ROOT, "resources")

PINK = (255, 143, 171)
PINK_DEEP = (229, 106, 140)
CREAM = (255, 247, 238)
WHITE = (255, 255, 255)
GLYPH = "粵"

FONTS = [
    ("C:/Windows/Fonts/msjhbd.ttc", 0),   # 微軟正黑體 Bold（繁體）
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
    """把單字渲染成透明底圖，裁到實際墨跡邊界後等比縮放到指定高度。

    這樣是「視覺居中」而非「字型度量居中」——CJK 字符的墨跡通常偏下，
    直接用 anchor='mm' 會讓字看起來偏高。
    """
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


def icon(size, glyph_ratio, font_path, font_index, bg=PINK):
    img = Image.new("RGB", (size, size), bg)
    g = glyph_layer(font_path, font_index, GLYPH, int(round(size * glyph_ratio)))
    img.paste(g, ((size - g.width) // 2, (size - g.height) // 2), g)
    return img


def splash(size, font_path, font_index):
    """啟動畫面：米色底 + 置中品牌方塊。"""
    img = Image.new("RGB", (size, size), CREAM)
    d = ImageDraw.Draw(img)
    box = int(size * 0.26)
    x0 = (size - box) // 2
    y0 = (size - box) // 2
    d.rounded_rectangle([x0, y0, x0 + box, y0 + box], radius=int(box * 0.22), fill=PINK)
    g = glyph_layer(font_path, font_index, GLYPH, int(box * 0.60))
    img.paste(g, ((size - g.width) // 2, (size - g.height) // 2), g)
    return img


def adaptive_pair(size, font_path, font_index):
    """Android 自適應圖示的前景／背景分層。

    前景層是 108dp 畫布，系統只保證中央 72dp（≈66.7%）安全區可見，
    所以字形要縮到安全區之內，否則圓形遮罩會切到筆畫。
    """
    fg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    g = glyph_layer(font_path, font_index, GLYPH, int(round(size * 0.40)))
    fg.paste(g, ((size - g.width) // 2, (size - g.height) // 2), g)
    bg = Image.new("RGB", (size, size), PINK)
    return fg, bg


def main():
    os.makedirs(ICON_DIR, exist_ok=True)
    os.makedirs(RES_DIR, exist_ok=True)
    fp, fi = pick_font()
    print("字型：%s（index %d）" % (fp, fi))

    jobs = [
        (os.path.join(ICON_DIR, "icon-180.png"), 180, 0.60),
        (os.path.join(ICON_DIR, "icon-192.png"), 192, 0.60),
        (os.path.join(ICON_DIR, "icon-512.png"), 512, 0.60),
        (os.path.join(ICON_DIR, "icon-1024.png"), 1024, 0.60),
        (os.path.join(ICON_DIR, "icon-maskable-512.png"), 512, 0.42),
        (os.path.join(RES_DIR, "icon.png"), 1024, 0.60),
    ]
    for path, size, ratio in jobs:
        img = icon(size, ratio, fp, fi)
        img.save(path, "PNG", optimize=True)
        print("  %-42s %dx%d" % (os.path.relpath(path, ROOT).replace("\\", "/"), size, size))

    sp = splash(2732, fp, fi)
    sp_path = os.path.join(RES_DIR, "splash.png")
    sp.save(sp_path, "PNG", optimize=True)
    print("  %-42s 2732x2732" % "resources/splash.png")

    # Android 自適應圖示分層（供 @capacitor/assets 產生全密度 mipmap）
    fg, bg = adaptive_pair(1024, fp, fi)
    fg.save(os.path.join(RES_DIR, "icon-foreground.png"), "PNG", optimize=True)
    bg.save(os.path.join(RES_DIR, "icon-background.png"), "PNG", optimize=True)
    print("  %-42s 1024x1024" % "resources/icon-foreground.png")
    print("  %-42s 1024x1024" % "resources/icon-background.png")

    total = sum(
        os.path.getsize(os.path.join(ICON_DIR, f)) for f in os.listdir(ICON_DIR)
    )
    print("\n圖示合計 %.1f KB" % (total / 1024))


if __name__ == "__main__":
    main()
