# 維運與故障排除指南 (Operations and Troubleshooting)

本文件提供 `econ-digest` 每週導讀系統的日常維運、狀態檢查、手動介入方式與常見問題排查指南。

---

## 目錄

- [日常維運](#日常維運)
  - [日誌位置與檢視方式](#日誌位置與檢視方式)
  - [檢查定時器與服務狀態](#檢查定時器與服務狀態)
  - [手動觸發與重新發送](#手動觸發與重新發送)
  - [重設單期快取](#重設單期快取)
- [問題排查速查表](#問題排查速查表)
- [常見問題深度排查](#常見問題深度排查)
  - [1. gwg: User location is not supported](#1-gwg-user-location-is-not-supported)
  - [2. gwg exit 75 / no free account](#2-gwg-exit-75--no-free-account)
  - [3. 模型配額耗盡 (Quota Exhaustion)](#3-模型配額耗盡-quota-exhaustion)
  - [4. Telegram: can't parse entities](#4-telegram-cant-parse-entities)
  - [5. 缺少 Token 或 Chat ID](#5-缺少-token-或-chat-id)
  - [6. 執行失敗與重試機制 (Failed Run)](#6-執行失敗與重試機制-failed-run)
  - [7. 執行鎖衝突 (Lock already held)](#7-執行鎖衝突-lock-already-held)

---

## 日常維運

### 日誌位置與檢視方式

系統提供兩種層級的日誌輸出：應用程式專屬滾動檔案日誌與 systemd 使用者單元日誌。

#### 1. 應用程式檔案日誌
- **預設路徑**：`data/logs/econ-digest.log`
- **輪替機制**：單一檔案大小上限為 2 MB，自動保留最近 3 份歷史輪替檔案（`econ-digest.log.1`、`.2`、`.3`）。
- **隱私安全**：所有敏感憑證（包括 `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`、`GITHUB_TOKEN` 以及 Telegram API URL 中的 Bot Token）在寫入日誌時均會自動遮蔽為 `[已隱藏]`。
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

#### 接續中斷的傳送（斷點續傳）
若推送至 Telegram 期間網路斷線或發生暫時性錯誤，直接再次執行 `send` 指令即可：
```sh
.venv/bin/econ-digest send
```
系統會自動讀取 `data/issues/te_<期別>/telegram_progress.json` 中的進度指標（`next_message`），自動跳過已發送之訊息與附件，接續傳送剩餘內容。

#### 重新發送已完成期別
若某期先前已發送完畢（已記錄於 `state.json` 的 `delivered` 中），系統預設會略過以避免干擾。若需強制重新發送全部內容：
```sh
# 重新發送最新一期
.venv/bin/econ-digest send --force

# 或重新發送特定期別
.venv/bin/econ-digest send --issue 2026.10.03 --force
```

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

## 問題排查速查表

| 現象或錯誤代碼 | 常見原因 | 系統預設處理機制 | 建議處置方式 |
| :--- | :--- | :--- | :--- |
| **`User location is not supported`** | 模型 API 節點暫時性地理位置限制（2026-10-05 曾於部分節點短暫出現）。 | 分類為 `location` 錯誤，當前模型立即中斷，自動切換至下一備援模型（如 `claude-sonnet-4-6`）。 | 檢查網路出口或代理設定；多數情況由備援模型接手即可順暢完成，無須手動干預。 |
| **`gwg exit 75` / `no free account`** | `gwg` 帳號池中所有可用帳號皆處於忙碌或暫時冷卻狀態。 | 分類為 `no_account`，以指數退避（30s、60s、120s…）自動等待至多 `no_account_wait_seconds`（預設 900 秒）。 | 若等待超時，執行 `gwg status` 檢查帳號池狀態，或登入新帳號以擴充集區。 |
| **配額耗盡 (`RESOURCE_EXHAUSTED` / 429)** | 模型達到個人帳號之每日或每小時呼叫額度限制。 | 分類為 `quota`，當前模型立即中斷，自動容錯切換至備援模型。 | 執行 `gwg status` 與 `gwg usage` 查看用量；待配額重設後重新執行（已快取單元不重複扣額）。 |
| **Telegram `can't parse entities`** | Telegram Bot API 拒絕 HTML 標籤格式（如標籤不對稱或不支援之語法）。 | 自動攔截錯誤並記錄警告，立即調用 `strip_tags()` 剝除 HTML 標籤改以純文字降級重送。 | 自動自我修復，訊息保證送達，維運人員無須處理。 |
| **缺少 Token 或 Chat ID** | 密鑰檔未建立、權限不符或尚未與 Telegram 機器人完成配對。 | 程式拒絕發送並提示設定說明，或擲出 `ConfigError`。 | 透過安全的 `read -rsp` 指令建立 `~/.config/econ-digest/env`（權限 600），並執行 `telegram-setup --test`。 |
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
