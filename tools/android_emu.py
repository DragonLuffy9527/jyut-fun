#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Android 模擬器一鍵腳本（粵.fun）
=================================================
把「建 AVD → 開機 → 裝 APK → 啟動 App → 截圖 → 抓 logcat」串成一條命令。

前置（只需一次）：
  1. 啟用 Windows Hypervisor Platform 並重開機
     dism /Online /Enable-Feature /FeatureName:HypervisorPlatform /All /NoRestart
  2. sdkmanager "emulator" "system-images;android-36;google_apis;x86_64"

用法：
  python tools/android_emu.py check              # 檢查環境（加速 / 鏡像 / AVD / APK）
  python tools/android_emu.py create             # 建立 AVD（已存在則跳過）
  python tools/android_emu.py start              # 啟動模擬器（有視窗）
  python tools/android_emu.py start --headless   # 無視窗啟動（適合自動化）
  python tools/android_emu.py start --keepalive  # 由當前背景任務持有，任務結束才關閉
  python tools/android_emu.py install            # 安裝 dist/ 的 APK（-r 覆蓋）
  python tools/android_emu.py launch             # 啟動 App
  python tools/android_emu.py shot 01-home       # 截圖到 store/screenshots-emu/
  python tools/android_emu.py logcat 60          # 抓 60 秒 logcat 到 tools/_logcat.txt
  python tools/android_emu.py inspect            # 開 WebView 遠端除錯埠（chrome://inspect）
  python tools/android_emu.py run                # 一條龍：create→start→install→launch

  python tools/android_emu.py stop               # 關閉模擬器
"""
import os
import re
import subprocess
import sys
import time

SDK = r"C:\Users\Luffy\AppData\Local\Android\Sdk"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EMULATOR = os.path.join(SDK, "emulator", "emulator.exe")
AVDMANAGER = os.path.join(SDK, "cmdline-tools", "latest", "bin", "avdmanager.bat")
ADB = os.path.join(SDK, "platform-tools", "adb.exe")

AVD_NAME = "jyutfun_api36"
SYS_IMAGE = "system-images;android-36;google_apis;x86_64"
DEVICE = "pixel_7"
PKG = "com.jyutfun.app"
ACTIVITY = "com.jyutfun.app.MainActivity"

DIST_DIR = os.path.join(ROOT, "dist")
SHOT_DIR = os.path.join(ROOT, "store", "screenshots-emu")
EMU_LOG = os.path.join(ROOT, "tools", "_emulator.log")


def _env():
    e = os.environ.copy()
    e["ANDROID_HOME"] = SDK
    e["ANDROID_SDK_ROOT"] = SDK
    return e


def run(cmd, timeout=600, check=False, quiet=True):
    """執行外部命令，回傳 (rc, stdout)。"""
    p = subprocess.run(cmd, capture_output=True, timeout=timeout, env=_env())
    out = p.stdout.decode("utf-8", "replace")
    err = p.stderr.decode("utf-8", "replace")
    if not quiet and err.strip():
        out += "\n[stderr] " + err
    if check and p.returncode != 0:
        raise RuntimeError("command failed (%d): %s\n%s" % (p.returncode, " ".join(cmd), out + err))
    return p.returncode, out.strip()


def adb(*args, timeout=120):
    return run([ADB, *args], timeout=timeout)


def banner(t):
    print("\n" + "=" * 68)
    print("  " + t)
    print("=" * 68)


# ---------------------------------------------------------------- check
def cmd_check():
    banner("環境檢查")
    ok = True

    def mark(good, label, detail=""):
        nonlocal ok
        if not good:
            ok = False
        print("  [%s] %-34s %s" % ("OK" if good else "--", label, detail))

    mark(os.path.exists(ADB), "adb", ADB)
    mark(os.path.exists(EMULATOR), "emulator", EMULATOR)
    mark(os.path.isdir(os.path.join(SDK, "system-images", "android-36")),
         "system-image android-36", SYS_IMAGE)
    avd_dir = os.path.join(os.path.expanduser("~"), ".android", "avd", AVD_NAME + ".avd")
    mark(os.path.isdir(avd_dir), "AVD " + AVD_NAME, avd_dir)

    # 加速：emulator -accel-check
    accel = "(emulator 未安裝，略過)"
    if os.path.exists(EMULATOR):
        rc, out = run([EMULATOR, "-accel-check"], timeout=60)
        accel = out.replace("\n", " / ").strip()[:160]
        good = ("is installed and usable" in out) or ("WHPX" in out and "not" not in out.lower())
        mark(good, "硬體加速 (WHPX)", accel)
    else:
        print("  [--] %-34s %s" % ("硬體加速 (WHPX)", accel))

    # APK
    apk = None
    if os.path.isdir(DIST_DIR):
        for f in sorted(os.listdir(DIST_DIR)):
            if f.lower().endswith(".apk"):
                apk = os.path.join(DIST_DIR, f)
    if apk:
        mb = os.path.getsize(apk) / 1048576.0
        mark(True, "待裝 APK", "%s  (%.1f MB)" % (os.path.basename(apk), mb))
    else:
        mark(False, "待裝 APK", "dist/ 下找不到 .apk")

    print("\n  結論：" + ("環境就緒，可直接 `python tools/android_emu.py run`"
                        if ok else "尚有缺口，見上方 [--] 項目"))
    return 0 if ok else 1


# ---------------------------------------------------------------- create
def cmd_create(force=False):
    banner("建立 AVD: " + AVD_NAME)
    if not os.path.exists(EMULATOR):
        print("  ✗ emulator 尚未安裝。先執行：")
        print('    sdkmanager "emulator" "system-images;android-36;google_apis;x86_64"')
        return 1
    avd_dir = os.path.join(os.path.expanduser("~"), ".android", "avd", AVD_NAME + ".avd")
    if os.path.isdir(avd_dir) and not force:
        print("  已存在，跳過（要重建請加 --force）：" + avd_dir)
        return 0

    cmd = [AVDMANAGER, "create", "avd", "-n", AVD_NAME, "-k", SYS_IMAGE,
           "-d", DEVICE, "-c", "512M", "--force"]
    p = subprocess.run(cmd, input=b"no\n", capture_output=True, timeout=300, env=_env())
    out = (p.stdout + p.stderr).decode("utf-8", "replace")
    print("  " + out.replace("\n", "\n  ").strip())
    if p.returncode != 0:
        print("  ✗ 建立失敗")
        return 1

    # 調教 config.ini：實體鍵盤、音訊、4G 資料分區、開硬體 GPU
    cfg = os.path.join(avd_dir, "config.ini")
    if os.path.exists(cfg):
        want = {
            "hw.keyboard": "yes",
            "hw.audioInput": "yes",
            "hw.audioOutput": "yes",
            "hw.gpu.enabled": "yes",
            "hw.gpu.mode": "auto",
            "disk.dataPartition.size": "4096M",
            "vm.heapSize": "256",
            "hw.ramSize": "3072",
        }
        lines = []
        seen = set()
        for line in open(cfg, encoding="utf-8"):
            if "=" in line:
                k = line.split("=", 1)[0].strip()
                if k in want:
                    lines.append("%s=%s\n" % (k, want[k]))
                    seen.add(k)
                    continue
            lines.append(line)
        for k, v in want.items():
            if k not in seen:
                lines.append("%s=%s\n" % (k, v))
        with open(cfg, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print("  ✓ 已調教 config.ini（鍵盤 / 音訊 / 3GB RAM / 4GB 資料分區）")

    print("  ✓ AVD 就緒：" + avd_dir)
    return 0


# ---------------------------------------------------------------- start
def _device_online():
    rc, out = adb("devices")
    return any(re.search(r"^emulator-\d+\s+device", l) for l in out.splitlines())


def _launch_process(args):
    """拉起 emulator。優先嘗試脫離 Windows Job Object，避免被呼叫端回收。"""
    logf = open(EMU_LOG, "ab")
    if os.name != "nt":
        return subprocess.Popen(args, stdout=logf, stderr=logf,
                                stdin=subprocess.DEVNULL, env=_env())
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    CREATE_BREAKAWAY_FROM_JOB = 0x01000000
    for flags in (DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB,
                  DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP):
        try:
            return subprocess.Popen(args, stdout=logf, stderr=logf,
                                    stdin=subprocess.DEVNULL, env=_env(),
                                    creationflags=flags)
        except OSError:
            continue
    raise RuntimeError("無法拉起 emulator")


def _wait_boot(timeout_min):
    """等待模擬器開機完成。回傳 True/False。"""
    print("  等待 device 上線 ...")
    rc, _ = adb("wait-for-device", timeout=timeout_min * 60)
    if rc != 0:
        print("  ✗ wait-for-device 失敗")
        return False
    print("  等待開機完成 (sys.boot_completed) ...")
    t0 = time.time()
    while time.time() - t0 < timeout_min * 60:
        rc, out = adb("shell", "getprop", "sys.boot_completed")
        if out.strip() == "1":
            print("  ✓ 開機完成，耗時 %.0f 秒" % (time.time() - t0))
            for k in ("window_animation_scale", "transition_animation_scale",
                      "animator_duration_scale"):
                adb("shell", "settings", "put", "global", k, "0")
            return True
        time.sleep(3)
    print("  ✗ 逾時仍未開機完成")
    return False


def cmd_start(headless=False, timeout_min=6, keepalive=False):
    banner("啟動模擬器" + ("（無視窗）" if headless else "（有視窗）")
           + ("  [keepalive]" if keepalive else ""))
    avd_dir = os.path.join(os.path.expanduser("~"), ".android", "avd", AVD_NAME + ".avd")
    if not os.path.isdir(avd_dir):
        print("  ✗ AVD 不存在，先執行 create")
        return 1

    if _device_online():
        print("  模擬器已在運行，跳過啟動")
        return 0

    args = [EMULATOR, "-avd", AVD_NAME, "-no-boot-anim", "-no-snapshot-save",
            "-memory", "3072", "-cores", "4"]
    if headless:
        args += ["-no-window", "-gpu", "swiftshader_indirect"]
    else:
        args += ["-gpu", "auto"]

    if keepalive:
        # 由呼叫端（長時間背景任務）持有子行程，任務不結束模擬器就不會被回收
        logf = open(EMU_LOG, "ab")
        proc = subprocess.Popen(args, stdout=logf, stderr=logf,
                                stdin=subprocess.DEVNULL, env=_env())
    else:
        proc = _launch_process(args)
    print("  已拉起 emulator (pid=%d)，log → %s" % (proc.pid, EMU_LOG))

    if not _wait_boot(timeout_min):
        return 1

    if keepalive:
        print("  [keepalive] 保持存活中，Ctrl-C 或關閉模擬器即結束 ...")
        try:
            proc.wait()
        except KeyboardInterrupt:
            pass
        print("  模擬器已結束")
    return 0


# ---------------------------------------------------------------- install / launch
def cmd_install(apk_path=None):
    banner("安裝 APK")
    if not _device_online():
        print("  ✗ 沒有運行中的模擬器，先執行 start")
        return 1
    if not apk_path:
        cands = [os.path.join(DIST_DIR, f) for f in sorted(os.listdir(DIST_DIR))
                 if f.lower().endswith(".apk")] if os.path.isdir(DIST_DIR) else []
        if not cands:
            print("  ✗ dist/ 下找不到 .apk")
            return 1
        apk_path = cands[0]
    print("  安裝 " + os.path.basename(apk_path))
    rc, out = adb("install", "-r", "-d", apk_path, timeout=900)
    print("  " + out.replace("\n", "\n  "))
    return 0 if rc == 0 and "Success" in out else 1


def cmd_launch():
    banner("啟動 App")
    if not _device_online():
        print("  ✗ 沒有運行中的模擬器，先執行 start")
        return 1
    rc, out = adb("shell", "am", "start", "-n", "%s/%s" % (PKG, ACTIVITY))
    print("  " + out.replace("\n", "\n  "))
    time.sleep(6)
    rc, out = adb("shell", "dumpsys", "activity", "activities")
    m = [l.strip() for l in out.splitlines() if "mResumedActivity" in l or "topResumedActivity" in l]
    if m:
        print("  目前前景：" + m[0][:150])
    return 0


def cmd_shot(name):
    banner("截圖 → " + name)
    if not _device_online():
        print("  ✗ 沒有運行中的模擬器")
        return 1
    os.makedirs(SHOT_DIR, exist_ok=True)
    if not name.lower().endswith(".png"):
        name += ".png"
    dst = os.path.join(SHOT_DIR, name)
    p = subprocess.run([ADB, "exec-out", "screencap", "-p"],
                       capture_output=True, timeout=120, env=_env())
    if p.returncode != 0 or len(p.stdout) < 1000:
        print("  ✗ 截圖失敗")
        return 1
    with open(dst, "wb") as f:
        f.write(p.stdout)
    print("  ✓ %s  (%.0f KB)" % (dst, len(p.stdout) / 1024.0))
    return 0


def cmd_logcat(seconds=60):
    banner("抓 logcat %ss" % seconds)
    if not _device_online():
        print("  ✗ 沒有運行中的模擬器")
        return 1
    dst = os.path.join(ROOT, "tools", "_logcat.txt")
    adb("logcat", "-c")
    p = subprocess.Popen([ADB, "logcat", "-v", "time"], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, env=_env())
    time.sleep(int(seconds))
    p.terminate()
    data = p.stdout.read() if p.stdout else b""
    text = data.decode("utf-8", "replace")
    keep = [l for l in text.splitlines()
            if re.search(r"jyutfun|Capacitor|chromium|WebView|Audio|MediaPlayer|ExoPlayer|"
                         r"console|ERROR|FATAL|Exception", l, re.I)]
    with open(dst, "w", encoding="utf-8") as f:
        f.write("\n".join(keep))
    print("  ✓ 共 %d 行（原 %d 行）→ %s" % (len(keep), len(text.splitlines()), dst))
    for l in keep[:25]:
        print("    " + l[:160])
    return 0


def cmd_inspect():
    banner("WebView 遠端除錯")
    if not _device_online():
        print("  ✗ 沒有運行中的模擬器")
        return 1
    adb("forward", "--remove-all")
    rc, out = adb("shell", "cat", "/proc/net/unix")
    socks = [l.split()[-1] for l in out.splitlines() if "webview_devtools_remote" in l]
    if not socks:
        print("  ✗ 找不到 webview_devtools_remote（App 可能未啟動）")
        return 1
    sock = sorted(set(socks))[-1]
    rc, out = adb("forward", "tcp:9222", "localabstract:" + sock)
    print("  已轉發 127.0.0.1:9222 → %s" % sock)
    print("  在電腦 Chrome 開啟：  chrome://inspect/#devices")
    print("  或直接抓目標清單：    http://127.0.0.1:9222/json")
    return 0


def cmd_stop():
    banner("關閉模擬器")
    adb("emu", "kill")
    print("  已送出關閉指令")
    return 0


def cmd_run(headless=False):
    if cmd_create() != 0:
        return 1
    if cmd_start(headless=headless) != 0:
        return 1
    if cmd_install() != 0:
        return 1
    if cmd_launch() != 0:
        return 1
    cmd_shot("emu-01-home")
    print("\n  提示：接著可用 `logcat 60` 看執行期錯誤、`inspect` 連 WebView 除錯。")
    return 0


def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 0
    c = argv[0]
    rest = argv[1:]
    headless = "--headless" in rest
    rest = [a for a in rest if not a.startswith("--")]

    if c == "check":
        return cmd_check()
    if c == "create":
        return cmd_create(force="--force" in argv)
    if c == "start":
        return cmd_start(headless=headless, keepalive="--keepalive" in argv)
    if c == "install":
        return cmd_install(rest[0] if rest else None)
    if c == "launch":
        return cmd_launch()
    if c == "shot":
        return cmd_shot(rest[0] if rest else "shot")
    if c == "logcat":
        return cmd_logcat(int(rest[0]) if rest else 60)
    if c == "inspect":
        return cmd_inspect()
    if c == "stop":
        return cmd_stop()
    if c == "run":
        return cmd_run(headless=headless)
    print("未知指令：" + c)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
