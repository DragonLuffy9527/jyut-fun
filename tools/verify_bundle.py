#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
校驗已打包產物（.aab / .apk）內的資源是否完整、且與源目錄 app/ 一致。

為什麼需要它：`_build_android.py` 只驗簽名，不驗內容。曾發生過
`npx cap sync android` 中途卡死、把 assets/public 清空到只剩 576KB
（音檔只拷進 25 段）卻仍建置成功的事件 —— 這種包「簽名正確、能安裝、
但學到一半沒聲音」。本腳本用「引用閉環」把它擋在發布之前。

校驗邏輯（不是只數檔案數，而是驗「資料引用的每個音檔都真的在包裡」）：
  ① curriculum.json 的每課 clips[] → audio/<clip>.mp3
  ② char_audio.json 的每個字 d / r[].* → audio/chars/<name>.mp3
  ③ 包內 mp3 全路徑集合 vs 源 app/ 目錄逐檔比對（雙向皆須為 0 差集）
  ④ 孤兒音檔（在包內但沒有任何資料引用）
  ⑤ 關鍵產物齊備（index/privacy/manifest/sw/兩份 json/icons）
  ⑥ 兩處已知修復是否在包（TTS.noApi、隱私頁聯絡信箱）

用法：
  python tools/verify_bundle.py                    # 自動挑 dist/ 下最新的 apk+aab
  python tools/verify_bundle.py dist/xxx.apk       # 指定單一產物
  python tools/verify_bundle.py --quiet            # 只印結論與錯誤（給 CI 用）

退出碼：0 = 全部通過；1 = 有缺檔／不一致；2 = 檔案或參數問題。
"""
import argparse
import json
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "app")
DIST = os.path.join(ROOT, "dist")

KEY_ARTIFACTS = [
    "index.html",
    "privacy.html",
    "manifest.json",
    "sw.js",
    "content/curriculum.json",
    "content/char_audio.json",
    "icons/icon-192.png",
    "icons/icon-512.png",
    "icons/icon-1024.png",
]

G, R, Y, D, N = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def ok(b):
    return (G + "✓" + N) if b else (R + "✗" + N)


def public_prefix(names):
    """找出包內 assets/public/ 的路徑前綴（AAB 會多一層 base/）。"""
    for n in names:
        i = n.find("assets/public/")
        if i >= 0:
            return n[: i + len("assets/public/")]
    return None


def src_mp3_rel():
    """源目錄 app/ 下所有 mp3 的相對路徑（用 / 分隔），如 audio/chars/u68da_paang4.mp3。"""
    out = set()
    for dirpath, _dirs, files in os.walk(SRC):
        for f in files:
            if f.endswith(".mp3"):
                rel = os.path.relpath(os.path.join(dirpath, f), SRC).replace("\\", "/")
                out.add(rel)
    return out


def verify(path, quiet=False):
    problems = []
    if not os.path.isfile(path):
        print("%s 找不到檔案：%s" % (ok(False), path))
        return 2

    z = zipfile.ZipFile(path)
    names = z.namelist()
    pre = public_prefix(names)
    if not pre:
        print("%s 包內找不到 assets/public/，可能不是 Capacitor 產物" % ok(False))
        return 2

    pkg_mp3 = {n[len(pre):] for n in names if n.startswith(pre) and n.endswith(".mp3")}
    size_mb = os.path.getsize(path) / 1048576.0

    def say(*a):
        if not quiet:
            print(*a)

    say("=" * 66)
    say(" 產物 : %s" % os.path.basename(path))
    say(" 大小 : %.1f MB   條目 : %d   mp3 : %d" % (size_mb, len(names), len(pkg_mp3)))
    say("=" * 66)

    # ---- 載入兩份核心資料 ----
    try:
        cur = json.loads(z.read(pre + "content/curriculum.json").decode("utf-8"))
        cha = json.loads(z.read(pre + "content/char_audio.json").decode("utf-8"))
    except KeyError as e:
        print("%s 缺少核心資料檔：%s" % (ok(False), e))
        return 1

    # ---- ① 課程 clips 閉環 ----
    course_refs = []
    for les in cur.get("lessons", []):
        for c in les.get("clips", []):
            course_refs.append(("audio/%s.mp3" % c, les.get("id", "?")))
    cmiss = sorted({p for p, _ in course_refs if p not in pkg_mp3})
    say("")
    say(" ① 課程音檔")
    say("    課數            : %d / %d 課有 clip" % (len({i for _, i in course_refs}), len(cur.get("lessons", []))))
    say("    引用 clip 數    : %d（去重 %d）" % (len(course_refs), len({p for p, _ in course_refs})))
    say("    缺檔            : %s %d" % (ok(not cmiss), len(cmiss)))
    for p in cmiss[:8]:
        say("        %s" % p)
    if cmiss:
        problems.append("課程音檔缺 %d 個" % len(cmiss))

    # ---- ② 單字庫閉環 ----
    char_refs = []
    chars = cha.get("chars", {})
    for ch, v in chars.items():
        if isinstance(v, dict):
            if v.get("d"):
                char_refs.append("audio/chars/%s.mp3" % v["d"])
            for rv in (v.get("r") or {}).values():
                if isinstance(rv, str):
                    char_refs.append("audio/chars/%s.mp3" % rv)
    hmiss = sorted({p for p in char_refs if p not in pkg_mp3})
    say("")
    say(" ② 單字庫音檔")
    say("    字數            : %d" % len(chars))
    say("    引用音檔數      : %d（去重 %d）" % (len(char_refs), len(set(char_refs))))
    say("    缺檔            : %s %d" % (ok(not hmiss), len(hmiss)))
    for p in hmiss[:8]:
        say("        %s" % p)
    if hmiss:
        problems.append("單字庫音檔缺 %d 個" % len(hmiss))

    # ---- ③ 包內 vs 源目錄 ----
    src = src_mp3_rel()
    only_src = sorted(src - pkg_mp3)
    only_pkg = sorted(pkg_mp3 - src)
    say("")
    say(" ③ 包內 vs 源目錄 app/")
    say("    源 %d 段 ／ 包內 %d 段" % (len(src), len(pkg_mp3)))
    say("    源有包無        : %s %d" % (ok(not only_src), len(only_src)))
    for p in only_src[:5]:
        say("        %s" % p)
    say("    包有源無        : %s %d" % (ok(not only_pkg), len(only_pkg)))
    for p in only_pkg[:5]:
        say("        %s" % p)
    if only_src:
        problems.append("源有 %d 段音檔未進包" % len(only_src))
    if only_pkg:
        problems.append("包內有 %d 段源目錄不存在的音檔" % len(only_pkg))

    # ---- ④ 孤兒音檔 ----
    used = {p for p, _ in course_refs} | set(char_refs)
    orphan = sorted(pkg_mp3 - used)
    say("")
    say(" ④ 孤兒音檔（無任何資料引用）")
    say("    數量            : %s %d" % (ok(not orphan), len(orphan)))
    for p in orphan[:8]:
        say("        %s" % p)
    if orphan:
        # 孤兒不算致命（只是包變大），但值得留意
        say("    %s（僅提示，不視為失敗）" % Y + "注意" + N)

    # ---- ⑤ 關鍵產物 ----
    say("")
    say(" ⑤ 關鍵產物")
    kmiss = [k for k in KEY_ARTIFACTS if pre + k not in names]
    for k in KEY_ARTIFACTS:
        say("    %s %s" % (ok(pre + k in names), k))
    if kmiss:
        problems.append("關鍵產物缺 %d 項" % len(kmiss))

    # ---- ⑥ 已知修復 ----
    say("")
    say(" ⑥ 已知修復是否在包")
    try:
        h = z.read(pre + "index.html").decode("utf-8")
    except KeyError:
        h = ""
    noapi = h.count("noApi")
    say("    TTS.noApi（Android 無語音合成）: %s %d 處" % (ok(noapi > 0), noapi))
    if noapi == 0:
        problems.append("index.html 缺 TTS.noApi 修復")

    try:
        pr = z.read(pre + "privacy.html").decode("utf-8")
    except KeyError:
        pr = ""
    has_ph = "請填入聯絡信箱" in pr or "please fill in contact email" in pr.lower()
    mails = sorted(set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", pr)))
    say("    隱私頁信箱                    : %s %s" % (ok(mails and not has_ph), "、".join(mails) or "（無）"))
    if has_ph:
        problems.append("privacy.html 仍有聯絡信箱佔位符")
    if not mails:
        problems.append("privacy.html 找不到聯絡信箱")

    # ---- 結論 ----
    # 注意：問題摘要「不受 quiet 抑制」—— 呼叫者（如 _build_android.py）用
    # quiet=True 只為省掉正常輸出，一旦失敗仍必須看到原因。
    say("")
    say("=" * 66)
    if problems:
        print(" %s [%s] 未通過，共 %d 項問題：" % (ok(False), os.path.basename(path), len(problems)))
        for p in problems:
            print("   - %s" % p)
        return 1
    if not quiet:
        print(" %s 全部通過：%d 段音檔引用閉環無缺、與源目錄逐檔一致" % (ok(True), len(pkg_mp3)))
    return 0


def latest(pattern):
    if not os.path.isdir(DIST):
        return []
    hits = []
    for f in os.listdir(DIST):
        if pattern in f.lower() and f.lower().endswith(pattern):
            hits.append(os.path.join(DIST, f))
    return sorted(hits, key=os.path.getmtime, reverse=True)


def main():
    ap = argparse.ArgumentParser(description="校驗 AAB/APK 內資源完整性（引用閉環）")
    ap.add_argument("bundles", nargs="*", help="要校驗的包（預設自動挑 dist/ 下最新 .apk 與 .aab）")
    ap.add_argument("--quiet", action="store_true", help="只印結論與錯誤")
    args = ap.parse_args()

    targets = args.bundles
    if not targets:
        targets = latest(".apk")[:1] + latest(".aab")[:1]
    if not targets:
        print("%s dist/ 下找不到 .apk 或 .aab，請先建置或用參數指定" % ok(False))
        return 2

    rc = 0
    for i, t in enumerate(targets):
        if i:
            print()
        r = verify(t, quiet=args.quiet)
        rc = max(rc, r)
    return rc


if __name__ == "__main__":
    sys.exit(main())
