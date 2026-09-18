#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
發音資產體檢：確保 App 講得出聲。

檢查三樣嘢
  1. app/content/char_audio.json 入面每個索引，對應嘅 MP3 真係存在
  2. tools/audio_manifest.json 嘅課程錄音（核心句／對話／詞彙）齊唔齊
  3. 有無「空殼檔」（體積細到明顯係合成失敗）

用法：python tools/verify_audio.py
"""
import json
import os
import sys

ROOT = r"D:/Code/cantonese-app"
CHAR_INDEX = os.path.join(ROOT, "app", "content", "char_audio.json")
CHARS_DIR = os.path.join(ROOT, "app", "audio", "chars")
MANIFEST = os.path.join(ROOT, "tools", "audio_manifest.json")
CLIPS_DIR = os.path.join(ROOT, "app", "audio")

MIN_BYTES = 700


def size_of(path):
    return os.path.getsize(path) if os.path.exists(path) else -1


def main():
    bad = []
    print("=" * 54)
    print(" 發音資產體檢")
    print("=" * 54)

    # ---- 1. 單字庫 ----
    if not os.path.exists(CHAR_INDEX):
        print("[X] 未有 char_audio.json，請先跑 tools/gen_char_audio.py")
        return 1
    doc = json.load(open(CHAR_INDEX, encoding="utf-8"))
    chars, meta = doc.get("chars", {}), doc.get("meta", {})
    uniq = set()
    for ch, e in chars.items():
        files = list((e.get("r") or {}).values())
        if e.get("d"):
            files.append(e["d"])
        for f in files:
            uniq.add(f)
    missing, thin = [], []
    for f in sorted(uniq):
        n = size_of(os.path.join(CHARS_DIR, f + ".mp3"))
        if n < 0:
            missing.append(f)
        elif n < MIN_BYTES:
            thin.append(f + " (%dB)" % n)
    tot = sum(os.path.getsize(os.path.join(CHARS_DIR, f + ".mp3"))
              for f in uniq if size_of(os.path.join(CHARS_DIR, f + ".mp3")) > 0)
    print("\n[1] 單字發音庫")
    print("    覆蓋漢字 : %d 個" % len(chars))
    print("    音檔數目 : %d 個（%.1f MB）" % (len(uniq), tot / 1048576))
    print("    音色設定 : %s  rate=%s" % (meta.get("voice", "?"), meta.get("rate", "?")))
    print("    同音替身 : %d 個（多音字借同音字發聲）" % len(meta.get("homophones") or {}))
    print("    缺失檔案 : %s" % (", ".join(missing[:10]) if missing else "無 ✓"))
    print("    可疑空殼 : %s" % (", ".join(thin[:10]) if thin else "無 ✓"))
    bad += missing

    # ---- 2. 課程錄音 ----
    print("\n[2] 課程錄音")
    if os.path.exists(MANIFEST):
        clips = json.load(open(MANIFEST, encoding="utf-8"))["clips"]
        cmiss, cthin = [], []
        for c in clips:
            n = size_of(os.path.join(CLIPS_DIR, c["id"] + ".mp3"))
            if n < 0:
                cmiss.append(c["id"])
            elif n < MIN_BYTES:
                cthin.append(c["id"])
        kinds = {}
        for c in clips:
            kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
        print("    索引 %d 段 %s" % (len(clips), kinds))
        print("    缺失檔案 : %s" % (", ".join(cmiss[:10]) if cmiss else "無 ✓"))
        print("    可疑空殼 : %s" % (", ".join(cthin[:10]) if cthin else "無 ✓"))
        bad += cmiss
    else:
        print("    [!] 未見 audio_manifest.json")

    # ---- 3. 課程點讀覆蓋率 ----
    print("\n[3] 課程點讀覆蓋率（模擬前端路由）")
    cur_path = os.path.join(ROOT, "app", "content", "curriculum.json")
    hm = meta.get("homophones") or {}
    if os.path.exists(cur_path):
        cur = json.load(open(cur_path, encoding="utf-8"))
        import re
        HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")

        def pick(ch, jp):
            e = chars.get(ch)
            if not e:
                return None
            if jp and e.get("r", {}).get(jp):
                return e["r"][jp]
            return e.get("d") or (list(e["r"].values())[0] if e.get("r") else None)

        hit = miss = 0
        miss_chars = {}
        sent_full = sent_local = 0
        dom_name = {d["id"]: d["name"] for d in cur.get("domains", [])}
        dom_stat = {}
        for L in cur["lessons"]:
            st = dom_stat.setdefault(L.get("domain", "?"), [0, 0])   # [句數, 全本地可讀]
            for group, key in ((L.get("core", []), "c"), (L.get("dialogue", []), "d"),
                               (L.get("vocab", []), "v")):
                for i, it in enumerate(group):
                    sent_full += 1
                    st[0] += 1
                    y = it.get("y", "")
                    cs = [c for c in y if HAN.match(c)]
                    syls = (it.get("p") or "").split()
                    if len(syls) != len(cs):
                        syls = []
                    ok_here = True
                    for k, c in enumerate(cs):
                        f = pick(c, syls[k] if syls else None)
                        if f and os.path.exists(os.path.join(CHARS_DIR, f + ".mp3")):
                            hit += 1
                        else:
                            miss += 1
                            ok_here = False
                            miss_chars[c] = miss_chars.get(c, 0) + 1
                    if ok_here:
                        sent_local += 1
                        st[1] += 1
        tot = hit + miss
        print("    逐字發音 : %d/%d 命中（%.1f%%）" % (hit, tot, 100.0 * hit / max(tot, 1)))
        print("    整句可讀 : %d/%d 句完全由本地音檔拼得出" % (sent_local, sent_full))
        print("    分領域覆蓋：")
        for did, (n_sent, n_ok) in dom_stat.items():
            print("      %-14s %4d 句  %4d 可讀  %s"
                  % (dom_name.get(did, did), n_sent, n_ok,
                     "✓" if n_ok == n_sent else "有 %d 句缺字" % (n_sent - n_ok)))
        if miss_chars:
            top = sorted(miss_chars.items(), key=lambda x: -x[1])[:8]
            print("    未覆蓋字 : %s" % "、".join("%s×%d" % (c, n) for c, n in top))
        print("    同音替身 : %s" % ("、".join("%s→%s" % (k, v) for k, v in list(hm.items())[:8]) or "無"))
    else:
        print("    [!] 未見 curriculum.json")

    # ---- 4. 目錄總覽 ----
    n_clip = len([f for f in os.listdir(CLIPS_DIR) if f.endswith(".mp3")]) \
        if os.path.isdir(CLIPS_DIR) else 0
    n_char = len([f for f in os.listdir(CHARS_DIR) if f.endswith(".mp3")]) \
        if os.path.isdir(CHARS_DIR) else 0
    print("\n[4] 磁碟實況")
    print("    app/audio/       %d 個 mp3" % n_clip)
    print("    app/audio/chars/ %d 個 mp3" % n_char)

    print("\n" + "=" * 54)
    if bad:
        print(" 結果：有 %d 個音檔缺失，需要重跑生成腳本" % len(bad))
    else:
        print(" 結果：全部齊備 ✓  點讀唔使靠系統粵語音色")
    print("=" * 54)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
