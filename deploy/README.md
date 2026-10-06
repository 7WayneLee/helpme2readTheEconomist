# 使用者定時器

先在儲存庫建立虛擬環境並安裝指令：

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
```

`gwg` 須可從 `~/.local/bin` 執行；密鑰放在 `~/.config/econ-digest/env`，權限設為 `600`。用 `econ-digest telegram-setup --test` 設定私人聊天室，並先執行 `econ-digest run --no-send` 檢閱報告。

可先只產生單元檔並驗證；這個模式不會呼叫 `systemctl` 或安裝定時器：

```sh
deploy/install-user-timer.sh --print-units data/systemd-preview
systemd-analyze --user verify data/systemd-preview/econ-digest.service data/systemd-preview/econ-digest.timer
```

使用者核准後，在要長期保留的儲存庫路徑執行：

```sh
deploy/install-user-timer.sh
systemctl --user list-timers econ-digest.timer
journalctl --user -u econ-digest.service
```

排程依台北時間在週六 07:00、13:00、19:00 與週日 09:00、20:00 檢查新一期；每次隨機延遲至多十分鐘，已傳送的期別會自動略過。錯過的排程會在下次登入時補跑；單次流程上限三小時。

未啟用 lingering 時，使用者定時器只在登入期間運作；`loginctl enable-linger "$USER"` 可讓使用者管理程序在登出後繼續運作。安裝程式不會修改 lingering 設定。

移除定時器：

```sh
deploy/install-user-timer.sh --uninstall
```

若移動儲存庫，請從新路徑重新執行安裝程式，以更新服務內的絕對路徑。每則 Telegram 訊息與附件完成後會記錄進度；一般失敗可直接再次執行 `econ-digest send` 接續傳送，`--force` 會從頭重新傳送。

## Threads 定時器（選用）

帳號、Meta Tester 與長期權杖設定見[維運手冊](../docs/operations.md#threads-文章排程)。先使用 `social threads preview` 與 `post-next --dry-run` 離線檢閱；預設 `social.threads.enabled = false`，安裝定時器本身不會啟用發文。

```sh
deploy/install-threads-timer.sh --print-units data/systemd-threads-preview
systemd-analyze --user verify data/systemd-threads-preview/econ-digest-threads.service data/systemd-threads-preview/econ-digest-threads.timer
deploy/install-threads-timer.sh
systemctl --user list-timers econ-digest-threads.timer
journalctl --user -u econ-digest-threads.service
```

第一次在使用者管理程序啟動約兩分鐘後喚醒，之後每次服務結束再等待設定的 `interval_minutes`；只有時段、每日上限、最短間隔及 Threads API 額度都通過才發布至多一則。修改發文間隔或移動儲存庫後，重新執行安裝程式。自訂設定可加 `--config /absolute/path/config.toml`，並將同一路徑寫入服務。此服務不呼叫 gwg。

```sh
.venv/bin/econ-digest social threads pause
systemctl --user disable --now econ-digest-threads.timer
.venv/bin/econ-digest social threads resume
systemctl --user enable --now econ-digest-threads.timer
deploy/install-threads-timer.sh --uninstall
```

服務使用 `UMask=0077`；env 與刷新權杖各自要求 mode 600。登入與 lingering 行為同上方每週導讀定時器。所有容器、貼文與時間紀錄保留在 `data/social/`，不以重新安裝或再次加入佇列的方式重置。
