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
- `tools/verify_audio.py` — 发音资产体检（单字库/课程音档完整性 + 模拟前端路由算覆盖率 + 分领域覆盖表）。
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
- **簽名**：`android/upload-keystore.jks` + `android/keystore.properties`（alias `upload`，CN=jyut.fun，RSA 2048 / 10000 天）。**兩者已 gitignore，只存在本機 → 必須離線備份，遺失即永久無法更新此 App。** `app/build.gradle` 會同時在 `android/app/` 與 `android/` 兩處找金鑰，兩處都無則主動報錯。
- **`app/index.html` 的 `isLessonClip()`**：板塊 regex **必須由 `CURR.domains` 動態推導**，不可寫死板塊 id（曾寫死 `basic|life|study|work`，令後加的 construction/medical 進度全不記錄）。
- **驗證**：`python tools/verify_release.py` 一鍵發布前自檢（靜態資源 + 打包純淨度 + 外部 URL 掃描 + CDP 實時探針）。CDP 探針**不可用 `--virtual-time-budget`**（會凍結虛擬時鐘）；查發音路由要聽 **Network domain 的 `.mp3` 請求**，不要讀 `audio.src`（單字走獨立 `charAudio` player 會誤判）。
- **iOS**：本機無 Mac，走 `.github/workflows/ios.yml`（macos-15）。未填 Apple 憑證 secrets 時只做無簽名封存驗證。

## 版控與備份

- **私有倉庫**：https://github.com/DragonLuffy9527/jyut-fun （`gh` 帳號 `DragonLuffy9527`，gh CLI 已認證且具 `repo`/`workflow` scope）。預設分支 `main`。
- **入庫範圍**：`app/`（含 3311 段音檔，約 57 MB）、`android/`、`ios/` 設定、`tools/`、`docs/`、`store/`、`resources/`、`.github/`、`.workbuddy/memory/`。總計約 60 MB / 3428 檔。
- **不進版控**（見 `.gitignore`）：`node_modules/`、`android/build/`、`android/app/build/`、`android/app/src/main/assets/public/`（`cap sync` 會重建）、`dist/`（AAB/APK 各約 50 MB）、`*.jks`／`keystore.properties`、`粵語教程/`、`archive/`、`prototype/`、`tools/*_acro_backup.json`、`tools/ocr_raw/`、`tools/models/`、`tools/_*`（但 `_build_android.py`／`_setup_android_sdk.py` 例外放行）。
- **新增內容前必做紅線掃描**：`.gitignore` 只擋已知路徑。提交前用內容特徵掃全部候選文字檔，例如
  `git diff --cached --name-only -z | xargs -0 grep -lI -E "粵語（香港話）教程|jointpublishing|pdfOffset|audioBaseUrl"`，
  確認沒有原教材衍生物漏網（曾靠此法攔下 `tools/*_acro_backup.json` 與 `prototype/`）。
- **`.gitattributes` 要點**：`gradlew` 必須釘 `eol=lf`（Linux CI 直接執行 `./gradlew`，CRLF 會令 interpreter 失敗）；mp3/png/jar/jks 標 `binary` 防換行轉換損毀。提交後建議抽驗 `git show :<path>` 與磁碟檔 byte 相等。
