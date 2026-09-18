#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
构建课程数据：合并四个领域 JSON → 用 ToJyutping（基於 rime-cantonese 語料）
自動生成權威粵拼 → 輸出 app/content/curriculum.json 及音頻清單。

設計原則：
  1. 粵拼一律由權威數據庫生成，唔靠人手打（避免誤導學習者）。
  2. 若作者已填 p 欄位，會同生成結果比對，列出差異供人工覆核。
  3. 個別多音字／口語讀音如有需要，可用 OVERRIDES 精準覆蓋。
"""
import json
import os
import re
import sys

ROOT = r"D:/Code/cantonese-app"
SRC_DIR = os.path.join(ROOT, "tools", "curriculum")
OUT = os.path.join(ROOT, "app", "content", "curriculum.json")
MANIFEST = os.path.join(ROOT, "tools", "audio_manifest.json")

DOMAIN_FILES = ["basic.json", "life.json", "study.json", "work.json",
                "construction.json", "medical.json"]

# 詞級讀音覆蓋：ToJyutping 句級轉換喺呢幾個詞上出錯，用雙詞庫（ToJyutping + pycantonese）
# 交叉驗證後確定正確讀音。key = 詞，value = 逐字讀音。
# 註：爸爸 baa4 baa1、媽媽 maa4 maa1、阿爸 aa3 baa4 經兩個獨立詞庫確認係真實變調，
#     唔屬於錯誤，故不覆蓋。
WORD_OVERRIDES = {
    "喺度": ["hai2", "dou6"],     # ToJyutping 句級誤判為 dok6
    "轉左": ["zyun3", "zo2"],     # ToJyutping 誤判為 zyun2，與「轉車 zyun3 ce1」不一致
    "轉右": ["zyun3", "jau6"],
    "轉介": ["zyun3", "gaai3"],   # 同上：轉工／轉校／轉行 兩個詞庫都係 zyun3
    "天秤": ["tin1", "cing3"],    # 塔式起重機嘅俗稱，唔係「天秤座」嘅 ping4
}

_toned = None


def jyutping(text):
    """漢字 → 粵拼（音節以空格分隔，忽略標點）；支援詞級覆蓋"""
    global _toned
    if _toned is None:
        from ToJyutping import get_jyutping_list
        _toned = get_jyutping_list
    pairs = _toned(text)
    chars = "".join(c for c, _ in pairs)
    syls = [jp for _, jp in pairs]
    for word, readings in WORD_OVERRIDES.items():
        start = 0
        while True:
            j = chars.find(word, start)
            if j < 0:
                break
            for k, r in enumerate(readings):
                syls[j + k] = r
            start = j + len(word)
    return " ".join(s for s in syls if s)


def fill(node, path, diffs, field="p"):
    """為 node 補上／校正 p 欄位；作者已填嘅值只用於比對，最終一律採用詞庫結果"""
    if node is None:
        return False
    text = node.get("y") or ""
    if not text:
        return False
    want = jyutping(text)
    have = node.get(field)
    if have and _norm(have) != _norm(want):
        diffs.append((path, text, have, want))
    node[field] = want
    return True


def _norm(s):
    return re.sub(r"[\s\-']", "", s.lower())


def main():
    domains = []
    lessons = []
    diffs = []
    manifest = []

    for fn in DOMAIN_FILES:
        p = os.path.join(SRC_DIR, fn)
        d = json.load(open(p, encoding="utf-8"))
        domains.append({
            "id": d["domain"], "name": d["name"],
            "emoji": d["emoji"], "color": d["color"], "desc": d["desc"],
        })
        for L in d["lessons"]:
            lid = L["id"]
            L["domain"] = d["domain"]
            clips = []

            for i, c in enumerate(L["core"], 1):
                fill(c, f'{lid}.core[{i}]', diffs)
                clips.append({"id": f"{lid}-c{i}", "text": c["y"], "kind": "core"})

            for i, t in enumerate(L["dialogue"], 1):
                fill(t, f'{lid}.dlg[{i}]', diffs)
                clips.append({"id": f"{lid}-d{i}", "text": t["y"], "kind": "dlg",
                              "sp": t["s"]})

            for i, v in enumerate(L["vocab"], 1):
                fill(v, f'{lid}.vocab[{i}]', diffs)
                clips.append({"id": f"{lid}-v{i}", "text": v["y"], "kind": "vocab"})

            # 完整對話（單一音檔，方便「聽成段」）
            L["dialogueText"] = "".join(t["y"] for t in L["dialogue"])
            clips.append({"id": f"{lid}-df", "text": L["dialogueText"], "kind": "dlgFull"})

            L["clips"] = [c["id"] for c in clips]
            manifest.extend(clips)
            lessons.append(L)

    data = {
        "meta": {
            "name": "粵.fun",
            "version": "1.0",
            "source": "原創課程內容，粵拼由 rime-cantonese 語料庫自動標註",
            "domains": len(domains),
            "lessons": len(lessons),
        },
        "domains": domains,
        "lessons": lessons,
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, separators=(",", ":"))
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump({"clips": manifest}, f, ensure_ascii=False, indent=1)

    n_core = sum(len(L["core"]) for L in lessons)
    n_dlg = sum(len(L["dialogue"]) for L in lessons)
    n_voc = sum(len(L["vocab"]) for L in lessons)
    print("DONE | domains %d | lessons %d" % (len(domains), len(lessons)))
    print("     | core %d | dialogue %d | vocab %d | clips %d"
          % (n_core, n_dlg, n_voc, len(manifest)))
    print("     | curriculum.json %.0f KB | manifest %.0f KB"
          % (os.path.getsize(OUT) / 1024, os.path.getsize(MANIFEST) / 1024))

    if diffs:
        print("\n[!] 手寫粵拼 vs 數據庫 — 共 %d 處差異（已採用數據庫版本）:" % len(diffs))
        for path, text, have, want in diffs[:40]:
            print("   %-22s %-14s %-22s -> %s" % (path, text, have, want))
        if len(diffs) > 40:
            print("   ... 其餘 %d 處" % (len(diffs) - 40))
    else:
        print("\n[OK] 手寫粵拼同數據庫完全一致")


if __name__ == "__main__":
    main()
