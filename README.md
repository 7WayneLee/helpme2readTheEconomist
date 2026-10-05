# econ-digest

每週《經濟學人》（The Economist）新刊發行時，`econ-digest` 會自動從 GitHub 下載最新 EPUB 期別，透過本機大型語言模型（LLM）池進行全文解析與台灣讀者導向的深度分級摘要。**系統預設以 Telegraph 即時檢視（Instant View）搭配私人圖文網站傳送至您的 Telegram 私人聊天室**：每期抵達時以**單則 Telegram 訊息**發送核心導讀（包含期別概覽、粗體「與台灣相關」焦點清單、無數字編號之 Instant View 各主題分頁連結，以及導向私人多頁網站的「🔒 圖文完整版（需帳密）」連結）。每一個 Telegraph 頁面均以該期封面圖為首圖（圖說標註「本期封面：…」），使 Instant View 與聊天室大圖預覽（Large media）均能完整呈現封面。同時提供可選用的舊版行為與逐則訊息推播模式，兼顧行動端極速閱讀、版權隱私與深度研讀需求。

---

## 目錄

- [這是什麼](#這是什麼)
  - [每週傳送方式：Telegraph 模式（預設）](#每週傳送方式telegraph-模式預設)
  - [選用舊式行為與逐則推播模式](#選用舊式行為與逐則推播模式)
- [Telegraph 頁面結構與排版規範](#telegraph-頁面結構與排版規範)
  - [邏輯分頁（無序號）](#邏輯分頁無序號)
  - [本週焦點（Focus Articles）](#本週焦點focus-articles)
  - [章節與排版規則](#章節與排版規則)
  - [圖片配置規範（Telegraph 公開頁面 vs 私人網站）](#圖片配置規範telegraph-公開頁面-vs-私人網站)
  - [雙向導覽列與自動分頁續頁](#雙向導覽列與自動分頁續頁)
  - [英文學習頁面與測驗解答](#英文學習頁面與測驗解答)
  - [隱私與版權安全說明](#隱私與版權安全說明)
- [私人網站與封存系統（`output/`）](#私人網站與封存系統output)
  - [`output/` 目錄結構](#output-目錄結構)
  - [私人網站發布（Private Site Publishing）](#私人網站發布private-site-publishing)
  - [發布失敗備援機制（Fallback）](#發布失敗備援機制fallback)
  - [私有 GitHub 儲存庫備份（Backup）](#私有-github-儲存庫備份backup)
- [Telegram 頻道推播（Channel）](#telegram-頻道推播channel)
- [分類與摘要深度](#分類與摘要深度)
  - [台灣關聯層級（Taiwan Levels）](#台灣關聯層級taiwan-levels)
  - [本週焦點機制](#本週焦點機制)
  - [章節與分類排序](#章節與分類排序)
  - [摘要深度等級表（Tiers）](#摘要深度等級表tiers)
  - [特殊文章處理](#特殊文章處理)
- [英文學習選文](#英文學習選文)
- [系統架構](#系統架構)
  - [處理管線流程](#處理管線流程)
  - [模組職責地圖](#模組職責地圖)
  - [本機 gwg 模型池與在地化](#本機-gwg-模型池與在地化)
- [安裝](#安裝)
- [Telegram、Telegraph 與頻道設定](#telegramtelegraph-與頻道設定)
  - [1. 建立 Telegram 機器人](#1-建立-telegram-機器人)
  - [2. 安全建立密鑰檔](#2-安全建立密鑰檔)
  - [3. 設定私人聊天室與頻道](#3-設定私人聊天室與頻道)
  - [4. 設定 Telegraph 帳號](#4-設定-telegraph-帳號)
  - [密鑰清單與安全防護](#密鑰清單與安全防護)
- [使用方式](#使用方式)
  - [指令與旗標一覽](#指令與旗標一覽)
  - [典型操作流程](#典型操作流程)
- [設定檔（`config.toml`）](#設定檔configtoml)
- [排程](#排程)
- [資料、封存與隱私](#資料封存與隱私)
- [開發與測試](#開發與測試)

---

## 這是什麼

`econ-digest` 是一套為台灣讀者量身打造的自動化每週《經濟學人》導讀系統。每週末新一期期刊釋出時，程式會自動抓取 EPUB 檔案，識別文章與台灣的政經關聯（包含台灣本土、兩岸情勢、半導體供應鏈等），依據重要性給予不同深度的中文摘要，並精選一篇適合中級英語學習者的長文產出完整研讀筆記。

### 每週傳送方式：Telegraph 模式（預設）

系統預設採用 Telegraph 即時檢視（Instant View）搭配私人網站發布，每週向您的 Telegram 私人聊天室發送**單則訊息（ONE message）**，帶來乾淨俐落、極速且無廣告干擾的閱讀體驗：

1. **單則 Telegram 核心摘要訊息**：
   - **期別標題與整體概覽**：刊出期別與核心統計概覽（包含總篇數、台灣相關篇數與英文選文）。
   - **「與台灣相關」焦點清單**：以粗體「**與台灣相關**」標籤與「•」清單列出至多 3 則關鍵台灣報導標題。系統對各國新聞均不使用國旗 emoji（其他國家要聞亦不加國旗），以文字標籤維持中立與清晰排版。
   - **各主題分頁 Instant View 超連結（無數字編號）**：
     - 本週導讀
     - 本週焦點
     - 國際
     - 財經・科技・文化
     - 英文學習
     （*僅列出當期實際存在的分頁，省略無內容之分頁*）
   - **私人圖文完整版連結**：末端附上「🔒 圖文完整版（需帳密）：開啟」，點擊即可開啟架設於個人伺服器、受帳號密碼保護的多頁式圖文完整版網站。
2. **大圖預覽與封面首圖**：
   - 每一個 Telegraph 頁面開頭均以當期期刊封面照片作為首圖（Figure，圖說標註「本期封面：…」）。
   - Telegram 收到訊息時會辨識第一頁 Telegraph 連結，並採用大圖卡（Large media）預覽，直接在聊天室展示精美封面照片；點擊 Instant View 亦能立即以原生介面展開閱讀。

### 選用舊式行為與逐則推播模式

若您偏好舊版的傳送習慣，可於 `config.toml` 的 `[telegram]` 區段調整以下開關（**預設皆為 `false`**）：
- `cover_photo = false`：設為 `true` 時，將封面改為獨立照片訊息發送（舊版行為）。
- `original_text_messages = false`：設為 `true` 時，會在聊天室以私訊摺疊區塊「📖 英文選文原文（點開）」隨附英文選文全文。
- `send_report_file = false`：設為 `true` 時，會在聊天室發送單檔離線 HTML 報告文件（`report.html`）。*注意：若私人網站發布失敗，系統會自動 fallback 附送此單檔報告*。
- `delivery = "messages"`：切換為舊版逐則發送多則 Telegram 訊息的模式。在此模式下，文章標題冠上層級代碼（如 `<b>T1 · 文章標題</b>`），各國新聞同樣不使用國旗 emoji。

---

## Telegraph 頁面結構與排版規範

### 邏輯分頁（無序號）

當使用預設的 Telegraph 傳送模式時，系統依據內容邏輯規劃分頁，**不使用任何數字序號**（如 ①、② 等），且僅產生實際有內容的分頁：

1. **本週導讀**（`weekly`）：
   - 整體脈絡綜述。
   - 「本週要聞速覽」：收錄該期 "The world this week" 政治與商業要聞，台灣相關要聞以「【台灣相關】」標記並置頂呈現。
   - 台灣專區報導（台灣關聯層級 T1 至 T3）之深度解析與詳細摘要。
2. **本週焦點**（`focus`）：
   - 獨立成頁之國際核心專題深度解析（詳見下方說明）。
3. **國際**（`international`）：
   - 收錄非台灣主軸、非焦點之各區域報導：美國（`intl.us`）、中國含港澳（`intl.china`）、亞太（`intl.asia`）、歐洲含英與俄烏（`intl.europe`）及其他全球區域報導（`intl.other`）。
4. **財經・科技・文化**（`topics`）：
   - 收錄財經商業（`finance`）、科技（`tech`）、科學（`science`）與文化生活（`culture`，含訃聞與讀者投書）專文與摘述。
5. **英文學習**（`english`）：
   - 精選長文研讀指南（詞彙庫、片語、長難句精析、修辭亮點與測驗）。

### 本週焦點（Focus Articles）

- **智慧評選**：除台灣專區文章外，模型會自當期全體候選文章中評選出最重要的 3 篇報導（數量由 `[analysis] focus_count` 設定，預設為 `3`）。
- **升級深度解析**：選出的焦點報導一律升級為最高規格的 **Tier A 深度解析**。
- **獨立設頁不重複**：焦點報導集中呈現於「本週焦點」獨立章節與獨立 Telegraph 分頁中，不會在後續的「國際」或「財經・科技・文化」頁面重複出現。

### 章節與排版規則

- **空章節完全省略**：當期若無特定分類之報導（例如該期無科學文章），該章節與對應分頁會完全隱藏，不留空白標題。
- **無章節數字序號**：分頁標籤與章節標題一律為純文字（「本週導讀」、「本週焦點」、「國際」等），不冠上序號。
- **專業用詞規範**：內文一律使用「**經濟學人立場**」與「**作者主張**」，絕不使用「社論」字眼。
- **無附錄**：報告不設冗長的附錄章節。
- **簡短條目無收合開關**：一句話簡短摘要（Tier E 等單句條目）直接展示內容，不加入多餘的「閱讀摘要」收合開關（disclosure toggle）。

### 圖片配置規範（Telegraph 公開頁面 vs 私人網站）

為嚴格遵守著作權法規並保障個人隱私，系統對公開與私密管道實施明確的圖片隔離政策：

1. **Telegraph 公開頁面**：
   - Telegraph 頁面為公開網址，任何人持有連結皆可瀏覽。基於版權保護，**Telegraph 頁面僅攜帶期刊封面照片作為首圖**（帶有圖說「本期封面：…」，供 Instant View 封面顯示），**絕不包含任何內文插圖、圖表、地圖、漫畫或原始英文全文**。
2. **私人網站（Private Site，需帳密認證）**：
   - **置頂題圖（Head image）**：文章若有配圖，題圖精確置於「一句話重點」標題正上方。
   - **內文圖表與地圖（Inline charts / maps / photos）**：僅出現在 **Tier A 深度解析**文章（台灣 T1 報導與本週焦點），並依照段落編號精準插入於「文章脈絡」對應段落旁。
   - **要聞速覽配圖**：要聞插圖緊接在所說明的條目下方，帶有「▲ 配圖：…」圖說。
   - **本週漫畫（Cartoon）**：於要聞區塊下方專設「本週漫畫」專題展示。

### 雙向導覽列與自動分頁續頁

- **容量限制預檢**：Telegraph 單頁內容 JSON 限制為 64 KB（64,000 位元組），系統預設每頁上限為 `page_limit_bytes = 60000`。
- **自動續頁**：若單一邏輯分頁內容過長，系統會自動拆分為續頁（如「本週導讀（續）」），並在導覽列標示為「本週導讀（續 2）」。文章本體視為原子單位，絕不跨頁斷句。
- **全頁雙向導覽列**：頁首列出所有可用分頁（當前分頁以粗體標示），頁尾提供 `← 上一頁` 與 `下一頁 →` 快速切換。

### 英文學習頁面與測驗解答

- **研讀內容**：中英標題、推薦理由、CEFR 分級、閱讀時間、背景導讀、重點單字庫（原形、詞性、釋義、例句、用法補充）、實用片語庫、長難句精析（句構與翻譯）、寫作修辭亮點與 3 題閱讀測驗。
- **答案置底**：測驗後插入水平線 `<hr>`，將繁體中文解答置於頁面最底端「答案」區塊，便於讀者自我測驗。
- **原文導引**：頁面清楚註明「原文全文請見圖文完整版。」，原文字句不公開於 Telegraph。

### 隱私與版權安全說明

> [!IMPORTANT]
> 1. **公開連結性質**：Telegraph 頁面任何持有 URL 者皆可瀏覽，且 Telegraph API 不支援刪除頁面，僅支援以 Token 原地編輯更新。
> 2. **版權嚴格隔離**：期刊內文插圖、圖表、地圖、漫畫與英文原文全文，**一律僅於私人網站（`output/`）與本機報告中流通**，絕不上傳至 Telegraph。
> 3. **隨機不可臆測網址**：系統以隨機雜湊路徑配置 Telegraph 頁面，防範外部爬取。請勿將個人 Telegraph 導讀連結公開散布。

---

## 私人網站與封存系統（`output/`）

系統每次執行時，會將當期內容建構成現代化的響應式多頁網站，存放於專屬的 `output/` 封存目錄中。

### `output/` 目錄結構

`output/` 目錄已由 `.gitignore` 排除，其結構如下：

```
output/
├── index.html                  # 歷史封存總覽首頁（卡片式列出所有期別、封面與概覽）
├── assets/
│   └── site.css                # 網站共用 CSS 樣式表
└── 2026-10-03/                 # 依期別命名的資料夾（格式：YYYY-MM-DD）
    ├── TheEconomist.2026.10.03.epub # 當期原始 EPUB 檔案（提供下載連結）
    ├── .issue.json             # 該期中繼資料（期別、標題、概覽、封面檔名）
    ├── index.html              # 本期導讀首頁（含封面、概覽、EPUB 下載與分頁導覽卡片）
    ├── brief.html              # 本週要聞速覽（含要聞配圖與本週漫畫）
    ├── taiwan.html             # 台灣專區（含文章題圖與脈絡圖表）
    ├── focus.html              # 本週焦點（3 篇深度解析與完整圖表）
    ├── world.html              # 國際（美國、中國、亞太、歐洲等）
    ├── topics.html             # 財經・科技・文化
    ├── english.html            # 英文學習（包含完整原文全文與段落編號）
    └── img/                    # 本期提取之高解析度插圖與圖表
        └── [hash].jpg
```

### 私人網站發布（Private Site Publishing）

透過 `config.toml` 中的 `[site]` 設定，系統能透過非互動式 SSH 與 `rsync` 自動將 `output/` 發布至您的私有 Web 伺服器：

```toml
[site]
enabled = true
base_url = "https://site.example.com"
ssh_host = "my-vm"
remote_dir = "/var/www/site"
ssh_timeout_seconds = 30
```

#### 伺服器規格與 Caddyfile 配置範例

建議使用具備自動 HTTPS 的 Caddy 網頁伺服器。伺服器配置需符合三項通用原則：
1. **全站 Basic Auth**：多頁網站、文章插圖與 EPUB 下載全面受到 HTTP 基本身分驗證保護。
2. **公開 `/covers/` 路徑**：Telegraph 伺服器需要讀取封面圖片以顯示 Instant View 首圖。系統發布時會將封面圖複製為不可猜測的 32 碼隨機檔名（`covers/[hash].jpg`）發布至 `/covers/`，此路徑需公開免密碼。
3. **防搜尋引擎檢索**：加入 `X-Robots-Tag: noindex, noarchive` 標頭。

Caddy 範例設定（`Caddyfile`）：

```caddy
site.example.com {
    root * /var/www/site
    encode gzip zstd

    # 防止搜尋引擎索引
    header X-Robots-Tag "noindex, nofollow, noarchive"

    # 1. Telegraph 讀取封面圖專用路徑（公開免驗證）
    @covers path /covers/*
    handle @covers {
        file_server
    }

    # 2. 其餘所有頁面、插圖與 EPUB 檔案一律要求帳號密碼
    handle {
        basicauth {
            username $2a$14$...hashed_password...
        }
        file_server
    }
}
```

### 發布失敗備援機制（Fallback）

若在網路離線、未連上指定 VPN 或 SSH 逾時導致私人網站發布失敗：
- 終端機與日誌會記錄警告：`私人網站發布失敗；改用單檔 HTML 報告。`
- 傳送至 Telegram 的摘要訊息會**自動省略**「🔒 圖文完整版」連結。
- 系統會**自動附送單檔離線 HTML 報告文件**（`report.html`）至私人聊天室，確保您在任何情況下都不會遺漏完整圖文內容。

### 私有 GitHub 儲存庫備份（Backup）

系統可將整個 `output/` 資料夾（獨立初始化之巢狀 Git 儲存庫）在每期處理完成後自動備份至您的私有 GitHub 儲存庫：

```toml
[backup]
enabled = true
remote = "git@github.com:OWNER/econ-digest-output.git"
branch = "main"
author_name = "Your Name"
author_email = "you@example.com"
```

> [!CAUTION]
> **嚴格安全要求**：
> 1. **必須維持為 PRIVATE 私有儲存庫**：`output/` 內含未公開之完整文章文字、插圖與 EPUB 原始檔案，備份儲存庫**絕對必須設為 Private**，且**絕不可指向公開的程式碼儲存庫**！系統內建安全檢查，若目錄指向程式碼工作區會主動拒絕執行。
> 2. **備份失敗不阻斷**：備份作業採盡力而為（Best-effort）原則。若發生網路失敗或 Git 驗證錯誤，系統僅記錄警告，導讀傳送主流程會持續順利完成。

---

## Telegram 頻道推播（Channel）

除私人聊天室外，系統支援將每期導讀同步推送至 Telegram 頻道（Channel）：

1. **設定頻道 ID**：
   執行設定指令自動綁定或指定頻道：
   ```sh
   .venv/bin/econ-digest telegram-setup --channel @my_channel
   ```
   （*機器人必須先加入該頻道，並被提升為管理員且具備「張貼訊息」（can_post_messages）權限。*）
2. **頻道推播內容規範**：
   - 頻道接收與私人聊天室相同的核心摘要（期別概覽、台灣相關焦點清單、各分頁 Instant View 超連結與大圖封面預覽）。
   - **完全不發送私人網站連結**：頻道訊息中**絕對不包含**「🔒 圖文完整版」連結。
   - **不發送文件與原文**：頻道絕對不發送任何附件檔案或摺疊原文，維護頻道簡潔與隱私安全。

---

## 分類與摘要深度

### 台灣關聯層級（Taiwan Levels）

| 層級代號 | 層級名稱 | 判定定義 | 預設摘要深度 |
| :--- | :--- | :--- | :--- |
| **T1** | 台灣本身 | 台灣是報導的主要主題。 | **Tier A**（深度解析） |
| **T2** | 台灣與國際 | 台灣是國際事件的主要參與者之一，例如台美關係、兩岸、半導體供應鏈等。 | **Tier B**（詳細摘要） |
| **T3** | 間接相關 | 報導實質提及台灣，或議題對台灣有重大牽連。 | **Tier C**（重點摘要） |

### 本週焦點機制

非台灣主軸報導中，模型每期挑選 **3 篇**最關鍵文章（`[analysis] focus_count = 3`），升級為 **Tier A 深度解析**，並於「本週焦點」獨立章節與頁面呈現，不與後續一般分類重疊。

### 章節與分類排序

非台灣主軸（T0）且非本週焦點的文章，依序歸入下列分類：

1. **美國**（`intl.us`）
2. **中國（含港澳）**（`intl.china`）
3. **亞太**（`intl.asia`）
4. **歐洲（含英國、俄烏）**（`intl.europe`）
5. **其他地區與全球議題**（`intl.other`）
6. **財經商業**（`finance`）
7. **科技**（`tech`）
8. **科學**（`science`）
9. **文化生活**（`culture`，含訃聞與讀者投書）

### 摘要深度等級表（Tiers）

| 深度代號 | 層級名稱 | 預期中文字數 | 核心產出內容 | 預設對應規則 |
| :---: | :--- | :--- | :--- | :--- |
| **A** | 深度解析 | 約 800–2,700 字 | 中文標題、背景脈絡、段落結構（標註段落範圍）、論點剖析（主張／論據／反方觀點／結論）、關鍵數據、忠實原文引述與中譯、立場分析、對台灣影響與啟示、延伸思考。 | 台灣 **T1** 報導；**本週焦點（3 篇）** |
| **B** | 詳細摘要 | 約 400–1,250 字 | 中文標題、4–6 項核心重點、完整論點分析、對台灣影響與啟示。 | 台灣 **T2** 報導；封面社論對應報導最低門檻 |
| **C** | 重點摘要 | 約 165–550 字 | 中文標題、3–5 項核心重點。 | 台灣 **T3** 報導；美國 (`intl.us`)、中國 (`intl.china`)；其他社論對應報導最低門檻；特別報導最低門檻 |
| **D** | 簡要摘要 | 約 50–210 字 | 中文標題、2–3 句簡明摘要。 | 亞太 (`intl.asia`)、歐洲 (`intl.europe`)、財經商業 (`finance`)、科技 (`tech`) |
| **E** | 一句話 | 約 20–85 字 | 一句話核心論點。 | 其他地區 (`intl.other`)、科學 (`science`)、文化生活 (`culture`)；讀者投書、訃聞 |

### 特殊文章處理

1. **本週要聞速覽（brief）**：取材自 "The world this week"，涉及台灣之條目標示「【台灣相關】」並置頂，不使用國旗 emoji。
2. **社論合併（merged）**：社論觀點合併至對應專題報導，標註為「經濟學人立場」（含「作者主張」），不產出重疊篇幅。
3. **略過不處理（skip）**：漫畫（`cartoon`）與經濟指標（`indicators`）直接略過，不消耗模型額度。

---

## 英文學習選文

每期系統自具學習價值之文體中（字數 600–1,300 字），結合最近 8 期選文紀錄避免連續重複主題，由模型評選出一篇適合中級英語學習者（全民英檢中級／多益 550–780／CEFR B1）之長文。包含篇章 CEFR 分析、中文推薦理由、背景導讀、14 個重點單字庫（字典原形、詞性、釋義、出自原文例句、用法補充）、7 個實用片語、長難句拆解分析、寫作修辭亮點與 3 題閱讀測驗（解答置底）。原文全文於私人網站中完整刊載對照。

---

## 系統架構

### 處理管線流程

```
[fetch] 下載 EPUB 檔案
   ↓
[parse] 解析結構與段落
   ↓
[classify] 透過 LLM 識別台灣關聯層級（T1–T3）與領域分類
   ↓
[pair] 將 Leaders 社論與各章節專文進行關聯配對
   ↓
[tiers] 套用深度政策，決定各篇 Tier（T1 與本週焦點 3 篇升為 Tier A）
   ↓
[summaries / brief / English] 平行呼叫 LLM 產出各級摘要、要聞速覽與英文研讀指南
   ↓
[zh-TW normalisation] 僅針對含非 Big5 字元之 CJK 片段以 OpenCC 轉繁，套用 glossary.tsv
   ↓
[render & site build] 產生 Markdown、HTML 報告、Telegraph 頁面節點與 output/ 多頁網站
   ↓
[site publish & backup] 透過 SSH rsync 發布私人網站，並將 output/ 備份至私有 GitHub 儲存庫
   ↓
[send] 推送 Telegram 單則核心摘要訊息（含 Instant View 連結與私人網站連結）與頻道推播
```

### 模組職責地圖

| 模組路徑 | 職責說明 |
| :--- | :--- |
| `src/econ_digest/cli.py` | 命令列介面入口與參數解析。 |
| `src/econ_digest/config.py` | TOML 設定檔載入、驗證與密鑰管理。 |
| `src/econ_digest/site/` | 多頁網站建置（`build.py`）、SSH rsync 發布（`publish.py`）與 Git 私有備份（`backup.py`）。 |
| `src/econ_digest/analysis/focus.py` | 評選本週 3 篇關鍵國際焦點專文並升級為 Tier A。 |
| `src/econ_digest/render/` | Markdown、HTML 報告、Telegraph 頁面與 Telegram 訊息切塊。 |
| `src/econ_digest/images.py` | 自 EPUB 提取封面、題圖、內文圖表、漫畫與要聞配圖。 |
| `src/econ_digest/commands/send.py` | Telegram 與 Telegraph 發送協調、斷點續傳與 `--pages-only` 整合。 |
| `src/econ_digest/commands/telegram_setup.py` | 私人聊天室與頻道設定。 |

---

## 安裝

### 系統需求
- **Python**：>= 3.11
- **gwg**：已於系統中安裝並登入，且位於 `PATH` 中。
- **opencc**（建議安裝）：`sudo apt install opencc`。
- **rsync / ssh**：用於私人網站發布。
- **git**：用於 `output/` 私有儲存庫備份。

### 安裝步驟

```sh
# 建立虛擬環境並安裝
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

---

## Telegram、Telegraph 與頻道設定

### 1. 建立 Telegram 機器人
1. 在 Telegram 搜尋 `@BotFather` 並發送 `/newbot`。
2. 取得機器人 Token。

### 2. 安全建立密鑰檔
執行下列指令以隱藏輸入方式建立 `~/.config/econ-digest/env`（權限自動設為 `600`）：
```sh
mkdir -p ~/.config/econ-digest && read -rsp 'Token: ' T && printf 'TELEGRAM_BOT_TOKEN=%s\n' "$T" > ~/.config/econ-digest/env && chmod 600 ~/.config/econ-digest/env && unset T; echo
```

### 3. 設定私人聊天室與頻道
- **綁定私人聊天室**：
  在 Telegram 向機器人發送 `/start`，隨後執行：
  ```sh
  .venv/bin/econ-digest telegram-setup --test
  ```
  程式會自動填入 `TELEGRAM_CHAT_ID` 並發送測試成功訊息。
- **綁定頻道**：
  將機器人加入頻道並設為管理員（具備張貼權限），隨後執行：
  ```sh
  .venv/bin/econ-digest telegram-setup --channel @my_channel --test
  ```
  程式會自動將頻道 ID 儲存至 `TELEGRAM_CHANNEL_ID`。

### 4. 設定 Telegraph 帳號
執行下列指令自動註冊專屬 Telegraph 帳號並寫入 Token：
```sh
.venv/bin/econ-digest telegraph-setup
```
若需重新產生全新帳號，可加上 `--force`。

### 密鑰清單與安全防護
所有密鑰存放於環境變數或 `~/.config/econ-digest/env`（權限 600），**絕不放入 `config.toml`**：
- `TELEGRAM_BOT_TOKEN`：機器人 Token。
- `TELEGRAM_CHAT_ID`：私人聊天室 ID。
- `TELEGRAM_CHANNEL_ID`：（選填）頻道 ID。
- `TELEGRAPH_ACCESS_TOKEN`：Telegraph 存取權杖。
- `GITHUB_TOKEN`：（選填）GitHub API 個人存取權杖。

日誌輸出中所有密鑰均會自動遮蔽為 `[已隱藏]`。

---

## 使用方式

### 指令與旗標一覽

全域參數：`econ-digest [-h] [--config PATH] [-v] <command> [options]`

| 子指令 | 支援旗標 | 功能說明 |
| :--- | :--- | :--- |
| `run` | `[--issue latest\|YYYY.MM.DD]`<br>`[--no-send]`<br>`[--dry-run]`<br>`[--force]`<br>`[--reanalyze]` | 執行完整管線：下載、解析、分析、建置網站、發布、備份與推播。<br>• `--no-send`：產生報告但不發送至 Telegram。<br>• `--dry-run`：執行分析並建置但不傳送。<br>• `--force`：已傳送期別依然重新處理。<br>• `--reanalyze`：重新執行模型分析。 |
| `fetch` | `[--issue latest\|YYYY.MM.DD]` | 下載指定期別的 EPUB 檔案。 |
| `parse` | `[--issue latest\|YYYY.MM.DD]` | 解析 EPUB 文章並儲存至 `issue.json` 快取。 |
| `signals` | `[--issue latest\|YYYY.MM.DD]` | 掃描文章並列出所有偵測到台灣相關關鍵詞之篇目。 |
| `analyze` | `[--issue latest\|YYYY.MM.DD]`<br>`[--reanalyze]`<br>`[--plan]`<br>`[--only-tier {A,B,C,D,E}]`<br>`[--limit N]` | 執行分類、配對、本週焦點評選、深度分級與摘要產生。<br>• `--plan`：僅列出分析批次規劃，不呼叫模型。<br>• `--only-tier`：僅產出指定深度之摘要。<br>• `--limit N`：最多產生 N 篇摘要。 |
| `render` | `[--issue latest\|YYYY.MM.DD]` | 從既有 `digest.json` 產出 Markdown、HTML 報告與切塊訊息。 |
| `send` | `[--issue latest\|YYYY.MM.DD]`<br>`[--force]`<br>`[--dry-run]`<br>`[--pages-only]` | 執行發布與推播：<br>• `--force`：重新發送所有訊息（Telegraph 原地編輯更新）。<br>• `--dry-run`：離線列印 Telegraph 頁面大小與訊息排版。<br>• `--pages-only`：**重建並重新發布私人網站、原地編輯更新 Telegraph 頁面、執行 GitHub 備份，完全不向 Telegram 聊天室發送任何訊息**。 |
| `telegraph-setup` | `[--force]` | 建立 Telegraph 導讀帳號。<br>• `--force`：建立新帳號並取代現有密鑰。 |
| `telegram-setup` | `[--channel [@USERNAME]]`<br>`[--chat-id CHAT_ID]`<br>`[--test]`<br>`[--wait SECONDS]` | 綁定私人聊天室或頻道。<br>• `--channel`：設定可張貼訊息之頻道。<br>• `--chat-id`：直接指定聊天室 ID。<br>• `--test`：發送測試確認訊息。<br>• `--wait`：等候 `/start` 秒數（預設 120）。 |

### 典型操作流程

#### 1. 首次手動執行（不發送）
```sh
.venv/bin/econ-digest run --no-send
```
檢視 `output/` 產出之網站與 `data/issues/te_<期別>/report.html`，確認內容無誤後推送：
```sh
.venv/bin/econ-digest send
```

#### 2. 原地維護更新（`send --pages-only`）
若微調了文字或詞彙表，希望更新已發布的 Telegraph 頁面、重新同步私人網站並完成備份，但**不打擾 Telegram 私人聊天室**：
```sh
# 離線預覽各分頁大小
.venv/bin/econ-digest send --pages-only --dry-run

# 重建並發布網站、更新 Telegraph 頁面、推送到備份儲存庫
.venv/bin/econ-digest send --pages-only
```

---

## 設定檔（`config.toml`）

複製範例設定檔進行客製化：
```sh
cp config.example.toml config.toml
```

### 完整範例（含站台與備份 Placeholder）

```toml
[paths]
data_dir = "data"
output_dir = "output"

[source]
repo = "hehonghui/awesome-english-ebooks"
branch = "master"
folder = "01_economist"

[llm]
backend = "gwg"
gwg_bin = "gwg"
max_parallel = 2
call_timeout_seconds = 300
no_account_wait_seconds = 900

[llm.models]
classify = ["gemini-3.8-flash-high", "claude-sonnet-4-6"]
pair = ["gemini-3.8-flash-high", "claude-sonnet-4-6"]
focus = ["gemini-3.8-flash-high", "claude-sonnet-4-6"]
summarize_a = ["gemini-3.8-flash-high", "claude-sonnet-4-6"]
summarize_b = ["gemini-3.8-flash-high", "claude-sonnet-4-6"]
summarize_c = ["gemini-3.8-flash-high", "claude-sonnet-4-6"]
summarize_d = ["gemini-3.8-flash-high", "claude-sonnet-4-6"]
summarize_e = ["gemini-3.8-flash-high", "claude-sonnet-4-6"]
brief = ["gemini-3.8-flash-high", "claude-sonnet-4-6"]
english = ["gemini-3.8-flash-high", "claude-sonnet-4-6"]

[tiers]
cover_companion_min = "B"
leader_companion_min = "C"
taiwan = { "1" = "A", "2" = "B", "3" = "C" }
category = { "intl.us" = "C", "intl.china" = "C", "intl.asia" = "D", "intl.europe" = "D", "finance" = "D", "tech" = "D", "intl.other" = "E", "science" = "E", "culture" = "E" }
min_tier_by_kind = { briefing = "C" }
force_tier_by_kind = { letters = "E", obituary = "E" }

[analysis]
focus_count = 3 # 台灣專區外，選出 3 篇關鍵國際焦點升為 Tier A

[english]
level = "全民英檢中級（多益約 550–780，CEFR B1）"
min_words = 600
max_words = 1300
vocab_count = 14
phrase_count = 7

[telegram]
enabled = true
delivery = "telegraph"
send_report_file = false        # 預設 false；網站發布失敗時自動備援發送
cover_photo = false             # 預設 false；選用舊版獨立相片訊息
original_text_messages = false  # 預設 false；選用私訊摺疊原文
message_delay_seconds = 1.1

[report]
embed_images = true

[telegraph]
author_name = "經濟學人導讀"
author_url = ""
page_limit_bytes = 60000

# 私人網站發布設定（請使用您的專屬主機與網址）
[site]
enabled = false
base_url = "https://site.example.com"
ssh_host = "my-vm"
remote_dir = "/var/www/site"
ssh_timeout_seconds = 30

# 私有儲存庫備份（必須是 Private repository）
[backup]
enabled = false
remote = "git@github.com:OWNER/econ-digest-output.git"
branch = "main"
author_name = "Your Name"
author_email = "you@example.com"
```

---

## 排程

透過 systemd 使用者定時器進行週末自動化監控與執行：
```sh
# 安裝並啟用定時器
deploy/install-user-timer.sh

# 查看執行狀態
systemctl --user list-timers econ-digest.timer
journalctl --user -u econ-digest.service
```

---

## 資料、封存與隱私

### `data/` 與 `output/` 配置說明

```
data/                           # 本機運算、模型快取與狀態（不公開）
├── .lock
├── state.json
├── logs/
└── issues/
    └── te_2026.10.03/
        ├── TheEconomist.2026.10.03.epub
        ├── issue.json
        ├── digest.json
        ├── report.md
        ├── report.html
        ├── telegraph_pages.json
        └── analysis/

output/                         # 網站發布與封存目錄（gitignored，備份至私有儲存庫）
├── index.html                  # 歷史總覽首頁
├── assets/site.css
└── 2026-10-03/
    ├── index.html
    ├── brief.html
    ├── taiwan.html
    ├── focus.html
    ├── world.html
    ├── topics.html
    ├── english.html
    └── img/
```

> [!IMPORTANT]
> `output/` 與 `data/issues/` 包含《經濟學人》原始文章與完整圖文，著作權歸 The Economist Newspaper Limited 所有。請確保 `output/` 備份儲存庫設定為 **Private**，切勿公開散布。

---

## 開發與測試

```sh
# 執行測試套件
.venv/bin/pytest
```
系統內建測試配額守衛（Quota Guard），防止自動測試時意外消耗共享 API 配額。
