# 維運與故障排除指南 (Operations and Troubleshooting)

本文件提供 `econ-digest` 每週導讀系統的日常維運、狀態檢查、私人網站與備份管理、手動介入方式與常見問題排查指南。

---

## 目錄

- [日常維運](#日常維運)
  - [日誌位置與檢視方式](#日誌位置與檢視方式)
  - [檢查定時器與服務狀態](#檢查定時器與服務狀態)
  - [手動觸發與傳送機制](#手動觸發與傳送機制)
  - [接續中斷的傳送（斷點續傳）](#接續中斷的傳送斷點續傳)
  - [重新發送已完成期別（`send --force`）](#重新發送已完成期別send---force)
  - [離線預覽檢視（`send --dry-run`）](#離線預覽檢視send---dry-run)
  - [原地維護更新（`send --pages-only`）](#原地維護更新send---pages-only)
  - [重設單期快取](#重設單期快取)
  - [更新詞彙對照表後重建報告](#更新詞彙對照表後重建報告)
- [私人網站發布與備份維運](#私人網站發布與備份維運)
  - [伺服器規格與 Caddyfile 配置](#伺服器規格與-caddyfile-配置)
  - [雙層導覽架構與出處標註維運](#雙層導覽架構與出處標註維運)
  - [發布流程與 SSH tar 暫存替換機制](#發布流程與-ssh-tar-暫存替換機制)
  - [發布失敗自動備援機制](#發布失敗自動備援機制)
  - [私有 GitHub 儲存庫備份維運](#私有-github-儲存庫備份維運)
- [Telegram 私人聊天室與頻道維運](#telegram-私人聊天室與頻道維運)
  - [私人聊天室傳送流程](#私人聊天室傳送流程)
  - [頻道推播管理（`--channel`）](#頻道推播管理--channel)
- [中央社新聞查證與台灣事實清單維運](#中央社新聞查證與台灣事實清單維運)
  - [中央社客觀證據檢索機制與排查](#中央社客觀證據檢索機制與排查)
  - [台灣事實清單維護與更新工作流](#台灣事實清單維護與更新工作流)
- [問題排查速查表](#問題排查速查表)
- [常見問題深度排查](#常見問題深度排查)
  - [1. gwg: User location is not supported](#1-gwg-user-location-is-not-supported)
  - [2. gwg exit 75 / no free account](#2-gwg-exit-75--no-free-account)
  - [3. 模型配額耗盡 (Quota Exhaustion)](#3-模型配額耗盡-quota-exhaustion)
  - [4. Telegram: can't parse entities](#4-telegram-cant-parse-entities)
  - [5. 缺少 Token、Chat ID 或 Channel ID](#5-缺少-tokenchat-id-或-channel-id)
  - [6. 執行失敗與重試機制 (Failed Run)](#6-執行失敗與重試機制-failed-run)
  - [7. 執行鎖衝突 (Lock already held)](#7-執行鎖衝突-lock-already-held)
  - [8. Telegraph: FLOOD_WAIT_N](#8-telegraph-flood_wait_n)
  - [9. 缺少或無效的 Telegraph Access Token](#9-缺少或無效的-telegraph-access-token)
  - [10. Telegraph 頁面超出容量上限 (Page Size Limit)](#10-telegraph-頁面超出容量上限-page-size-limit)
  - [11. 原地維護機制與模式限制 (`send --pages-only`)](#11-原地維護機制與模式限制-send---pages-only)
  - [12. 私人網站發布與 SSH / tar 失敗排查](#12-私人網站發布與-ssh--tar-失敗排查)
  - [13. Telegram 內建瀏覽器無法處理 Basic Auth 彈窗問題](#13-telegram-內建瀏覽器無法處理-basic-auth-彈窗問題)
  - [14. 網站備份 push 失敗排查](#14-網站備份-push-失敗排查)
  - [15. 英文學習選文或指南失敗與容錯機制](#15-英文學習選文或指南失敗與容錯機制)
  - [16. edit 與 ground 階段耗時與逾時處理](#16-edit-與-ground-階段耗時與逾時處理)
  - [17. 中央社新聞檢索異常與快取維護](#17-中央社新聞檢索異常與快取維護)
  - [18. 台灣事實檔更新提醒處理工作流](#18-台灣事實檔更新提醒處理工作流)
  - [19. 標題與要聞編修驗證退回機制](#19-標題與要聞編修驗證退回機制)

---

## 日常維運

### 日誌位置與檢視方式

系統提供兩種類型的日誌輸出：應用程式專屬滾動檔案日誌與 systemd 使用者單元日誌。

#### 1. 應用程式檔案日誌
- **預設路徑**：`data/logs/econ-digest.log`
- **輪替機制**：單檔上限 2 MB，自動保留最近 3 份歷史檔案（`econ-digest.log.1`、`.2`、`.3`）。
- **機密遮蔽**：所有敏感憑證（`TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`、`TELEGRAM_CHANNEL_ID`、`GITHUB_TOKEN`、`TELEGRAPH_ACCESS_TOKEN`）在寫入日誌時均會自動過濾並遮蔽為 `[已隱藏]`。
- **檢視指令**：
  ```sh
  # 即時追蹤最新日誌輸出
  tail -f data/logs/econ-digest.log

  # 檢視最近的警告與錯誤
  grep -E 'WARNING|ERROR' data/logs/econ-digest.log | tail -n 50
  ```

#### 2. systemd 服務日誌
定時器觸發的執行紀錄會直接記錄至 systemd journal：
```sh
# 即時追蹤使用者服務日誌
journalctl --user -u econ-digest.service -f

# 檢視最近 100 行紀錄
journalctl --user -u econ-digest.service -n 100 --no-pager
```

---

### 檢查定時器與服務狀態

```sh
# 1. 檢查定時器排程、下次觸發時間與上次執行結果
systemctl --user list-timers econ-digest.timer

# 2. 查看定時器單元詳細狀態
systemctl --user status econ-digest.timer

# 3. 查看背景服務單元狀態
systemctl --user status econ-digest.service
```

> [!NOTE]
> 若要在使用者登出伺服器後持續運行定時器，請確認已啟用 lingering：
> ```sh
> loginctl enable-linger "$USER"
> ```

---

### 手動觸發與傳送機制

#### 手動立即執行完整流程
```sh
# 透過 systemd 背景啟動
systemctl --user start econ-digest.service

# 或直接在前台執行（即時輸出進度）
.venv/bin/econ-digest run
```

#### Telegraph 模式每週傳送機制
在預設的 Telegraph 傳送模式下，執行 `send` 指令時，系統向 Telegram 私人聊天室發送**單則訊息（ONE message）**：
1. **單則 Telegram 核心導讀訊息**：
   - **刊期標題與標頭摘要列**：刊期標題（`📰 經濟學人導讀｜YYYY 年 M 月 D 日號`）與標頭列（`〈本期封面故事標題〉｜共 N 篇文章`）。本期不再發送舊版「與台灣相關」獨立條列區塊，維持中立與極簡純粹的排版。
   - **Instant View 主題分頁超連結（無數字編號）**：
     - 本週導讀
     - 台灣（獨立設頁，收錄 T1 至 T3 專區報導，陳述下方附帶中央社查證出處超連結）
     - 本週焦點（由模型評選 3 篇除台灣外最重要報導升為 Tier A 深度解析，獨立設頁不重複）
     - 國際
     - 財經・科技・文化
     - 英文學習
     （*僅列出當期實際存在之頁面；若無內容則自動省略該章節與連結*）
   - **「🔒 圖文完整版（需帳密）」連結**：導向架設於私有伺服器之多頁式圖文完整版網站。
2. **大圖預覽與封面首圖**：
   - 每一個 Telegraph 頁面開頭均以當期封面圖為首圖（帶圖說「本期封面：…」）。
   - Telegram 會辨識連結並採用大圖卡（Large media）預覽，直接在聊天室展示封面照片；點擊 Instant View 即可在原生介面極速展開閱讀。
3. **每週事實檔更新提醒（私訊專屬）**：
   - 每週若經由查證檢驗發現潛在過期事實，系統會向私人聊天室發送單則「⚠️ 台灣事實檔可能需要更新：…（請確認）」警報訊息（附中央社連結），頻道絕不推送此警報，不打擾公眾頻道。
4. **選用舊版行為（預設皆為 `false`）**：
   - `cover_photo = false`：設為 `true` 時，將封面改為獨立相片訊息發送。
   - `original_text_messages = false`：設為 `true` 時，會在聊天室以私訊摺疊區塊隨附英文原文。
   - `send_report_file = false`：設為 `true` 時，會在聊天室發送單檔 HTML 報告文件（`report.html`）。*注意：若私人網站發布失敗，系統會自動 fallback 附送此單檔報告*。

---

### 接續中斷的傳送（斷點續傳）

若在建立 Telegraph 頁面、發布網站或推送訊息期間網路斷線：
```sh
.venv/bin/econ-digest send
```
系統會自 `data/issues/te_<期別>/telegram_progress.json` 讀取發送進度（`pages_published` 頁面發布狀態、`next_message` 索引、`channel_sent` 與 `document_sent`），跳過已完成之項目，接續完成剩餘工作。

---

### 重新發送已完成期別（`send --force`）

若某期先前已記錄為發送完成（存於 `state.json` 的 `delivered` 中），欲強制重新發布與傳送：
```sh
# 重新發送最新一期
.venv/bin/econ-digest send --force

# 或指定特定期別
.venv/bin/econ-digest send --issue 2026.10.03 --force
```
- **Telegraph 原地編輯（In-Place Edit）**：系統會讀取既有的 `telegraph_pages.json`，對已發布的 Telegraph 頁面進行**原地編輯（EDIT）**更新內容。網址維持完全不變，先前已送出的 Instant View 連結持續有效。
- **網站重新發布與備份**：重新建置 `output/` 網站、透過 SSH tar 串流暫存替換發布至遠端伺服器，並 push 備份至私有儲存庫。
- **Messages 模式行為**：若設定檔中為 `[telegram] delivery = "messages"`，則自第一則起重新發送全部切分訊息。

---

### 離線預覽檢視（`send --dry-run`）

若欲在不建立 Telegraph 頁面、不發布網站、不備份且不向 Telegram 發送任何訊息的情況下預覽輸出排版：
```sh
.venv/bin/econ-digest send --dry-run
```
終端機會列印出預計發布的私人網站網址、備份規劃、各分頁標題與 UTF-8 位元組大小，以及即將送出的單則 Telegram 訊息內容與頻道訊息。

---

### 原地維護更新（`send --pages-only`）

在微調了摘要提示詞、正體字對照表（`glossary.tsv`）或修改文章內容後，若希望同步更新已發布的 Telegraph 頁面、重新建置並發布私人網站，並執行 GitHub 備份，但**完全不向 Telegram 私人聊天室或頻道發送任何訊息**（避免打擾手機端讀者）：
```sh
# 1. 離線預覽各分頁標題與大小（不發布）
.venv/bin/econ-digest send --pages-only --dry-run

# 2. 執行重建網站、重新發布、更新 Telegraph 頁面與備份
.venv/bin/econ-digest send --pages-only

# 或指定特定期別
.venv/bin/econ-digest send --issue 2026.10.03 --pages-only
```
- **完整維護動作**：
  1. 重建本地多頁網站（`output/`）。
  2. 透過 SSH tar 串流暫存替換發布更新至遠端 Web 伺服器（若 `[site] enabled = true`）。
  3. 對既有的 Telegraph 頁面進行**原地編輯（EDIT）**（網址維持不變）。
  4. 提交並 push 至私有 GitHub 儲存庫（若 `[backup] enabled = true`）。
- **零干擾保障**：不發送任何 Telegram 聊天室或頻道訊息，亦不修改 `state.json` 的 `delivered` 傳送狀態。
- **模式限制**：`--pages-only` 僅適用於 Telegraph 傳送模式（`[telegram] delivery = "telegraph"`）。若在 messages 模式下執行，會提示錯誤並退出。

---

### 重設單期快取

若特定期別因模型輸出異常需全部重新分析：
```sh
# 使用命令列參數（推薦）
.venv/bin/econ-digest analyze --issue 2026.10.03 --reanalyze

# 或在完整管線中重新分析並發送
.venv/bin/econ-digest run --issue 2026.10.03 --reanalyze --force
```
亦可手動刪除快取檔案：
```sh
rm -rf data/issues/te_2026.10.03/analysis
rm -f data/issues/te_2026.10.03/digest.json
```
（*請保留 `.epub` 與 `issue.json`，免於重複下載與解析。*）

---

### 更新詞彙對照表後重建報告

系統的單元級快取（版本 2）儲存的是未經正體化轉換前的原始輸出。若編輯或擴充了 `src/econ_digest/zhtw/glossary.tsv`，**不需要**消耗模型額度重新分析，直接執行下列指令即可：
```sh
# 1. 重新組裝導讀（全數從快取載入，套用最新 glossary.tsv）
.venv/bin/econ-digest analyze --issue 2026.10.03

# 2. 重新渲染報告與訊息
.venv/bin/econ-digest render --issue 2026.10.03

# 3. 原地更新網站與 Telegraph 頁面（不干擾聊天室）
.venv/bin/econ-digest send --issue 2026.10.03 --pages-only
```

---

## 私人網站發布與備份維運

### 伺服器規格與 Caddyfile 配置

私人網站由 `output/` 目錄建構而成，透過 SSH 上傳至遠端 Web 伺服器。伺服器配置建議使用 Caddy，通用要求如下：
1. **全站 Basic Auth**：除封面圖目錄外，所有 HTML 頁面、插圖與 EPUB 下載皆受帳號密碼保護。
2. **公開 `/covers/` 路徑**：Telegraph 伺服器需要讀取封面圖片以顯示 Instant View 封面。發布時封面會以 32 碼隨機檔名放置於 `/covers/`，此路徑免驗證。
3. **防止搜尋引擎檢索**：加入 `X-Robots-Tag: noindex, noarchive`。

Caddy 範例設定（`Caddyfile`）：
```caddy
site.example.com {
    root * /var/www/site
    encode gzip zstd

    # 防止搜尋引擎索引
    header X-Robots-Tag "noindex, nofollow, noarchive"

    # Telegraph 讀取封面圖專用路徑（公開免密碼）
    @covers path /covers/*
    handle @covers {
        file_server
    }

    # 其餘所有路徑一律要求帳號密碼
    handle {
        basicauth {
            username $2a$14$...hashed_password...
        }
        file_server
    }
}
```

### 雙層導覽架構與出處標註維運

多頁網站（`output/`）建置採用現代化雙層導覽架構，兼顧單手操作與長文通讀體驗：
1. **頂部麵包屑導覽（Breadcrumb）**：各分頁頂部呈現「[所有期別](../index.html) › YYYY/MM/DD 號」，標明目錄階層，讀者可隨時返回封存首頁或本期導讀首頁。
2. **置頂黏性分頁導覽列（Sticky Tabs）**：置頂橫向分頁標籤（包含「要聞」、「台灣」、「焦點」、「國際」、「財經科技文化」、「英文」），頁面滾動時保持固定，當前頁面標註 `aria-current="page"`，點擊即平滑跳轉。
3. **頁尾章節切換連結（Previous / Next Links）**：各章節底部提供「‹ 前一章節」與「後一章節 ›」切換按鈕，方便循序通讀整份期刊導讀。
4. **客觀查證出處標註**：在台灣專區及相關文章之「與台灣的關聯」或「對台灣的意涵」段落下方，精準呈現至多 3 筆「依據：中央社 YYYY/MM/DD〈標題〉」外部來源超連結，便於核對第一手權威報導。

### 發布流程與 SSH tar 暫存替換機制

在 `config.toml` 中配置 `[site]`：
```toml
[site]
enabled = true
base_url = "https://site.example.com"
ssh_host = "your-server"
remote_dir = "/var/www/site"
ssh_timeout_seconds = 30
```
- 發布前進行環境預檢：本機必須存在 `ssh` 與 `tar`，系統並會透過 SSH 於遠端伺服器執行 `command -v tar` 確認支援。
- 本期發布目錄（含頁面與樣式）以 tar 封裝透過 SSH 串流傳輸至遠端暫存目錄（`remote_dir/.incoming/<name>.<nonce>`）解開，並套用目錄 755、檔案 644 之權限。
- 採用原子替換（atomic swap）方式完成部署：舊版本目錄暫存為 `.backup` 備份，若替換過程失敗自動還原；替換成功後自動清理備份目錄。
- 將封面圖以 32 碼隨機雜湊檔名部署至遠端 `/covers/`，供 Telegraph 即時檢視讀取。

### 發布失敗自動備援機制

若因 SSH 連線逾時、主機離線或網路不通導致發布失敗：
- 終端機與日誌記錄：`私人網站發布失敗；改用單檔 HTML 報告。`
- 傳送至 Telegram 的摘要訊息會**自動拿掉**「🔒 圖文完整版」連結。
- 系統會**自動附送單檔離線 HTML 報告文件**（`report.html`）至私人聊天室，確保閱讀不中斷。

### 私有 GitHub 儲存庫備份維運

在 `config.toml` 中配置 `[backup]`：
```toml
[backup]
enabled = true
remote = "git@github.com:OWNER/econ-digest-output.git"
branch = "main"
author_name = "Your Name"
author_email = "you@example.com"
```
- 每次建置後，系統自動將 `output/` 提交並 push 至遠端儲存庫。
- **嚴格要求**：該 GitHub 儲存庫**絕對必須是 PRIVATE 私有儲存庫**，且絕不可指向公開程式碼儲存庫。
- **失敗容錯**：備份作業若發生網路或驗證錯誤，系統僅記錄警告：`網站備份失敗（...）；導讀傳送繼續。`，主流程持續進行。

---

## Telegram 私人聊天室與頻道維運

### 私人聊天室傳送流程

1. **取得 Token 並寫入密鑰檔**：
   ```sh
   mkdir -p ~/.config/econ-digest
   read -rsp 'Token: ' T && printf 'TELEGRAM_BOT_TOKEN=%s\n' "$T" > ~/.config/econ-digest/env && chmod 600 ~/.config/econ-digest/env && unset T; echo
   ```
2. **向機器人傳送 `/start`**。
3. **綁定聊天室並發送測試訊息**：
   ```sh
   .venv/bin/econ-digest telegram-setup --test
   ```

### 頻道推播管理（`--channel`）

若欲將導讀摘要同步推送至公開或私密頻道：
1. 將機器人加入該頻道，並提升為**管理員**（Admin），勾選「**張貼訊息**」（Post Messages）權限。
2. 執行設定指令綁定頻道：
   ```sh
   .venv/bin/econ-digest telegram-setup --channel @my_channel --test
   ```
   程式會向 Telegram API 驗證頻道類型與管理員權限，並將頻道 ID 儲存至 `~/.config/econ-digest/env` 中的 `TELEGRAM_CHANNEL_ID`。
3. **推播特性**：
   - 頻道接收核心導讀（刊期標題、標頭摘要列 `〈本期封面故事標題〉｜共 N 篇文章`）、各分頁 Instant View 超連結與大圖封面預覽。
   - **絕不包含**私人網站連結（「🔒 圖文完整版」）。
   - **完全不發送事實清單更新提醒**：台灣事實檔更新提醒（`fact_alerts`）為私訊專屬，絕不推送至頻道。
   - **絕不傳送**任何報告文件或英文原文全文。

---

## 中央社新聞查證與台灣事實清單維運

### 中央社客觀證據檢索機制與排查

`econ-digest` 於 `src/econ_digest/research/cna.py` 實作自動化中央社新聞檢索與取證機制，為涉台報導分析與事實清單檢查提供可驗證之外部依據：

1. **網址路徑日期嚴格解析**：
   - 中央社新聞之真實刊登日期，系統一律透過正規表達式自新聞 URL 路徑直接提取（`/news/[a-z]+/(\d{8})\d+\.aspx$`，取出 `YYYYMMDD`），並轉換為 ISO 日期物件。
   - **避免時間誤差**：絕不採用外部搜尋引擎或中繼資料呈現之發布時間，防範搜尋引擎索引時間偏差導致證據時序錯亂。
2. **禮貌頻率限制與退避重試（Polite Rate Limit & Exponential Backoff）**：
   - 客戶端在發起每次 HTTP 連線時，嚴格維護至少 **2.5 秒**（`REQUEST_INTERVAL = 2.5`）之請求冷卻間隔，展現對中央社新聞伺服器之禮貌與善意，防止造成頻寬壓力。
   - 若遇 HTTP 429 或 503 錯誤，會依標頭 `Retry-After`（支援秒數或 HTTP 日期）或指數退避（2.5 秒、5 秒、10 秒）自動重試至多 3 次。
3. **每次分析請求上限（Request Budget）**：
   - 每次分析嚴格限制至多發出 40 次 HTTP 請求（`cna_request_budget = 40`）。
   - 若達請求上限，系統記錄警告：`中央社每次分析請求上限（40 次）已達；後續查證僅使用快取。`，後續查證直接依賴快取結果，不再發出外部請求。
4. **短摘錄快取於 `data/research/` 與效期（Cache TTL）**：
   - 檢索與內文解析僅提取新聞標題與前兩段（至多 200 字）之純文字短摘錄，作為客觀事實判定依據。
   - 快取檔案存放於 `data/research/`（由 `.gitignore` 排除，絕不納入版本控制）。
   - 搜尋結果快取效期為 **7 天**（`SEARCH_TTL`），文章內文短摘錄快取效期為 **30 天**（`ARTICLE_TTL`）。
   - 快取目錄設有自動淘汰機制，最多保留最近 **500 筆** JSON 快取檔案，過期或超額檔案自動清除。
5. **網路斷線與連線失敗容錯（Fallback）**：
   - 若遇網路不通、DNS 異常、請求逾時或中央社伺服器無回應，`CNAClient` 會捕捉 `OSError`、`ValueError` 與 `TimeoutError`，記錄異常原因並安全回傳空證據清單。
   - 系統記錄警告：`中央社暫時無法連線；台灣關聯改以原文、事實檔與已取得的證據查證。`，管線不會中斷，改以原文脈絡與本機現存事實清單完成後續分析。

### 台灣事實清單維護與更新工作流

`src/econ_digest/facts/taiwan.md` 是提供給模型在執行涉台分析與查證時之核心客觀基準檔。

1. **事實清單涵蓋範圍（9 大關鍵領域）**：
   - **邦交國概況**：截至統計維持 12 友邦，包含各友邦近期動態、邦誼維護與歷史斷交紀錄。
   - **府會與國安首長**：現任正副總統、行政院長、外交部長與國防部長名單。
   - **立法院第 11 屆現況**：總席次 113 席分布（國民黨 52 席、民進黨 51 席、民眾黨 8 席、無黨籍 2 席）、三黨不過半局勢與正副院長。
   - **國防預算與占 GDP 比例**：115 年度（2026）執行預算（9,495 億元，占 GDP 3.32%）與 116 年度編列進度。
   - **對外貿易結構反轉**：對美出口占 30.9%，對中港降至 26.6%，美國睽違 26 年重返第一大出口市場。
   - **台積電（TSMC）海外晶圓廠進度**：美國亞利桑那廠、日本熊本廠、德國德勒斯登廠量產時程與封頂動態。
   - **台美關係與安全合作**：常態化對台軍售案（航材、M109A7、海馬士）與國防授權法 TSCI 倡議。
   - **台海現狀與共軍演習脈絡**：累計 7 次環台演習歷史背景、2025 年末「正義使命-2025」演習，以及 2026 年海空戰備警巡與海警灰色地帶巡查常態。
   - **關鍵戰略定位補充**：台灣掌握全球約 90% 先進半導體（7nm以下）產能；核三廠 2 號機除役後全台邁入無核電階段。
2. **嚴格溯源原則**：
   - 清單中每一項數據與事件，**必須具備具體「截至日期」與特定中央社新聞或官方公告之完整 URL**，嚴禁無來源之推論。
3. **每週定期自動時效檢查（`facts` 階段）**：
   - 每週執行管線時，模型會依據 `FACT_QUERIES` 自中央社檢索最新動態，與 `taiwan.md` 逐項對照。
   - **已發生事實認定原則**：檢查**僅通報已實際發生的重大事實變更**（如已就職、已請辭、已斷交、立法院已三讀通過、官方已公布最終正式數據）。
   - **排除未來式與未定事件**：競選言論、表態支持（背書）、提名、民調、預測、籌備規劃與假設條件句一律不採計；選舉結果僅在投票日當天或之後方得採計。
   - 若偵測到實際發生的事實變更，會在 Telegram 私人聊天室推送警報提醒（至多 5 則；每則警報帶有 `evidence_title`，必須逐字等於所引用之中央社新聞標題，並作為超連結文字呈現；無標題之舊式警報則顯示為「中央社」）：
     ```
     ⚠️ 台灣事實檔可能需要更新：
     • <事實檔說法> → <已完成的疑似新值與日期>（〈<中央社標題>〉）
     （請確認）
     ```
   - 此訊息僅發送至私人聊天室，絕不推播至頻道。
4. **維護與更新操作步驟**：
   - **第一步：查核與確認**：點擊警報訊息中之中央社超連結，閱讀新聞確認官方宣布或事實變更。
   - **第二步：手動編輯檔案**：使用文字編輯器修改 `src/econ_digest/facts/taiwan.md`，更新相應章節之文字、數據、截至日期與中央社 URL。
   - **第三步：提交並推送**：
     ```sh
     # 檢視修改差異
     git diff src/econ_digest/facts/taiwan.md

     # 加入暫存區並提交
     git add src/econ_digest/facts/taiwan.md
     git commit -m "docs(facts): update Taiwan diplomatic and defense status"

     # 推送至遠端儲存庫
     git push origin master
     ```

---

## 問題排查速查表

| 現象或錯誤代碼 | 常見原因 | 系統預設處理機制 | 建議處置方式 |
| :--- | :--- | :--- | :--- |
| **`User location is not supported`** | 模型 API 節點地理位置暫時性限制。 | 分類為 `location` 錯誤，立即切換至下一備援模型（如 `claude-sonnet-4-6`）。 | 檢查出站代理；通常由備援模型接手完成，無須干預。 |
| **`gwg exit 75` / `no free account`** | 帳號池無可用帳號，或 Claude 5 小時額度耗盡使整帳號進入冷卻（連帶阻斷 Gemini 呼叫）。 | 分類為 `no_account`，指數退避等待至多 `no_account_wait_seconds`（預設 900 秒）；單元快取有效，重跑不重複扣額。 | 執行 `gwg status` 與 `gwg usage --json` 檢視配額重設時間；待重設後重新執行，或於 `config.toml` 將繁重階段暫時改為 Flash。 |
| **配額耗盡 (`RESOURCE_EXHAUSTED` / 429)** | 模型達到帳號呼叫額度限制。 | 分類為 `quota`，立即切換至備援模型。 | 待配額重設後重新執行，已快取單元不重複扣額。 |
| **Telegram `can't parse entities`** | HTML 標籤格式不符合 Telegram 規範。 | 自動捕捉錯誤，立即調用 `strip_tags()` 剝除標籤改以純文字降級重送。 | 自動自我修復，訊息保證送達，無須介入。 |
| **缺少 Token 或 Chat ID** | 密鑰檔未建立或尚未執行配對。 | 拒絕發送並提示設定說明。 | 透過 `telegram-setup --test` 完成綁定。 |
| **Telegraph `FLOOD_WAIT_N`** | Telegraph API 觸發頻率限制。 | 解析等待秒數並自動 sleep 退避重試（最多 5 次）。 | 自動自我恢復，無須手動干預。 |
| **缺少或無效的 Telegraph Token** | 未設定或 Token 遭伺服器撤銷。 | 自動嘗試重新註冊帳號並寫入密鑰檔。 | 執行 `telegraph-setup --force` 強制重新註冊。 |
| **Telegraph 頁面超過容量上限** | 單篇內容加上導覽超過 60 KB 上限。 | 本地排版階段預先檢驗並中止，避免建立半殘頁面。 | 在 `config.toml` 中調高 `[telegraph] page_limit_bytes`（上限 64,000）或調整摘要深度。 |
| **私人網站發布失敗 (SSH / tar)** | 本機缺 ssh/tar、遠端缺 tar、SSH 逾時或目錄權限錯誤。 | 記錄警告，摘要訊息自動省略網站連結，自動改傳單檔 HTML 報告備援。 | 檢查本機與遠端 tar/ssh 安裝、SSH 連線、`ssh_host` 與金鑰設定；單檔報告保證讀者取得內容。 |
| **Telegram 內建瀏覽器無法登入網站** | Telegram 內建瀏覽器不支援 HTTP Basic Auth 彈窗。 | 屬於 Telegram 應用程式限制。 | 點擊瀏覽器選單選擇「在預設瀏覽器中開啟」（Safari / Chrome）即可正常輸入帳密。 |
| **GitHub 備份 push 失敗** | Git 權限不符、儲存庫未建立或網路問題。 | 記錄警告（`網站備份失敗`），導讀主流程持續完成。 | 檢查 GitHub SSH 金鑰與儲存庫權限；確保備份儲存庫設定為 Private。 |
| **英文選文或學習指南失敗** | 選文或指南模型呼叫逾時或格式錯誤。 | 記錄警告（`英文選文失敗`），導讀主流程持續完成。 | 檢查模型配額與網路；必要時加上 `--reanalyze` 重新執行。 |
| **插圖說明產生失敗，圖片保留但無說明。** | 圖片讀取或模型呼叫失敗，或圖說種類、字數、圖片名稱驗證未通過（圖表、地圖 20–180 字；照片、插畫 8–60 字）。 | 私人網站與單檔 HTML 保留圖片，省略失敗的圖說；其餘導讀仍可產出。地圖圖說使用「▲ 地圖：」，圖表使用「▲ 圖表：」，照片與插畫使用「▲ 配圖：」。 | 檢查 `data/issues/te_YYYY.MM.DD/figures/` 圖片與 gwg 配額，確認 `[llm.models] figures` 支援看圖後重新執行 `analyze`；成功的單元沿用快取。提示詞以 140 字內及清楚可辨識的主張為目標，省略細微差異與未標示的例外。若需重試已快取的不合規個別圖說，僅刪除對應的 `analysis/figures-*.json`。 |
| **`--pages-only` 於 messages 模式失敗** | 設定檔為 `delivery = "messages"` 時執行了 `--pages-only`。 | 輸出提示並以 exit code 2 退出。 | 確認 `delivery = "telegraph"`；若在 messages 模式下需重送請用 `--force`。 |
| **執行鎖已被占用 (`AlreadyRunning`)** | 同一時間已有另一個實例正在運行。 | 捕捉非阻塞檔案鎖失敗並安全退出（exit code 0）。 | 正常保護機制；若程序卡死，使用 `ps aux \| grep econ-digest` 確認。 |
| **`edit` 或 `ground` 階段逾時** | `edit`（預設 900 秒）批次編修或 `ground`（預設 600 秒，`ground_queries` 亦同）取證比對耗時超出門檻。 | 達逾時門檻後，`edit` 自動切換至 Claude Sonnet 4.6 備援，`ground` 自動切換至 Gemini 3.8 Flash 備援。 | 確認 `stage_timeout_seconds` 未被誤設過低；檢查網路連線。 |
| **中央社暫時無法連線** | 中央社網站維護、DNS 異常或連線逾時。 | 記錄警告，自動降級以原文、事實檔與已快取證據查證，主流程順利完成。 | 屬暫時性外部網路問題，無須介入；管線保證閱讀內容產出。 |
| **標題與要聞編修驗證退回** | 模型改寫未符合字數規範、標點符號（如一句話重點非單句、非「。」結尾、含全形空格或問驚號、重複標題）或實體名稱守衛。 | 逐欄位安全驗證，不合規條目自動退回原文字，記錄警告。 | 安全保護機制生效，保證報告標題結構完整不損毀，無須緊急處置。 |
| **收到事實檔更新提醒 (`fact_alerts`)** | 每週比對僅通報已實際發生之重大事實變更（已就職、已請辭、已斷交、立法院三讀通過、官方正式數據；排除競選言論、民調、預測與規劃）。 | 於私人聊天室發送 `⚠️ 台灣事實檔可能需要更新` 警報（至多 5 則，每則附帶 `evidence_title` 呈現〈中央社標題〉連結）。 | 點擊連結確認屬實後，編輯 `src/econ_digest/facts/taiwan.md` 並 commit/push。 |
| **每週管線執行時間顯著拉長** | 外部取證比對與深度解析模型運算。2026-10-06 實測 17 個編修區塊在 Gemini Flash（parallel=2）約需 30 分鐘，加上前期各階段模型時間約需 31 分鐘。 | 正常架構行為，單期完整執行耗時約 45–60 分鐘。 | 屬預期現象；systemd 服務已配置 3 小時上限（`TimeoutStartSec=3h`），空間充裕無須調整。 |

---

## 常見問題深度排查

### 1. gwg: User location is not supported

- **詳細成因**：模型 API 端點伺服器判定來源 IP 所在地理區域不支援。
- **系統處理機制**：LLM 客戶端捕捉 `location` 錯誤，當前模型立即中斷，無縫切換到 `[llm.models]` 中定義的備援模型（如 `claude-sonnet-4-6`）。
- **處置建議**：通常無須手動干預；若欲排查主要模型，檢查主機網路與代理設定。

---

### 2. gwg exit 75 / no free account

- **現象描述**：所有帳號皆回報結束代碼 `75`（`gwg exit 75`）或 `no free account`，且不僅 Claude 階段無法呼叫，連 Gemini 階段也一併失敗。
- **詳細成因**：當 Claude 5 小時額度耗盡時，`gwg` 會讓整個帳號進入冷卻狀態（cooldown），連帶阻斷該帳號上的 Gemini 呼叫，直到額度桶重設時點。
- **系統內部行為**：
  - 管線捕捉後歸類為 `no_account`，並以指數退避（30 秒、60 秒、120 秒…）在 `no_account_wait_seconds`（預設 900 秒）內持續重試等待釋出可用帳號。
  - 單元級快取（Unit-level cache）保證已完成之單元持續有效，後續重新執行時絕不重複消耗模型額度。
- **處置建議**：
  1. 檢查帳號狀態與額度重設時點：
     ```sh
     gwg status
     gwg usage --json
     ```
     透過 `gwg usage --json` 檢視各帳號之 5 小時與每週配額用量及精確重設時間。
  2. 待額度重設後重新執行，已快取單元不重複扣額：
     ```sh
     .venv/bin/econ-digest run --issue YYYY.MM.DD
     ```
  3. 若急需產出且不想等待，可暫時於本地 `config.toml` 的 `[llm.models]` 中將繁重階段導向 Flash：
     ```toml
     [llm.models]
     summarize_a = ["gemini-3.8-flash-high", "claude-sonnet-4-6"]
     ground = ["gemini-3.8-flash-high", "claude-sonnet-4-6"]
     facts = ["gemini-3.8-flash-high", "claude-sonnet-4-6"]
     ```

---

### 3. 模型配額耗盡 (Quota Exhaustion)

- **詳細成因**：帳號在短時間內達到呼叫額度限制（HTTP 429）。
- **系統處理機制**：標記為 `quota` 錯誤，立即轉移至備援模型繼續處理剩餘批次。
- **處置建議**：待配額重設後重新執行，單元級快取保證已完成部分不重複扣額。

---

### 4. Telegram: can't parse entities

- **詳細成因**：Telegram 拒絕不合規的 HTML 標籤結構（HTTP 400）。
- **系統處理機制**：`send_message_safe()` 自動攔截錯誤並記錄警告，立即調用 `strip_tags()` 剝除標籤改以純文字降級重送。
- **處置建議**：系統保證 100% 送達，無須維運處置。

---

### 5. 缺少 Token、Chat ID 或 Channel ID

- **處置步驟**：
  1. 建立 `~/.config/econ-digest/env` 寫入 `TELEGRAM_BOT_TOKEN`（權限 600）。
  2. 綁定私人聊天室：發送 `/start` 後執行 `.venv/bin/econ-digest telegram-setup --test`。
  3. 綁定頻道（選填）：機器人設為頻道管理員後執行 `.venv/bin/econ-digest telegram-setup --channel @my_channel --test`。

---

### 6. 執行失敗與重試機制 (Failed Run)

- **系統處理機制**：
  1. 失敗時向 Telegram 私人聊天室發送警報：`⚠️ 本週經濟學人導讀產生失敗（{error_type}），稍後會自動重試。`
  2. **單日防洗版保護**：同一期別在同一曆日內最多僅發送一次失敗警報。
  3. 定時器於下個排程時段自動重試。

---

### 7. 執行鎖衝突 (Lock already held)

- **詳細成因**：排程背景工作正在進行時，手動重複啟動程序。
- **系統處理機制**：系統在 `data/.lock` 上調用非阻塞排他鎖，取得鎖失敗時捕捉 `AlreadyRunning` 並優雅退出（exit code 0）。
- **處置建議**：若程序卡死，使用 `ps aux | grep econ-digest` 查看，超過 3 小時會由 systemd 強制終止。

---

### 8. Telegraph: FLOOD_WAIT_N

- **詳細成因**：短時間內頻繁發起 Telegraph API 請求觸發頻率限制。
- **系統處理機制**：客戶端自動解析等待秒數並 sleep 退避重試（最多 5 次）。
- **處置建議**：自動自我修復，無須介入。

---

### 9. 缺少或無效的 Telegraph Access Token

- **處置建議**：執行 `.venv/bin/econ-digest telegraph-setup --force` 強制重新註冊專屬帳號並覆蓋密鑰檔。

---

### 10. Telegraph 頁面超出容量上限 (Page Size Limit)

- **詳細成因**：單篇內容加上導覽列超出 `page_limit_bytes`（上限 64,000 位元組）。
- **處置建議**：
  1. 開啟 `config.toml` 調高 `[telegraph] page_limit_bytes = 63000`。
  2. 或在 `[tiers]` 調低該文體摘要深度後重新執行。

---

### 11. 原地維護機制與模式限制 (`send --pages-only`)

- **功能特色**：
  - 重建本地多頁網站（`output/`）。
  - 發布更新至遠端 Web 伺服器（若 `[site] enabled = true`）。
  - 原地編輯已發布之 Telegraph 頁面（網址維持不變）。
  - 提交並 push 備份至私有 GitHub 儲存庫。
  - **完全不發送 Telegram 訊息**，不修改已發送狀態。
- **模式限制**：僅適用於 Telegraph 傳送模式（`delivery = "telegraph"`）。

---

### 12. 私人網站發布與 SSH / tar 失敗排查

- **詳細成因**：
  1. 本機缺少 `ssh` 或 `tar`，或遠端伺服器未安裝 `tar`（`command -v tar` 預檢失敗）。
  2. SSH 金鑰未配置免密碼登入或逾時（`ssh_timeout_seconds`）。
  3. 伺服器端目錄（`remote_dir`）權限不足，無法建立 `.incoming` 暫存目錄或完成原子替換。
  4. 當前設備處於外部未受信任網路，無法連線至指定主機。
- **系統內部行為**：
  - 系統在發布前會先驗證本機具備 `ssh` 與 `tar`，並透過 SSH 於遠端伺服器執行 `command -v tar` 預檢。
  - 將本期發布目錄以 tar 封裝透過 SSH 串流傳輸至遠端暫存目錄（`.incoming/`）解開，並以原子替換（atomic swap）方式部署（舊版本暫存為備份，若替換失敗自動還原；替換成功後清除備份）。
  - 若遇傳輸中斷、預檢失敗或替換異常，`publish_site()` 捕捉 `PublishError`，記錄警告：`私人網站發布失敗；改用單檔 HTML 報告。`（並附帶 stderr 尾部除錯資訊）。
  - 傳送訊息時 `site_url` 設為 `None`，摘要訊息自動拿掉「🔒 圖文完整版」連結。
  - 自動啟用備援機制，將單檔完整 HTML 報告（`report.html`）作為附件檔案發送至 Telegram 私人聊天室。
- **維運處置**：
  1. 測試本機與遠端工具及連線：
     ```sh
     which tar
     ssh -o BatchMode=yes your-server "command -v tar && mkdir -p /var/www/site"
     ```
  2. 確認遠端目錄擁有者與權限（確保登入使用者具備寫入權限）。
  3. 若網路環境暫時無法連線至 Web 伺服器，系統的單檔報告備援機制可確保閱讀體驗不受影響。

---

### 13. Telegram 內建瀏覽器無法處理 Basic Auth 彈窗問題

- **現象描述**：讀者在 Telegram 手機端點擊「🔒 圖文完整版」連結時，Telegram 內建之 In-App Browser 偶爾無法正確彈出 HTTP Basic Auth 帳號密碼對話框，或登入後反覆跳轉 401 錯誤。
- **成因解析**：部分平台的 Telegram 內建瀏覽器 WebKit 核心對 HTTP 401 Challenge 支援度不一致，可能阻斷基本身分驗證對話框。
- **解決方式**：
  - **在系統瀏覽器中開啟**：點擊右上角選單（三點圖示或分享圖示），選擇「**在瀏覽器中開啟**」（如 Safari、Chrome 或 Firefox）。
  - 系統瀏覽器具備完整的 HTTP Basic Auth 支援與密碼自動填入（Keychain / Google 密碼管理員），輸入一次後即可長期免密碼閱讀。

---

### 14. 網站備份 push 失敗排查

- **現象描述**：日誌中出現警告：`網站備份失敗（SubprocessError）；導讀傳送繼續。`
- **成因解析**：
  1. Git 無法透過 SSH 連線至 GitHub（缺少 SSH 金鑰或 `ssh-agent` 未啟動）。
  2. 遠端儲存庫不存在、URL 錯誤或使用者無推送權限。
- **處置步驟**：
  1. 檢查 `output/` 內的獨立 Git 狀態：
     ```sh
     git -C output remote -v
     git -C output status
     ```
  2. 測試 GitHub SSH 驗證：
     ```sh
     ssh -T git@github.com
     ```
  3. **確認儲存庫屬性**：至 GitHub 確認該備份儲存庫（如 `OWNER/econ-digest-output`）屬性設定為 **Private**，嚴禁設定為 Public。

---

### 15. 英文學習選文或指南失敗與容錯機制

- **現象描述**：日誌中出現警告：`英文選文失敗（quota），本期未提供學習指南。` 或 `英文學習指南失敗（timeout），本期未提供學習指南。`
- **成因解析**：
  1. 當期無符合字數範圍（600–1,300 字）之候選文章。
  2. 英文選文或指南生成單元發生模型額度耗盡或逾時。
- **系統內部行為**：
  - 英文學習單元採獨立錯誤捕捉設計。若選文或指南製作失敗，系統將 `digest.english` 設為 `None`，並在日誌記錄警告。
  - 整期導讀的其他分析、要聞速覽、台灣專區、網站建置與 Telegram 發送**完全不受影響**，管線不會崩潰中斷。
- **維運處置**：
  - 若為偶發配額問題，待配額重設後執行：
    ```sh
    .venv/bin/econ-digest analyze --issue <期別> --reanalyze
    .venv/bin/econ-digest send --issue <期別> --pages-only
    ```
    即可重新嘗試評選與製作學習指南，並原地更新至 Telegraph 頁面與私人網站。

---

### 16. edit 與 ground 階段耗時與逾時處理

- **現象描述**：日誌中顯示 `edit` 或 `ground` 階段持續運行數分鐘，或偶發逾時錯誤（`timeout`）。
- **成因解析**：
  1. `edit` 階段每批至多處理 10 項（9,000 bytes），需逐項核對數字、實體詞彙並進行自然繁體新聞風格編修；預設主要模型為 Gemini 3.8 Flash，備援模型為 Claude Sonnet 4.6。實測在 Gemini Flash 上一個編修區塊約需 70–250 秒、消耗 42–51k tokens（在 Opus 上則曾需 240–560 秒）。
  2. `ground` 階段（及 `ground_queries` 階段）使用具深度思考之 Claude Opus 4.6 (thinking)，結合中央社外部客觀證據與台灣事實清單進行嚴謹比對。
- **系統內部行為**：
  - 系統於 `config.toml` 預設提供階段專屬逾時配置：`stage_timeout_seconds = { edit = 900, ground = 600 }`。`ground_queries` 共用 `ground` 之 600 秒逾時設定，其餘階段維持全域 `call_timeout_seconds = 300` 秒。
  - 若逾時或異常，LLM 客戶端自動切換至各階段定義之備援模型（`edit` 切換至 Claude Sonnet 4.6，`ground` 切換至 Gemini 3.8 Flash）接手完成。
- **維運處置**：
  - 此為預期的逐項編修與深度查證耗時，無須過度干預。
  - 若自訂 `config.toml`，請務必保留 `edit`（至少 900 秒）與 `ground`（至少 600 秒）之充足逾時門檻，切勿將其設得過短。

---

### 17. 中央社新聞檢索異常與快取維護

- **現象描述**：日誌中出現警告：`中央社暫時無法連線；台灣關聯改以原文、事實檔與已取得的證據查證。` 或 `中央社每次分析請求上限（40 次）已達；後續查證僅使用快取。`
- **成因解析**：
  1. 中央社網站進行維護、DNS 解析延遲、連線逾時（超過 15 秒），或短時間內發起過多請求觸發 HTTP 429 / 503 頻率限制。
  2. 單次管線執行累計請求次數達到 40 次安全上限（`cna_request_budget = 40`）。
- **系統內部行為**：
  - 客戶端保持至少 2.5 秒請求冷卻間隔；遇到 HTTP 429 或 503 時，依 `Retry-After` 標頭或指數退避（2.5 秒、5 秒、10 秒）自動重試至多 3 次。
  - 當請求數達到 40 次上限，或連線發生例外時，`CNAClient` 安全記錄原因，不引發程式崩潰。
  - 台灣關聯查證單元（`ground_digest`）自動改以原文脈絡、本機 `taiwan.md` 事實清單與 `data/research/` 既有快取完成分析。
- **維運處置**：
  - 通常為暫時性網路抖動或配額保護，導讀生成會平順完成，無須手動介入。
  - `data/research/` 快取目錄由系統自動維護（搜尋結果 7 天、文章短摘錄 30 天，上限 500 筆循環覆蓋），不會無限制佔用磁碟。

---

### 18. 台灣事實檔更新提醒處理工作流

- **現象描述**：Telegram 私人聊天室收到獨立訊息：
  ```
  ⚠️ 台灣事實檔可能需要更新：
  • <事實檔說法> → <已完成的疑似新值與日期>（〈<中央社標題>〉）
  （請確認）
  ```
- **成因解析**：
  - 每週定期執行的 `facts` 檢查階段比對中央社最新要聞與 `src/econ_digest/facts/taiwan.md`。檢查僅通報已實際發生的重大事實變更（如已就職、已請辭、已斷交、立法院已三讀通過、官方已公布最終正式數據；排除競選言論、支持背書、提名、民調、預測、規劃與假設句；選舉結果僅於投票日當天或之後採計）。
- **系統內部行為**：
  - 系統僅在私人聊天室發送私密提醒（至多 5 則；每則警報帶有 `evidence_title`，必須逐字等於所引用之中央社新聞標題，並作為超連結文字呈現；無標題之舊式警報則顯示為「中央社」），**絕不推播至頻道**，整期導讀主發布流程順利完成。
- **維運處置**：
  1. 點擊警報訊息中之中央社連結，查閱官方最新報導或外交/國防公告確認屬實。
  2. 編輯更新 `src/econ_digest/facts/taiwan.md` 對應章節內容、截至日期與中央社 URL。
  3. 透過 Git 提交並推送至儲存庫：
     ```sh
     git add src/econ_digest/facts/taiwan.md
     git commit -m "docs(facts): update Taiwan diplomatic and defense status"
     git push origin master
     ```

---

### 19. 標題與要聞編修驗證退回機制

- **現象描述**：日誌中出現警告：`標題與要聞編修失敗，保留原文字。`
- **成因解析**：
  - 模型在 `edit` 階段產出之改寫標題、一句話重點（`headline_zh`）或要聞條目未通過嚴格語法、長度或實體守衛：
    1. **新聞標題規範**：字數須介於 8–26 字；不得包含問號「？」、逗號「，」或非發言引述之冒號「：」；改寫後數字須與原文數字一致；不得出現原文未提及且不在標準新聞詞彙表內的陌生專有名詞（實體名稱閘道攔截）。
    2. **一句話重點規範（`headline_zh`）**：必須為單一自然句，長度 30–60 字（中文字數）且以「。」結尾（全句僅能包含一個句號「。」）；不得重複中文標題內容；不得包含全形空格（`\u3000`）、換行符號、問號（`?`、`？`）或驚嘆號（`!`、`！`）；且必須忠實於輸入內容。
    3. **要聞條目規範**：各條要聞長度須符合字數範圍，數字與關鍵實體須完全對齊輸入內容。
- **系統內部行為**：
  - `editor.py` 實作「逐欄位安全退回機制」（Field-by-field safe fallback）。
  - 若特定文章標題、一句話重點或要聞條目未通過驗證，系統自動退回採用前一階段之原文字（保留原摘要文字），保證不產出任何毀損或格式異常之內容。
- **維運處置**：
  - 屬於正常的品質守衛保護機制，整期導讀不受影響，無須緊急處置。
