# -*- coding: utf-8 -*-
"""把 `app/privacy.html` 發佈成商店要求嘅「公開可訪問私隱政策網址」。

背景：Google Play 與 App Store 都要求私隱政策有一個**獨立、公開、免登入可訪問**嘅
URL，唔可以只係 App 內頁面。本專案主倉庫 `jyut-fun` 係 PRIVATE，
而免費版 GitHub Pages 唔支援私有倉庫，所以另開一個只放私隱政策頁嘅公開倉庫。

用法：
    python tools/publish_privacy.py --email you@example.com     # 生成 + 推送 + 開 Pages
    python tools/publish_privacy.py --email you@example.com -n  # 只生成本地站台，唔推送
    python tools/publish_privacy.py --status                    # 查 Pages 狀態同網址

副作用（重要）：
    本腳本會同時把電郵寫入 `app/privacy.html`（App 內頁面同網頁必須一致）。
    改完之後要跑 `python tools/sync_assets.py` 再重建 AAB，
    否則 App 內嘅私隱政策仍然係舊內容。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

ROOT = r"D:\Code\cantonese-app"
SRC = os.path.join(ROOT, "app", "privacy.html")
STAGE = os.path.join(ROOT, "dist", "privacy-site")
OWNER = "DragonLuffy9527"
REPO = "jyut-fun-privacy"
BRANCH = "main"

# 兩個佔位符：中文版 + 英文摘要版
PLACEHOLDER_RE = re.compile(
    r'<span class="ph">\[(?:請填入聯絡信箱|please fill in contact email)\]</span>'
)
MAIL_RE = re.compile(r'<a class="mail" href="mailto:[^"]+">[^<]+</a>')

SITE_README = """# 粵.fun 私隱政策 / Privacy Policy

此倉庫只存放 **粵.fun（粵語學習 App）** 的公開私隱政策頁，供 Google Play 與
App Store 審核時訪問。App 本身**完全離線、不收集任何個人資料**。

- 網址：https://{owner}.github.io/{repo}/
- 來源檔：jyut-fun 專案的 `app/privacy.html`（App 內同一份內容）

此頁由 `tools/publish_privacy.py` 自動發佈，請勿直接在此手改 —— 改動會被覆寫。
"""


def sh(cmd, cwd=None, check=True, capture=True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=capture, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        print("!! 指令失敗：%s" % " ".join(cmd))
        print((r.stdout or "") + (r.stderr or ""))
        raise SystemExit(r.returncode)
    return r


def render(email):
    """把 email 寫進 app/privacy.html（冪等），回傳最終 HTML。"""
    with open(SRC, "r", encoding="utf-8") as f:
        html = f.read()

    link = '<a class="mail" href="mailto:%s">%s</a>' % (email, email)
    html_new, n_ph = PLACEHOLDER_RE.subn(link, html)

    if n_ph == 0:
        # 已經填過 → 覆寫成新信箱（同樣冪等）
        html_new, n_mail = MAIL_RE.subn(link, html)
        if n_mail == 0:
            print("!! 找不到聯絡信箱佔位符，也未找到已填的信箱連結。")
            print("   請確認 app/privacy.html 第 10 節仍為：")
            print('   <span class="ph">[請填入聯絡信箱]</span>')
            raise SystemExit(5)
        print("   （原有信箱已更新為 %s，共 %d 處）" % (email, n_mail))
    else:
        print("   （佔位符已替換為 %s，共 %d 處）" % (email, n_ph))

    if html_new != html:
        with open(SRC, "w", encoding="utf-8", newline="\n") as f:
            f.write(html_new)
        print("   已寫回 app/privacy.html")
    else:
        print("   app/privacy.html 無需變更")
    return html_new


def stage(html):
    """把頁面寫到 dist/privacy-site（乾淨重建）。"""
    if os.path.isdir(STAGE):
        shutil.rmtree(STAGE, ignore_errors=True)
    os.makedirs(STAGE)

    files = {
        "index.html": html,
        # 保留原名，方便用 /privacy.html 直接訪問
        "privacy.html": html,
        "README.md": SITE_README.format(owner=OWNER, repo=REPO),
        ".nojekyll": "",  # 停用 Jekyll，避免多餘處理
    }
    for name, content in files.items():
        with open(os.path.join(STAGE, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
    print("   站台已生成：%s（%d 個檔案）" % (STAGE, len(files)))


def ensure_repo():
    r = sh(["gh", "repo", "view", "%s/%s" % (OWNER, REPO),
            "--json", "name,visibility"], check=False)
    if r.returncode == 0:
        info = json.loads(r.stdout)
        print("   倉庫已存在：%s/%s（%s）" % (OWNER, REPO, info.get("visibility")))
        return False
    print("   倉庫不存在，將新建公開倉庫 %s/%s" % (OWNER, REPO))
    return True


def push():
    sh(["git", "init", "-b", BRANCH], cwd=STAGE, check=False)
    sh(["git", "add", "-A"], cwd=STAGE)
    sh(["git", "-c", "user.email=noreply@github.com", "-c", "user.name=" + OWNER,
        "commit", "-m", "publish: 粵.fun 私隱政策頁"], cwd=STAGE, check=False)

    need_create = ensure_repo()
    if need_create:
        sh(["gh", "repo", "create", "%s/%s" % (OWNER, REPO),
            "--public", "--source", ".", "--remote", "origin", "--push",
            "--description", "粵.fun 私隱政策 / Privacy Policy（公開頁，供商店審核）"],
           cwd=STAGE)
    else:
        # 已存在 → 確保有 origin 並強推（此倉庫內容由本腳本全權擁有）
        r = sh(["git", "remote", "get-url", "origin"], cwd=STAGE, check=False)
        if r.returncode != 0:
            sh(["git", "remote", "add", "origin",
                "https://github.com/%s/%s.git" % (OWNER, REPO)], cwd=STAGE)
        sh(["git", "push", "-u", "origin", BRANCH, "--force"], cwd=STAGE)
    print("   已推送到 %s/%s#%s" % (OWNER, REPO, BRANCH))


def enable_pages():
    sh(["gh", "api", "--method", "POST",
        "repos/%s/%s/pages" % (OWNER, REPO),
        "-F", "source[branch]=" + BRANCH, "-F", "source[path]=/"], check=False)
    # 若已啟用會回 409，忽略即可


def pages_status(wait=True, timeout=180):
    url = None
    deadline = time.time() + timeout
    while True:
        r = sh(["gh", "api", "repos/%s/%s/pages" % (OWNER, REPO)], check=False)
        if r.returncode != 0:
            print("   Pages 尚未生效（API 回非 0），稍後再查")
            return None
        info = json.loads(r.stdout)
        url = info.get("html_url")
        st = info.get("status")

        b = sh(["gh", "api", "repos/%s/%s/pages/builds/latest" % (OWNER, REPO)],
               check=False)
        bst = ""
        if b.returncode == 0:
            try:
                bst = json.loads(b.stdout).get("status", "")
            except json.JSONDecodeError:
                pass

        print("   Pages status=%s build=%s url=%s" % (st, bst or "-", url))
        if st == "built" or bst == "built":
            return url
        if not wait or time.time() > deadline:
            return url
        time.sleep(10)


def probe(url):
    """確認頁面真的公開可訪問（HTTP 200）。"""
    r = sh(["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}",
            "-L", "--max-time", "25", url], check=False)
    code = (r.stdout or "").strip()
    print("   HTTP %s  %s" % (code or "?", url))
    return code == "200"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", help="要公開的聯絡信箱")
    ap.add_argument("-n", "--no-push", action="store_true", help="只生成本地站台")
    ap.add_argument("--status", action="store_true", help="只查 Pages 狀態")
    args = ap.parse_args()

    url = "https://%s.github.io/%s/" % (OWNER, REPO)

    if args.status:
        print("== Pages 狀態 ==")
        u = pages_status(wait=False, timeout=0)
        if u or url:
            probe(u or url)
        return 0

    if not args.email:
        print("!! 請用 --email 指定要公開的聯絡信箱")
        return 2
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", args.email):
        print("!! 信箱格式看起來不對：%s" % args.email)
        return 2

    print("== 1. 渲染私隱政策 ==")
    html = render(args.email)

    print("== 2. 生成本地站台 ==")
    stage(html)

    if args.no_push:
        print("\n（--no-push：已略過推送。可用 python -m http.server -d %s 預覽）" % STAGE)
        return 0

    print("== 3. 推送公開倉庫 ==")
    push()

    print("== 4. 啟用 GitHub Pages ==")
    enable_pages()

    print("== 5. 等待上線 ==")
    final = pages_status(wait=True) or url

    print("\n=== 完成 ===")
    print("  公開網址 : %s" % final)
    print("  備用網址 : %sprivacy.html" % final)
    print("\n  下一步（要手動）：")
    print("   ① 把上面網址填進 Google Play「私隱政策」欄位（App Store 同）")
    print("   ② 因為 app/privacy.html 已改，記得同步再重建 App：")
    print("        python tools/sync_assets.py && python tools/_build_android.py")
    print("     否則 App 內嘅政策頁仍係舊內容")
    return 0


if __name__ == "__main__":
    sys.exit(main())
