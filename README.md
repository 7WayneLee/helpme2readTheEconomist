# econ-digest

每週《經濟學人》（The Economist）新刊發行時，`econ-digest` 會自動從 GitHub 下載最新 EPUB 期別，透過本機大型語言模型（LLM）池進行全文解析與台灣讀者導向的深度分級摘要，並依主題排版推送至您的 Telegram 私人聊天室。推播內容包含即時掌握全球情勢的「本週要聞速覽」、依台灣關聯與重要性分級的深度解析與重點整理、合併社論立場分析、專為台灣英語學習者打造的「英文學習選文與研讀指南」，並隨附完整美觀的離線 HTML 報告，讓您在手機或電腦上輕鬆掌握當期精華。

---

## 目錄

- [這是什麼](#這是什麼)
- [分類與摘要深度](#分類與摘要深度)
  - [台灣關聯層級（Taiwan Levels）](#台灣關聯層級taiwan-levels)
  - [章節與分類排序](#章節與分類排序)
  - [摘要深度等級表（Tiers）](#摘要深度等級表tiers)
  - [特殊文章處理](#特殊文章處理)
- [英文學習選文](#英文學習選文)
- [系統架構](#系統架構)
  - [處理管線流程](#處理管線流程)
  - [模組職責地圖](#模組職責地圖)
  - [本機 gwg 模型池與在地化](#本機-gwg-模型池與在地化)
- [安裝](#安裝)
- [Telegram 設定](#telegram-設定)
- [使用方式](#使用方式)
  - [指令與旗標一覽](#指令與旗標一覽)
  - [典型操作流程](#典型操作流程)
- [設定檔](#設定檔)
- [排程](#排程)
- [資料與隱私](#資料與隱私)
- [開發與測試](#開發與測試)

---

## 這是什麼

`econ-digest` 是一套為台灣讀者設計的自動化每週《經濟學人》導讀機器人。每週末新一期期刊釋出時，程式會自動抓取 EPUB 檔案，識別每篇文章與台灣的政經關聯（包含台灣本身、兩岸關係、半導體供應鏈等），依據重要性給予不同深度的中文摘要，並挑選一篇適合中級英語學習者的長文產出完整研讀筆記。全部內容會格式化後推播到個人的 Telegram，同時生成排版良好的獨立 HTML 報告檔案，兼顧行動端碎片化閱讀與桌面端離線精讀需求。

---

## 分類與摘要深度

系統根據文章主題與台灣的相關程度，將內容分為三個台灣關聯等級，並按照固定順序進行章節分類與摘要深度分級。

### 台灣關聯層級（Taiwan Levels）

定義源自 `src/econ_digest/taxonomy.py`：

| 層級代號 | 層級名稱 | 判定定義 | 預設摘要深度 |
| :--- | :--- | :--- | :--- |
| **T1** | 台灣本身 | 台灣是報導的主要主題。 | **Tier A**（深度解析） |
| **T2** | 台灣與國際 | 台灣是國際事件的主要參與者之一，例如台美關係、兩岸、台積電與晶片供應鏈或邦交國。 | **Tier B**（詳細摘要） |
| **T3** | 間接相關 | 台灣並非主要參與者，但報導實質提及台灣，或議題對台灣有重大影響。 | **Tier C**（重點摘要） |

### 章節與分類排序

非台灣主軸（T0）的文章，依下列順序在報告與推播中呈現：

1. **美國**（`intl.us`）
2. **中國（含港澳）**（`intl.china`）
3. **亞太（日韓、北韓、東南亞、南亞、澳紐、太平洋島國）**（`intl.asia`）
4. **歐洲（含英國、俄烏）**（`intl.europe`）
5. **其他地區與全球議題（美洲、中東、非洲、跨國議題）**（`intl.other`）
6. **財經商業**（`finance`）
7. **科技**（`tech`）
8. **科學**（`science`）
9. **文化生活（書評、藝術、影視、體育、生活、訃聞）**（`culture`）

### 摘要深度等級表（Tiers）

摘要深度共分為 A 到 E 五級，各等級之繁中字數與預設對應規則如下（設定源自 `config.example.toml` 中的 `[tiers]`）：

| 深度代號 | 層級名稱 | 預期中文字數 | 核心產出內容 | 預設對應規則 |
| :---: | :--- | :--- | :--- | :--- |
| **A** | 深度解析 | 約 800–2,700 字 | 中文標題、背景脈絡、段落結構（標註段落範圍）、論點剖析（主張／論據／反方觀點／結論）、關鍵數據、忠實原文引述與中譯、立場分析、對台灣影響與啟示、延伸思考。 | 台灣 **T1** 報導 |
| **B** | 詳細摘要 | 約 400–1,250 字 | 中文標題、4–6 項核心重點、完整論點分析（主張／論據／反方觀點／結論）、對台灣影響與啟示。 | 台灣 **T2** 報導；封面社論對應報導（最低門檻） |
| **C** | 重點摘要 | 約 165–550 字 | 中文標題、3–5 項核心重點。 | 台灣 **T3** 報導；美國 (`intl.us`)、中國 (`intl.china`)；其他社論對應報導（最低門檻）；特別報導（briefing 最低門檻） |
| **D** | 簡要摘要 | 約 50–210 字 | 中文標題、2–3 句簡明摘要。 | 亞太 (`intl.asia`)、歐洲 (`intl.europe`)、財經商業 (`finance`)、科技 (`tech`) |
| **E** | 一句話 | 約 20–85 字 | 一句話核心論點。 | 其他地區 (`intl.other`)、科學 (`science`)、文化生活 (`culture`)；強制指定：讀者投書（letters）、訃聞（obituary） |

#### 深度規則調整原則
- **封面社論對應報導（Cover companion）**：若某報導為封面社論（Our cover）對應之延伸專文，其摘要深度至少提升至 **Tier B**（`cover_companion_min = "B"`）。
- **一般社論對應報導（Leader companion）**：若某報導為其他社論對應之延伸專文，其摘要深度至少提升至 **Tier C**（`leader_companion_min = "C"`）。
- **特別報導種類門檻（Briefing）**：特別報導文章種類之深度至少為 **Tier C**（`min_tier_by_kind = { briefing = "C" }`）。
- **強制指定深度（Force tier）**：讀者投書（letters）與訃聞（obituary）強制指定為 **Tier E**（`force_tier_by_kind = { letters = "E", obituary = "E" }`）。

### 特殊文章處理

1. **本週要聞速覽（brief）**：
   - 取材自期刊前段之 "The world this week"（包含政治 `world_politics` 與商業 `world_business`）。
   - 彙整為重點條列，若條目內容涉及台灣，會標記 🇹🇼 並置頂呈現。
2. **社論合併（merged）**：
   - 社論（Leaders）在當期若有對應的專題報導，會將社論觀點合併至該專題報導中，呈現為「經濟學人社論立場」（包含 2–3 句核心社論主張），不單獨產出重疊的摘要篇幅。
3. **略過不處理（skip）**：
   - 漫畫（`cartoon`）與經濟金融指標（`indicators`）直接略過，不消耗模型配額。

---

## 英文學習選文

每期系統會精選一篇英文文章，產出專為台灣英語學習者設計的研讀指南。

### 選文機制
- **候選門檻**：限於 `article`、`leader`、`briefing`、`column`、`by_invitation` 或 `obituary` 等具閱讀價值的文體，且英文總字數須介於 `min_words`（預設 600 字）與 `max_words`（預設 1,300 字）之間。
- **歷史去重**：讀取 `data/state.json` 中最近 8 期的選文紀錄（`english_history`），避免連續重複挑選相同專欄或相近主題。
- **模型評選**：由模型針對設定之目標程度（預設：`全民英檢中級（多益約 550–780，CEFR B1）`）評估題材趣味性、論述嚴謹度與詞彙實用性，並產出中文推薦理由（`reason_zh`）。

### 學習指南內容
- **篇章資訊**：文章 CEFR 分級評估（A2–C2）、單字量統計與預估閱讀分鐘數。
- **背景導讀（`pre_reading_zh`）**：約 100–330 字的中文背景介紹。
- **重點單字庫（`vocabulary`）**：預設 14 個單字，包含單字（`word`）、詞性（`pos`）、中文釋義（`meaning_zh`）、用法註記（`note_zh`），以及嚴格出自原文的忠實例句（`example_en`）。
- **實用片語庫（`phrases`）**：預設 7 個常用慣用語或搭配詞，包含片語（`phrase`）、中文釋義與原文例句。
- **長難句精析（`sentences`）**：2–3 句文章中之長難句，附原文長句、句構剖析（主詞、動詞、修飾語與子句拆解）與繁體中文翻譯。
- **寫作修辭亮點（`writing_notes_zh`）**：1–2 則關於文章修辭、論點銜接或行文風格的分析筆記。
- **閱讀測驗（`quiz`）**：3 題英文理解測驗，附繁體中文答案、詳解與對應段落引述（如「第 3 段」）。

---

## 系統架構

### 處理管線流程

系統依照下列管線階段循序或平行推進：

```
[fetch] 下載 EPUB 檔案
   ↓
[parse] 解析 XHTML / OPF / TOC，萃取文章結構與段落
   ↓
[classify] 透過 LLM 識別台灣關聯層級（T1–T3）與領域分類
   ↓
[pair] 將 Leaders 社論與各章節候選專文進行關聯配對
   ↓
[tiers] 套用深度政策、封面與社論對應門檻，決定各篇 Tier
   ↓
[summaries / brief / English] 平行呼叫 LLM 產出摘要、要聞速覽、選文評選與學習指南
   ↓
[zh-TW normalisation] 透過 OpenCC (s2tw) 與詞彙對照表轉換為台灣正體用語並檢查
   ↓
[render] 生成 Markdown、HTML 報告與 Telegram 分段訊息
   ↓
[Telegram] 依序推送訊息與完整 HTML 附件至 Telegram 私人聊天室
```

### 模組職責地圖

| 模組路徑 | 職責說明 |
| :--- | :--- |
| `src/econ_digest/cli.py` | 命令列介面入口，負責參數解析、日誌初始化與指令分發。 |
| `src/econ_digest/config.py` | TOML 設定檔載入、路徑解析、型別驗證與密鑰管理。 |
| `src/econ_digest/fetch.py` | 透過 GitHub API 探測最新期別並下載 EPUB 檔案。 |
| `src/econ_digest/epub_parser.py` | 解析 EPUB 壓縮檔、目錄清單、文章結構與純文字段落。 |
| `src/econ_digest/signals.py` | 本機台灣關鍵字規則引擎，用於輔助分類與容錯降級。 |
| `src/econ_digest/taxonomy.py` | 台灣關聯定義、章節分類、摘要深度與文章類型政策。 |
| `src/econ_digest/state.py` | 執行狀態持久化（`state.json`）與非阻塞式檔案鎖（`.lock`）。 |
| `src/econ_digest/pipeline.py` | 排程核心流程控制，包含單元重試、失敗通報與鎖管理。 |
| `src/econ_digest/llm/` | LLM 客戶端封裝；包含子程序排程、多模型容錯降級與結構化 JSON 輸出修復。 |
| `src/econ_digest/analysis/` | 提示詞組裝、分類、配對、摘要生成、英文選文與指南製作。 |
| `src/econ_digest/zhtw/` | 台灣正體中文轉換器（OpenCC + `glossary.tsv` 詞彙對照表）與用語檢查。 |
| `src/econ_digest/render/` | Markdown、HTML 報告渲染與 Telegram HTML 區塊分頁包裝。 |
| `src/econ_digest/telegram/` | Telegram Bot API 通訊客戶端、安全重試與格式保護。 |
| `src/econ_digest/commands/` | 各子指令獨立實作（`run`, `analyze`, `send`, `telegram-setup` 等）。 |

### 本機 gwg 模型池與在地化

1. **本機 `gwg` 模型池**：
   - 系統透過本機執行的 Antigravity `agy` headless 介面呼叫大型語言模型，無須外連第三方中繼服務。
   - 模型優先順序依設定檔由前往後嘗試（預設主要模型：`gemini-3.8-flash-high`，備援模型：`claude-sonnet-4-6`）。遇到配額耗盡（429）、無可用帳號（exit 75）或地理位置不支援時，自動切換至下一模型。
2. **單元級快取（Per-unit caching）**：
   - 每個分析步驟均以輸入內容、文章 ID 集合、提示詞與模型參數計算雜湊鍵，產生快取檔案（存於 `data/issues/te_<期別>/analysis/`）。
   - 成功的單元立即快取；失敗或未完成的單元不快取，後續重新執行時僅補跑未完成部分。
3. **台灣正體用語在地化（zh-TW Normaliser）**：
   - 先透過系統安裝之 `opencc` 以 `s2tw` 配置轉換簡繁字型。
   - 經過 `src/econ_digest/zhtw/glossary.tsv` 對照表，精確將兩岸詞彙替換為台灣慣用語（例如將「軟件」轉為「軟體」、「算法」轉為「演算法」、「服務器」轉為「伺服器」等）。
   - 自動將文字中的直角引號「」規範化，並由 `lint_zh_tw` 檢驗殘留簡體字與未轉換術語，列入分析警告。

---

## 安裝

### 系統需求
- **Python**：>= 3.11
- **gwg**：已於系統中安裝並已登入帳號，且其執行檔位於 `PATH` 中（常見於 `~/.local/bin` 或 `/usr/local/bin`）。
- **opencc**（建議安裝）：系統套件 `opencc`（Debian/Ubuntu: `sudo apt install opencc`）。若系統未安裝，程式仍可透過內建術語字典運作。

### 安裝步驟

```sh
# 建立 Python 虛擬環境
python3 -m venv .venv

# 啟動虛擬環境並安裝專案及開發相依套件
.venv/bin/pip install -e '.[dev]'
```

安裝完成後，可透過 `.venv/bin/econ-digest --help` 驗證指令是否就緒。

---

## Telegram 設定

### 1. 建立 Telegram 機器人
1. 在 Telegram 搜尋 `@BotFather`。
2. 發送 `/newbot`，依循指示設定機器人名稱與使用者名稱。
3. 取得機器人存取權杖（Token）。

### 2. 安全建立密鑰檔
為了避免敏感 Token 被寫入 Shell 歷史紀錄（`.bash_history`）或在螢幕上被他人窺見，請於終端機執行下列指令（以隱藏方式輸入 Token，並自動將檔案權限設為 `600`）：

```sh
mkdir -p ~/.config/econ-digest && read -rsp 'Token: ' T && printf 'TELEGRAM_BOT_TOKEN=%s\n' "$T" > ~/.config/econ-digest/env && chmod 600 ~/.config/econ-digest/env && unset T; echo
```

### 3. 設定私人聊天室
1. 開啟剛剛建立的 Telegram 機器人對話視窗，點擊或發送 `/start`。
2. 於終端機執行設定指令：
   ```sh
   .venv/bin/econ-digest telegram-setup
   ```
   程式會自動偵測收到 `/start` 的聊天室 ID，並安全更新至 `~/.config/econ-digest/env`。
3. 若要同時驗證連線並發送測試訊息，可加上 `--test` 旗標：
   ```sh
   .venv/bin/econ-digest telegram-setup --test
   ```

---

## 使用方式

### 指令與旗標一覽

全域參數格式：
```sh
econ-digest [-h] [--config PATH] [-v] <command> [options]
```

- `-h, --help`：顯示說明訊息並離開。
- `--config PATH`：指定 TOML 設定檔路徑。
- `-v, --verbose`：顯示詳細偵錯日誌。

各子指令詳細選項：

| 子指令 | 支援旗標 | 功能說明 |
| :--- | :--- | :--- |
| `run` | `[--issue latest\|YYYY.MM.DD]`<br>`[--no-send]`<br>`[--dry-run]`<br>`[--force]`<br>`[--reanalyze]` | 執行完整管線流程：下載、解析、分析、渲染並發送至 Telegram。<br>• `--no-send`：產生報告但不發送至 Telegram。<br>• `--dry-run`：執行分析並產生報告但不傳送。<br>• `--force`：已傳送過的期別依然重新處理並發送。<br>• `--reanalyze`：重新執行模型分析（清除分析快取）。 |
| `fetch` | `[--issue latest\|YYYY.MM.DD]` | 下載指定期別的 EPUB 檔案（預設 `latest`，可指定如 `2026.10.03` 或 `2026-10-03`）。 |
| `parse` | `[--issue latest\|YYYY.MM.DD]` | 解析 EPUB 文章並儲存至 `issue.json` 快取，顯示文章數與字數統計。 |
| `signals` | `[--issue latest\|YYYY.MM.DD]` | 掃描文章並列出所有偵測到台灣相關關鍵詞之篇目與摘要片段。 |
| `analyze` | `[--issue latest\|YYYY.MM.DD]`<br>`[--reanalyze]`<br>`[--plan]`<br>`[--only-tier {A,B,C,D,E}]`<br>`[--limit N]` | 執行文章分類、配對、深度分級與摘要產生。<br>• `--reanalyze`：清除本期分析快取後重新分析。<br>• `--plan`：僅列出分析批次規劃與提示詞大小，不呼叫模型。<br>• `--only-tier`：僅產出指定深度（A–E）之摘要。<br>• `--limit N`：最多產生 N 篇摘要。 |
| `render` | `[--issue latest\|YYYY.MM.DD]` | 從既有的 `digest.json` 產出 Markdown、HTML 報告與 Telegram 訊息切塊。 |
| `send` | `[--issue latest\|YYYY.MM.DD]`<br>`[--force]`<br>`[--dry-run]` | 將渲染好的報告與訊息推送至 Telegram。<br>• `--force`：重新傳送本期所有訊息與附件。<br>• `--dry-run`：僅在終端機列印待傳送的訊息內容而不實際發送。 |
| `telegram-setup` | `[--chat-id CHAT_ID]`<br>`[--test]`<br>`[--wait SECONDS]` | 偵測並綁定 Telegram 私人聊天室。<br>• `--chat-id`：直接指定聊天室 ID。<br>• `--test`：發送測試確認訊息。<br>• `--wait`：等候 `/start` 的秒數（預設 120 秒）。 |

### 典型操作流程

#### 1. 首次手動執行與檢視
建議在初次部屬時先產生報告但不發送，確認模型運算與輸出內容：
```sh
# 執行下載、解析、分析並生成報告（不推送至 Telegram）
.venv/bin/econ-digest run --no-send

# 檢視生成的 HTML 報告（預設路徑）
# data/issues/te_latest/report.html

# 確認無誤後，推送至 Telegram
.venv/bin/econ-digest send
```

#### 2. 中斷續傳與重新發送
- **網路中斷後續傳**：若在推送至 Telegram 期間網路斷線，直接再次執行 `.venv/bin/econ-digest send`，程式會自 `telegram_progress.json` 紀錄之斷點接續發送，不會重複推播已發送的訊息。
- **重新傳送全期內容**：若欲強制重新傳送整期所有訊息：
  ```sh
  .venv/bin/econ-digest send --force
  ```

#### 3. 提示詞調校與除錯（Prompt Tuning）
在調整提示詞模板或設定時，可透過 `analyze` 旗標精準控制呼叫範圍，節省配額：
```sh
# 預覽本期呼叫規劃、評估批次與提示詞大小，不呼叫真實模型
.venv/bin/econ-digest analyze --plan

# 僅針對 Tier A（深度解析）產出一篇摘要以檢驗效果
.venv/bin/econ-digest analyze --only-tier A --limit 1
```

---

## 設定檔

程式在沒有設定檔時即可全預設運作。如需自訂參數，可複製範例檔：

```sh
cp config.example.toml config.toml
```

### 設定項說明

- **`[paths]`**：
  - `data_dir`：儲存 EPUB、分析快取、報告與日誌的目錄（預設 `"data"`）。
- **`[source]`**：
  - `repo`：期刊來源 GitHub 儲存庫（預設 `"hehonghui/awesome-english-ebooks"`）。
  - `branch`：來源分支（預設 `"master"`）。
  - `folder`：期刊存放資料夾（預設 `"01_economist"`）。
- **`[llm]`**：
  - `backend`：模型呼叫後端（目前固定為 `"gwg"`）。
  - `gwg_bin`：`gwg` 執行檔名稱或路徑。
  - `max_parallel`：同時平行發起的請求數（預設 `2`）。
  - `call_timeout_seconds`：單次呼叫逾時秒數（預設 `300`）。
  - `no_account_wait_seconds`：無可用帳號時的等待重試秒數（預設 `900`）。
- **`[llm.models]`**：
  - 各階段（`classify`, `pair`, `summarize_a`~`summarize_e`, `brief`, `english`）依序嘗試之模型清單。第一個為主要模型，其餘為備援模型。
  - 預設值：`["gemini-3.8-flash-high", "claude-sonnet-4-6"]`。
- **`[tiers]`**：
  - `cover_companion_min`：封面社論對應專文之最低深度門檻（預設 `"B"`）。
  - `leader_companion_min`：其他社論對應專文之最低深度門檻（預設 `"C"`）。
  - `taiwan`：台灣關聯層級（1, 2, 3）對應之摘要深度。
  - `category`：各非台灣領域分類對應之預設深度。
  - `min_tier_by_kind`：特定文體最低深度（如 `briefing = "C"`）。
  - `force_tier_by_kind`：特定文體強制深度（如 `letters = "E"`, `obituary = "E"`）。
- **`[english]`**：
  - `level`：目標英語程度敘述（預設 `"全民英檢中級（多益約 550–780，CEFR B1）"`）。
  - `min_words` / `max_words`：選文字數範圍（預設 600 / 1300 字）。
  - `vocab_count` / `phrase_count`：單字與片語數量（預設 14 / 7 個）。
- **`[telegram]`**：
  - `enabled`：是否啟用推播（預設 `true`）。
  - `send_report_file`：是否將完整的 `report.html` 作為附件檔案發送（預設 `true`）。
  - `message_delay_seconds`：訊息發送間隔秒數，防止觸發 Telegram 頻率限制（預設 `1.1`）。

### 設定檔解析優先順序
1. 命令列旗標 `--config PATH`
2. 環境變數 `ECON_DIGEST_CONFIG`
3. 當前工作目錄下的 `config.toml`
4. 若皆無指定或檔案不存在，則全部採用內建預設值執行

### 密鑰載入順序
密鑰包含 `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID` 與選填的 `GITHUB_TOKEN`，絕對不應直接寫入 `config.toml`：
1. 系統環境變數
2. 環境變數 `ECON_DIGEST_ENV_FILE` 指定之路徑
3. 預設密鑰檔 `~/.config/econ-digest/env`

---

## 排程

專案提供 systemd 使用者定時器（user timer），能夠在每週末自動偵測最新期刊並完成分析推送。

### 定時器安裝與管理

```sh
# 預覽將產生的 systemd 服務與定時器檔案內容（不進行安裝變更）
deploy/install-user-timer.sh --print-units /tmp/systemd-preview

# 安裝並啟用使用者定時器
deploy/install-user-timer.sh

# 查看定時器執行排程狀態
systemctl --user list-timers econ-digest.timer

# 查看執行日誌
journalctl --user -u econ-digest.service

# 移除定時器
deploy/install-user-timer.sh --uninstall
```

### 排程細節
- **排程時間**：依台北時間（`Asia/Taipei`），在每週末的五個時段自動執行：
  - 週六 07:00、13:00、19:00
  - 週日 09:00、20:00
- **隨機延遲（`RandomizedDelaySec=10min`）**：定時器啟動時隨機延遲至多 10 分鐘，避免集中瞬間發起請求。
- **單次執行上限（`TimeoutStartSec=3h`）**：單次管線執行上限為 3 小時，防範任何卡死程序。
- **冪等性保障（Idempotent）**：程式在下載與分析前會比對 `data/state.json`，若該期已經成功發送且無 `--force` 旗標，程式會直接退出（顯示「沒有新的一期」），絕不重複發送或徒增 AI 額度消耗。
- **筆電休眠補跑（`Persistent=true`）**：定時器設定了 `Persistent=true`。若您的電腦在排程觸發時處於關機或睡眠狀態，系統會在下次開機或喚醒時自動補跑錯過的排程。
- **關於 Lingering 的重要提醒**：systemd 使用者服務預設僅在使用者登入（登入 Session）期間運行。若要在使用者登出或無登入互動時持續運作定時器，請手動啟用 lingering：
  ```sh
  loginctl enable-linger "$USER"
  ```
  （安裝指令碼不會自動修改使用者的 lingering 設定。）

---

## 資料與隱私

### `data/` 目錄結構

所有的持久化狀態、原始下載內容、快取與報表均存放在 `data/` 目錄中：

```
data/
├── .lock                     # 防止多個程序重複執行的非阻塞檔案鎖
├── state.json                # 已交付期別清單、英文選文歷史、最近執行狀態與失敗通報記錄
├── logs/
│   └── econ-digest.log       # 滾動日誌（單檔上限 2MB，保留 3 份，敏感密鑰已隱藏）
├── agy-workdir/              # gwg 子程序的工作目錄
└── issues/
    └── te_2026.10.03/        # 依期別劃分的專屬資料夾
        ├── TheEconomist.2026.10.03.epub # 下載之原始期刊 EPUB（受版權保護）
        ├── issue.json                   # 解析後之結構化文章純文字與中繼資料
        ├── digest.json                  # 完成彙總之完整導讀資料
        ├── report.md                    # 渲染輸出之 Markdown 報告
        ├── report.html                  # 獨立且美觀排版的 HTML 報告
        ├── telegram_messages.json       # 切分完畢之 Telegram HTML 訊息清單
        ├── telegram_progress.json       # 發送進度追蹤（斷點續傳專用）
        └── analysis/                    # 單元級模型快取目錄
            ├── classify-*.json          # 分類與標籤快取
            ├── pair-*.json              # 社論與專文配對快取
            ├── summarize_a-*.json       # 各級別摘要快取
            ├── brief-*.json             # 本週要聞速覽快取
            ├── english_pick-*.json      # 英文選文快取
            └── english_guide-*.json     # 英文研讀指南快取
```

### 版權與隱私說明
> [!IMPORTANT]
> `data/issues/` 資料夾內包含《經濟學人》原始文章之完整英文內容與 EPUB 檔案，其著作權歸 The Economist Newspaper Limited 所有。
> 專案 `.gitignore` 預設已排除 `data/` 資料夾。請確保產出的報告與本機快取僅供個人離線學習研讀之用，切勿將包含全文之資料公開放置於公開網站、公用儲存庫或公開頻道。

---

## 開發與測試

專案使用 `pytest` 進行全方位單元測試與管線驗證。

### 執行測試套件

```sh
.venv/bin/pytest
```

### 測試配額防護機制（Quota Guard）
為了避免開發與自動化測試時意外消耗寶貴的 LLM 共享配額，`tests/conftest.py` 內建了自動配額守衛（Quota Guard）：
- 在執行 `pytest` 期間，測試夾具會自動在 `PATH` 最前端置入一個模擬的 `gwg` 執行檔，阻斷任何非預期的真實 API 請求。
- 只有當您明確設定環境變數 `ECON_DIGEST_LIVE_GWG=1` 時，才會執行真實連線至模型池的冒煙測試（smoke test）：
  ```sh
  ECON_DIGEST_LIVE_GWG=1 .venv/bin/pytest tests/llm/test_gwg.py -k test_live_gwg_smoke
  ```
