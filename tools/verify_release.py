# -*- coding: utf-8 -*-
"""上架前自檢（一鍵）：靜態資源 + 打包純淨度 + 執行期行為。

用法：
    python tools/verify_release.py

它會自己起一個本機 HTTP 服務（隨機埠）指向 app/，所以唔需要預先開服務。

執行期部分交給 tools/verify_app.mjs（CDP 實時探針）。為何唔用 headless 的
--virtual-time-budget：本 App 會令虛擬時鐘停擺，探針的 setTimeout 永不觸發。
"""
import functools
import http.server
import json
import os
import re
import socket
import subprocess
import sys
import threading

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
TOOLS = os.path.join(ROOT, "tools")
NODE = r"C:\Users\Luffy\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"

OK = "✓"
BAD = "✗"
warnings = []
failures = []


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(port):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=APP)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


# ---------------------------------------------------------------- 靜態檢查
def check_assets(port):
    print("[1] 打包資源可訪問性")
    import urllib.request
    want = [
        "index.html", "manifest.json", "sw.js", "privacy.html",
        "content/curriculum.json", "content/char_audio.json",
        "icons/icon-192.png", "icons/icon-512.png", "icons/icon-180.png",
        "icons/icon-maskable-512.png",
        "audio/basic-01-c1.mp3", "audio/chars/u4f60_nei5.mp3", "audio/con-11-c6.mp3",
    ]
    for p in want:
        try:
            r = urllib.request.urlopen("http://127.0.0.1:%d/%s" % (port, p), timeout=10)
            print("    %-32s %s  %d bytes" % (p, r.status, len(r.read())))
        except Exception as e:
            print("    %-32s %s  %s" % (p, BAD, e))
            failures.append("資源無法訪問: " + p)


def check_purity():
    print("\n[2] 打包目錄純淨度（版權紅線）")
    entries = sorted(os.listdir(APP))
    print("    app/ 內容：", entries)

    forbidden = {
        "pages": "原教材頁面截圖",
        "book.json": "PDF 時代由原教材抽取的內容",
        "layout.json": "PDF 時代版式資料",
    }
    for name, why in forbidden.items():
        if name in entries or os.path.exists(os.path.join(APP, name)):
            print("    %s 殘留 %s（%s）" % (BAD, name, why))
            failures.append("打包目錄殘留 " + name)
        else:
            print("    %s 無 %-12s（%s）" % (OK, name, why))

    cdir = os.path.join(APP, "content")
    print("    app/content：", sorted(os.listdir(cdir)))
    extra = set(os.listdir(cdir)) - {"curriculum.json", "char_audio.json"}
    if extra:
        print("    %s content/ 多餘檔案：%s" % (BAD, sorted(extra)))
        failures.append("content/ 有多餘檔案 " + str(sorted(extra)))

    audio = os.path.join(APP, "audio")
    clips = len([f for f in os.listdir(audio) if f.endswith(".mp3")])
    chars = os.path.join(audio, "chars")
    nchars = len([f for f in os.listdir(chars) if f.endswith(".mp3")]) if os.path.isdir(chars) else 0
    size = 0
    for dp, _d, fs in os.walk(APP):
        for f in fs:
            size += os.path.getsize(os.path.join(dp, f))
    print("    課程音檔 %d ＋ 單字音檔 %d ＝ %d（%.1f MB）" % (clips, nchars, clips + nchars, size / 1048576))
    if clips < 1500 or nchars < 1700:
        print("    %s 音檔數量低於預期" % BAD)
        failures.append("音檔數量不足")


def check_external():
    print("\n[3] 外部網路請求掃描（純離線設計）")
    hits = []
    for dirpath, _d, files in os.walk(APP):
        for f in files:
            if not f.endswith((".html", ".js", ".json")):
                continue
            fp = os.path.join(dirpath, f)
            try:
                s = open(fp, encoding="utf-8").read()
            except Exception:
                continue
            for m in re.finditer(r"https?://[^\s\"'<>)\]]+", s):
                u = m.group(0)
                if "www.w3.org" in u or "json-schema" in u:
                    continue
                hits.append((os.path.relpath(fp, ROOT).replace("\\", "/"), u))
    if hits:
        for f, u in hits:
            print("    %s %-24s %s" % (BAD, f, u))
            failures.append("外部引用 %s -> %s" % (f, u))
    else:
        print("    %s 無任何外部 URL 引用（可爭取豁免 ICP / 工信部備案）" % OK)


# ---------------------------------------------------------------- 執行期檢查
def check_runtime(port):
    print("\n[4] 執行期探針（CDP 實時，真實時間）")
    if not os.path.exists(NODE):
        print("    %s 找不到 node：%s" % (BAD, NODE))
        warnings.append("跳過執行期探針（node 缺失）")
        return None
    script = os.path.join(TOOLS, "verify_app.mjs")
    r = subprocess.run([NODE, script, str(port)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=600)
    out = (r.stdout or "").strip()
    try:
        rep = json.loads(out)
    except Exception:
        print("    %s 探針輸出無法解析" % BAD)
        print(out[:1500])
        print((r.stderr or "")[:800])
        failures.append("執行期探針失敗")
        return None

    ph = rep.get("phases", {})
    st = ph.get("static", {})
    print("    App 就緒 ............... %s" % (OK if rep.get("ready") else BAD))
    print("    板塊 / 課程 ............ %s / %s" % (st.get("domains"), st.get("lessons")))
    print("    各板塊課數 ............. %s" % st.get("domainCounts"))
    print("    字庫 / 音檔 ............ %s 字 / %s 檔" % (
        st.get("charAudioKeys"), (ph.get("me") or {}).get("engFiles")))
    print("    原文索引 / 詞庫 ........ %s / %s" % (st.get("text2clip"), st.get("vocabClip")))
    print("    Store 適配層 ........... %s (ready=%s, native=%s)" % (
        st.get("store"), st.get("storeReady"), st.get("storeNative")))
    print("    manifest / theme ....... %s / %s" % (st.get("manifest"), st.get("themeColor")))
    print("    viewport-fit=cover ..... %s" % st.get("viewportFit"))
    print("    隱私連結 / AI 披露 ..... %s / %s" % (st.get("privacyLink"), st.get("hasAiNote")))
    print("    圖示載入 ............... %s" % ph.get("icons"))
    les = ph.get("lesson", {})
    print("    首課 ................... %s「%s」" % (les.get("title"), les.get("firstLine")))
    print("    逐字拼音對齊 ........... %s（%s 字塊，首句 %s）" % (
        OK if les.get("aligned") else BAD, les.get("charSpans"), les.get("firstPy")))
    print("    整句音檔 ............... %s" % les.get("lineClipAttr"))

    print("    點字發音路由抽樣（%s）：" % ph.get("charSampleTitle"))
    for k in sorted([k for k in ph if k.startswith("char") and k[4:].isdigit()],
                    key=lambda x: int(x[4:])):
        v = ph[k]
        mark = OK if v.get("match") else "△"
        print("        %s %-3s %-12s 期望 %-22s 實得 %s" % (
            mark, v.get("ch"), v.get("jp"), v.get("expected"), v.get("got")))
        if not v.get("match"):
            warnings.append("「%s」未走字庫（實得 %s），多為課程原聲優先，需人工確認" % (v.get("ch"), v.get("got")))

    pr = ph.get("prefs", {})
    print("    偏好開關（走 Store）.... py %s→%s→%s | slow %s→%s→%s" % (
        pr.get("pyBefore"), pr.get("pyAfter"), pr.get("pyRestored"),
        pr.get("slowBefore"), pr.get("slowAfter"), pr.get("slowRestored")))
    print("    localStorage 鍵 ........ %s" % pr.get("lsKeys"))
    me = ph.get("me", {})
    print("    我的頁 ................. %s 張卡 / 引擎點 %s" % (me.get("cards"), me.get("engDot")))
    print("    版本行 ................. %s" % me.get("verLine"))

    errs = rep.get("jsErrors") or []
    cons = rep.get("consoleMsgs") or []
    print("    JS 例外 ................ %s" % (errs if errs else "無 " + OK))
    print("    主控台錯誤 ............. %s" % (cons if cons else "無 " + OK))
    if errs:
        failures.append("執行期有 JS 例外：%s" % errs[:3])
    return rep


def main():
    port = free_port()
    httpd = serve(port)
    print("本機服務 http://127.0.0.1:%d/ -> %s\n" % (port, APP))
    try:
        check_assets(port)
        check_purity()
        check_external()
        check_runtime(port)
    finally:
        httpd.shutdown()

    print("\n" + "=" * 56)
    if failures:
        print("結論：%s 有 %d 項必須處理" % (BAD, len(failures)))
        for f in failures:
            print("   - " + f)
    else:
        print("結論：%s 全部通過，可進入打包" % OK)
    if warnings:
        print("注意（非阻斷）：")
        for w in warnings:
            print("   - " + w)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
