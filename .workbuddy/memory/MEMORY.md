# 粵.fun 项目长期备注

## 产品方向（2026-09-18 重大转向）
- 粤语学习 App。**已放弃基于 PDF 教材及其配套音频的全部路线**（版权风险 + OCR 固有错字 + 音频无逐句切分 + 学习路径错配）。
- **现方案：100% 原创场景课程 + 自产粤语配音**，无第三方版权负担。
- 用户偏好：UI 可爱、不死板（奶油色系 + 戴耳机小橘猫吉祥物）；搭配小游戏学习；边做边迭代，不追求一次性定型；**非常重视发音/拼音准确性，不能误导学习者**。
- 技术路线（2026-09-18 定案）：HTML 原型（`app/index.html`，本地预览 `python -m http.server 8777 --directory app`）**已完成全部内容验证，不再迁 Flutter**，改用 **Capacitor 8.5.2 包壳**为 iOS/Android 原生应用。理由：本案是「静态内容 + 本地音档」形态、零重原生依赖，重写等于作废全部验证成果。仅当日后要加跟读评分等重原生功能时才重新评估 Flutter。

## 课程体系（现行）
- **6 领域 66 课**：基礎發音 4 / 生活日常 12 / 學習進修 6 / 職場工作 8 / **香港建築業 18** / **香港醫療業 18**；难度 L1–L3。
- 每课结构：場景 + 目標×3 + 核心句×6–7 + 對話×6–8 + 詞彙×8–10 + 貼士×3–4 + 即學即練×2–3。
- 累计：**438 核心句 / 468 对话句 / 600 词汇 / 1572 段课程音档**；单字库 **1659 字 / 1739 音档**。

## 关键资产与文件（现行）
- `tools/curriculum/{basic,life,study,work,construction,medical}.json` — 课程原稿。**只写汉字 + 普通话对译，不手写粤拼**。
- `tools/build_curriculum.py` — 合并各领域 → 自动标注粤拼 → 产出 `app/content/curriculum.json` + `tools/audio_manifest.json`；含 `WORD_OVERRIDES` 词级读音覆盖表；会打印「手写 vs 词库」差异报告。
- `tools/gen_audio.py` — edge-tts 并发(6)生成 `app/audio/*.mp3`，断点续跑。命名：`{课号}-c{n}` / `-d{n}` / `-v{n}` / `-df`（完整对话）。对话男女双声（A 女 HiuMaan / B 男 WanLung / C 女 HiuGaai），核心句与词汇用 HiuMaan（词 −18%、句 −10% 语速）；`-df` 由逐句 MP3 字节拼接。
- `tools/gen_char_audio.py` — 生成单字发音库 `app/audio/chars/` + 索引 `app/content/char_audio.json`，令点读完全不依赖系统粤语音色。可断点续跑。
- `tools/verify_audio.py` — **源目录**发音资产体检（单字库/课程音档完整性 + 模拟前端路由算覆盖率 + 分领域覆盖表）。
- `tools/verify_bundle.py` — **打包产物**（.aab/.apk）资源完整性终检。与 `verify_audio.py` 分工不同：前者查 `app/` 源，后者查已封装的包。做法是**引用闭环**（非数档数）：`curriculum.json` 每课 `clips[]` → `audio/<clip>.mp3`；`char_audio.json` 每字 `d`/`r[]` → `audio/chars/<name>.mp3`；再与源 `app/` 双向差集比对 + 孤兒音档 + 关键产物 + 已知修复（TTS.noApi／隐私页信箱）。**已接入 `_build_android.py`**，建置後自動跑，失敗輸出完整報告並回傳非 0 —— 防的是「簽名正確、能裝能開，但音檔沒進包」這類事故（`cap sync` 卡死曾把 `assets/public` 清到只剩 25 段音檔）。支援 `--quiet`（只印錯誤）。
- **音檔路徑約定（寫碼時別猜）**：所有 mp3 都在 `assets/public/audio/` 下（單字庫是子目錄 `audio/chars/`）。課程 `audio.src='audio/'+clipId+'.mp3'`；單字 `charAudio.src='audio/chars/'+f+'.mp3'`。資料端：課程用 `clips:["basic-01-c1"]`（**無副檔名**），單字用 `chars["㗎"].d="u35ce_gaa3"`。3311 = 課程 1572 + 單字 1739。
- `app/index.html` — 场景课程学习页 + 四层发音路由点读 + 游戏 + 生词本 + 打卡；课程数/领域数文案由 `renderMeta()` 动态生成，勿写死。
- `docs/課程設計.html` — 课程设计文档（旧方案放弃原因、粤拼验证过程、两大专业板块课目一览）。
- Python venv（edge-tts / ToJyutping / pycantonese / RapidOCR / pymupdf）：`C:/Users/Luffy/.workbuddy/binaries/python/envs/default`

## 粤拼质量保障（核心机制，不要退回手写）
- 自动标注：**ToJyutping**（基于 **rime-cantonese**，粵語計算語言學基礎建設組，CC BY 4.0）——多音字处理可靠。
- 交叉验证：**pycantonese**（独立词库）复核高风险词。
- **重要教训**：双词库交叉验证**只能抓「库间分歧」，抓不到「两库一致地错」**。行业术语必须额外做网络/权威来源查证——例如「天秤」（塔式起重机）两库都给 tin1 ping4，实际应为 **tin1 cing3**。
- 已验证结论（不要再改）：爸爸 baa4 baa1 / 媽媽 maa4 maa1 是真实变调；轉左/轉右/**轉介** 用 zyun3；喺度 覆盖为 hai2 dou6；天秤 覆盖为 tin1 cing3；跌打 tit3 daa2（两库一致）。
- **同音字替身法**（多音字单字发音）：单字 MP3 读音由 edge-tts 决定、无法指定，故找一个**只读该音节的常用字**（GB2312 一级字库）代替合成。触发条件必须是「课程读音 ≠ 字典首选读音」，否则会误替数百字。
- 标注 rime-cantonese 出处（CC BY 4.0 要求），已在 App「我的」页注明。

## 已停用资产（保留在磁盘，未删除，待用户决定）
- `粵語教程/`（原 PDF + 138 MP3，约 126MB）、`app/pages/`、`app/content/book.json`、`app/content/layout.json`、`tools/ocr_raw/`、`tools/extract_*.py`、`tools/build_book.py`、`tools/build_from_ocr.py`、`tools/build_layout.py`、`prototype/`、`docs/跨平台应用设计方案.html`。

## 数据更新流程（可复用）
- 改 `tools/curriculum/*.json` → `build_curriculum.py` → `gen_audio.py` → `gen_char_audio.py` → `verify_audio.py`。
- **注意**：改过某课的 Y 文本后，必须手动删除该课所有 `app/audio/<lessonId>-*.mp3` 再跑 `gen_audio.py`，否则旧音档会被断点续跑逻辑跳过（`-df` 整段对话同理）。

## 待办 / 风险
- 后续增强方向：生词本接 SRS 间隔重复、跟读打分（音高/时长比对）、落 Flutter 工程。
- **环境坑（重要）**：① 该 bash 环境**默认 PATH 不含 coreutils**，`ls`/`head`/`tail`/`grep`/`dirname`/`curl`/`unzip` 会报 `command not found`（stderr 每次都有 `dirname: command not found` 的 shim 噪音，可忽略）。**解法：每条命令前加 `export PATH="/usr/bin:/bin:/usr/local/bin:$PATH"`** 即可全部恢复，比用 Python 代替更省事；Bash 工具里 `echo` 等 builtin 不受影响。② **同一轮并行发多个 Edit 到同一文件会静默丢失**——要逐条发，或用 Python `str.replace` + `assert count==1` 原子化改写。③ **单次 Write/Edit 有输出长度上限（约 15K 字符）**，大文件需分块写（先 Write 头部+前几课，再用 Edit 以文件末尾唯一 anchor 逐批 append）。

## 發布上架（長期要點）

- **語音授權是結構性風險**：全部語音由 `edge-tts` 生成，而它是對 Edge「大聲朗讀」的逆向封裝，**未獲微軟授權用於第三方分發**。若要上架商店，須改用 **Azure 官方 Speech 同名預建神經語音**（付費訂閱商用合法、無需署名、須披露 AI 合成）。改用時只換 `gen_audio.py` / `gen_char_audio.py` 的合成後端，音色名與檔名規則不變，前端零改動。
- **技術路線已定調：Capacitor 包殼，不重寫 Flutter**（除非日後要加跟讀評分等重原生功能）。原 `docs/跨平台应用设计方案.html` 的 Flutter 結論已過期，因為後來改以 HTML 原型實作並完成全部內容驗證。
- **打包排除紅線**：`app/pages/`（389 張原教材截圖，16.9 MB）與 `粵語教程/`（原書 PDF + 138 段原版錄音）**絕不可進入發布包**，它們目前就在 `app/` 底下，需顯式排除。
- **關鍵路徑是資質不是技術**：軟著 60 工作日 >> 技術工作（< 1 週）。任何發布計畫都應先送軟著。
- **合規設計原則**：App 應維持**零外部網路請求**（內容與音檔全內建）。純離線可爭取豁免 ICP 與工信部 App 備案。
- **平台事實（會變動，提交前須複查）**：App Store 中國區強制 ICP 備案號；Google Play 新個人帳號須 12 名測試者連續 opt-in 14 天（**不是 20，那是 2024-12 前的舊規**）；國內安卓軟著必交且四項名稱須一字不差。

## Android / iOS 打包環境（2026-09-18 建立）

- **Capacitor 8 硬性要求 JDK 21**（`node_modules/@capacitor/android/capacitor/build.gradle:66` 寫死 `JavaVersion.VERSION_21`）。本機原有 JDK 17 **不足**，會報 `錯誤: 無效的源發行版：21`。
- **JDK 21 已裝到用戶空間**：`C:\Users\Luffy\.workbuddy\binaries\jdk21\jdk-21.0.12.1+1`（Temurin，`java -version` = 21.0.12.1 LTS）。**切勿改 node_modules 的 sourceCompatibility**，`cap sync`／`npm install` 會還原。
- **Android SDK**：`C:\Users\Luffy\AppData\Local\Android\Sdk`（免 Android Studio，用 `tools/_setup_android_sdk.py` 裝 commandlinetools + platform-tools + android-36 + build-tools）。`android/local.properties` 的 `sdk.dir` **必須用正斜線**（Java properties 會把 `\` 當轉義）。
- **建置指令**：`python tools/_build_android.py`（內部自動挑 JDK 21+，找不到會列出本機所有版本）；產物 `android/app/build/outputs/{bundle,apk}/release/`。
- **簽名**：`android/upload-keystore.jks` + `android/keystore.properties`（alias `upload`，CN=jyut.fun，RSA 2048 / SHA256withRSA / 10000 天，有效期至 2054-02-03）。✅ **2026-09-18 已把憑證 `C=HK` 改成 `C=CN` 並重建金鑰與 AAB/APK**（`L/ST=Hong Kong` 保留）——未上架前改零成本，上傳 Play 後永久鎖定。現憑證 **SHA-256 `8EC4CB47…5392`**、SHA-1 `4642180F…BF2F`，上架各渠道填的就是這個。舊 `C=HK` 備份留檔 `dist/keystore-backup/OBSOLETE-keystore-C_HK-2026-09-18.zip`（勿再使用）。
- **簽名金鑰備份**：`python tools/backup_keystore.py` 產出 `dist/keystore-backup/jyutfun-keystore-backup-<日期>.zip`（jks + properties + `README.txt` 還原說明 + `SHA256SUMS.txt`）；`--show` 只印指紋不打包，`--force` 覆蓋。zip 內檔名刻意全 ASCII —— 舊版 Info-ZIP 不認 UTF-8 檔名旗標，中文名會變亂碼。**打包只是第一步，複製到兩處離線位置（加密隨身碟 + 密碼管理器附件）只能人工做**，且要與密碼分開存放、做一次解壓還原測試。
- **【產物自檢坑】`jarsigner` 不能驗 APK，且不可用英文關鍵字硬匹配**：① 中文 Windows 上 jarsigner 用系統 ANSI(GBK) 輸出中文（「jar 已驗證。」），用 UTF-8 解碼會變亂碼，grep `"jar verified"` 永遠匹配不到 → **明明簽好了卻報「未簽名」**（曾因此誤報一次）。解法：加 `-J-Duser.language=en -J-Duser.country=US` 強制英文，解碼再加 gbk 退路。同招適用 `keytool -list -v`（中文標籤「所有者／有效期」同樣不可靠）。② **APK 一律用 `apksigner` 驗**：本專案 minSdk 24，APK 只掛 v2 方案、冇 v1，`jarsigner` 會把它判成 `jar is unsigned`（假陰性）。AAB 用 jarsigner、APK 用 apksigner，兩者不可互換。兩個坑方向相同 —— 都在「狼來了」，會令真正的未簽名事故被當成噪音忽略。已在 `tools/_build_android.py` 修好並分流。
- **`tools/_build_android.py` 的簽名自檢**已改成：`.apk` 走 SDK `build-tools/*/apksigner verify --print-certs -v`（解析 `Verified using vN scheme` 與 `certificate DN`），其餘走 jarsigner；找不到 apksigner 會明確報錯而非假通過。
- **`app/index.html` 的 `isLessonClip()`**：板塊 regex **必須由 `CURR.domains` 動態推導**，不可寫死板塊 id（曾寫死 `basic|life|study|work`，令後加的 construction/medical 進度全不記錄）。
- **驗證（兩套探針，用途不同，勿互相取代）**：
  - `python tools/verify_release.py` — 發布前一鍵自檢（靜態資源 + 打包純淨度 + 外部 URL 掃描 + 桌面 CDP 探針）。日常邏輯回歸用這個，快。
  - `tools/probe_webview.mjs` — **真機／模擬器 Chromium WebView** 探針，驗證「只在 Android 才會踩到」的問題（原生儲存、`https://localhost` 來源、媒體自動播放策略、`speechSynthesis` 有無、安全區）。用法：`adb forward tcp:9222 localabstract:webview_devtools_remote_<pid>` 後 `node tools/probe_webview.mjs 9222`。
  - **CDP 探針不可用 `--virtual-time-budget`**（會凍結虛擬時鐘，App 頁計時器永不觸發）。
  - **發音路由的觀測點兩邊不同**：桌面 Edge 可以聽 **Network domain 的 `.mp3` 請求**；但 **WebView 內不行** —— Capacitor 用 `WebViewLocalServer` 在 `shouldInterceptRequest` 攔截 `https://localhost/*`，那些請求不進 Network 域，永遠回 0，會誤判「音訊全掛」。**WebView 版一律直接讀播放器狀態**：`charAudio.src` / `audio.src` 決定走哪條路，`readyState` / `paused` / `currentTime` 決定是否真的在播（單字走獨立 `charAudio`，課程原聲走 `audio`）。
  - **WebView 內點擊必須發真實指標事件**（`Input.dispatchMouseEvent` 的 `mouseMoved`→`mousePressed`→`mouseReleased`，座標取 `getBoundingClientRect()` 中心）。`element.click()` 不是 trusted user gesture，Chromium 會擋掉音訊播放，量到的是假路由。
  - **陷阱**：`Runtime.evaluate` 傳 `awaitPromise:false` 配 `async` IIFE，CDP 會回 Promise 物件（序列化成 `{}`）而函式仍在背景跑，造成步驟交錯、整輪驗證假通過。另外**可見性不能靠讀內容判斷** —— `display:none` 子樹裡的元素一樣讀得到 `textContent`；`tools/probe_webview.mjs` 的 `realClick` 會在 rect 寬高為 0 時直接拋錯。
- **iOS**：本機無 Mac，走 `.github/workflows/ios.yml`（macos-15）。未填 Apple 憑證 secrets 時只做無簽名封存驗證。

## Android 模擬器（2026-09-18 建立，可重複使用）

- **加速前提**：本機 Hyper-V 已開（用戶跑 WSL2）→ **AEHD/HAXM 不可用**（要求 Hyper-V 關閉），只能走 **WHPX**。已用 `dism /Online /Enable-Feature /FeatureName:HypervisorPlatform /All /NoRestart` 啟用。**DISM 回 `3010`（要求重啟）但實測毋須重啟** —— `emulator -accel-check` 即刻回 `WHPX ... is installed and usable`，開機 40 秒完成。**先試再說，不要一見 3010 就叫用戶重啟。**
- **AVD**：`jyutfun_api36`（`pixel_7` / `system-images;android-36;google_apis;x86_64` / 1080×2400 @ density 420 / 3 GB RAM / 4 GB data）。
- **操作入口**：`python tools/android_emu.py {check|create|start|install|launch|shot|logcat|inspect|stop|run}`。
- **【環境坑】模擬器活不過一次工具呼叫**：沙箱在背景任務結束時回收整個 process tree（`DETACHED_PROCESS` 與 `CREATE_BREAKAWAY_FROM_JOB` 都無效）→ **必須用 `start --keepalive`**，讓長時間背景任務持有子行程。
- **【環境坑】`npx cap sync android` 會清空目標目錄後卡死**（實測只複製 25 個 mp3 就停住，`assets/public` 由 52.8 MB 打成 576 KB；npm debug log 停在啟動階段）。**改用 `python tools/sync_assets.py`**：逐檔比對 mtime+size 的鏡像複製，保留 `cordova.js`/`cordova_plugins.js`，完成後驗證檔案數 / mp3 3311 / 五個關鍵產物 / 總大小，可重複安全執行（約 78 秒）。若真要殺卡死的 `cap sync`：殺 node 行程中命令行含 `cap sync android` 的兩個（npx 包裝 + `capacitor` 本體），**勿殺 MCP 服務那幾個 node**。
- **App 在 Android 上不是 edge-to-edge**：WebView 自身 `screenY=136`、`height=2201`（2400−136 狀態列−63 導覽列），`env(safe-area-inset-*) = 0` 屬正確。Capacitor `SystemBars.java:270` 那個 `Error injecting safe area CSS` 是**上游 bug 但無害**（注入時 `document.documentElement` 仍為 null）。判警的正確做法是先讀 target 描述的 `screenY`，**只有 `screenY === 0`（真 edge-to-edge）才需要檢查 `env()`**。
- **Android WebView 冇 `speechSynthesis`**（桌面 Chrome/Safari 有）→ App 內 `TTS.noApi` 會成立，音色卡顯示「不支援」。任何依賴 Web Speech API 的功能在 Android 上都不可用，別當它是 fallback。

## 隱私政策公開網址（商店硬性要求）

- Play 與 App Store 都要**公開、免登入可訪問的獨立 URL**，App 內頁面不算。App 內入口（「我的」）另計。
- **⚠️ 更正**：原稿寫「開個 GitHub Pages 放 `privacy.html`」—— 但主倉庫 `jyut-fun` 是 **private**，而**免費版 GitHub Pages 不支援私有倉庫**（需付費 Pro）。正解是**另開一個只放政策頁的公開倉庫** `jyut-fun-privacy`。
- 工具：`python tools/publish_privacy.py --email <信箱>` —— 把信箱寫回 `app/privacy.html`（**幂等**，中英兩處 `[請填入聯絡信箱]` / `[please fill in contact email]` 一起換）→ 生成 `dist/privacy-site/`（`index.html` + `privacy.html` + `.nojekyll` + `README.md`）→ 建公開倉庫（已存在則強推）→ 開 Pages → 驗 HTTP 200。`--status` 查狀態、`-n` 只生成本地站台。目標網址 `https://dragonluffy9527.github.io/jyut-fun-privacy/`。
- **連鎖注意**：此腳本會改 `app/privacy.html`，即 App 內政策頁 → 換信箱**必須**再跑 `python tools/sync_assets.py && python tools/_build_android.py`，否則 App 內仍是舊內容。
- **踩坑（safe-delete）**：`stage()` 原本用 `shutil.rmtree` 整目錄重建，會撞上本機沙箱的 safe-delete 攔截（`SAFE_DELETE_FAIL_CLOSED` / trash 失敗）令腳本中斷。已改成**就地覆寫 + 只清非預期檔（保留 `.git`）**，受限環境同樣能跑。
- **已辦（2026-09-18）**：公開網址 **https://dragonluffy9527.github.io/jyut-fun-privacy/** 已上線（實測 HTTP 200，`index.html` 與 `privacy.html` 都有）；對外聯絡信箱 **hjjliufei@qq.com** 已寫入 `app/privacy.html` 中英兩處、`store/listing.md`（表格欄位 + 英文描述「Email hjjliufei@qq.com and we will fix it」）與上架指南。公開倉庫提交署名固定為 `DragonLuffy9527 <noreply@github.com>`，不外洩私人信箱。
- **注意**：本機 git 身分是 `FlowerWeSaw <191559729@qq.com>`（global），私有倉庫所有提交都帶此署名 —— 私有倉庫無妨，但若日後要公開此倉庫需先改身分。

## 離線能力與 APK 分發（2026-09-18 實測）

- **100% 離線可用，已實測**：模擬器開飛航模式 + 關 WiFi/數據（`ping 223.5.5.5` → `Network is unreachable`）下 `adb install` 裝 APK → 啟動 → CDP 探針抽驗：逐字點讀 **6/6 命中**（棚/架/要/由/合/資，全 `char-clip`、`readyState=4` 且在播）、整句課程音檔 `con-11-c1.mp3` 正常播放、進度寫入原生 Preferences 往返成功，**0 JS 錯誤 / 0 console 錯誤 / 0 次網絡 mp3 請求**。
- **App 內零外部網址**：全 `app/` 掃 `https?://` 只中命名空間；唯一 `fetch()` 是相對路徑 `content/char_audio.json`、`content/curriculum.json`（均在包內）。音檔路徑全相對：`audio/<clip>.mp3`、`audio/chars/<字>_<粵拼>.mp3`。教材來源只是文字署名，無外鏈。
- **`INTERNET` 權限 ≠ 上網**：Capacitor 用 WebView 內建本機伺服器把 APK 資產以 `https://localhost/` 供應（探針實測 `location.href` 即 `https://localhost/`），此權限是 loopback 所需，移除會壞，勿動。
- **APK 通用性**：包內 **0 個 .so**（純 Java/Kotlin + WebView，單 dex）→ **全 ABI 通用**（arm64/armeabi/x86 皆可）；`minSdk 24`（Android 7.0+）、targetSdk 36。
- **直裝注意**：自簽上傳金鑰 → 手機需開「允許安裝未知來源」；**因 2026-09-18 換過金鑰（C=HK→C=CN），若手機已有舊版必須先卸載再裝**，否則報 `INSTALL_FAILED_UPDATE_INCOMPATIBLE`（模擬器實測踩到）。
- 證據截圖：`screenshots-emu/emu-offline-me.png`（狀態欄有飛航圖示，底部迷你播放器仍掛住該課音檔）。

## 版控與備份

- **私有倉庫**：https://github.com/DragonLuffy9527/jyut-fun （`gh` 帳號 `DragonLuffy9527`，gh CLI 已認證且具 `repo`/`workflow` scope）。預設分支 `main`。
- **入庫範圍**：`app/`（含 3311 段音檔，約 57 MB）、`android/`、`ios/` 設定、`tools/`、`docs/`、`store/`、`resources/`、`.github/`、`.workbuddy/memory/`。總計約 60 MB / 3428 檔。
- **不進版控**（見 `.gitignore`）：`node_modules/`、`android/build/`、`android/app/build/`、`android/app/src/main/assets/public/`（由 `tools/sync_assets.py` 重建）、`dist/`（AAB/APK 各約 50 MB）、`*.jks`／`keystore.properties`、`粵語教程/`、`archive/`、`prototype/`、`tools/*_acro_backup.json`、`tools/ocr_raw/`、`tools/models/`、`tools/_*`（但 `_build_android.py`／`_setup_android_sdk.py` 例外放行）。
- **新增內容前必做紅線掃描**：`.gitignore` 只擋已知路徑。提交前用內容特徵掃全部候選文字檔，例如
  `git diff --cached --name-only -z | xargs -0 grep -lI -E "粵語（香港話）教程|jointpublishing|pdfOffset|audioBaseUrl"`，
  確認沒有原教材衍生物漏網（曾靠此法攔下 `tools/*_acro_backup.json` 與 `prototype/`）。
- **`.gitattributes` 要點**：`gradlew` 必須釘 `eol=lf`（Linux CI 直接執行 `./gradlew`，CRLF 會令 interpreter 失敗）；mp3/png/jar/jks 標 `binary` 防換行轉換損毀。提交後建議抽驗 `git show :<path>` 與磁碟檔 byte 相等。
