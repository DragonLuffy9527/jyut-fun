#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
單字發音庫生成器 —— 令「點讀單字」徹底唔使靠系統粵語音色。

背景：瀏覽器 Web Speech API 要靠作業系統裝咗粵語音色先讀得準，
      Android / 部分 Windows / 多數桌面瀏覽器都無裝 → 點讀直接失效。
解法：事先用 edge-tts 嘅粵語神經音色，為課程每一個漢字生成 MP3，
     前端點字嗰陣直接播本地檔，音色缺失問題就唔再存在。

生成策略（三層正確性保證）
  1. 由 curriculum.json 對齊「漢字 ↔ 粵拼」，拎到每個字喺課程中嘅真實讀音
  2. 掃 CJK 建「讀音 → 單音常用字」反查表（單音字 = 只有一個讀音，唔會讀錯）
  3. 合成時：
       單音字        → 直接合成自己
       多音字        → 用該讀音嘅「同音單音常用字」發聲
                      例：行(hong4) 用「航」、行(haang4) 用返自己
       搵唔到同音字  → 退回合成原字
  咁樣就算係「銀行」嘅行，都保證讀 hong4 而唔會讀成 haang4。

輸出
  app/audio/chars/<uXXXX>[_<jyutping>].mp3
  app/content/char_audio.json        ← 前端索引

可重複執行：已存在而且唔係空檔會自動跳過。
"""
import asyncio
import collections
import datetime
import json
import os
import re
import sys

ROOT = r"D:/Code/cantonese-app"
CURRICULUM = os.path.join(ROOT, "app", "content", "curriculum.json")
OUT_DIR = os.path.join(ROOT, "app", "audio", "chars")
INDEX = os.path.join(ROOT, "app", "content", "char_audio.json")

VOICE = "zh-HK-HiuMaanNeural"     # 女聲，同課程詞彙示範一致
RATE = "-20%"                     # 單字放慢，方便跟讀
CONCURRENCY = 6
MIN_BYTES = 700

HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


# ---------------------------------------------------------------- 粵拼工具
def load_jyutping():
    """延遲載入 ToJyutping（Rust 擴充，載入慢，唔用時唔好叫）"""
    from ToJyutping import get_jyutping, get_jyutping_candidates
    return get_jyutping, get_jyutping_candidates


def default_reading(char, get_jyutping):
    """拿單字預設讀音，例如 'si1'；失敗回傳 None"""
    try:
        raw = get_jyutping(char) or ""
    except Exception:
        return None
    m = re.search(r"\(([^)]+)\)\s*$", raw)
    if m:
        return m.group(1).split(",")[0].strip()
    return None


def is_common(char):
    """GB2312 一級字庫（最常用 3755 字）判定 —— 避免用生僻字做同音替身"""
    try:
        b = char.encode("gb2312")
    except Exception:
        return False
    return len(b) == 2 and 0xB0 <= b[0] <= 0xD7


def build_mono_table(get_jyutping_candidates):
    """掃 CJK 基本區，建「讀音 → 只讀呢個音嘅常用字」反查表"""
    mono = collections.defaultdict(list)
    for cp in range(0x4E00, 0xA000):
        ch = chr(cp)
        try:
            res = get_jyutping_candidates(ch)
        except Exception:
            continue
        if not res:
            continue
        cands = res[0][1]
        if len(cands) != 1:
            continue
        mono[cands[0]].append(ch)
    return mono


# ---------------------------------------------------------------- 課程對齊
def collect_course_reading(get_jyutping):
    """把課程每句嘅漢字同粵拼逐一對齊，統計「字 → 讀音頻次」"""
    cur = json.load(open(CURRICULUM, encoding="utf-8"))
    read = collections.defaultdict(collections.Counter)
    problems = []

    def feed(yue, py):
        if not py:
            return
        chars = [c for c in yue if HAN.match(c)]
        syls = str(py).split()
        if len(chars) != len(syls):
            problems.append((yue, py))
            return
        for c, s in zip(chars, syls):
            read[c][s] += 1

    for L in cur["lessons"]:
        for c in L.get("core", []):
            feed(c.get("y", ""), c.get("p"))
        for d in L.get("dialogue", []):
            feed(d.get("y", ""), d.get("p"))
        for v in L.get("vocab", []):
            feed(v.get("y", ""), v.get("p"))
    return read, problems


def collect_all_hanzi(cur):
    """課程所有文本欄位出現過嘅漢字（連對譯／目標／貼士／練習都要能點讀）"""
    buf = []
    for L in cur["lessons"]:
        buf += L.get("goals", [])
        buf.append(L.get("scene", ""))
        buf.append(L.get("sceneZh", ""))
        buf.append(L.get("title", ""))
        buf.append(L.get("titleZh", ""))
        for c in L.get("core", []):
            buf += [c.get("y", ""), c.get("z", "")]
        for d in L.get("dialogue", []):
            buf += [d.get("y", ""), d.get("z", "")]
        for v in L.get("vocab", []):
            buf += [v.get("y", ""), v.get("z", "")]
        notes = L.get("notes") or []
        for n in notes:
            buf += list(n.values()) if isinstance(n, dict) else [str(n)]
        for q in L.get("quiz") or []:
            buf += [str(x) for x in (q.values() if isinstance(q, dict) else [q])]
    text = "".join(buf)
    return {c for c in text if HAN.match(c)}


# ---------------------------------------------------------------- 目標排程
def build_targets(hanzi, read, mono, get_jyutping, get_jyutping_candidates):
    """
    為每個漢字決定要生成邊幾個音檔。
    回傳 [{char, reading, source, file, why}]
    """
    course_chars = set(read.keys())
    targets = []
    used_homophone = collections.Counter()

    for ch in sorted(hanzi):
        try:
            res = get_jyutping_candidates(ch)
        except Exception:
            res = None
        cands = res[0][1] if res else []
        # 字典首選讀音：只有當課程讀音偏離佢，先值得出動同音替身。
        # （若唔做呢個限制，幾乎所有字都會被誤判成「多音字」而亂替換）
        dflt = cands[0] if cands else default_reading(ch, get_jyutping)

        # 呢個字要生成邊幾個讀音：課程出現過嘅（按頻次），加預設讀音墊底
        readings = []
        for r, _n in read.get(ch, collections.Counter()).most_common():
            readings.append(r)
        if dflt and dflt not in readings:
            readings.append(dflt)
        if not readings:
            readings.append(None)          # 無讀音資料 → 純檔案，前端當預設用

        for r in readings:
            source, why = ch, "self"
            # 只有「課程讀音 ≠ 字典首選讀音」先換替身：
            # 例如 行(hong4) 字典首選係 haang4 → 借「航」出聲；
            #      行(haang4) 同首選一致 → 直接用返「行」。
            if r and r != dflt and len(cands) > 1 and r in cands:
                pool = mono.get(r, [])
                pick = next((y for y in pool if y in course_chars), None)
                if pick is None:
                    pick = next((y for y in pool if is_common(y)), None)
                if pick is not None and pick != ch:
                    source, why = pick, "homophone"
            fname = "u%04x" % ord(ch) + ("" if not r else "_" + r) + ".mp3"
            targets.append({"char": ch, "reading": r, "source": source,
                            "file": fname, "why": why})
            if why == "homophone":
                used_homophone[ch] = source

    return targets, used_homophone


# ---------------------------------------------------------------- 合成
async def synth(edge_tts, sem, job, ok, fail):
    dst = os.path.join(OUT_DIR, job["file"])
    if os.path.exists(dst) and os.path.getsize(dst) >= MIN_BYTES:
        ok.append(job["file"])
        return
    async with sem:
        for attempt in (1, 2, 3):
            try:
                c = edge_tts.Communicate(job["source"], VOICE, rate=RATE)
                await c.save(dst)
                if os.path.getsize(dst) >= MIN_BYTES:
                    ok.append(job["file"])
                    return
            except Exception as e:
                if attempt == 3:
                    fail.append((job["file"], job["source"], str(e)[:60]))
                else:
                    await asyncio.sleep(1.2 * attempt)


async def main():
    import edge_tts

    get_jyutping, get_jyutping_candidates = load_jyutping()
    cur = json.load(open(CURRICULUM, encoding="utf-8"))

    print("[1/4] 對齊課程漢字同粵拼 …")
    read, problems = collect_course_reading(get_jyutping)
    print("      對齊成功 %d 字（有讀音），錯位句 %d" % (len(read), len(problems)))
    for y, p in problems[:5]:
        print("      [!] 對唔上：", y, "|", p)

    hanzi = collect_all_hanzi(cur)
    print("[2/4] 課程漢字去重：%d 個" % len(hanzi))

    print("[3/4] 掃 CJK 建同音字表 …")
    mono = build_mono_table(get_jyutping_candidates)
    print("      可用讀音 %d 組" % len(mono))

    targets, homophones = build_targets(hanzi, read, mono,
                                        get_jyutping, get_jyutping_candidates)
    print("[4/4] 需生成音檔 %d 個（其中 %d 個用同音字替身）"
          % (len(targets), len(homophones)))
    if homophones:
        print("      同音替身：", "、".join(
            "%s→%s" % (k, v) for k, v in list(homophones.items())[:18]))

    os.makedirs(OUT_DIR, exist_ok=True)
    sem = asyncio.Semaphore(CONCURRENCY)
    ok, fail = [], []
    CHUNK = 60
    for i in range(0, len(targets), CHUNK):
        await asyncio.gather(*[synth(edge_tts, sem, j, ok, fail)
                               for j in targets[i:i + CHUNK]])
        print("      進度 %d/%d  ok %d  fail %d"
              % (min(i + CHUNK, len(targets)), len(targets), len(ok), len(fail)))

    # ---- 寫前端索引 ----
    chars = {}
    for j in targets:
        e = chars.setdefault(j["char"], {"d": None, "r": {}})
        if j["reading"]:
            e["r"][j["reading"]] = j["file"][:-4]
        else:
            e["d"] = j["file"][:-4]
    for ch, e in chars.items():
        if e["d"] is None:
            e["d"] = (e["r"] or {}).get(next(iter(e["r"]), ""), None)
            if e["d"] is None and e["r"]:
                e["d"] = list(e["r"].values())[0]
        # 預設檔 = 課程出現最多嘅讀音，同 r 表對齊
        dflt = default_reading(ch, get_jyutping)
        if dflt and dflt in e["r"]:
            e["d"] = e["r"][dflt]
        if not e["d"] and e["r"]:
            e["d"] = list(e["r"].values())[0]

    doc = {
        "meta": {
            "voice": VOICE,
            "rate": RATE,
            "chars": len(chars),
            "files": len(ok),
            "homophones": homophones,
            "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "sizeKB": round(sum(os.path.getsize(os.path.join(OUT_DIR, f))
                                for f in os.listdir(OUT_DIR) if f.endswith(".mp3")) / 1024, 1),
        },
        "chars": chars,
    }
    json.dump(doc, open(INDEX, "w", encoding="utf-8"), ensure_ascii=False)
    print("索引寫入：%s" % INDEX)
    print("完成 | 成功 %d / %d | 檔案 %d 個 | %.1f MB"
          % (len(ok), len(targets), doc["meta"]["files"], doc["meta"]["sizeKB"] / 1024))
    if fail:
        print("[!] 失敗 %d：" % len(fail))
        for f in fail[:15]:
            print("    ", f)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
