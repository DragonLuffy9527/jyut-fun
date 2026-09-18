#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
準備 iOS 工程（純 Windows 可跑，唔需要 Mac）。

Capacitor 的 iOS 模板係隨 CLI 打包嘅（node_modules/@capacitor/cli/assets/
ios-pods-template.tar.gz），解壓同修改都唔需要 macOS —— 只有 `pod install`
同 `xcodebuild` 先要。所以本腳本負責把工程「離線備好並客製化」，
雲端 CI 就只需要做 pod install + 編譯。

做嘅事（全部冪等，可重複跑）：
  1. 若 ios/ 不存在 → 從模板解壓
  2. 修 Info.plist：
       - CFBundleDisplayName: My App → 粵.fun
       - 補 ITSAppUsesNonExemptEncryption=false（否則每次上傳都要答出口合規問題）
       - UIRequiredDeviceCapabilities: armv7 → arm64（iOS 15+ 全係 64 位元）
       - 補 CFBundleLocalizations（en / zh-Hant / zh-Hans）
  3. 寫 App 級 PrivacyInfo.xcprivacy
       （@capacitor/preferences 用 UserDefaults.standard → 宣告 CA92.1）
  4. 改 project.pbxproj：
       - 把 PrivacyInfo.xcprivacy 加入 Copy Bundle Resources
       - PRODUCT_BUNDLE_IDENTIFIER: com.getcapacitor.App → com.jyutfun.app
       - TARGETED_DEVICE_FAMILY: "1,2" → "1"（只做 iPhone，免 iPad 截圖矩陣）
  5. 換 App 圖示同啟動圖（由 resources/ 生成）
  6. 自我檢查

用法：
  python tools/ios_setup.py              # 全部套用
  python tools/ios_setup.py --check      # 只檢查現狀，唔改動
  python tools/ios_setup.py --with-ipad  # 額外支援 iPad（TARGETED_DEVICE_FAMILY=1,2）
"""

import argparse
import os
import plistlib
import re
import shutil
import sys
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IOS = os.path.join(ROOT, "ios")
TEMPLATE = os.path.join(
    ROOT, "node_modules", "@capacitor", "cli", "assets", "ios-pods-template.tar.gz"
)

INFO_PLIST = os.path.join(IOS, "App", "App", "Info.plist")
PBXPROJ = os.path.join(IOS, "App", "App.xcodeproj", "project.pbxproj")
PRIVACY = os.path.join(IOS, "App", "App", "PrivacyInfo.xcprivacy")
ASSETS = os.path.join(IOS, "App", "App", "Assets.xcassets")
APPICON = os.path.join(ASSETS, "AppIcon.appiconset", "AppIcon-512@2x.png")
SPLASH_DIR = os.path.join(ASSETS, "Splash.imageset")

# pbxproj 用嘅物件 ID（24 位十六進位，唔會同模板現有 ID 撞）
ID_BUILDFILE = "A1B2C3D4E5F60718293A4B5C"
ID_FILEREF = "A1B2C3D4E5F60718293A4B5D"

DISPLAY_NAME = "粵.fun"
BUNDLE_ID = "com.jyutfun.app"

PRIVACY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
\t<key>NSPrivacyTracking</key>
\t<false/>
\t<key>NSPrivacyTrackingDomains</key>
\t<array/>
\t<key>NSPrivacyCollectedDataTypes</key>
\t<array/>
\t<key>NSPrivacyAccessedAPITypes</key>
\t<array>
\t\t<dict>
\t\t\t<key>NSPrivacyAccessedAPIType</key>
\t\t\t<string>NSPrivacyAccessedAPICategoryUserDefaults</string>
\t\t\t<key>NSPrivacyAccessedAPITypeReasons</key>
\t\t\t<array>
\t\t\t\t<string>CA92.1</string>
\t\t\t</array>
\t\t</dict>
\t</array>
</dict>
</plist>
"""


def say(msg=""):
    print(msg, flush=True)


def ok(flag):
    return "✓" if flag else "✗"


# ────────────────────────────── 1. 解壓模板 ──────────────────────────────

def ensure_template(apply_changes):
    if os.path.exists(PBXPROJ):
        say("  ios/ 工程已存在，只套用修補")
        return True
    if not os.path.exists(TEMPLATE):
        say("  ✗ 找唔到模板：%s" % TEMPLATE)
        say("    請先執行：npm install")
        return False
    if not apply_changes:
        say("  ✗ ios/ 不存在（--check 模式唔會建立）")
        return False
    say("  從 CLI 內附模板解壓 ios/ …")
    os.makedirs(IOS, exist_ok=True)
    with tarfile.open(TEMPLATE, "r:gz") as tf:
        try:
            tf.extractall(IOS, filter="data")  # Python 3.12+：避免棄用警告
        except TypeError:
            tf.extractall(IOS)
    say("  ✓ 已建立 %d 個檔案" % sum(len(f) for _, _, f in os.walk(IOS)))
    return True


# ──────────────────────────── 2. Info.plist ────────────────────────────

def patch_info_plist(apply_changes):
    if not os.path.exists(INFO_PLIST):
        say("  ✗ 找唔到 Info.plist")
        return False
    with open(INFO_PLIST, "rb") as f:
        pl = plistlib.load(f)

    changes = []

    if pl.get("CFBundleDisplayName") != DISPLAY_NAME:
        changes.append("CFBundleDisplayName: %r → %r" % (pl.get("CFBundleDisplayName"), DISPLAY_NAME))
        pl["CFBundleDisplayName"] = DISPLAY_NAME

    # 出口合規：唔宣告就會在每次上傳後被 Apple 追問，妨礙 TestFlight 自動化
    if pl.get("ITSAppUsesNonExemptEncryption") is not False:
        changes.append("ITSAppUsesNonExemptEncryption: (無) → False")
        pl["ITSAppUsesNonExemptEncryption"] = False

    caps = pl.get("UIRequiredDeviceCapabilities")
    if caps == ["armv7"]:
        changes.append("UIRequiredDeviceCapabilities: [armv7] → [arm64]")
        pl["UIRequiredDeviceCapabilities"] = ["arm64"]

    locs = ["en", "zh-Hant", "zh-Hans"]
    if pl.get("CFBundleLocalizations") != locs:
        changes.append("CFBundleLocalizations → %s" % locs)
        pl["CFBundleLocalizations"] = locs

    if not changes:
        say("  ✓ 已是最新，無需修改")
        return True

    for c in changes:
        say("    · %s" % c)
    if apply_changes:
        with open(INFO_PLIST, "wb") as f:
            plistlib.dump(pl, f, fmt=plistlib.FMT_XML, sort_keys=False)
        say("  ✓ 已寫入 %d 項修改" % len(changes))
    return True


# ─────────────────────────── 3. 隱私清單 ───────────────────────────

def write_privacy_manifest(apply_changes):
    # 一律用 LF。Xcode 唔理行尾，但如果比對時把 want 轉成 os.linesep（Windows
    # 係 CRLF）而寫入卻用 LF，兩邊永遠唔相等 —— 每次跑都報「內容有差異」，
    # 令工具輸出不可信，git 亦易生無謂 diff。
    if os.path.exists(PRIVACY):
        with open(PRIVACY, "r", encoding="utf-8", newline="") as f:
            cur = f.read()
        if cur.replace("\r\n", "\n").strip() == PRIVACY_XML.strip():
            say("  ✓ 已存在且內容一致")
            return True
        say("    · 內容有差異，重寫")
    else:
        say("    · 新增 PrivacyInfo.xcprivacy（宣告 UserDefaults / CA92.1）")
    if apply_changes:
        with open(PRIVACY, "w", encoding="utf-8", newline="\n") as f:
            f.write(PRIVACY_XML)
        say("  ✓ 已寫入")
    return True


# ─────────────────────────── 4. project.pbxproj ───────────────────────────

def patch_pbxproj(apply_changes, with_ipad):
    if not os.path.exists(PBXPROJ):
        say("  ✗ 找唔到 project.pbxproj")
        return False
    with open(PBXPROJ, "r", encoding="utf-8", newline="") as f:
        src = f.read()
    nl = "\r\n" if "\r\n" in src else "\n"
    txt = src

    def sub_once(text, old, new, label):
        if old not in text:
            if new in text:
                say("    · %s：已是目標值" % label)
                return text, False
            say("    ✗ %s：找唔到預期字串，跳過（請人手檢查）" % label)
            return text, False
        say("    · %s" % label)
        return text.replace(old, new, 1), True

    def sub_all(text, old, new, label):
        """取代**全部**出現位置。

        用於「每個 build configuration 都必須一致」嘅設定。pbxproj 入面
        Debug 同 Release 各有一份 buildSettings，只改第一處會令 Release
        （＝雲端歸檔實際用嘅）仍然帶住模板預設值，令歸檔或上傳失敗。
        """
        n = text.count(old)
        if n == 0:
            if new in text:
                say("    · %s：已是目標值" % label)
                return text, False
            say("    ✗ %s：找唔到預期字串，跳過（請人手檢查）" % label)
            return text, False
        say("    · %s（%d 處）" % (label, n))
        return text.replace(old, new), True

    # 4a. 資源清單加入隱私清單
    if "PrivacyInfo.xcprivacy" not in txt:
        txt = txt.replace(
            "/* End PBXBuildFile section */",
            "\t\t%s /* PrivacyInfo.xcprivacy in Resources */ = {isa = PBXBuildFile; "
            "fileRef = %s /* PrivacyInfo.xcprivacy */; };%s"
            "/* End PBXBuildFile section */" % (ID_BUILDFILE, ID_FILEREF, nl),
            1,
        )
        txt = txt.replace(
            "/* End PBXFileReference section */",
            "\t\t%s /* PrivacyInfo.xcprivacy */ = {isa = PBXFileReference; "
            "lastKnownFileType = text.xml; path = PrivacyInfo.xcprivacy; "
            "sourceTree = \"<group>\"; };%s"
            "/* End PBXFileReference section */" % (ID_FILEREF, nl),
            1,
        )
        txt = txt.replace(
            "\t\t\t\t504EC3131FED79650016851F /* Info.plist */,",
            "\t\t\t\t504EC3131FED79650016851F /* Info.plist */,"
            "%s\t\t\t\t%s /* PrivacyInfo.xcprivacy */," % (nl, ID_FILEREF),
            1,
        )
        txt = txt.replace(
            "\t\t\t\t504EC3121FED79650016851F /* LaunchScreen.storyboard in Resources */,",
            "\t\t\t\t504EC3121FED79650016851F /* LaunchScreen.storyboard in Resources */,"
            "%s\t\t\t\t%s /* PrivacyInfo.xcprivacy in Resources */," % (nl, ID_BUILDFILE),
            1,
        )
        say("    · 資源清單加入 PrivacyInfo.xcprivacy")
    else:
        say("    · 隱私清單：已在資源清單內")

    # 4b. Bundle ID —— 必須 Debug 與 Release 同時改，否則 Release 歸檔
    #     會用住模板值 com.getcapacitor.App，簽名／上傳一定失敗。
    txt, _ = sub_all(
        txt,
        "PRODUCT_BUNDLE_IDENTIFIER = com.getcapacitor.App;",
        "PRODUCT_BUNDLE_IDENTIFIER = %s;" % BUNDLE_ID,
        "Bundle ID → %s" % BUNDLE_ID,
    )
    # 兜底：模板若改用其他寫法，殘留一律清走
    leftover = txt.count("com.getcapacitor.App")
    if leftover:
        txt = txt.replace("com.getcapacitor.App", BUNDLE_ID)
        say("    · 清走模板殘留 Bundle ID（%d 處）" % leftover)

    # 4c. 目標裝置
    want_family = '"1,2"' if with_ipad else '"1"'
    if 'TARGETED_DEVICE_FAMILY = "1,2";' in txt and not with_ipad:
        txt = txt.replace('TARGETED_DEVICE_FAMILY = "1,2";', 'TARGETED_DEVICE_FAMILY = "1";')
        say("    · TARGETED_DEVICE_FAMILY → \"1\"（只做 iPhone，免 iPad 截圖矩陣）")
    elif 'TARGETED_DEVICE_FAMILY = "1";' in txt and with_ipad:
        txt = txt.replace('TARGETED_DEVICE_FAMILY = "1";', 'TARGETED_DEVICE_FAMILY = "1,2";')
        say("    · TARGETED_DEVICE_FAMILY → \"1,2\"（同時支援 iPad）")
    else:
        say("    · TARGETED_DEVICE_FAMILY：已是 %s" % want_family)

    if txt == src:
        say("  ✓ 無改動")
        return True

    # 檢查改完仍然平衡
    if txt.count("/* Begin PBXBuildFile section */") != 1 or txt.count(
        "/* End PBXBuildFile section */"
    ) != 1:
        say("  ✗ 改動後結構異常，已中止（未寫入）")
        return False

    if apply_changes:
        with open(PBXPROJ, "w", encoding="utf-8", newline="") as f:
            f.write(txt)
        say("  ✓ 已寫入")
    return True


# ────────────────────────────── 5. 圖示與啟動圖 ──────────────────────────────

def copy_assets(apply_changes):
    try:
        from PIL import Image
    except ImportError:
        say("  ✗ 需要 Pillow：pip install Pillow")
        return False

    icon_src = os.path.join(ROOT, "resources", "icon.png")
    splash_src = os.path.join(ROOT, "resources", "splash.png")

    jobs = []
    if os.path.exists(icon_src):
        jobs.append((icon_src, APPICON, (1024, 1024), "App 圖示 1024×1024"))
    else:
        say("  ✗ 找唔到 resources/icon.png")

    if os.path.exists(splash_src):
        for name in ("splash-2732x2732.png", "splash-2732x2732-1.png", "splash-2732x2732-2.png"):
            jobs.append((splash_src, os.path.join(SPLASH_DIR, name), (2732, 2732), "啟動圖 %s" % name))
    else:
        say("  ✗ 找唔到 resources/splash.png")

    if not jobs:
        return False

    for src, dst, size, label in jobs:
        im = Image.open(src)
        # App Store 圖示禁止 alpha 通道 —— 強制轉 RGB 並確認
        if im.mode != "RGB":
            im = im.convert("RGB")
        if im.size != size:
            im = im.resize(size, Image.LANCZOS)
        same = os.path.exists(dst) and _same_bytes(dst, src, size) if False else False
        if apply_changes:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            im.save(dst, "PNG", optimize=True)
        say("    · %-26s %s  mode=RGB（無 alpha）" % (label, "已寫入" if apply_changes else "(預覽)"))

    # 確認真嘅無 alpha
    if apply_changes and os.path.exists(APPICON):
        check = Image.open(APPICON)
        say("  ✓ App 圖示實測：%s mode=%s（App Store 要求無 alpha）" % (check.size, check.mode))
    return True


# ────────────────────────────── 6. 自我檢查 ──────────────────────────────

def verify(with_ipad):
    say("")
    say("═" * 60)
    say(" 自我檢查")
    say("═" * 60)
    problems = []

    # Info.plist
    try:
        with open(INFO_PLIST, "rb") as f:
            pl = plistlib.load(f)
        say("  Info.plist")
        for key, want in (
            ("CFBundleDisplayName", DISPLAY_NAME),
            ("ITSAppUsesNonExemptEncryption", False),
            ("UIRequiredDeviceCapabilities", ["arm64"]),
        ):
            got = pl.get(key, "(缺)")
            flag = got == want
            say("    %s %-32s %s" % (ok(flag), key, got))
            if not flag:
                problems.append("Info.plist %s" % key)
    except Exception as e:  # noqa: BLE001
        problems.append("Info.plist 讀唔到：%s" % e)
        say("    ✗ 讀唔到 Info.plist：%s" % e)

    # 隱私清單
    say("  PrivacyInfo.xcprivacy")
    if os.path.exists(PRIVACY):
        with open(PRIVACY, "rb") as f:
            pv = plistlib.load(f)
        used = pv.get("NSPrivacyAccessedAPITypes", [])
        names = [d.get("NSPrivacyAccessedAPIType") for d in used]
        say("    ✓ 存在；宣告 API：%s" % (", ".join(names) or "（無）"))
        say("    ✓ 收集資料：%d 項；追蹤：%s" % (
            len(pv.get("NSPrivacyCollectedDataTypes", [])), pv.get("NSPrivacyTracking")))
    else:
        problems.append("缺少 PrivacyInfo.xcprivacy")
        say("    ✗ 不存在")

    # pbxproj
    with open(PBXPROJ, "r", encoding="utf-8", errors="replace") as f:
        pb = f.read()
    say("  project.pbxproj")
    # 每個 build configuration（Debug / Release）都必須指向同一個 Bundle ID。
    # 只查 `in` 是攔不住「只改咗 Debug、Release 仍然係模板值」嘅情況 —— 那正是
    # 雲端歸檔（用 Release）失敗而本機看似無事嘅成因，所以這裡逐個值核對。
    ids = [v.strip() for v in re.findall(r"PRODUCT_BUNDLE_IDENTIFIER = ([^;]+);", pb)]
    ids_ok = bool(ids) and all(v == BUNDLE_ID for v in ids)
    checks = [
        ("隱私清單已入資源", "PrivacyInfo.xcprivacy in Resources" in pb),
        ("Bundle ID 全部 config = %s（%d 處）" % (BUNDLE_ID, len(ids)), ids_ok),
        ("無模板殘留 com.getcapacitor.App", "com.getcapacitor.App" not in pb),
        ("目標裝置 = %s" % ('"1,2"' if with_ipad else '"1"'),
         ("TARGETED_DEVICE_FAMILY = %s;" % ('"1,2"' if with_ipad else '"1"')) in pb),
        ("部署目標 = 15.0", "IPHONEOS_DEPLOYMENT_TARGET = 15.0;" in pb),
    ]
    for label, flag in checks:
        say("    %s %s" % (ok(flag), label))
        if not flag:
            problems.append("pbxproj：%s" % label)

    # 圖示
    say("  圖示 / 啟動圖")
    try:
        from PIL import Image
        ic = Image.open(APPICON)
        good = ic.size == (1024, 1024) and ic.mode == "RGB"
        say("    %s %s mode=%s" % (ok(good), ic.size, ic.mode))
        if not good:
            problems.append("App 圖示規格不符")
        n = len([x for x in os.listdir(SPLASH_DIR) if x.endswith(".png")])
        say("    %s 啟動圖 %d 張" % (ok(n >= 3), n))
    except Exception as e:  # noqa: BLE001
        problems.append("圖示檢查失敗：%s" % e)
        say("    ✗ %s" % e)

    say("")
    if problems:
        say(" 結論：%d 項待處理" % len(problems))
        for p in problems:
            say("   - %s" % p)
        return 1
    say(" 結論：iOS 工程已就緒，可以在雲端 CI 上 pod install + 編譯")
    return 0


def main():
    ap = argparse.ArgumentParser(description="準備 iOS 工程（Windows 可跑）")
    ap.add_argument("--check", action="store_true", help="只檢查，唔改動")
    ap.add_argument("--with-ipad", action="store_true", help="同時支援 iPad")
    args = ap.parse_args()
    do = not args.check

    say("═" * 60)
    say(" 準備 iOS 工程%s" % ("（只檢查）" if args.check else ""))
    say("═" * 60)

    say("\n[1/5] 模板")
    if not ensure_template(do):
        return 1

    say("\n[2/5] Info.plist")
    patch_info_plist(do)

    say("\n[3/5] 隱私清單")
    write_privacy_manifest(do)

    say("\n[4/5] Xcode 工程設定")
    patch_pbxproj(do, args.with_ipad)

    say("\n[5/5] 圖示與啟動圖")
    copy_assets(do)

    if args.check:
        say("\n（--check 模式：未寫入任何變更）")
    return verify(args.with_ipad)


if __name__ == "__main__":
    sys.exit(main())
