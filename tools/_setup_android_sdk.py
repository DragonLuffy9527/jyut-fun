# -*- coding: utf-8 -*-
"""安裝 Android 命令列 SDK（不動系統目錄，只裝在用戶空間）。

步驟：下載 commandlinetools → 解壓到 <SDK>/cmdline-tools/latest → 接受授權
→ 安裝 platform-tools / platforms;android-36 / build-tools;36.0.0。

用法：python tools/_setup_android_sdk.py
"""
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

sys.stdout.reconfigure(encoding="utf-8")

SDK = r"C:\Users\Luffy\AppData\Local\Android\Sdk"
TMP = r"C:\Users\Luffy\AppData\Local\Android\_setup_tmp"
URL = "https://dl.google.com/android/repository/commandlinetools-win-13114758_latest.zip"
JAVA_HOME = r"C:\Program Files\Eclipse Adoptium\jdk-17.0.19.10-hotspot"

PACKAGES = [
    "platform-tools",
    "platforms;android-36",
    "build-tools;36.0.0",
]


def log(*a):
    print(*a, flush=True)


def download(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 100 * 1024 * 1024:
        log("  已存在，略過下載：%s (%.1f MB)" % (dest, os.path.getsize(dest) / 1024 / 1024))
        return dest
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    t = time.time()
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        last = 0
        while True:
            chunk = r.read(1024 * 256)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if time.time() - last > 3:
                last = time.time()
                pct = (100.0 * got / total) if total else 0
                log("  下載 %.1f / %.1f MB (%.0f%%)" % (got / 1048576, total / 1048576, pct))
    log("  下載完成 %.1f MB，耗時 %.0fs" % (os.path.getsize(dest) / 1048576, time.time() - t))
    return dest


def main():
    os.environ["JAVA_HOME"] = JAVA_HOME
    os.environ["PATH"] = os.path.join(JAVA_HOME, "bin") + os.pathsep + os.environ.get("PATH", "")

    log("[1] 下載 commandlinetools")
    zip_path = os.path.join(TMP, "cmdline-tools.zip")
    download(URL, zip_path)

    log("\n[2] 解壓到 %s" % os.path.join(SDK, "cmdline-tools", "latest"))
    latest = os.path.join(SDK, "cmdline-tools", "latest")
    if os.path.isdir(latest):
        shutil.rmtree(latest, ignore_errors=True)
    os.makedirs(latest, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(TMP + r"\extract")
    inner = os.path.join(TMP, "extract", "cmdline-tools")
    for name in os.listdir(inner):
        shutil.move(os.path.join(inner, name), os.path.join(latest, name))
    log("  bin: %s" % sorted(os.listdir(os.path.join(latest, "bin")))[:8])

    sdkmanager = os.path.join(latest, "bin", "sdkmanager.bat")
    if not os.path.exists(sdkmanager):
        log("!! 找不到 sdkmanager")
        return 1

    env = dict(os.environ)

    log("\n[3] 接受授權")
    # sdkmanager --licenses 會逐條問 y/N；餵足夠多的 y
    r = subprocess.run([sdkmanager, "--sdk_root=" + SDK, "--licenses"],
                       input="y\n" * 60, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=900, env=env)
    log("  rc=%s" % r.returncode)
    log("  " + (r.stdout or "")[-800:].replace("\n", "\n  "))

    log("\n[4] 安裝套件：%s" % ", ".join(PACKAGES))
    r = subprocess.run([sdkmanager, "--sdk_root=" + SDK] + PACKAGES,
                       input="y\n" * 60, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=3600, env=env)
    log("  rc=%s" % r.returncode)
    log("  " + (r.stdout or "")[-2500:].replace("\n", "\n  "))
    if r.stderr:
        log("  STDERR " + (r.stderr or "")[-800:].replace("\n", "\n  "))

    log("\n[5] 結果")
    for sub in ["cmdline-tools", "platform-tools", "platforms", "build-tools"]:
        p = os.path.join(SDK, sub)
        log("  %-16s %s" % (sub, sorted(os.listdir(p)) if os.path.isdir(p) else "(缺失)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
