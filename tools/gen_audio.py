#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
用 edge-tts 嘅粵語神經音色，為課程每個語句生成 MP3。

音色分配：
  A 角色 → zh-HK-HiuMaanNeural（女）
  B 角色 → zh-HK-WanLungNeural（男）
  C 角色 → zh-HK-HiuGaaiNeural（女）
  核心句／詞彙 → HiuMaan（清晰、慢速示範）
  完整對話 → 由逐句音檔拼接而成（保留男女對答）

特性：併發下載、斷點續跑（已存在且非空嘅檔案會跳過）。
"""
import asyncio
import json
import os
import sys

RATE_LIMIT = 6           # 併發數
ROOT = r"D:/Code/cantonese-app"
MANIFEST = os.path.join(ROOT, "tools", "audio_manifest.json")
OUT_DIR = os.path.join(ROOT, "app", "audio")

V_A = "zh-HK-HiuMaanNeural"     # 女
V_B = "zh-HK-WanLungNeural"     # 男
V_C = "zh-HK-HiuGaaiNeural"     # 女（另一把聲）
V_MAIN = "zh-HK-HiuMaanNeural"

RATE_DLG = "-10%"
RATE_WORD = "-18%"


def voice_for(clip):
    kind = clip["kind"]
    if kind == "dlg":
        return {"A": V_A, "B": V_B, "C": V_C}.get(clip.get("sp"), V_A)
    return V_MAIN


def rate_for(clip):
    return RATE_WORD if clip["kind"] == "vocab" else RATE_DLG


async def synth(edge_tts, sem, clip, done, fail):
    cid = clip["id"]
    dst = os.path.join(OUT_DIR, cid + ".mp3")
    if os.path.exists(dst) and os.path.getsize(dst) > 1200:
        done.append(cid)
        return
    async with sem:
        for attempt in (1, 2, 3):
            try:
                c = edge_tts.Communicate(clip["text"], voice_for(clip),
                                         rate=rate_for(clip))
                await c.save(dst)
                if os.path.getsize(dst) > 1200:
                    done.append(cid)
                    return
            except Exception as e:
                if attempt == 3:
                    fail.append((cid, str(e)[:70]))
                else:
                    await asyncio.sleep(1.2 * attempt)


def concat(full_id, parts):
    """把逐句 MP3 併成完整對話（edge-tts 輸出參數一致，可直接位元組拼接）"""
    dst = os.path.join(OUT_DIR, full_id + ".mp3")
    if os.path.exists(dst) and os.path.getsize(dst) > 1200:
        return True
    buf = bytearray()
    for p in parts:
        fp = os.path.join(OUT_DIR, p + ".mp3")
        if not os.path.exists(fp):
            return False
        with open(fp, "rb") as f:
            buf += f.read()
    if not buf:
        return False
    with open(dst, "wb") as f:
        f.write(buf)
    return True


async def main():
    import edge_tts
    os.makedirs(OUT_DIR, exist_ok=True)
    clips = json.load(open(MANIFEST, encoding="utf-8"))["clips"]
    speech = [c for c in clips if c["kind"] != "dlgFull"]
    fulls = [c for c in clips if c["kind"] == "dlgFull"]

    print("clips total %d | speech %d | full-dialogue %d"
          % (len(clips), len(speech), len(fulls)))

    sem = asyncio.Semaphore(RATE_LIMIT)
    done, fail = [], []
    CHUNK = 40
    for i in range(0, len(speech), CHUNK):
        await asyncio.gather(*[synth(edge_tts, sem, c, done, fail)
                               for c in speech[i:i + CHUNK]])
        print("  progress %d/%d ok (fail %d)" % (min(i + CHUNK, len(speech)),
                                                 len(speech), len(fail)))

    ok_full = 0
    for f in fulls:
        base = f["id"][:-3]                       # life-05-df -> life-05
        n = sum(1 for c in speech if c["kind"] == "dlg"
                and c["id"].startswith(base + "-d"))
        parts = ["%s-d%d" % (base, k) for k in range(1, n + 1)]
        if concat(f["id"], parts):
            ok_full += 1

    total_bytes = sum(os.path.getsize(os.path.join(OUT_DIR, x))
                      for x in os.listdir(OUT_DIR) if x.endswith(".mp3"))
    print("DONE | speech %d | full %d/%d | files %d | %.1f MB"
          % (len(done), ok_full, len(fulls),
             len([x for x in os.listdir(OUT_DIR) if x.endswith('.mp3')]),
             total_bytes / 1048576))
    if fail:
        print("[!] failed %d:" % len(fail))
        for cid, err in fail[:20]:
            print("   ", cid, err)


if __name__ == "__main__":
    asyncio.run(main())
