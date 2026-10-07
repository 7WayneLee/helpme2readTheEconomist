# econ-digest

每週《經濟學人》（The Economist）新刊發行時，`econ-digest` 會自動從 GitHub 下載最新 EPUB 期別，透過本機大型語言模型（LLM）池進行全文解析與台灣讀者導向的深度分級摘要。**系統預設以 Telegraph 即時檢視（Instant View）搭配私人圖文網站傳送至您的 Telegram 私人聊天室**：每期抵達時以**單則 Telegram 訊息**發送核心導讀（包含刊期標題、標頭摘要列「〈本期封面故事標題〉｜共 N 篇文章」、無數字編號之 Instant View 各主題分頁連結，以及導向私人多頁網站的「🔒 圖文完整版（需帳密）」連結）。每一個 Telegraph 頁面均以該期封面圖為首圖（圖說標註「本期封面：…」），使 Instant View 與聊天室大圖預覽（Large media）均能完整呈現封面。同時提供可選用的舊版行為與逐則訊息推播模式，兼顧行動端極速閱讀、版權隱私與深度研讀需求。

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
  - [雙層導覽架構（Two-Level Navigation）](#雙層導覽架構two-level-navigation)
  - [私人網站發布（Private Site Publishing）](#私人網站發布private-site-publishing)
  - [發布失敗備援機制（Fallback）](#發布失敗備援機制fallback)
  - [私有 GitHub 儲存庫備份（Backup）](#私有-github-儲存庫備份backup)
- [Telegram 頻道推播（Channel）](#telegram-頻道推播channel)
- [Threads 文章排程](#threads-文章排程)
- [新聞編輯與寫作風格（House Style）](#新聞編輯與寫作風格house-style)
- [分類與摘要深度](#分類與摘要深度)
  - [台灣關聯層級（Taiwan Levels）與外部查證約束](#台灣關聯層級taiwan-levels與外部查證約束)
  - [本週焦點機制](#本週焦點機制)
  - [章節與分類排序](#章節與分類排序)
  - [摘要深度等級表（Tiers）](#摘要深度等級表tiers)
  - [特殊文章處理](#特殊文章處理)
- [英文學習選文](#英文學習選文)
- [系統架構](#系統架構)
  - [處理管線流程](#處理管線流程)
  - [模組職責地圖](#模組職責地圖)
  - [模型路由與管線階段（Model Routing & Pipeline Stages）](#模型路由與管線階段model-routing--pipeline-stages)
  - [多來源證據檢索（Research）](#多來源證據檢索research)
  - [台灣事實清單維護（Fact Sheet Maintenance）](#台灣事實清單維護fact-sheet-maintenance)
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

1. **單則 Telegram 核心導讀訊息**：
   - **刊期標題與標頭摘要列**：刊期標題（`📰 經濟學人導讀｜YYYY 年 M 月 D 日號`）與標頭列（`〈本期封面故事標題〉｜共 N 篇文章`）。不再發送「與台灣相關」獨立條列區塊，維持極致俐落與專業的中立排版。
   - **各主題分頁 Instant View 超連結（無數字編號）**：
     - 本週導讀
     - 台灣
     - 本週焦點
     - 國際
     - 財經・科技・文化
     - 英文學習
     （*僅列出當期實際存在的分頁，省略無內容之分頁*）
   - **私人圖文完整版連結**：末端附上「🔒 圖文完整版（需帳密）：開啟」，點擊即可開啟架設於個人伺服器、受帳號密碼保護的多頁式圖文完整版網站。
2. **大圖預覽與封面首圖**：
   - 每一個 Telegraph 頁面開頭均以當期期刊封面照片作為首圖（Figure，圖說標註「本期封面：…」）。
   - Telegram 收到訊息時會辨識第一頁 Telegraph 連結，並採用大圖卡（Large media）預覽，直接在聊天室展示精美封面照片；點擊 Instant View 亦能立即以原生介面展開閱讀。
3. **事實檔更新提醒（私訊專屬）**：
   - 每週若透過查證機制發現潛在事實異動，系統會另行於私人聊天室發送單則「⚠️ 台灣事實檔可能需要更新：…（請確認）」警報訊息（附中央社連結），頻道絕不推送此訊息，亦不干擾主導讀訊息。

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
   - 標頭概覽（`〈本期封面故事標題〉｜共 N 篇文章`）。
   - 「本週要聞速覽」：收錄該期 "The world this week" 政治與商業要聞，台灣相關要聞以「【台灣相關】」標記並置頂呈現。
2. **台灣**（`taiwan`）：
   - 獨立成頁！收錄台灣專區報導（台灣關聯層級 T1 至 T3）之深度解析與詳細摘要。
   - 台灣陳述與意涵下方均標註客觀查證出處（如「依據：來源名稱 YYYY/MM/DD〈標題〉」超連結）。
3. **本週焦點**（`focus`）：
   - 獨立成頁之國際核心專題深度解析（詳見下方說明）。
4. **國際**（`international`）：
   - 收錄非台灣主軸、非焦點之各區域報導：美國（`intl.us`）、中國含港澳（`intl.china`）、亞太（`intl.asia`）、歐洲含英與俄烏（`intl.europe`）及其他全球區域報導（`intl.other`）。
5. **財經・科技・文化**（`topics`）：
   - 收錄財經商業（`finance`）、科技（`tech`）、科學（`science`）與文化生活（`culture`，含訃聞與讀者投書）專文與摘述。
6. **英文學習**（`english`）：
   - 精選長文研讀指南（詞彙庫、片語、長難句精析、修辭亮點與測驗）。
   - 選文只參考早於當期的最近 8 筆紀錄；重新分析已送出的期別時，沿用該期最後送出的有效選文，指南照常產生或讀取快取。每期僅保留最後送出的選文紀錄；舊選文失效時會警告並重新評選，指南失敗時仍可改選另一篇。

### 本週焦點（Focus Articles）

- **智慧評選**：除台灣專區文章外，模型會自當期全體候選文章中評選出最重要的 3 篇報導（數量由 `[analysis] focus_count` 設定，預設為 `3`）。
- **升級深度解析**：選出的焦點報導一律升級為最高規格的 **Tier A 深度解析**。
- **獨立設頁不重複**：焦點報導集中呈現於「本週焦點」獨立章節與獨立 Telegraph 分頁中，不會在後續的「國際」或「財經・科技・文化」頁面重複出現。

### 章節與排版規則

- **空章節完全省略**：當期若無特定分類之報導（例如該期無科學文章），該章節與對應分頁會完全隱藏，不留空白標題。
- **無章節數字序號**：分頁標籤與章節標題一律為純文字（「本週導讀」、「台灣」、「本週焦點」、「國際」等），不冠上序號。
- **專業用詞規範**：內文一律使用「**經濟學人立場**」與「**作者主張**」，絕不使用「社論」字眼。
- **無附錄**：報告不設冗長的附錄章節。
- **簡短條目無收合開關**：一句話簡短摘要（Tier E 等單句條目）直接展示內容，不加入多餘的「閱讀摘要」收合開關（disclosure toggle）。
- **具體查證出處標註**：台灣專區與涉台報導之關聯陳述或意涵下方，一律附上至多 3 筆「依據：來源名稱 YYYY/MM/DD〈標題〉」外部來源超連結（此標註行見於私人網站、HTML 報告、Markdown 報告與 Telegraph 頁面，Telegram 聊天室訊息則省略以維持版面簡潔）。

### 圖片配置規範（Telegraph 公開頁面 vs 私人網站）

為嚴格遵守著作權法規並保障個人隱私，系統對公開與私密管道實施明確的圖片隔離政策：

1. **Telegraph 公開頁面**：
   - Telegraph 頁面為公開網址，任何人持有連結皆可瀏覽。基於版權保護，**Telegraph 頁面僅攜帶期刊封面照片作為首圖**（帶有圖說「本期封面：…」，供 Instant View 封面顯示），**絕不包含任何內文插圖、圖表、地圖、漫畫或原始英文全文**。
2. **私人網站（Private Site，需帳密認證）**：
   - **置頂題圖（Head image）**：文章若有配圖，題圖精確置於「一句話重點」標題正上方。
   - **內文圖表與地圖（Inline charts / maps / photos）**：僅出現在 **Tier A 深度解析**文章（台灣 T1 報導與本週焦點），並依照段落編號精準插入於「文章脈絡」對應段落旁。
   - **內文圖片說明**：模型直接查看圖片，以 6–40 字的 `alt_zh` 簡短辨識主題，另以 `description_zh` 交代如何讀圖。圖表與地圖先用一句 10–60 字的 `takeaway_zh` 提出最清楚的單一重點，圖說為「▲ 圖表｜重點：…　…」或「▲ 地圖｜重點：…　…」；讀圖說明為 20–140 字，交代清楚印出的類型、比較對象、單位、期間及來源。重點與說明都省略小箭頭、細微差距、近似項目的排名及不明確的例外，數值只引用印出的數字或明確落在刻度上的值。照片與插畫保留「▲ 配圖：…」，描述為 8–60 字，不含重點句。重點句無效時仍顯示讀圖說明；其他欄位無效時保留原圖並省略圖說。單檔 HTML 報告採用相同格式，舊導讀仍沿用原圖說與替代文字。
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
> 3. **隨機網址**：系統以隨機雜湊路徑配置 Telegraph 頁面。選用 Threads 發文後，選定專區的導讀連結會隨貼文公開；私人圖文網站與原文仍由帳密保護。

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

### 雙層導覽架構（Two-Level Navigation）

私人多頁網站具備專為行動端與桌面端設計的現代化雙層導覽體系：
1. **頂部麵包屑導覽（Breadcrumb）**：各分頁頂部呈現「[所有期別](../index.html) › 本期期別（如 2026/10/03 號）」，標示網站階層並便於隨時返回歷史封存首頁或本期首頁。
2. **置頂黏性章節分頁籤（Sticky Section Tabs）**：置頂橫向分頁導覽列（包含「要聞」、「台灣」、「焦點」、「國際」、「財經科技文化」、「英文」），隨頁面滾動固定於頂部，當前所在頁面高亮標示（`aria-current="page"`），便於單手滑動切換。
3. **頁尾章節切換連結（Previous / Next Links）**：各章節底部提供「‹ 前一章節」與「後一章節 ›」切換按鈕，方便讀者順暢依序通讀全刊導讀。
4. **具體查證出處標註**：在台灣專區與相關文章之「與台灣的關聯」或「對台灣的意涵」段落下方，精準附上至多 3 筆「依據：來源名稱 YYYY/MM/DD〈標題〉」外部查證連結。
5. **閱讀摘要預設展開**：台灣專區所有文章的「閱讀摘要」均預設展開，包含 C 級文章；其他專區依原有規則僅展開 A、B 級摘要。單檔 HTML 報告的台灣文章亦同。

### 私人網站發布（Private Site Publishing）

透過 `config.toml` 中的 `[site]` 設定，系統能透過非互動式 SSH 與 `tar` 串流自動將 `output/` 發布至您的私有 Web 伺服器：
- **環境需求與預檢**：本機必須存在 `ssh` 與 `tar`，連線時會於遠端執行 `command -v tar` 預檢，確認遠端環境支援。
- **暫存串流與原子替換**：將本期發布資料夾以 tar 封裝透過 SSH 串流傳輸至遠端暫存目錄（`.incoming/`），解開並確認權限後，以原子替換（atomic swap）方式部署至目標目錄（舊版目錄暫存為備份，若替換失敗自動還原；成功後清除備份）。
- **失敗備援**：若發布失敗，摘要訊息自動省略網站連結，自動改以單檔 HTML 報告文件（`report.html`）作為附件備援。傳輸與部署均透過 SSH 與 tar 完成。

```toml
[site]
enabled = true
base_url = "https://site.example.com"
ssh_host = "your-server"
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
   - 頻道接收與私人聊天室相同的核心導讀（刊期標題、標頭摘要列「〈本期封面故事標題〉｜共 N 篇文章」、各分頁 Instant View 超連結與大圖封面預覽）。
   - **完全不發送私人網站連結**：頻道訊息中**絕對不包含**「🔒 圖文完整版」連結。
   - **完全不發送事實清單更新提醒**：台灣事實檔更新提醒（`fact_alerts`）為私訊專屬，絕不推送至頻道。
   - **不發送文件與原文**：頻道絕對不發送任何附件檔案或摺疊原文，維護頻道簡潔與隱私安全。

---

## 新聞編輯與寫作風格（House Style）

導讀的標題重寫與中文摘要遵循 `src/econ_digest/prompts/_style.md`。原有中央社人地譯名與短標題、《報導者》的制度背景框架，再加入轉角國際的解釋方法與公視的平實歸因：先寫行動與變化，再補爭點；陌生機構先全名後簡稱；保留提案、估計與預測的條件；區分百分比與百分點。台灣連結須有提供的原文、事實檔或查證證據，不以相似處境預言相同結果。研究方法與來源見 [docs/research/writing-style.md](docs/research/writing-style.md)。

### 1. 標題語法規範（嚴格遵循）

- **長度規範**：目標字數為 **12–24 個繁體中文字**。
- **雙子句全形空格分隔**：至多兩個子句，子句間**一律以全形空格「　」**分隔（禁止使用逗號「，」、斜線「/」或分號）。
- **禁用問號「？」**：一律以主動、肯定或評估判斷句陳述核心事實與動向，絕不使用「…嗎？」等反問句。
- **冒號「：」嚴格限於發言主體與引述**：僅用於引出特定發言者、機構或來源（如「經濟學人：…」、「民調：…」、「印度財長：…」），嚴禁用冒號代替破折號或同位語。
- **強力主動動詞**：多用精準單雙音節動詞（如控、批、擬、恐、創、遭、獲、拚、揭、陷、飆、釀、襲、示警、反攻、重挫等）。
- **阿拉伯數字與術語**：數字、百分比、日期統一採**阿拉伯數字**（如 2026年、51%、3.2億美元）；標題簡化為「**AI**」而不寫「人工智慧」（內文首次提及可寫全稱）。

### 2. 忠於原文與真實性（最高核心原則）

- **嚴禁增添原文未提及之內容**：摘要與標題必須**嚴格忠於原文**，絕對不得自行添加原文未載明的事實、推論、立場標籤、戲劇性衝突或情緒化字眼。
- **精簡原則（捨細節而非造框架）**：在字數限制下壓縮時，應刪減次要細節，絕不可憑空捏造敘事框架。
- **立場與評論標記**：遇評論文章若需點明立場，使用「經濟學人：…」、「經濟學人專欄：…」或「經濟學人立場：…」；**絕對禁用「社論」二字**。

### 3. 翻譯腔黑名單與自然置換

系統全面禁止生硬英式直譯，於提示詞與後處理中嚴格執行替換：
- 剔除「進行訪問/打擊」（改為訪問、空襲）、「作出決定/反應」（改為拍板、反擊）、「對…進行」。
- 剔除「隨著…的…」（改為因、鑑於、在…之際）、「基於」、「該國/該機構」（改為這個國家、此機構、相關部會）。
- 剔除模糊套話「存隱憂」（改為恐難成局、藏變數、現隱患）、「面臨消長」（改為態勢逆轉、首度超越、差距拉大）。
- 剔除劣質俗語「力抗/大秀」（改為抵禦、展現）、「開創新局」（改為開啟新頁、迎來轉機）、「接熱線」（改為通話、接聽危機專線）。

### 4. 樂詞網概念譯名參考

摘要 A–E 與編輯階段會逐篇比對英文標題、簡介與全文，加入「譯名參考（國家教育研究院樂詞網）：English → 中文；…」。套件附 119 個精選概念，涵蓋外交、經貿、法律、軍事、資訊、半導體、能源與公共衛生；整詞、不分大小寫，多詞組優先，每篇最多 15 詞、900 UTF-8 bytes。模型依語境選用，人名與地名仍依中央社，不把提示當成新增事實的依據。

資料只在本機讀取，不連網查詞；詞檔缺失、無法讀取或無命中時，提示保持原狀。清單刪除多譯名、常見單字與不可靠記錄，覆蓋範圍有限。精選依樂詞網資料開放宣告註明出處後發布，顯名、下載來源與授權見 [terms-NOTICE.md](src/econ_digest/zhtw/terms-NOTICE.md)，不代表國教院背書。文風或命中的術語提示改變會使相關生成快取失效；產出後的 `glossary.tsv` 正體化另行處理，操作方式見[操作文件](docs/operations.md#文風與樂詞網術語更新)。

---

## 分類與摘要深度

### 台灣關聯層級（Taiwan Levels）與外部查證約束

為確保台灣專區報導具備實質意義與客觀依據，系統實施嚴格的關聯認定、提及型態分類與查證防護機制：

| 層級代號 | 層級名稱 | 判定定義與實質提及規則 | 預設摘要深度 |
| :--- | :--- | :--- | :--- |
| **T1** | 台灣本身 | 台灣是報導的主要主題。原文實質討論台灣，陳述事實關聯，不可標記「（推論）」。 | **Tier A**（深度解析） |
| **T2** | 台灣與國際 | 台灣是國際事件的主要參與者之一（如台美關係、兩岸、半導體供應鏈關鍵環節）。原文實質討論台灣，陳述事實關聯，不可標記「（推論）」。 | **Tier B**（詳細摘要） |
| **T3** | 間接相關 | 報導**實質討論台灣**（substantive mention，如具體政策、歷史事件、對台政治訊息，至少為 T3 且如實陳述不加「（推論）」），或原文未提及但具備**具體影響機制**（如具名政策、貿易或供應鏈曝險、安全承諾、邦交國，必須標記「（推論）」開頭）。 | **Tier C**（重點摘要） |
| **T0** | 無實質關聯 | 原文**路過提及**（incidental mention，如僅列於國家清單、借用台灣研究作他國案例，`mentions_taiwan = true`）或僅為泛泛地緣政治臆測，**一律維持 T0**，保留於各領域分類章節，不列入台灣專區。 | 各章節預設 Tier |

#### 提及型態與分類判定規則（Classification Rules）
1. **提及型態（`taiwan_mention_kind`）**：分類階段嚴格記錄三種型態之一：
   - `substantive`（實質討論）：原文包含一段敘述、歷史事件、比較、政策或對台政治訊息（如中共對台宣傳或施壓）。此類報導**至少為 T3**，其 `taiwan_link` 必須如實陳述原文事實，**嚴禁標記「（推論）」**。
   - `incidental`（路過提及）：僅在國家清單列名，或借用台灣研究、數據作為其他國家之案例。**維持 T0**，留在所屬領域分類章節，不進入台灣專區（但 `mentions_taiwan = true`）。
   - `none`（未提及）：原文完全未提及台灣。只有在具備原文依據之具體機制（具名政策、貿易或供應鏈曝險、安全承諾、原文明列之邦交國）時才可判定為 T3，且其關聯陳述**必須以「（推論）」開頭**並說明具體機制；若無充分依據則為 T0。泛論「中國影響力擴大，所以台灣受影響」一律為 T0。
2. **逐字證據（`taiwan_evidence`）**：凡有提及台灣（`kind != "none"`）或判定為非零層級（T1–T3），模型必須逐字摘錄輸入文章中的一個英文句子作為核對依據，確保判斷不憑空捏造；其餘為 `null`。

#### 台灣查證（Grounding）防護守則
1. **查證絕不調升台灣層級（Grounding Never Raises Level）**：查證階段**絕不調升**任何文章的台灣關聯層級：
   - **本週焦點報導（T0）**：初判為 T0 的焦點報導一律維持 T0 並保留於「本週焦點」獨立章節與頁面；查證僅在其 Tier A 深度解析中補充具備中央社證據之「對台灣的意涵」，絕不改變其層級或改列入台灣專區。
   - **初判 T1–T3 報導**：查證僅能維持或限縮降級（T1 可維持或限縮為 T2/T3/T0；T2 可維持或限縮為 T3/T0；T3 可維持或降為 T0）。
2. **實質討論與推論規範**：
   - **原文實質討論連結保留**：原文若屬實質討論（`substantive`），原文即為充分依據，系統嚴格保留其事實關聯敘述（如實陳述原文事實，不標記「（推論）」）。即使外部檢索無新證據，亦不刪除其事實關聯。
   - **未提及台灣必加「（推論）」**：原文未提及台灣（`none`）之報導，其關聯陳述**一律必須以「（推論）」開頭**。若查證階段缺乏有效外部依據或關聯不足，其層級強制歸零（T0），回歸一般章節。
3. **主軸因果約束（禁止次要事件連鎖推論）**：
   - 台灣關聯陳述或意涵**必須直接源自報導的「主要主題」（MAIN subject）**。
   - 嚴禁透過報導中僅順帶提及的次要事件進行連鎖推論（Chaining through passing mentions）——報導順帶提及之事件所引發的後續效應，既非該文章之台灣連結，亦不得作為「對台灣的意涵」。
4. **「對台灣的意涵」選填化**：「對台灣的意涵」（`taiwan_implications`）為選填項目（0–3 筆），僅在具備充分事實基礎或外部證據時才撰寫；若無實質依據則完全留空，絕不湊數或牽強附會。
5. **查證出處標註行**：在私人網站、HTML 報告、Markdown 報告與 Telegraph 頁面中，台灣關聯陳述與意涵下方均附上至多 3 筆「依據：來源名稱 YYYY/MM/DD〈標題〉」超連結（Telegram 聊天室訊息不加來源行，保持簡潔）。

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
| **B** | 詳細摘要 | 約 400–1,250 字 | 中文標題、4–6 項核心重點、完整論點分析、對台灣影響與啟示。 | 台灣 **T2** 報導；封面經濟學人立場（Leaders）對應報導最低門檻 |
| **C** | 重點摘要 | 約 165–550 字 | 中文標題、3–5 項核心重點。 | 台灣 **T3** 報導；美國 (`intl.us`)、中國 (`intl.china`)；其他經濟學人立場文章對應報導最低門檻；特別報導最低門檻 |
| **D** | 簡要摘要 | 約 50–210 字 | 中文標題、2–3 句簡明摘要。 | 亞太 (`intl.asia`)、歐洲 (`intl.europe`)、財經商業 (`finance`)、科技 (`tech`) |
| **E** | 一句話 | 約 20–85 字 | 一句話核心論點。 | 其他地區 (`intl.other`)、科學 (`science`)、文化生活 (`culture`)；讀者投書、訃聞 |

### 特殊文章處理

1. **本週要聞速覽（brief）**：取材自 "The world this week"，涉及台灣之條目標示「【台灣相關】」並置頂，不使用國旗 emoji。
2. **經濟學人立場合併（merged）**：Leaders 的觀點合併至對應專題報導，標註為「經濟學人立場」（含「作者主張」），不產出重疊篇幅。
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
[classify] 透過 LLM 識別台灣提及型態（substantive/incidental/none）與關聯層級（T1–T3；路過提及與泛論為 T0），記錄原文逐字證據與領域分類
   ↓
[pair] 將 Leaders（經濟學人立場）與各章節專文進行關聯配對
   ↓
[tiers] 套用深度政策，決定各篇 Tier（T1 與本週焦點 3 篇升為 Tier A）
   ↓
[summaries / brief / English] 平行呼叫 LLM 產出各級摘要、要聞速覽與英文研讀指南
   ↓
[edit] 標題、一句話重點與要聞新聞專業編修（每批至多 10 項 / 9,000 bytes，逐欄位驗證退回原文字）
   ↓
[ground_queries + ground] 產生搜尋詞並檢索中央社證據，執行客觀台灣關聯查證（約束層級與意涵）
   ↓
[facts] 每週定期檢查台灣事實清單（taiwan.md）時效性，發送私密更新提醒
   ↓
[figures] 查看深度解析「文章脈絡」內文圖片，產生圖表、地圖、照片與插畫說明（每篇各自分批，每批至多 4 張）
   ↓
[zh-TW normalisation] 僅針對含非 Big5 字元之 CJK 片段以 OpenCC 轉繁，套用 glossary.tsv
   ↓
[render & site build] 產生 Markdown、HTML 報告、Telegraph 頁面（獨立台灣頁）與 output/ 多頁網站（雙層導覽）
   ↓
[site publish & backup] 透過 SSH tar 串流暫存替換發布私人網站，並將 output/ 備份至私有 GitHub 儲存庫
   ↓
[send] 推送 Telegram 單則核心導讀訊息（Instant View 連結與私人網站連結）與頻道推播
```

### 模組職責地圖

| 模組路徑 | 職責說明 |
| :--- | :--- |
| `src/econ_digest/cli.py` | 命令列介面入口與參數解析。 |
| `src/econ_digest/config.py` | TOML 設定檔載入、驗證與密鑰管理。 |
| `src/econ_digest/site/` | 多頁網站建置（`build.py`，雙層導覽）、SSH tar 串流暫存替換發布（`publish.py`）與 Git 私有備份（`backup.py`）。 |
| `src/econ_digest/analysis/editor.py` | 標題、一句話重點與要聞編修，支援批次切分與逐欄位安全驗證退回機制。 |
| `src/econ_digest/analysis/grounding.py` | 台灣關聯查證（`ground_queries`、`ground`）與事實清單每週時效檢查（`facts`）。 |
| `src/econ_digest/analysis/focus.py` | 評選本週 3 篇關鍵國際焦點專文並升級為 Tier A。 |
| `src/econ_digest/analysis/figures.py` | 以圖片像素產生私人 HTML 圖說，獨立快取並保留無說明的原圖備援。 |
| `src/econ_digest/research/` | 核准新聞與政府證據、robots、共同請求上限、TLS 中繼憑證與短摘錄快取。 |
| `src/econ_digest/facts/` | 具體日期與出處之台灣核心現況事實清單（`taiwan.md`）與載入器（`__init__.py`）。 |
| `src/econ_digest/render/` | Markdown、HTML 報告、Telegraph 頁面節點與 Telegram 訊息切塊。 |
| `src/econ_digest/images.py` | 自 EPUB 提取封面、題圖、內文圖表、漫畫與要聞配圖。 |
| `src/econ_digest/commands/send.py` | Telegram 與 Telegraph 發送協調、斷點續傳與 `--pages-only` 整合。 |
| `src/econ_digest/commands/telegram_setup.py` | 私人聊天室與頻道設定。 |

### 模型路由與管線階段（Model Routing & Pipeline Stages）

系統採用混合模型路由（Hybrid Model Routing）架構，在產出品質與執行效率間取得最佳平衡：

| 階段 (Stage) | 主要模型 (Primary) | 備援模型 (Fallback) | 逾時時間 | 批次規格與職責說明 |
| :--- | :--- | :--- | :---: | :--- |
| `classify` | Gemini 3.8 Flash | Claude Sonnet 4.6 | 300 秒 | 初步識別台灣關聯與各文篇領域分類。 |
| `pair` | Gemini 3.8 Flash | Claude Sonnet 4.6 | 300 秒 | 將封面與各章節專文與其對應的經濟學人立場配對。 |
| `focus` | Gemini 3.8 Flash | Claude Sonnet 4.6 | 300 秒 | 評選當期除台灣外最關鍵的 3 篇專案報導升為 Tier A。 |
| `summarize_a` | Claude Opus 4.6 (thinking) | Gemini 3.8 Flash | 300 秒 | 台灣 T1 報導與 3 篇本週焦點專文之高規格深度解析。 |
| `summarize_b`~`e` | Gemini 3.8 Flash | Claude Sonnet 4.6 | 300 秒 | B 級詳細摘要、C 級重點摘要、D 級簡要摘要與 E 級單句摘要。 |
| `brief` | Gemini 3.8 Flash | Claude Sonnet 4.6 | 300 秒 | "The world this week" 政治與商業要聞重點整理。 |
| `english` | Gemini 3.8 Flash | Claude Sonnet 4.6 | 300 秒 | 候選文章評選（`english_pick`）與學習指南生成（`english_guide`）。 |
| `edit` | Gemini 3.8 Flash | Claude Sonnet 4.6 | 900 秒 | 標題、一句話重點與要聞之台灣新聞風格編修（每批至多 10 項 / 9,000 bytes）。 |
| `ground_queries` | Claude Opus 4.6 (thinking) | Gemini 3.8 Flash | 600 秒 | 針對涉台候選報導提出 1–3 組中央社繁體中文搜尋詞（共用 `ground` 模型與逾時設定）。 |
| `ground` | Claude Opus 4.6 (thinking) | Gemini 3.8 Flash | 600 秒 | 結合中央社客觀證據查證台灣關聯與具體意涵（每批至多 3 篇 / 90 KB）。 |
| `facts` | Claude Opus 4.6 (thinking) | Gemini 3.8 Flash | 300 秒 | 比對中央社最新要聞與台灣事實清單（`taiwan.md`）新鮮度。 |
| `figures` | Gemini 3.8 Flash | Claude Sonnet 4.6 | 300 秒 | 台灣 T1 或本週焦點之 A 級文章內文圖片說明，每篇獨立呼叫、每批至多 4 張。 |

#### 路由與執行特性

`figures` 以 `[llm.models] figures` 設定模型。圖片提取至已忽略的 `data/issues/te_YYYY.MM.DD/figures/`，透過 gwg 的 `--add-dir` 授權讀取；快取鍵包含圖片內容雜湊與提示詞，與資料目錄的絕對路徑無關。短替代文字與重點句的提示詞更新會使圖說單元重新產生一次，之後沿用快取。圖說不送入其他提示詞，已有分析快取可直接沿用；`analyze --plan` 會列出圖片單元但不提取檔案或呼叫模型。

1. **模型分工與備援機制**：
   - **Claude Opus 4.6 (thinking)**：主理最高思維深度任務（Tier A 深度解析 `summarize_a`、關聯查證 `ground`（`ground_queries` 亦共用此模型設定）與事實更新檢查 `facts`）。若呼叫失敗自動降級至 Gemini 3.8 Flash。
   - **Gemini 3.8 Flash**：主理高吞吐常規任務（初步分類、焦點評選、常規摘要、要聞速覽、英文選文，以及標題與要聞編修 `edit`）。若呼叫失敗自動切換至 Claude Sonnet 4.6。
   - **編修模型配置緣由**：在 2026-10-06 完整執行一期時，使用 Claude Opus 進行編修 pass（一期約 13 個區塊）耗盡了所有 gwg 帳號的 Claude 五小時額度；gwg 配額錯誤會使整個帳號進入冷卻狀態，連帶阻斷 Gemini 呼叫直到額度重設。因此 `edit` 預設優先使用 Gemini 3.8 Flash，並以 Claude Sonnet 4.6 作為備援。
2. **階段逾時配置（`stage_timeout_seconds`）**：
   `LLMConfig.stage_timeout_seconds` 預設為 `{"edit": 900, "ground": 600}`。`ground_queries` 共用 `ground` 的 600 秒逾時門檻，其餘階段維持全域 `call_timeout_seconds = 300` 秒。
3. **標題與一句話重點編修守衛（Validation Guard & Fallback）**：
   在 `edit` 階段，標題與一句話重點（`headline_zh`）均受到嚴格驗證。一句話重點必須為單一自然句，長度 30–60 字且以「。」結尾（全句不得包含其他句號、全形空格、換行符號、問號或驚嘆號），且內容不得重複中文標題。若模型編修版本驗證失敗，系統會觸發逐欄位安全退回機制，保留前一階段之原文字。
4. **每週預期執行時間（Expected Runtime）**：
   相較於全 Flash 輕量管線，引入深度解析與外部中央社檢索後，每週分析耗時有所增加。依據 2026-10-06 實測數據，僅針對 `edit`、`ground` 與 `facts` 階段呼叫模型之重跑即耗時約 37 分鐘（其中 `edit` 包含 17 個區塊在 Gemini Flash 上以 parallel=2 執行，耗時約 30 分鐘，共消耗約 803k tokens；相較於早期 Opus 單區塊需 240–560 秒大幅提速）；若加上 2026-10-05 實測全新期別的前期階段（classify、pair、focus、summaries、brief、english 約 31 分鐘模型時間），整期管線預期執行耗時約落在 **45–60 分鐘**。Systemd 服務預設已配置 3 小時逾時上限（`TimeoutStartSec=3h`），緩衝充足無須額外調整。

### 多來源證據檢索（Research）

台灣關聯與每週事實檔檢查使用 `src/econ_digest/research/` 的核准來源；`[research]` 各來源預設啟用，可將下表的設定鍵改為 `false`。

| 來源／設定鍵 | 存取方式 |
| --- | --- |
| 中央社 `cna` | 站內搜尋與文章前兩段；發布日期取自新聞網址；robots 禁止搜尋時改用政治 RSS（目前 robots 禁止此搜尋路徑）。 |
| 公視新聞網 `pts` | 站內搜尋；robots 禁止或搜尋無法解析時改用 `newsfeed.xml` RSS（目前 robots 禁止搜尋）。 |
| 聯合新聞網 `udn` | 站內搜尋的 HTML 日期與標題，必要時讀取文章日期；無法解析時改用要聞 RSS。已檢查公開搜尋頁與載入腳本，未採用未確認的 JSON API。 |
| 自由時報 `ltn` | 站內搜尋的 HTML；相對時間不當發布日期，須讀取文章發布中繼資料。搜尋 404 視為零筆結果，不轉用 RSS、不列警告；其他搜尋失敗仍轉用備援政治 RSS，目前回應 403，會列出警告。 |
| BBC News Asia `bbc_asia`、BBC 中文繁體 `bbc_zh`、DW 中文 `dw`、RFI 中文 `rfi`、The Guardian Taiwan `guardian` | 官方 RSS，每次分析各抓取一次（包含快取）；用中文搜尋詞及原文標題、rubric、台灣訊號中的英文關鍵字比對，國際來源合計每篇最多 3 筆。摘錄為 RSS description，最多 200 字元。 |
| 外交部 `mofa`、國防部 `mnd`、總統府 `president`、行政院 `ey`、主計總處 `dgbas`、中選會 `cec` | 官方最新新聞或公告列表；國防部包含新聞稿與共機動態，中選會讀取首頁公告區的 Nuxt 公開資料。事實檔檢查全部納入；關聯查證只納入關鍵字相符的項目。 |

RFI 使用繁體 RSS `https://www.rfi.fr/tw/rss`。DW 未找到可用的繁體 RSS，沿用官方中文 `rss-chi-all`；標題與摘錄在關鍵字比對及成為查證依據之前，使用既有 OpenCC `s2tw` 做字體轉換，包含已快取的資料，不套用導讀用詞表、不改寫新聞用詞與連結。需安裝 `opencc` 才能執行此轉換；缺少工具時會記錄警告並保留原文字。

聯合與自由並用以平衡政治評價。事實優先採用中央社、公視與政府第一手公告；媒體評論、學者判斷或 The Diplomat 類型分析須保留發言者歸屬。聯合與自由的評價若有分歧，提示詞要求並列來源；政府的評價也不等同客觀事實。每篇合併證據後去除近似標題與重複網址，最多 12 筆，id 在該篇內唯一，ground 提示詞仍限制 90 KB。出處行列明來源，例如「依據：公視 2026/09/30〈標題〉」，最多 3 行。

- **日期與時效**：日期只取網站頁面、官方列表、RSS 或新聞網址，不取外部搜尋引擎。搜尋最多回溯出刊日之前 365 天，RSS 為出刊日前 14 天，排除出刊日後的項目。政府列表最多回溯 365 天，保留較久前公布的正式統計。即時 RSS 可能已不含舊期別的報導，零筆相符不代表該來源無相關新聞。
- **禮貌與共同上限**：使用 `econ-digest/0.1 (Taiwan news evidence; limited requests)`，同主機每次 HTTP 請求間隔至少 2.5 秒，預設逾時 15 秒。429／503 尊重秒數或 HTTP 日期的 Retry-After，至少按 2.5、5、10 秒退避，最多重試 3 次。全部來源、robots、重新導向及重試共用每次分析 `request_budget = 120`；0 表示只讀快取。舊 `cna_request_budget` 仍可作已棄用別名；兩者並存時以 `request_budget` 為準。
- **robots**：每個搜尋主機先檢查 robots.txt，快取 24 小時；禁止或無法確認時不請求搜尋頁，改用該站 RSS 並寫日誌。robots 404 代表沒有該檔案；403、逾時或驗證失敗不視為允許。
- **快取**：只存日期、標題、網址與至多 200 字元的短摘錄，不存完整報導；位於被忽略的 `data/research/`。搜尋 7 天、文章摘錄 30 天、RSS／政府列表 6 小時、robots 24 小時。中央社保留既有 500 筆輪替；共用快取最多 1,000 筆。讀取快取時仍重新檢查時效。
- **失敗備援**：部分來源失敗時警告列出來源名稱，繼續使用成功取得的證據；全部無法連線時維持原文、事實檔與快取的備援規則。未查證推論不得保留，原文已實質討論台灣的事實關聯仍保留。事實檔只提醒已完成的變動，政府公告為最強依據；`evidence_title` 必須逐字等於引用證據中的標題，程式不自動改寫事實檔。
- **存取限制**：Reuters 回應 401、AP 回應 403，未納入來源；VOA、RFA、中國時報也未獲核准。搜尋結果、短摘錄與有限的最新列表並不涵蓋完整歷史，無法取代人工查證。

政府 TLS 驗證沿用系統根憑證，僅對外交部、總統府與主計總處另載入套件中的 `research/certs/twca-secure-ssl.pem`，絕不關閉憑證或主機名稱驗證。中繼憑證為 **TWCA Secure SSL Certification Authority**，發行者是系統信任的 **TWCA Global Root CA**；有效期至 2030-10-16。2026-10-06 以葉憑證 AIA 的 CA Issuers 位址取得，SHA-256 指紋為 `1A:2C:75:FD:09:6E:04:99:E9:FF:6A:C7:4E:52:6F:61:EA:AE:3E:DF:C8:C2:EA:44:36:FE:E0:C2:4D:8B:7D:0E`，三站葉憑證均以系統根憑證驗證成功。

中繼憑證更新流程（需要 OpenSSL；在臨時目錄操作後再檢查差異）：

```sh
openssl s_client -connect www.mofa.gov.tw:443 -servername www.mofa.gov.tw -showcerts </dev/null > /tmp/mofa-chain.pem
openssl x509 -in /tmp/mofa-chain.pem -noout -issuer -ext authorityInfoAccess
# 另對 www.president.gov.tw、www.stat.gov.tw 重做以上檢查；以當次葉憑證 AIA 為準。
python3 -c 'from urllib.request import urlopen; from pathlib import Path; Path("/tmp/twca.crt").write_bytes(urlopen("https://sslserver.twca.com.tw/cacert/secure_sha2_2023G3.crt", timeout=15).read())'
openssl x509 -inform DER -in /tmp/twca.crt -out /tmp/twca.pem
openssl x509 -in /tmp/twca.pem -noout -subject -issuer -dates -fingerprint -sha256
openssl verify /tmp/twca.pem
openssl verify -untrusted /tmp/twca.pem /tmp/mofa-chain.pem
# 每站都須 OK；確認是公開中繼憑證、系統信任的根及合理有效期後才替換。
cp /tmp/twca.pem src/econ_digest/research/certs/twca-secure-ssl.pem
.venv/bin/python -m pytest tests/research -q
```

若發行者或 AIA 改變，請重新取得新的中繼憑證、驗證三站完整鏈並更新指紋與有效期；不可把葉憑證或任意自簽根加入信任庫。

### 台灣事實清單維護（Fact Sheet Maintenance）

- **事實清單定位**：由 `src/econ_digest/facts/taiwan.md` 統籌管理台灣核心政經與國防現況，包含 9 大核心領域：
  1. 邦交國概況（截至統計，維持 12 友邦）
  2. 府會與國安首長
  3. 立法院第 11 屆席次與政黨分布
  4. 國防預算與占 GDP 比例
  5. 對外貿易結構與出口市場反轉（美超越中港成最大出口市場）
  6. 台積電（TSMC）海外晶圓廠進度（美、日、德）
  7. 台美關係與安全合作（軍售常態化與法案）
  8. 台海現狀與共軍大規模演習歷史脈絡（環台軍演與灰色地帶常態化）
  9. 關鍵戰略定位補充（先進製程產能與無核電轉型）
- **具體日期與溯源規範**：事實清單中每一項數據與事件，**必須具備明確的「截至日期」與具體中央社（CNA）或官方新聞稿 URL**，嚴禁無依據之條目。
- **每週自動新鮮度檢查（已發生事實認定原則）**：
  每週管線之 `facts` 階段會自中央社抓取最新要聞比對事實清單：
  - **僅通報已實際發生的重大事實變更**（如已就職、已請辭、已斷交、立法院已三讀通過、官方已公布最終正式數據）。
  - **排除未來式與未定事件**：競選言論、表態支持（背書）、提名、民調、預測、籌備規劃與假設條件句一律不採計；選舉結果僅在投票日當天或之後方得採計。
  - 若偵測到實際發生的重大事實變更，會在 Telegram 私人聊天室發送私密訊息提醒（至多 5 則；每則警報帶有 `evidence_title`，必須逐字等於所引用之中央社新聞標題，並作為超連結文字呈現；無標題之舊式警報則顯示為「中央社」）：
    ```
    ⚠️ 台灣事實檔可能需要更新：
    • <事實檔說法> → <已完成的疑似新值與日期>（〈<中央社標題>〉）
    （請確認）
    ```
    （此警報訊息僅發送至私人聊天室，頻道與公開頁面絕不呈現）。
- **維護與更新工作流**：
  維運人員收到通知後，點擊連結確認中央社報導屬實，即可手動編輯更新 `src/econ_digest/facts/taiwan.md`，並提交推送：
  ```sh
  git add src/econ_digest/facts/taiwan.md
  git commit -m "docs(facts): update Taiwan diplomatic and defense status"
  git push origin master
  ```

---

## 安裝

### 系統需求
- **Python**：>= 3.11
- **gwg**：已於系統中安裝並登入，且位於 `PATH` 中。（若遇 Claude 五小時額度耗盡導致所有帳號回報 `exit 75` / `no free account` 並使整帳號冷卻連帶阻斷 Gemini，管線會等待至多 `no_account_wait_seconds` 且快取單元保持有效；可透過 `gwg usage --json` 與 `gwg status` 檢查重設時點後重跑，或於 `config.toml` `[llm.models]` 將繁重階段暫時切換至 Flash）。
- **ssh 與 tar**：用於私人網站發布（本機需具備 `ssh` 與 `tar`，遠端主機亦需安裝 `tar`；傳輸全面採用 SSH tar 串流）。
- **opencc**（建議安裝）：`sudo apt install opencc`。
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
stage_timeout_seconds = { edit = 900, ground = 600 }

[llm.models]
classify = ["gemini-3.8-flash-high", "claude-sonnet-4-6"]
pair = ["gemini-3.8-flash-high", "claude-sonnet-4-6"]
focus = ["gemini-3.8-flash-high", "claude-sonnet-4-6"]
summarize_a = ["claude-opus-4-6-thinking", "gemini-3.8-flash-high"]
summarize_b = ["gemini-3.8-flash-high", "claude-sonnet-4-6"]
summarize_c = ["gemini-3.8-flash-high", "claude-sonnet-4-6"]
summarize_d = ["gemini-3.8-flash-high", "claude-sonnet-4-6"]
summarize_e = ["gemini-3.8-flash-high", "claude-sonnet-4-6"]
brief = ["gemini-3.8-flash-high", "claude-sonnet-4-6"]
english = ["gemini-3.8-flash-high", "claude-sonnet-4-6"]
# 使用 Claude Opus 時，一期 13 個編修區塊曾耗盡所有帳號的 Claude 五小時額度並使整帳號冷卻，因此編修預設優先使用 Gemini Flash
edit = ["gemini-3.8-flash-high", "claude-sonnet-4-6"]
ground = ["claude-opus-4-6-thinking", "gemini-3.8-flash-high"]
facts = ["claude-opus-4-6-thinking", "gemini-3.8-flash-high"]

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

## Threads 文章排程

選用的 Threads 發文預設停用。完成每期傳送後，可依「台灣 → 本週焦點 → 國際 → 財經・科技・文化」逐篇發布自己的中文摘要，第一則為附封面的本期介紹；合併文章不重複發文。**文章貼文為純文字，不公開期刊原文與內文圖片；封面只附在本期介紹貼文。** 每則保守預算 500 字元，保留完整句子、推論標示與台灣關聯。

先依 [Meta 官方入門文件](https://developers.facebook.com/documentation/threads/get-started/)建立專用 Threads 帳號、Access the Threads API 應用程式，邀請並接受 Threads Tester；授予 `threads_basic` 與 `threads_content_publish`，依[長期權杖文件](https://developers.facebook.com/documentation/threads/get-started/long-lived-tokens/)換取 60 天權杖。把 `THREADS_ACCESS_TOKEN`、`THREADS_USER_ID` 與取得時間 `THREADS_TOKEN_ISSUED_AT` 放在 mode 600 的 `~/.config/econ-digest/env`；不要放在 TOML 或公開儲存庫。完整帳號設定、權限、所有設定鍵與故障處理見[維運手冊](docs/operations.md#threads-文章排程)。

```sh
.venv/bin/econ-digest social threads preview --issue 2026.10.03
.venv/bin/econ-digest social threads enqueue --issue 2026.10.03
.venv/bin/econ-digest social threads post-next --dry-run
.venv/bin/econ-digest social threads status
```

預覽與試跑完全離線。檢閱後在 `config.toml` 的 `[social.threads]` 設 `enabled = true`，再執行 `deploy/install-threads-timer.sh`。預設台北時間 08:00–22:00、每 60 分鐘至多一則、每天最多 15 則；API 額度另查詢官方端點。刷新權杖與佇列均保存在忽略的 `data/social/`。`social threads pause` / `resume` 可暫停及恢復，停用定時器使用 `systemctl --user disable --now econ-digest-threads.timer`；授權或刷新失敗會暫停並只嘗試一次私人 Telegram 警示。

每則貼文只有一個主題，透過建立容器的 `topic_tag` API 參數設定，內文不附加 # 標籤。`[social.threads] topic_tag` 預設為「經濟學人導讀」，須為 1–50 字元且不含 `.` 或 `&`；設為 `""` 不送主題。舊設定只有 `hashtags` 時，取第一個並移除開頭的 `#`。參見 [Threads 官方發布文件](https://developers.facebook.com/documentation/threads/posts/)。

### 修正已發布貼文

1. 在 Threads App 刪除要修正的舊貼文。
2. 執行 `.venv/bin/econ-digest social threads requeue --issue 2026.10.03 --index 1`，按 `preview`／`status` 的本期序號選取；介紹是第 1 則，也可使用 `requeue --key` 搭配 `status` 顯示的完整佇列鍵。
3. 等待定時器依原順序與發文時段重新發布。

`requeue` 完全離線，保留佇列原文字、移除舊版 # 標籤尾行，並套用目前的主題設定；舊貼文 ID 與發布時間留在歷史。它不會刪除 Threads 上的貼文，也不需要重新讀取期號資料；仍待發布的項目不變更。
