# -*- coding: utf-8 -*-
"""Android 上傳金鑰離線備份打包工具。

背景：`android/upload-keystore.jks` 與 `android/keystore.properties` 已刻意排除在
版控之外（見 .gitignore）。這意味著它們**只存在於本機磁碟**。一旦遺失，
就永遠無法再更新已上架的 App —— 只能換包名重新上架，舊用戶無法升級。

本工具把兩個檔案 + 還原說明 + 校驗值打成一個 zip，方便複製到多處離線儲存。

用法：
    python tools/backup_keystore.py              # 打包到 dist/keystore-backup/
    python tools/backup_keystore.py --force      # 覆蓋同日期的舊備份
    python tools/backup_keystore.py --show       # 只印憑證資訊，不打包

輸出：
    dist/keystore-backup/jyutfun-keystore-backup-YYYY-MM-DD.zip
    並在 stdout 印出憑證指紋（上架時各渠道要填的就是這個 SHA-256）。
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")

ROOT = r"D:\Code\cantonese-app"
AND = os.path.join(ROOT, "android")
OUT_DIR = os.path.join(ROOT, "dist", "keystore-backup")

JKS = os.path.join(AND, "upload-keystore.jks")
PROPS = os.path.join(AND, "keystore.properties")

JDK_GLOBS = [
    os.path.expanduser(r"~\.workbuddy\binaries\jdk*\jdk-*"),
    os.path.expanduser(r"~\.workbuddy\binaries\jdk*\*"),
    r"C:\Program Files\Eclipse Adoptium\jdk-*",
    r"C:\Program Files\Java\jdk-*",
]


def find_keytool():
    """找出可用的 keytool（優先 JDK 21+，也是建置用的那套）。"""
    import glob
    best = None
    for pat in JDK_GLOBS:
        for home in glob.glob(pat):
            kt = os.path.join(home, "bin", "keytool.exe")
            if not os.path.isfile(kt):
                continue
            release = os.path.join(home, "release")
            major = 0
            try:
                with open(release, "r", encoding="utf-8", errors="replace") as f:
                    m = re.search(r'JAVA_VERSION="(\d+)', f.read())
                major = int(m.group(1)) if m else 0
            except OSError:
                pass
            # 挑版本最高的（不用 sorted 因為 keytool 路徑本身不代表版本）
            if major >= 21 and (best is None or major > best[0]):
                best = (major, kt)
    return best


def read_props(path):
    """讀 keystore.properties -> dict（Java properties 極簡解析）。"""
    d = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip()
    return d


def cert_info(keytool, props):
    """跑 keytool -list -v 取主體與指紋。keytool 輸出編碼混亂，故用 bytes 解碼。"""
    # 強制英文輸出：中文 keytool 訊息的編碼隨系統 locale 變動，會解析失敗。
    cmd = [keytool, "-J-Duser.language=en", "-J-Duser.country=US",
           "-list", "-v",
           "-keystore", JKS,
           "-storepass", props["storePassword"],
           "-alias", props["keyAlias"]]
    r = subprocess.run(cmd, capture_output=True, timeout=60)
    raw = r.stdout or b""
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            txt = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        txt = raw.decode("utf-8", errors="replace")

    def grab(label):
        m = re.search(label + r"\s*:\s*(.+)", txt)
        return m.group(1).strip() if m else ""

    # 有效期：英文 keytool 是「Valid from: X until: Y」；中文是「有效期: 从 X 到 Y」
    valid = ""
    m = re.search(r"Valid from:\s*(.+?)\s*until:\s*(.+)", txt)
    if m:
        valid = "%s → %s" % (m.group(1).strip(), m.group(2).strip())
    else:
        m = re.search(r"(?:有效期|Valid)\s*[:：]\s*从\s*(.+?)\s*到\s*(.+)", txt)
        if m:
            valid = "%s → %s" % (m.group(1).strip(), m.group(2).strip())

    return {
        "owner": grab(r"(?:所有者|Owner)"),
        "valid": valid,
        "algo": grab(r"(?:签名算法名称|Signature algorithm name|公開金鑰演算法|Public Key Algorithm)"),
        "sha1": grab(r"SHA1:\s*([0-9A-F:]+)") or grab(r"SHA1"),
        "sha256": grab(r"SHA256:\s*([0-9A-F:]+)") or grab(r"SHA256"),
        "raw": txt,
    }

README = """粵.fun — Android 上傳簽名金鑰備份
產生時間：{ts}

═══ 這個壓縮檔是什麼 ═══
Google Play / 各安卓渠道對同一包名的 App，只認「第一次上傳時的簽名金鑰」。
本包內的 upload-keystore.jks 就是這支金鑰。**遺失即永久無法更新 App** ——
你只能改包名重新上架，舊用戶拿不到升級。

═══ 內容物 ═══
  upload-keystore.jks      簽名金鑰庫（JKS）
  keystore.properties      Gradle 讀取的設定（含密碼、別名）
  README.txt               本說明
  SHA256SUMS.txt           上述檔案的校驗值，還原後可用來確認沒損毀

═══ 還原方式 ═══
把 upload-keystore.jks 與 keystore.properties 一起複製回專案的 android/ 目錄，
然後跑 python tools/_build_android.py 即可重建已簽名的 AAB/APK。

═══ 金鑰資訊 ═══
  別名 (alias)      : {alias}
  金鑰庫密碼         : {storepass}
  金鑰密碼           : {keypass}
  憑證主體           : {owner}
  有效期             : {valid}
  憑證 SHA-1         : {sha1}
  憑證 SHA-256       : {sha256}
  金鑰庫檔案 SHA-256 : {jkssum}

憑證 SHA-256 就是上架各渠道（Google Play 應用簽署、國內渠道、以及日後
App Links / 微信 SDK 等需要指紋的地方）要填的值，請一併記進密碼管理器。

═══ 保存要求 ═══
★ 本壓縮檔內含簽名密碼，等同「App 發佈權」，不可放在公開位置。
★ 至少放兩處離線儲存：加密隨身碟 + 密碼管理器（如 1Password / Bitwarden 附件）。
★ 密碼另外抄一份在紙上／另一個密碼管理器，不要與金鑰同處存放。
★ 不要提交進 git（.gitignore 已擋 *.jks / keystore.properties）。
"""


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    force = "--force" in sys.argv
    show_only = "--show" in sys.argv

    for p in (JKS, PROPS):
        if not os.path.isfile(p):
            print("!! 找不到 %s" % p)
            print("   金鑰不在本機 → 若先前有備份，請先還原再重跑。")
            return 2

    found = find_keytool()
    if not found:
        print("!! 找不到 JDK 21+ 的 keytool")
        return 3
    java_ver, keytool = found
    print("keytool  : %s (Java %s)" % (keytool, java_ver))

    props = read_props(PROPS)
    need = ("storeFile", "storePassword", "keyAlias", "keyPassword")
    missing = [k for k in need if k not in props]
    if missing:
        print("!! keystore.properties 缺少欄位：%s" % ", ".join(missing))
        return 4
    if props["storeFile"].replace("\\", "/") != "upload-keystore.jks":
        print("!! storeFile 不指向 upload-keystore.jks（實際：%s），請自行確認路徑。"
              % props["storeFile"])

    info = cert_info(keytool, props)
    if not info["owner"]:
        print("!! keytool 讀不到憑證主體 —— 密碼或別名可能不對。")
        print(info["raw"][:500])
        return 5

    jkssum = sha256_file(JKS)
    print("憑證主體 : %s" % info["owner"])
    print("有效期   : %s" % info["valid"])
    print("SHA-1    : %s" % info["sha1"])
    print("SHA-256  : %s" % info["sha256"])
    print("JKS 檔指紋: %s" % jkssum)

    if show_only:
        return 0

    import datetime
    stamp = datetime.date.today().isoformat()
    os.makedirs(OUT_DIR, exist_ok=True)

    readme = README.format(
        ts=stamp, alias=props["keyAlias"],
        storepass=props["storePassword"], keypass=props["keyPassword"],
        owner=info["owner"], valid=info["valid"],
        sha1=info["sha1"], sha256=info["sha256"], jkssum=jkssum,
    )
    sums = "".join(
        "%s  %s\n" % (sha256_file(p), os.path.basename(p)) for p in (JKS, PROPS)
    )

    # (zip 內檔名, 來源路徑 or None, 文字內容 or None)
    entries = [
        ("upload-keystore.jks", JKS, None),
        ("keystore.properties", PROPS, None),
        # 檔名刻意用 ASCII：舊版 Info-ZIP 不認 UTF-8 檔名旗標，中文名會變亂碼
        ("README.txt", None, readme),
        ("SHA256SUMS.txt", None, sums),
    ]

    zip_path = os.path.join(OUT_DIR, "jyutfun-keystore-backup-%s.zip" % stamp)
    if os.path.exists(zip_path) and not force:
        print("\n!! 已存在 %s（要覆蓋請加 --force）" % zip_path)
        return 6

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, src, text in entries:
            if src is not None:
                z.write(src, name)
            else:
                z.writestr(name, text.encode("utf-8"))

    zsum = sha256_file(zip_path)
    size = os.path.getsize(zip_path)
    print("\n=== 備份包 ===")
    print("  路徑   : %s" % zip_path)
    print("  大小   : %.1f KB（含 %d 個檔案）" % (size / 1024, len(entries)))
    print("  SHA-256: %s" % zsum)

    print("\n=== 接下來請你手動做（無法自動化） ===")
    print("  1. 把上面這個 zip 複製到至少兩處離線位置：")
    print("       - 加密隨身碟／外接硬碟")
    print("       - 密碼管理器附件（1Password / Bitwarden / KeePass）")
    print("  2. 把上面「金鑰庫密碼／別名／憑證 SHA-256」另外抄一份，")
    print("     與 zip 分開存放（同處遺失等於一起沒了）。")
    print("  3. 還原測試：解壓到別的目錄，用 keytool -list 確認讀得出來。")
    print("  ★ 這個 zip 不能進 git，也不能放雲端硬碟的一般資料夾。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
