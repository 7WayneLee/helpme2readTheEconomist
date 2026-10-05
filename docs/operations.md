# 維運與故障排除指南 (Operations and Troubleshooting)

本文件提供 `econ-digest` 每週導讀系統的日常維運、狀態檢查、手動介入方式與常見問題排查指南。

---

## 目錄

- [日常維運](#日常維運)
  - [日誌位置與檢視方式](#日誌位置與檢視方式)
  - [檢查定時器與服務狀態](#檢查定時器與服務狀態)
  - [手動觸發與重新發送](#手動觸發與重新發送)
  - [重設單期快取](#重設單期快取)
  - [更新詞彙對照表後重建報告](#更新詞彙對照表後重建報告)
- [問題排查速查表](#問題排查速查表)
- [常見問題深度排查](#常見問題深度排查)
  - [1. gwg: User location is not supported](#1-gwg-user-location-is-not-supported)
  - [2. gwg exit 75 / no free account](#2-gwg-exit-75--no-free-account)
  - [3. 模型配額耗盡 (Quota Exhaustion)](#3-模型配額耗盡-quota-exhaustion)
  - [4. Telegram: can't parse entities](#4-telegram-cant-parse-entities)
  - [5. 缺少 Token 或 Chat ID](#5-缺少-token-或-chat-id)
  - [6. 執行失敗與重試機制 (Failed Run)](#6-執行失敗與重試機制-failed-run)
  - [7. 執行鎖衝突 (Lock already held)](#7-執行鎖衝突-lock-already-held)
  - [8. Telegraph: FLOOD_WAIT_N](#8-telegraph-flood_wait_n)
  - [9. 缺少或無效的 Telegraph Access Token](#9-缺少或無效的-telegraph-access-token)
  - [10. Telegraph 頁面超出容量上限 (Page Size Limit)](#10-telegraph-頁面超出容量上限-page-size-limit)
  - [11. Telegraph 頁面維護與模式限制 (send --pages-only)](#11-telegraph-頁面維護與模式限制-send---pages-only)

---

## 日常維運

### 日誌位置與檢視方式

系統提供兩種層級的日誌輸出：應用程式專屬滾動檔案日誌與 systemd 使用者單元日誌。

#### 1. 應用程式檔案日誌
- **預設路徑**：`data/logs/econ-digest.log`
- **輪替機制**：單一檔案大小上限為 2 MB，自動保留最近 3 份歷史輪替檔案（`econ-digest.log.1`、`.2`、`.3`）。
- **隱私安全**：所有敏感憑證（包括 `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`、`GITHUB_TOKEN`、`TELEGRAPH_ACCESS_TOKEN` 以及 Telegram API URL 中的 Bot Token）在寫入日誌時均會自動遮蔽為 `[已隱藏]`。
- **即時檢視指令**：
  ```sh
  # 持續監控最新日誌輸出
  tail -f data/logs/econ-digest.log

  # 檢視最近的錯誤紀錄
  grep -E 'WARNING|ERROR' data/logs/econ-digest.log | tail -n 50
  ```

#### 2. systemd 服務日誌
定時器觸發的執行紀錄會直接串接至 systemd journal：
```sh
# 即時追蹤使用者服務輸出
journalctl --user -u econ-digest.service -f

# 檢視本次開機週期內的執行紀錄
journalctl --user -u econ-digest.service -b

# 檢視最近 100 行紀錄（不分頁）
journalctl --user -u econ-digest.service -n 100 --no-pager
```

---

### 檢查定時器與服務狀態

若已透過 `deploy/install-user-timer.sh` 安裝使用者排程，可使用下列指令監控運作狀態：

```sh
# 1. 檢查定時器排程、下次觸發時間與上次執行結果
systemctl --user list-timers econ-digest.timer

# 2. 查看定時器單元詳細狀態
systemctl --user status econ-digest.timer

# 3. 查看最近一次執行的背景服務單元狀態（執行時間與退出碼）
systemctl --user status econ-digest.service
```

> [!NOTE]
> 使用者定時器預設在登入狀態下運作。若要在登出伺服器後持續在背景執行，請確認已啟用 lingering：
> ```sh
> loginctl enable-linger "$USER"
> ```

---

### 手動觸發與重新發送

#### 手動立即執行完整流程
無須等待週末排程，可隨時手動觸發 systemd 服務或直接在命令列執行：
```sh
# 透過 systemd 背景啟動
systemctl --user start econ-digest.service

# 或直接在終端機前台執行（顯示即時進度）
.venv/bin/econ-digest run
```

#### Telegraph 模式每週傳送順序與機制
在預設的 Telegraph 傳送模式下，執行 `send` 指令時，系統依序發送三階段內容至 Telegram 私人聊天室：
1. **封面照片搭配摘要圖說（`send_photo`）**：
   - 以當期《經濟學人》封面照片發送，圖說為核心摘要（包含期別標題概覽 overview、粗體「**與台灣相關**」焦點標題條列與 4 個 Instant View 分頁超連結）。
   - **字數超限容錯**：若圖說超過 Telegram 的 1024 字元（UTF-16 單位）上限，系統會自動精簡圖說（暫時省略與台灣相關焦點）；若仍超過 1024 字元，封面圖說僅保留期別標題，並將完整摘要作為下一則獨立文字訊息發送。
   - **無封面回退**：若電子書缺少封面照片或設定 `[telegram] cover_photo = false`，系統自動回退為發送純文字摘要訊息。
   - **無國旗設計原則**：系統各國新聞均不使用國旗 emoji（其他國家要聞亦不加國旗），以文字標籤維持中立與排版整潔。
2. **英文選文原文私密傳送**：
   - 緊隨摘要之後，將英文選文全文以 Telegram 可展開／收合的引用區塊「**📖 英文選文原文（點開）**」（篇幅長時以「**📖 英文選文原文（續）**」接續分則）私密傳送。
3. **完整圖文 HTML 報告檔案（`send_document`）**：
   - 發送內嵌完整封面、文章插圖、圖表地圖與本週漫畫之獨立 HTML 報告（`report.html`，單檔約 7–8 MB），附帶圖說「**完整報告（含插圖與英文選文原文）**」（由 `[telegram] send_report_file` 控制，預設已恢復為 `true`；圖片內嵌由 `[report] embed_images` 控制，預設 `true`）。

> [!IMPORTANT]
> **Telegraph 頁面純文字與版權隱私防護原則**
> Telegraph 頁面為公開網址，任何持有連結者皆可瀏覽存取。為保護著作權與個人閱讀隱私：
> - **Telegraph 頁面一律維持純文字（Text-Only）**，絕不包含任何期刊圖片、封面照片、文章插圖、圖表或漫畫，亦絕對不放上《經濟學人》原始文章之英文全文。
> - 插圖與英文原始全文**一律僅於 Telegram 私人聊天室（照片圖說、私訊摺疊區塊、文件附件）以及本機私密報告檔案流通**。
> - Markdown 報告（`report.md`）亦維持純文字排版，不內嵌圖片。

#### 接續中斷的傳送（斷點續傳）
若在發布 Telegraph 頁面或推送至 Telegram 期間網路斷線或發生暫時性錯誤，直接再次執行 `send` 指令即可：
```sh
.venv/bin/econ-digest send
```
系統會自動讀取 `data/issues/te_<期別>/telegram_progress.json` 中的進度指標（包含 `pages_published` 頁面發布狀態與 `next_message` 訊息傳送索引），自動跳過已發布之頁面與已發送之訊息，接續傳送剩餘內容。

#### 重新發送已完成期別（原地編輯與強制重送）
若某期先前已發送完畢（已記錄於 `state.json` 的 `delivered` 中），系統預設會略過以避免干擾。若需強制重新發送全部內容：
```sh
# 重新發送最新一期
.venv/bin/econ-digest send --force

# 或重新發送特定期別
.venv/bin/econ-digest send --issue 2026.10.03 --force
```
- **Telegraph 原地編輯（In-Place Edit）**：在預設的 Telegraph 模式下，`--force` 不會重複產生新的公開網址，而是讀取 `data/issues/te_<期別>/telegraph_pages.json`，對既有的 Telegraph 頁面進行**原地編輯（EDIT）**更新內容。網址維持完全相同，先前已推送至 Telegram 聊天室的 Instant View 預覽與連結均持續有效；若因調整摘要深度使分頁數量減少，多餘的舊頁面會自動被編輯為標題「此頁已不再使用」（並提供回當期第一頁之超連結）。
- **Messages 模式行為**：若設定檔中為 `[telegram] delivery = "messages"`，則 `--force` 會自第一則起重新發送全部切分訊息。在此模式下，文章標題冠上「T1 · …」等關聯層級代碼（例如 `<b>T1 · 文章標題</b>`），清晰識別重要程度；其他國家的新聞亦不使用國旗 emoji 標示。

#### 離線預覽檢視（Dry-run）
若欲在不對外建立 Telegraph 頁面且不向 Telegram 發送任何訊息的情況下，檢查頁面排版與大小，可加上 `--dry-run` 旗標：
```sh
.venv/bin/econ-digest send --dry-run
```
終端機會列印出所有分頁標題、以預覽網址計算的 UTF-8 JSON 位元組大小（驗證是否低於 `page_limit_bytes`），以及即將發送至 Telegram 的封面照片圖說、摘要訊息與英文選文私訊摺疊區塊。

#### 僅原地更新 Telegraph 頁面（`send --pages-only`）
若在修訂摘要提示詞、正體字對照表或修正報告文字後，需要更新已發布的 Telegraph 頁面，但**不想向 Telegram 私人聊天室再次發送任何訊息**（避免打擾手機端），可使用 `--pages-only` 旗標：
```sh
# 1. 離線預覽 Telegraph 各分頁標題與 UTF-8 位元組大小（不發布）
.venv/bin/econ-digest send --pages-only --dry-run

# 2. 原地更新 Telegraph 頁面
.venv/bin/econ-digest send --pages-only

# 或指定特定期別
.venv/bin/econ-digest send --issue 2026.10.03 --pages-only
```
- **維持網址與進度不變**：程式會讀取 `data/issues/te_<期別>/telegraph_pages.json`，對既有的 Telegraph 頁面進行**原地編輯（EDIT）**，公開網址維持不變，已推送至 Telegram 的連結持續有效。
- **不更動狀態**：不會向 Telegram 私人聊天室發送任何訊息，亦不會修改 `telegram_progress.json` 的傳送進度或 `state.json` 的已傳送紀錄。
- **模式限制**：`--pages-only` 僅適用於 Telegraph 傳送模式（`[telegram] delivery = "telegraph"`）。若在 messages 模式下執行，程式會輸出 `--pages-only 僅適用於 Telegraph 模式；請將 telegram.delivery 設為 telegraph。` 並以結束代碼 2 退出。

---

### 重設單期快取

若特定期別因提示詞變更或模型輸出不理想，需全部重新分析：

#### 方法一：使用命令列參數（推薦）
```sh
# 清除本期分析快取並重新呼叫模型分析
.venv/bin/econ-digest analyze --issue 2026.10.03 --reanalyze

# 或在完整管線中清除快取並強制重跑發送
.venv/bin/econ-digest run --issue 2026.10.03 --reanalyze --force
```

#### 方法二：手動刪除快取檔案
可直接刪除該期別目錄下的分析快取目錄與導讀摘要檔案：
```sh
rm -rf data/issues/te_2026.10.03/analysis
rm -f data/issues/te_2026.10.03/digest.json
```
> [!TIP]
> 手動刪除時請保留 `TheEconomist.2026.10.03.epub` 與 `issue.json`，如此系統在重新分析時無須重新自 GitHub 下載或重新剖析電子書結構。

---

### 更新詞彙對照表後重建報告

系統的單元級快取（版本 2）儲存的是通過結構驗證、但**尚未執行台灣正體在地化（zh-TW normalisation）**的原始輸出；正體化轉換與詞彙替換是在組裝完整導讀資料（`digest.json`）時才執行。

若維運期間編輯或擴充了 `src/econ_digest/zhtw/glossary.tsv` 中的在地化慣用語對照表，**不需要**清除快取或重新呼叫模型，可直接依序執行下列指令重建報告：

```sh
# 1. 重新組裝導讀（所有單元直接從快取讀取，不消耗模型配額，重新套用最新 glossary.tsv）
.venv/bin/econ-digest analyze --issue 2026.10.03

# 2. 重新渲染 Markdown、HTML 報告與 Telegram 訊息切塊
.venv/bin/econ-digest render --issue 2026.10.03
```

- 若欲將更新後的內容重新推送到 Telegram 私人聊天室（包含重新發送封面照片、私密原文與完整報告檔案）：
  ```sh
  .venv/bin/econ-digest send --issue 2026.10.03 --force
  ```
- 若**僅欲原地更新 Telegraph 頁面而不向 Telegram 私人聊天室發送任何訊息**（保留進度與傳送狀態）：
  ```sh
  .venv/bin/econ-digest send --issue 2026.10.03 --pages-only
  ```

---

## 問題排查速查表

| 現象或錯誤代碼 | 常見原因 | 系統預設處理機制 | 建議處置方式 |
| :--- | :--- | :--- | :--- |
| **`User location is not supported`** | 模型 API 節點暫時性地理位置限制（2026-10-05 曾於部分節點短暫出現）。 | 分類為 `location` 錯誤，當前模型立即中斷，自動切換至下一備援模型（如 `claude-sonnet-4-6`）。 | 檢查網路出口或代理設定；多數情況由備援模型接手即可順暢完成，無須手動干預。 |
| **`gwg exit 75` / `no free account`** | `gwg` 帳號池中所有可用帳號皆處於忙碌或暫時冷卻狀態。 | 分類為 `no_account`，以指數退避（30s、60s、120s…）自動等待至多 `no_account_wait_seconds`（預設 900 秒）。 | 若等待超時，執行 `gwg status` 檢查帳號池狀態，或登入新帳號以擴充集區。 |
| **配額耗盡 (`RESOURCE_EXHAUSTED` / 429)** | 模型達到個人帳號之每日或每小時呼叫額度限制。 | 分類為 `quota`，當前模型立即中斷，自動容錯切換至備援模型。 | 執行 `gwg status` 與 `gwg usage` 查看用量；待配額重設後重新執行（已快取單元不重複扣額）。 |
| **Telegram `can't parse entities`** | Telegram Bot API 拒絕 HTML 標籤格式（如標籤不對稱或不支援之語法）。 | 自動攔截錯誤並記錄警告，立即調用 `strip_tags()` 剝除 HTML 標籤改以純文字降級重送。 | 自動自我修復，訊息保證送達，維運人員無須處理。 |
| **缺少 Token 或 Chat ID** | 密鑰檔未建立、權限不符或尚未與 Telegram 機器人完成配對。 | 程式拒絕發送並提示設定說明，或擲出 `ConfigError`。 | 透過安全的 `read -rsp` 指令建立 `~/.config/econ-digest/env`（權限 600），並執行 `telegram-setup --test`。 |
| **Telegraph `FLOOD_WAIT_N`** | Telegraph API 觸發頻率限制（例如短時間內發送多個請求，回傳 `FLOOD_WAIT_7`）。 | 自動以正規表示式解析等待秒數，調用 `sleep` 暫停並自動重試（至多重試 5 次）。 | 系統自動退避重試，維運人員無須手動介入。 |
| **缺少或無效的 Telegraph Token** | 密鑰檔未設定 `TELEGRAPH_ACCESS_TOKEN` 或該 Token 遭撤銷/無效。 | 在 `send` 時會嘗試自動呼叫 API 重新建立並寫入；若發生錯誤則中止。 | 執行 `.venv/bin/econ-digest telegraph-setup --force` 強制建立新帳號並更新密鑰。 |
| **Telegraph 頁面超過容量上限** | 單篇內容加上導覽列超出 `page_limit_bytes` 上限（擲出 `ValueError`），或 API 回報內容超過 64 KB（64,000 位元組）。 | 發布前於本機檢驗節點大小，超限時立即中止，避免發布失敗或內容截斷。 | 在 `config.toml` 中調高 `[telegraph] page_limit_bytes`（上限為 64,000；預設 60,000），或調整該篇摘要深度。 |
| **`--pages-only` 於 messages 模式失敗** | 設定檔為 `[telegram] delivery = "messages"` 時執行了 `send --pages-only`。 | 輸出 `--pages-only 僅適用於 Telegraph 模式；請將 telegram.delivery 設為 telegraph。` 並以結束代碼 2 退出。 | 確認 `[telegram] delivery = "telegraph"`；若在 messages 模式下需重新發送訊息，請使用 `--force`。 |
| **封面圖說超出上限 (Caption > 1024)** | 摘要文字長度超過 Telegram 圖說上限（1024 個 UTF-16 單位）。 | 自動先精簡圖說（暫時省略與台灣相關焦點）；若仍超限，封面僅保留期別標題，並將完整摘要作為下一則獨立文字訊息發送。 | 系統全自動自我容錯降級，保證內容完整送達，維運人員無須干預。 |
| **私人 HTML 報告體積較大（約 7–8 MB）** | HTML 報告預設以 Base64 Data URI 完整內嵌封面照片、文章題圖、圖表地圖、合併社論插圖（標註「社論插圖」）與本週漫畫。 | 內嵌於單一 HTML 檔案，離線可直接閱讀，Markdown 報告維持純文字。 | 若需關閉圖片內嵌，可設定 `[report] embed_images = false`；若不欲在 Telegram 附送報告檔案，可設定 `[telegram] send_report_file = false`。 |
| **Telegraph 頁面維持純文字** | Telegraph 頁面為公開網址，基於版權與個人隱私保護，一律不放圖片與英文全文。 | 圖片與英文原文僅於 Telegram 私人聊天室與私人報告檔案流通。 | 正常保護機制，切勿手動將包含全文或插圖之頁面公開散播。 |
| **新聞標籤無國旗設計** | 維持排版清晰與中立，各國新聞均不使用國旗 emoji。 | 摘要使用粗體「與台灣相關」與「•」清單，要聞使用文字標籤「【台灣相關】」，messages 模式使用「T1 · …」標記。 | 正常設計規範，全系統均不使用國旗 emoji。 |
| **執行失敗 (Failed Run)** | 外部網路逾時、來源期別尚未釋出，或模型失敗率高於 30%。 | 每日每期至多發送一次 Telegram 失敗警報（避免洗版）；定時器於下個排程時段自動重試。 | 檢視 `data/logs/econ-digest.log` 查明失敗原因；排除外在問題後可隨時手動重新執行。 |
| **執行鎖已被占用 (`AlreadyRunning`)** | 同一時間已有另一個 `econ-digest` 實例正在執行中。 | 取得非阻塞排他鎖（`fcntl.flock`）失敗時主動優雅退出（exit code 0），避免寫入衝突。 | 此為正常保護機制。若懷疑程序卡死，使用 `ps aux \| grep econ-digest` 確認，超時 3 小時系統會自動終止釋放。 |

---

## 常見問題深度排查

### 1. gwg: User location is not supported

- **詳細成因**：
  在呼叫 Google Gemini 等模型節點時，偶爾會因端點伺服器判定來源 IP 地理位置不在允許區域內，回傳類似以下錯誤：
  ```
  FAILED_PRECONDITION: User location is not supported for the API use.
  ```
  此現象在 2026-10-05 曾在特定 API 節點被觀察到，通常為短暫的路由或判定異常。
- **系統內部行為**：
  LLM 客戶端的 `classify_error()` 函式會精確捕捉 `location` 錯誤，當前模型單元不會盲目進行無謂的重試，而是立即放棄當前模型，無縫切換到設定檔 `[llm.models]` 中定義的下一款備援模型（預設為 `claude-sonnet-4-6`）重新發起分析。
- **維運處置**：
  1. 通常無須採取任何手動措施，管線會在備援模型協助下自動完成本期導讀。
  2. 若想確保主要模型正常，可檢查主機出站網路是否掛載了特定地區的 VPN / Proxy，並執行 `gwg status` 確認帳號區域連線狀態。

---

### 2. gwg exit 75 / no free account

- **詳細成因**：
  當本機安裝之 `gwg` 模型池正在處理其他平行作業，或是帳號池中的免費用戶達到短暫速率上限時，`gwg` 子程序會以結束代碼 `75` 退出。
- **系統內部行為**：
  系統識別為 `no_account` 狀態，自動進入指數退避等待循環（初始等待 30 秒，隨後 60 秒、120 秒遞增），最高在 `no_account_wait_seconds`（預設 900 秒 / 15 分鐘）的等待預算內持續監控並等待釋出帳號。
- **維運處置**：
  1. 若偶爾出現，等待數分鐘即可自動恢復。
  2. 若等待預算用盡導致流程終止，請執行下列指令確認本機帳號池狀態：
     ```sh
     gwg status
     ```
  3. 若帳號已失效，請依 `gwg` 規範重新登入或補充分流帳號。

---

### 3. 模型配額耗盡 (Quota Exhaustion)

- **詳細成因**：
  單一帳號在短時間內發起大量分析請求，收到模型 API 回報 `RESOURCE_EXHAUSTED`、HTTP 429 或 `Individual quota reached`。
- **系統內部行為**：
  `econ-digest` 會將其標記為 `quota` 錯誤，停止當前模型的重試嘗試，立即容錯降級轉移至備援模型繼續處理剩餘的分析批次。
- **維運處置**：
  1. 檢視配額用量：
     ```sh
     gwg usage
     ```
  2. 若全部模型配額皆耗盡，無須擔心資料毀損。只要等到配額重置窗口過後（或隔日），重新執行：
     ```sh
     .venv/bin/econ-digest run
     ```
  3. 由於系統具備**單元級落盤快取（Per-unit caching）**，先前已成功產出並快取的單元絕不會重複呼叫模型，僅會針對未完成的單元發起請求，極大化節省配額。

---

### 4. Telegram: can't parse entities

- **詳細成因**：
  Telegram 對訊息內的 HTML 格式有嚴格限制（如標籤未閉合、字元實體錯誤或不合法的巢狀結構）。若直接發送不符合規格的 HTML，Telegram Bot API 會回傳 HTTP 400：
  ```
  Bad Request: can't parse entities: ...
  ```
- **系統內部行為**：
  `src/econ_digest/telegram/client.py` 封裝了 `send_message_safe()` 防禦函式：
  ```python
  try:
      return self.send_message(chat_id, html, **kw)
  except TelegramError as error:
      if error.status != 400 or "can't parse entities" not in error.description.lower():
          raise
  _LOGGER.warning("Telegram rejected HTML entities; retrying the message as plain text")
  return self.send_message(chat_id, strip_tags(html), ...)
  ```
  一旦遇到實體解析失敗，客戶端會自動以正則表達式剝除所有 HTML 標籤，立即降級為純文字重新發送。
- **維運處置**：
  - 此設計確保 Telegram 推播具備 100% 送達韌性，維運人員無須手動介入處理。

---

### 5. 缺少 Token 或 Chat ID

- **詳細成因**：
  初次部署或設定檔搬移時，未在環境變數或 `~/.config/econ-digest/env` 填入正確之機器人 Token 或私人聊天室 ID。
- **維運處置步驟**：
  1. **建立並儲存 Token**（確保不留存在歷史紀錄中）：
     ```sh
     mkdir -p ~/.config/econ-digest
     read -rsp 'Token: ' T && printf 'TELEGRAM_BOT_TOKEN=%s\n' "$T" > ~/.config/econ-digest/env && chmod 600 ~/.config/econ-digest/env && unset T; echo
     ```
  2. **啟動機器人**：
     開啟 Telegram，找到您的機器人並按下 `/start`。
  3. **自動繫結聊天室並驗證**：
     ```sh
     .venv/bin/econ-digest telegram-setup --test
     ```
     程式會自動解析收到的 `/start` 訊息，將 `TELEGRAM_CHAT_ID` 寫入密鑰檔，並向您的聊天室發送測試成功訊息。

---

### 6. 執行失敗與重試機制 (Failed Run)

- **詳細成因**：
  外部連線中斷（GitHub 無法存取）、當期電子書尚未發布，或模型分析失敗率超過容許門檻（30%）。
- **系統內部行為**：
  1. **失敗警報推送**：系統會向 Telegram 私人聊天室發送警報：
     `⚠️ 本週經濟學人導讀產生失敗（{error_type}），稍後會自動重試。`
  2. **單日防洗版保護**：
     為避免定時器頻繁重試導致手機收到過多干擾訊息，系統在 `state.json` 的 `error_notices` 中記錄發送日期（以 `Asia/Taipei` 日期為準）。同一期別在同一曆日內**最多只會發送一次**失敗通報。
  3. **定時器自動重試**：
     若逢週末，systemd 定時器會在預設的五個時段（週六 07:00、13:00、19:00 及週日 09:00、20:00）依序自動再次執行，自動拾取未完成之進度。
- **維運處置**：
  - 可先透過日誌確認失敗類型。若是外部來源尚未更新，定時器會在稍後時段自動抓取，無須手動處置。
  - 若已手動修復問題，可隨時手動執行 `.venv/bin/econ-digest run` 重新發起作業。

---

### 7. 執行鎖衝突 (Lock already held)

- **詳細成因**：
  當定時器排程已觸發背景工作，維運人員又同時在命令列手動執行 `econ-digest run`，或是前次任務仍在進行中。
- **系統內部行為**：
  系統在 `data/.lock` 上採用 Unix 標準的 `fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)` 非阻塞排他鎖：
  ```python
  with run_lock(config.paths.data_dir):
      ...
  ```
  後進的程序若無法立即取得鎖，會捕捉 `AlreadyRunning` 例外並印出：
  `已有 econ-digest 程序正在執行，本次略過。`
  程式會安全退出（回傳值 0），保證絕對不會發生兩組程序同時寫入同一份報告或重複向 Telegram 發送訊息的競態問題。
- **維運處置**：
  1. `fcntl.flock` 屬於作業系統核心層級的行程鎖。若正在運行的程序異常崩潰或被強制終止（kill），作業系統會**自動釋放**該檔案鎖，無須手動刪除 `.lock` 檔案。
  2. 若懷疑有程序長時間停滯，可確認其運行狀態：
     ```sh
     ps aux | grep econ-digest
     ```
  3. 注意：systemd service 單元已配置 `TimeoutStartSec=3h`，任何持續執行超過 3 小時的失控程序均會被 systemd 自動強制終止，確保系統在下一排程時段可順暢接軌。

---

### 8. Telegraph: FLOOD_WAIT_N

- **詳細成因**：
  在發布或原地編輯多個 Telegraph 分頁時，若短時間內頻繁向 Telegraph API 發起 HTTP 請求，或與其他服務共用同一網路出口，Telegraph API 端點會觸發速率限制保護，回傳如下格式之錯誤代碼：
  ```
  FLOOD_WAIT_N
  ```
  其中 `N` 為整數，代表 Telegraph 伺服器要求發送端需冷卻等待的秒數（例如 `FLOOD_WAIT_5` 代表需等待 5 秒）。
- **系統內部行為**：
  `src/econ_digest/telegraph/client.py` 封裝了安全的重試機制：
  ```python
  flood = re.fullmatch(r"FLOOD_WAIT_(\d+)", error_code)
  if flood and attempt < 5:
      self._sleep(int(flood[1]))
      continue
  ```
  當捕獲 `FLOOD_WAIT_N` 時，客戶端會使用正規表示式精確解析等待秒數，並自動暫停等待（sleep）該秒數後自動發起重試（最多允許重試 5 次）。
- **維運處置**：
  此為系統全自動自我恢復機制，維運人員無須手動干預，程式會在冷卻後自動繼續完成分頁發布與編輯。

---

### 9. 缺少或無效的 Telegraph Access Token

- **詳細成因**：
  1. 初次部署時尚未執行 `telegraph-setup` 建立帳號，且尚未由 `send` 自動產生。
  2. 既有的 `TELEGRAPH_ACCESS_TOKEN` 因人為誤改、檔案毀損或遭到 Telegraph 伺服器端撤銷失效，導致 API 回傳 `Telegraph 帳號缺少存取密鑰` 或存取權限錯誤。
- **系統內部行為**：
  - 在執行 `send` 或完整管線流程時，`src/econ_digest/commands/send.py` 會自動調用 `ensure_account()`：若密鑰檔中完全缺少 `TELEGRAPH_ACCESS_TOKEN`，系統會自動向 Telegraph API 申請建立專屬帳號，並將取得的 Token 自動以權限 `600` 寫入 `~/.config/econ-digest/env`。
  - 但若密鑰檔中已存在 Token，而該 Token 實際上已無效，Telegraph API 在呼叫 `createPage` 或 `editPage` 時會拒絕請求。
- **維運處置**：
  若遇到 Token 無效或欲更換全新 Telegraph 帳號，請執行：
  ```sh
  .venv/bin/econ-digest telegraph-setup --force
  ```
  `--force` 旗標會強制向 Telegraph API 重新註冊帳號，並以原子方式覆蓋更新 `~/.config/econ-digest/env` 內的 `TELEGRAPH_ACCESS_TOKEN`。

---

### 10. Telegraph 頁面超出容量上限 (Page Size Limit)

- **詳細成因**：
  1. Telegraph 官方 API 規範單一頁面內容的 JSON 結構以 UTF-8 編碼後，其大小不可超過 **64 KB（64,000 位元組）**。若超過此限制，Telegraph API 會拒絕請求。
  2. 系統在本地排版時，預設每頁上限為 `page_limit_bytes = 60000`（預留 4,000 位元組供全頁導覽列與換頁按鈕使用）。若某一章節包含極長的文章摘要，導致該「單篇文章」本體加上導覽列後便已超過單頁可用預算，程式為維護文章結構完整性（不隨意腰斬文章或漏失引述欄位），會主動拋出例外：
     ```
     ValueError: <組別>的單篇內容加上導覽超過頁面上限；請提高 telegraph.page_limit_bytes
     ```
- **系統內部行為**：
  - `src/econ_digest/render/telegraph.py` 的 `render_telegraph()` 會在對外發起任何 API 呼叫前，預先精算所有文章節點與導覽列之 UTF-8 JSON 位元組數。若文章過長，會在分配公開頁面網址前立即中止，絕不在公共空間建立空頁或半殘內容。
  - `src/econ_digest/telegraph/publish.py` 也會在發布與原地編輯前再度執行嚴格節點結構與容量校驗。
- **維運處置**：
  1. **調高設定檔中的單頁上限**：
     開啟 `config.toml`，在 `[telegraph]` 區段將 `page_limit_bytes` 適度調高（最高可設為 64,000）：
     ```toml
     [telegraph]
     page_limit_bytes = 63000
     ```
  2. **調整文章摘要深度**：
     若調高至 63,000 ~ 64,000 仍超出上限，代表該篇內容異常龐大。可透過 `config.toml` 的 `[tiers]` 調整該文體或領域之摘要等級（例如由 Tier A 深度解析調整為 Tier B 詳細摘要），並重新執行：
     ```sh
     .venv/bin/econ-digest analyze --issue <期別> --reanalyze
     .venv/bin/econ-digest send --issue <期別> --force
     ```

---

### 11. Telegraph 頁面維護與模式限制 (`send --pages-only`)

- **詳細成因與設計目的**：
  在維運期間，若修改了提示詞、正體字對照表（`glossary.tsv`）或微調了報告文字，通常希望將更新後的內容同步至已發布的 Telegraph 導讀頁面，讓讀者點開 Telegram 既有的 Instant View 連結時能呈現最新修正。然而，此時維運人員**往往不希望**再次向 Telegram 私人聊天室發送整套訊息，避免打擾手機端讀者，亦不希望更動已記錄的傳送進度與狀態。
- **系統內部行為**：
  - `src/econ_digest/commands/send.py` 檢查當前傳送模式：
    ```python
    telegraph = config.telegram.delivery == "telegraph"
    if pages_only and not telegraph:
        log("--pages-only 僅適用於 Telegraph 模式；請將 telegram.delivery 設為 telegraph。")
        return 2
    ```
    若在 `delivery = "messages"` 模式下使用 `--pages-only`，程式會輸出提示並以 exit code 2 拒絕執行。
  - 在 Telegraph 模式下，系統會讀取 `data/issues/te_<期別>/telegraph_pages.json`，對既有的 Telegraph 頁面調用 `publish_pages()` 進行**原地編輯（EDIT）**更新內容。網址維持完全相同，不再使用的多餘頁面會標註「此頁已不再使用」。
  - 處理完成後直接以 exit code 0 退出，**完全不觸碰** `telegram_progress.json` 的傳送進度，亦不修改 `state.json` 的已傳送紀錄（`delivered`），更不會發送任何 Telegram 聊天訊息。
  - 支援與 `--dry-run` 結合使用（`send --pages-only --dry-run`），離線列印各分頁標題與 UTF-8 位元組大小，不發起任何對外連線。
- **維運處置**：
  1. **離線預覽分頁大小**：
     ```sh
     .venv/bin/econ-digest send --pages-only --dry-run
     ```
  2. **原地發布更新**：
     ```sh
     .venv/bin/econ-digest send --pages-only
     ```
     或指定期別：
     ```sh
     .venv/bin/econ-digest send --issue 2026.10.03 --pages-only
     ```
  3. 若欲重新推送整套內容至 Telegram 私人聊天室（包含重新發送封面照片、私訊與報告檔案），請改用：
     ```sh
     .venv/bin/econ-digest send --issue 2026.10.03 --force
     ```
