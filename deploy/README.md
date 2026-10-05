# 使用者定時器

先在儲存庫建立虛擬環境並安裝指令：

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
```

`gwg` 須可從 `~/.local/bin` 執行；密鑰放在 `~/.config/econ-digest/env`，權限設為 `600`。用 `econ-digest telegram-setup --test` 設定私人聊天室，並先執行 `econ-digest run --no-send` 檢閱報告。

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
