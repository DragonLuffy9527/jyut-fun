#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Web 資源 → Android assets 同步（取代 `npx cap sync android` 的複製步驟）
=================================================
為何需要這個：`cap sync` 在此環境會**清空目標目錄後卡死**（只複製了 25 個 mp3 就停住），
把 `android/app/src/main/assets/public/` 從 52.8MB 打成 576KB。此腳本改用
逐檔比對（mtime + size）的鏡像複製，可重複執行、可驗證、而且不會卡。

用法：
  python tools/sync_assets.py            # 鏡像複製 + 驗證
  python tools/sync_assets.py --dry-run  # 只列出會做什麼
  python tools/sync_assets.py --no-prune # 不刪除目標端多餘檔案

注意：
  * `cordova.js` / `cordova_plugins.js` 由 Capacitor 產生，不在 app/ 內，
    會被保留，不會被 prune 掉。
  * 完成後仍需自行執行 Gradle 打包（見 tools/_build_android.py）。
"""
import argparse
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "app")
DST = os.path.join(ROOT, "android", "app", "src", "main", "assets", "public")

# 由 Capacitor 產生、app/ 內沒有的檔案，prune 時必須保留
KEEP = {"cordova.js", "cordova_plugins.js", "native-bridge.js"}
# 必要存在的產物，用來確認同步真的完成
EXPECT = ["index.html", "manifest.json", "privacy.html", "sw.js", "content/curriculum.json"]


def walk(base):
    out = {}
    for dp, _, fns in os.walk(base):
        for fn in fns:
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, base).replace("\\", "/")
            out[rel] = p
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-prune", action="store_true")
    args = ap.parse_args()

    if not os.path.isdir(SRC):
        print("✗ 來源不存在：" + SRC)
        return 1
    os.makedirs(DST, exist_ok=True)

    src = walk(SRC)
    dst = walk(DST)
    print("來源 %s：%d 檔 / %.1f MB" % (SRC, len(src), sum(os.path.getsize(p) for p in src.values()) / 1048576))
    print("目標 %s：%d 檔" % (DST, len(dst)))
    print()

    copied = skipped = 0
    t0 = time.time()
    for i, (rel, sp) in enumerate(sorted(src.items()), 1):
        dp = os.path.join(DST, rel.replace("/", os.sep))
        need = True
        if os.path.exists(dp):
            ss, ds = os.stat(sp), os.stat(dp)
            need = (ss.st_size != ds.st_size) or (int(ss.st_mtime) != int(ds.st_mtime))
        if not need:
            skipped += 1
            continue
        if args.dry_run:
            copied += 1
            continue
        os.makedirs(os.path.dirname(dp), exist_ok=True)
        shutil.copy2(sp, dp)
        copied += 1
        if i % 500 == 0:
            print("  ... %d/%d  (已複製 %d, 略過 %d)" % (i, len(src), copied, skipped), flush=True)

    removed = 0
    if not args.no_prune:
        for rel, dp in sorted(dst.items()):
            if rel in src:
                continue
            if os.path.basename(rel) in KEEP:
                continue
            if args.dry_run:
                removed += 1
                continue
            os.remove(dp)
            removed += 1

    dt = time.time() - t0
    print("\n複製 %d 檔、略過（內容相同）%d 檔、移除多餘 %d 檔，耗時 %.1f 秒%s"
          % (copied, skipped, removed, dt, "（dry-run，未實際寫入）" if args.dry_run else ""))

    if args.dry_run:
        return 0

    # ---------------- 驗證 ----------------
    print("\n=== 驗證 ===")
    ok = True
    after = walk(DST)
    print("  目標檔案數 ......... %d" % len(after))
    exp_n = len(src) + len([k for k in dst if os.path.basename(k) in KEEP and k not in src])
    if len(after) != exp_n:
        print("  ✗ 檔案數不符（預期 %d）" % exp_n)
        ok = False
    n_mp3 = sum(1 for r in after if r.endswith(".mp3"))
    n_char = sum(1 for r in after if r.startswith("audio/chars/"))
    print("  mp3 總數 ........... %d（課程 %d + 單字 %d）" % (n_mp3, n_mp3 - n_char, n_char))
    if n_mp3 != 3311:
        print("  ✗ mp3 數量不是 3311")
        ok = False
    for rel in EXPECT:
        p = os.path.join(DST, rel.replace("/", os.sep))
        good = os.path.exists(p)
        print("  %-24s %s" % (rel, "✓" if good else "✗ 缺"))
        if not good:
            ok = False
    for k in KEEP:
        if os.path.exists(os.path.join(DST, k)):
            print("  %-24s ✓ 保留" % k)
    size_mb = sum(os.path.getsize(p) for p in after.values()) / 1048576
    print("  總大小 ............. %.1f MB" % size_mb)
    print("\n" + ("✓ 同步完成且驗證通過" if ok else "✗ 驗證失敗，請檢查上方項目"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
