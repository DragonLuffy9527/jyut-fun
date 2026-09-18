# -*- coding: utf-8 -*-
"""產生商店上架素材：Google Play 宣傳圖（feature graphic）＋ 商店圖示。

產出：
  store/feature-graphic-1024x500.png   Play 必填宣傳圖
  store/app-icon-512.png               Play 必填商店圖示（由 app/icons 複製）
  store/hi-res-icon-1024.png           App Store 用 1024 圖示（不可有透明）

設計沿用 App 的暖色系（米底 + 品牌粉），與截圖成套。
"""
import os
import shutil
import sys

from PIL import Image, ImageDraw, ImageFont

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.path.join(ROOT, "store")
ICONS = os.path.join(ROOT, "app", "icons")

PINK = (255, 143, 171)
PINK_DEEP = (229, 106, 140)
CREAM = (255, 247, 238)
CREAM2 = (255, 233, 239)
INK = (61, 50, 46)
MUTED = (138, 120, 112)
WHITE = (255, 255, 255)

BOLD = "C:/Windows/Fonts/msjhbd.ttc"
REG = "C:/Windows/Fonts/msjh.ttc"
GLYPH = "粵"


def font(path, size, index=0):
    return ImageFont.truetype(path, size, index=index)


def glyph_layer(ch, target_h, color=WHITE, path=BOLD):
    probe = 400
    f = font(path, probe)
    canvas = Image.new("RGBA", (probe * 2, probe * 2), (0, 0, 0, 0))
    ImageDraw.Draw(canvas).text((probe, probe), ch, font=f, fill=color + (255,), anchor="mm")
    bbox = canvas.getbbox()
    if not bbox:
        raise RuntimeError("字型無法渲染 " + ch)
    ink = canvas.crop(bbox)
    w = max(1, int(round(ink.width * target_h / ink.height)))
    return ink.resize((w, target_h), Image.LANCZOS)


def vertical_gradient(w, h, c1, c2):
    img = Image.new("RGB", (w, h), c1)
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(h - 1, 1)
        d.line([(0, y), (w, y)], fill=tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)))
    return img


def feature_graphic():
    W, H = 1024, 500
    img = vertical_gradient(W, H, CREAM, CREAM2).convert("RGBA")
    d = ImageDraw.Draw(img, "RGBA")

    # 裝飾：只保留兩團柔和色塊，加減法比堆元素安全
    d.ellipse([W - 300, -140, W + 120, 280], fill=(255, 143, 171, 40))
    d.ellipse([-120, H - 220, 200, H + 100], fill=(155, 140, 219, 34))
    d.ellipse([W - 120, H - 150, W + 40, H + 40], fill=(255, 143, 171, 30))

    # 品牌方塊
    box, bx, by = 150, 74, 128
    d.rounded_rectangle([bx, by, bx + box, by + box], radius=int(box * 0.24), fill=PINK + (255,))
    g = glyph_layer(GLYPH, int(box * 0.60))
    img.paste(g, (bx + (box - g.width) // 2, by + (box - g.height) // 2), g)

    tx = bx + box + 44
    d.text((tx, 132), "粵.fun", font=font(BOLD, 88), fill=INK)
    d.text((tx + 4, 244), "場景粵語學習", font=font(BOLD, 40), fill=PINK_DEEP)
    d.text((tx + 4, 306), "六大板塊 66 課 · 香港建築業 · 香港醫療業",
           font=font(REG, 25), fill=INK)
    d.text((tx + 4, 344), "3311 段粵語配音　完全離線　即點即讀",
           font=font(REG, 25), fill=MUTED)

    out = os.path.join(STORE, "feature-graphic-1024x500.png")
    img.convert("RGB").save(out, "PNG", optimize=True)
    return out


def main():
    os.makedirs(STORE, exist_ok=True)
    print("宣傳圖：", os.path.relpath(feature_graphic(), ROOT).replace("\\", "/"))

    pairs = [("icon-512.png", "app-icon-512.png"),
             ("icon-1024.png", "hi-res-icon-1024.png")]
    for src, dst in pairs:
        s = os.path.join(ICONS, src)
        if os.path.exists(s):
            shutil.copy(s, os.path.join(STORE, dst))
            im = Image.open(s)
            print("  %-26s ← %s  %dx%d %s" % (dst, src, im.width, im.height, im.mode))
    print("\n商店素材目錄：", os.path.relpath(STORE, ROOT).replace("\\", "/"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
