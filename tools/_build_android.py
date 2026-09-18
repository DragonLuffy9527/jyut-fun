# -*- coding: utf-8 -*-
"""建置 Android 發行產物：AAB（上傳 Google Play）+ APK（真機側載試玩）。

用法：python tools/_build_android.py [任務...]
預設任務：bundleRelease assembleRelease

Capacitor 8 的 capacitor-android 模組要求 Java 21（sourceCompatibility VERSION_21），
只有 JDK 17 會在建置時報「無效的源發行版：21」。因此這裡自動挑選本機可用的
JDK 21+，並在找不到時明確報錯，而不是讓 Gradle 丟出難懂的訊息。
"""
import glob
import os
import re
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

ROOT = r"D:\Code\cantonese-app"
AND = os.path.join(ROOT, "android")
SDK = r"C:\Users\Luffy\AppData\Local\Android\Sdk"
MIN_JAVA = 21

# 依序尋找的 JDK 來源（glob 模式）
JDK_GLOBS = [
    os.path.expanduser(r"~\.workbuddy\binaries\jdk*\jdk-*"),
    os.path.expanduser(r"~\.workbuddy\binaries\jdk*\*"),
    r"C:\Program Files\Eclipse Adoptium\jdk-*",
    r"C:\Program Files\Java\jdk-*",
    r"C:\Program Files\Microsoft\jdk-*",
]


def _java_major(home):
    """讀 release 檔取得主版本號；找不到則回 None。"""
    release = os.path.join(home, "release")
    try:
        with open(release, "r", encoding="utf-8", errors="replace") as f:
            txt = f.read()
    except OSError:
        return None
    m = re.search(r'JAVA_VERSION="(\d+)', txt)
    if m:
        return int(m.group(1))
    # 退路：目錄名裡的 jdk-21 / jdk1.8
    m = re.search(r"jdk-(\d+)", os.path.basename(home))
    return int(m.group(1)) if m else None


def find_jdk():
    """回傳 (JAVA_HOME, 版本) —— 挑符合 MIN_JAVA 的最高版本。"""
    cands = []

    # 1) 明確指定的環境變數優先
    for var in ("CANTONESE_JAVA_HOME", "JAVA_HOME"):
        v = os.environ.get(var)
        if v and os.path.isdir(v):
            cands.append(v)

    # 2) 掃描已知位置
    for pat in JDK_GLOBS:
        cands.extend(glob.glob(pat))

    seen, found = set(), []
    for c in cands:
        c = os.path.normpath(c)
        if c in seen or not os.path.isfile(os.path.join(c, "bin", "java.exe")):
            continue
        seen.add(c)
        major = _java_major(c)
        if major:
            found.append((major, c))

    ok = sorted([f for f in found if f[0] >= MIN_JAVA], reverse=True)
    if ok:
        return ok[0][1], ok[0][0]

    print("!! 找不到 JDK %d+（Capacitor 8 需要）。" % MIN_JAVA)
    if found:
        print("   本機偵測到的 JDK：")
        for major, path in sorted(found, reverse=True):
            print("     - Java %-3s %s" % (major, path))
    print("   請安裝 Temurin JDK 21 後重試。")
    return None, None


def main():
    tasks = sys.argv[1:] or ["bundleRelease", "assembleRelease"]

    java_home, java_ver = find_jdk()
    if not java_home:
        return 3

    env = dict(os.environ)
    env["JAVA_HOME"] = java_home
    env["ANDROID_HOME"] = SDK
    env["ANDROID_SDK_ROOT"] = SDK
    env["PATH"] = os.path.join(java_home, "bin") + os.pathsep + env.get("PATH", "")
    env["GRADLE_OPTS"] = "-Dfile.encoding=UTF-8"

    gradlew = os.path.join(AND, "gradlew.bat")
    print("gradlew  :", gradlew, os.path.exists(gradlew))
    print("任務     :", tasks)
    print("JAVA_HOME: %s  (Java %s)" % (java_home, java_ver))
    print("SDK      :", SDK)
    print("=" * 60, flush=True)

    t = time.time()
    proc = subprocess.Popen([gradlew] + tasks + ["--no-daemon", "--console=plain"],
                            cwd=AND, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", bufsize=1)
    for line in proc.stdout:
        print(line.rstrip(), flush=True)
    proc.wait()
    print("=" * 60)
    print("Gradle rc = %s | 耗時 %.0fs" % (proc.returncode, time.time() - t))

    print("\n=== 產物 ===")
    outs = [
        os.path.join(AND, "app", "build", "outputs", "bundle", "release", "app-release.aab"),
        os.path.join(AND, "app", "build", "outputs", "apk", "release", "app-release.apk"),
    ]
    produced = []
    for p in outs:
        exists = os.path.exists(p)
        print("  %-64s %s" % (os.path.relpath(p, ROOT).replace("\\", "/"),
                              ("%.1f MB" % (os.path.getsize(p) / 1048576)) if exists else "(不存在)"))
        if exists:
            produced.append(p)

    # 簽名驗證：未簽名的包上傳 Google Play 一定會被拒，這裡先自己把關。
    if produced:
        print("\n=== 簽名驗證 ===")
        for p in produced:
            if p.lower().endswith(".apk"):
                ok, detail = verify_apk(p, SDK)
            else:
                ok, detail = verify_signature(p, java_home)
            print("  %-46s %s  %s" % (os.path.basename(p), "✓ 已簽名" if ok else "✗ 未簽名／驗證失敗", detail))

    return proc.returncode


def verify_apk(path, sdk):
    """用 SDK 的 apksigner 驗證 APK 簽名，回傳 (是否通過, 摘要)。

    為何不用 jarsigner：APK 在 minSdk >= 24 時可以只掛 v2 方案、完全不掛 v1
    （本專案就是這樣，見 apksigner 的「Verified using v1 scheme: false」）。
    jarsigner 只認 v1，會把簽好的 APK 誤判為 unsigned，所以 APK 一律走 apksigner。
    """
    import glob
    cands = sorted(glob.glob(os.path.join(sdk, "build-tools", "*", "apksigner.bat")))
    if not cands:
        return False, "(找不到 apksigner，請確認 build-tools 已安裝)"
    apksigner = cands[-1]
    try:
        r = subprocess.run([apksigner, "verify", "--print-certs", "-v", path],
                           capture_output=True, timeout=180)
    except Exception as e:  # noqa: BLE001
        return False, "(驗證異常：%s)" % e

    raw = (r.stdout or b"") + (r.stderr or b"")
    out = None
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            out = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if out is None:
        out = raw.decode("utf-8", errors="replace")

    # apksigner 驗證失敗會回非 0 並印 "DOES NOT VERIFY"
    if r.returncode != 0 or "DOES NOT VERIFY" in out:
        first = next((l.strip() for l in out.splitlines() if l.strip()), "")
        return False, first[:80] or "apksigner 回傳非 0"

    schemes = []
    for name in ("v1", "v2", "v3", "v3.1"):
        m = re.search(r"Verified using %s scheme[^:]*:\s*(true|false)" % re.escape(name), out)
        if m and m.group(1) == "true":
            schemes.append(name)
    dn = ""
    m = re.search(r"certificate DN:\s*(.+)", out)
    if m:
        cn = re.search(r"CN=([^,]+)", m.group(1))
        dn = "簽署者 CN=%s" % cn.group(1).strip() if cn else m.group(1).strip()
    return True, ("%s | 簽名方案 %s" % (dn, "+".join(schemes))) if schemes else dn


def verify_signature(path, java_home):
    """用 JDK 內附的 jarsigner 驗證 v1(JAR) 簽名，回傳 (是否通過, 摘要)。

    坑：jarsigner 在中文 Windows 上會用系統 ANSI 碼頁(GBK)輸出中文訊息
    （「jar 已驗證。／jar 未簽名」），用 UTF-8 解碼會變亂碼，
    令「jar verified」關鍵字永遠匹配不到 → 明明簽好了卻報「未簽名」。
    解法：用 -J-Duser.language=en 強制英文輸出，解碼再加 GBK 退路。
    """
    jarsigner = os.path.join(java_home, "bin", "jarsigner.exe")
    if not os.path.exists(jarsigner):
        return False, "(找不到 jarsigner)"
    try:
        r = subprocess.run(
            [jarsigner, "-J-Duser.language=en", "-J-Duser.country=US",
             "-verify", "-certs", path],
            capture_output=True, timeout=180)
    except Exception as e:  # noqa: BLE001
        return False, "(驗證異常：%s)" % e

    raw = (r.stdout or b"") + (r.stderr or b"")
    out = None
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            out = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if out is None:
        out = raw.decode("utf-8", errors="replace")

    low = out.lower()
    if "jar verified" in low or "jar 已驗證" in out:
        signer = ""
        m = re.search(r"CN=([^,]+)", out)
        if m:
            signer = "簽署者 CN=%s" % m.group(1).strip()
        return True, signer
    if "unsigned" in low or "未簽名" in out:
        return False, "jar is unsigned"
    first = next((l.strip() for l in out.splitlines() if l.strip()), "")
    return False, first[:80]


if __name__ == "__main__":
    sys.exit(main())
