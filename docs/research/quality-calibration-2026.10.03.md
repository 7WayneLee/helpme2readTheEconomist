# 品質校準紀錄：2026.10.03

校準日期：2026/10/05。使用獨立工作樹中的資料副本，原始資料與傳送紀錄未修改；沒有發送 Telegram 或發布 Telegraph。

最初整期編修一次處理 98 個項目（含標題、一句話重點及要聞），歷經重試後由 Flash 成功完成；另對指定 2 篇提出搜尋詞、抓取中央社證據並查證台灣關聯，再執行事實檔更新檢查。初始呼叫上限為 8 次；協調者因前三次無效呼叫授權最多再加 4 次，實際次數見下表。

正式設計依實測修正為每批至多 20 個項目、15,000 UTF-8 位元組，依 max_parallel 平行執行；edit 與 ground（含搜尋詞）逾時預設 600 秒，其餘仍為 300 秒。下列 10 篇另以正式批次大小校準，模型為 claude-opus-4-6-thinking，實際提示詞 13,944 位元組。

## 10 篇標題前後比較

| 英文標題 | 編修前 | 驗證後採用 |
| --- | --- | --- |
| In an AI crisis, would China answer the phone? | 人工智慧危機爆發時中國會接熱線嗎？美中軍事應變機制存隱憂 | 美盼建AI危機熱線　中國態度冷淡恐難成局 |
| For the first time Latin Americans prefer China to America | 民調顯示拉美民眾對中國好感首度超越美國，美中區域影響力面臨消長 | 民調：拉美民眾對中國好感首度超越美國 |
| Can Jesus Christ sell moderates on Democrats? | 川普基督徒基本盤現裂痕，民主黨牧師參選人主打溫和信仰搶票 | 川普基督徒基本盤現裂痕　民主黨牧師主打溫和信仰搶票 |
| Bond markets whack France for fiscal irresponsibility | 財政赤字與政局動盪引發債市拋售，法國公債殖利率攀升創 2008 年新高 | 法國財政赤字與政局動盪　公債殖利率創2008年來新高 |
| Xi Jinping uses old festivals to boost the party’s image | 習近平借傳統節慶強化中共形象：中秋文化包裝下的政治宣傳與對台統戰 | 習近平借傳統節慶宣傳　強化中共文化統戰形象 |
| Japan’s tea farmers enjoy a matcha boom | 全球抹茶熱潮助日本茶農翻身：鹿兒島產量躍居第一與中國競爭威脅 | 全球瘋抹茶帶動增產　日本茶農迎中國低價競爭 |
| Finland has a fix for nuclear waste | 芬蘭啟用全球首座深層核廢料處置場，封存地底十萬年解能源難題 | 芬蘭啟用首座深層處置場　封存核廢料10萬年 |
| Abolish the White House press corps | 白宮記者團體制過時？專欄主張藉川普打壓契機推動採訪改革 | 經濟學人專欄：白宮記者團體制過時　應推採訪改革 |
| How will AI philanthropy change development aid? | 人工智慧新貴跨足國際慈善，能否為全球發展援助開創新局？ | AI新貴跨足國際慈善　全球援助體系迎新資金 |
| Authoritarians have a secret Achilles heel: City Hall | 市政廳成抵禦威權堡壘：地方首長在民主政治中的關鍵防線 | 地方首長守民主防線　市政廳成抵禦威權堡壘 |

最後查證輸出一度因歷史台海危機把 AI 專線文章升為 T1；外部證據不能改變原文主題，程式依原始 T3 的直接參與上限保留 T3。編修另修正瘋、晤、推等一般新聞動詞的誤拒，陌生人名與新增數字仍退回。

驗證後採用 67 篇改寫標題；3 篇模型建議未通過驗證，保留原標題。驗證以字數、標點、數字與名稱為界；語意忠實另由編修提示約束，陌生名稱字元採保守退回。

## 台灣關聯查證

### In an AI crisis, would China answer the phone?

原等級 T3 → 最終 T3；分類摘要深度 C，已寫摘要保留 C 深度。

文章明確指出1998年美中總統熱線係因1996年中國向台灣附近水域發射飛彈、美方派遣兩艘航母應對的台海危機而建立，台灣為此一危機溝通機制的歷史起點。

- （推論）文章揭示中方在歷次危機中拒接或拖延回應熱線的慣性模式；鑑於該熱線源自台海危機，且中國2025至2026年間持續以環台軍演及灰色地帶行動對台施壓，美中AI危機溝通管道能否有效運作，直接攸關台海突發事態的升級管控。（依據：article, facts）

意涵使用完整 [台灣事實檔](../../src/econ_digest/facts/taiwan.md)；其軍演與灰色地帶現況列有 [中央社 2025/12/29 環台軍演報導](https://www.cna.com.tw/news/acn/202512290029.aspx)、[中央社 2026/02/01 海警巡查報導](https://www.cna.com.tw/news/aipl/202602010035.aspx) 作為具體出處。此版沒有採用學者意見作為現況證明，Digest 的 sources 不勉強填入未被採用的取證。

另查得中央社資料（本次沒有採為直接關聯的依據）：

- [中央社 2024-05-25〈中國若封鎖台灣 彭博估全球經濟損失160兆元〉](https://www.cna.com.tw/news/aipl/202405253001.aspx)
- [中央社 2026-05-12〈川習會在即 中國學者：川普很多問題有求於中國〉](https://www.cna.com.tw/news/acn/202605120198.aspx)

搜尋詞：台灣 美中軍事熱線 危機溝通、台海 AI 軍事風險、台灣 美中元首會晤。

### For the first time Latin Americans prefer China to America

原等級 T3 → 最終 0（一般分類）；分類摘要深度 E，已寫摘要保留 C 深度。

沒有保留可證明的台灣關聯，移回原類別；對台灣的意涵未強行補寫。

另查得中央社資料（本次沒有採為直接關聯的依據）：

- [中央社 2026-07-24〈拉美暨加勒比海經貿辦事處成立 林佳龍：互利共榮〉](https://www.cna.com.tw/news/aipl/202607240313.aspx)
- [中央社 2026-03-19〈北京拉攏巴拉圭政界促外交轉向 美力挺巴台夥伴關係〉](https://www.cna.com.tw/news/aipl/202603190017.aspx)
- [中央社 2026-06-24〈台北國際食品展登場 拉美館集結友邦美食促雙邊合作〉](https://www.cna.com.tw/news/aipl/202606240213.aspx)

搜尋詞：台灣 拉美 邦交國 中國、巴拉圭 瓜地馬拉 台灣 邦交、拉美 中國影響力 台灣友邦。

拉美整體好感度民調不足以證明個別台灣友邦會調整外交政策；即使另有巴拉圭受北京拉攏的報導，也不能把兩者直接串成因果。

**拉美文章是否仍為 T3：否。**

## 事實檔提醒

本次所取中央社短摘錄未找到足以提出更新提醒的新證據，fact_alerts 為空；這不代表逐項事實都已獨立證實。

中央社取證連線錯誤：0 次。證據只存短摘錄於忽略的 data/research/，此紀錄不收錄原文段落。

前三次均沒有可用 JSON（前兩次 Opus 回應為空，第三次 Flash 回應也沒有 JSON）；第四次 Flash 才通過驗證。未確認 gwg 回應欄位解析錯誤，因此沒有修改 llm/gwg.py。前兩次 gwg 未回報 Token 或有效時長，以下以未回報標示，秒數為快取目錄建立及收據時間推算的約值。

## 每次模型呼叫

| 次數 | 階段 | 模型 | Token | 秒數 | 傳輸結果 |
| --- | --- | --- | ---: | ---: | --- |
| 1 | edit | claude-opus-4-6-thinking | 未回報（gwg=0） | 309.39 | invalid_output（空回應，時長約值） |
| 2 | edit | claude-opus-4-6-thinking | 未回報（gwg=0） | 317.85 | invalid_output（空回應，時長約值） |
| 3 | edit | gemini-3.8-flash-high | 88,900 | 154.38 | invalid_output（沒有 JSON） |
| 4 | edit | gemini-3.8-flash-high | 89,223 | 177.15 | success |
| 5 | ground_queries | claude-opus-4-6-thinking | 8,462 | 8.57 | success |
| 6 | ground | claude-opus-4-6-thinking | 21,271 | 99.61 | success |
| 7 | facts | claude-opus-4-6-thinking | 32,844 | 59.51 | success |
| 8 | edit | claude-opus-4-6-thinking | 29,254 | 290.15 | success |
| 9 | ground | claude-opus-4-6-thinking | 33,361 | 139.07 | success |

合計 9 次，303,315 Token、928.44 秒已回報的模型傳輸時間（不含中央社取證與前兩次未回報時長；前兩次另約 627 秒）。

## 驗證

`.venv/bin/python -m pytest -q`：859 passed、1 skipped；測試禁止 HTTP/HTTPS 與實際 gwg 呼叫，使用合成資料及假 opener。

Python 3.11 以上、僅標準函式庫；資料副本、新聞摘錄、快取與產出均未加入版本控制。來源模型欄位支援舊 digest，私人網站、單檔 HTML、Markdown 與 Telegraph 在台灣陳述下方顯示至多 3 筆連結，Telegram 摘要不加來源列，事實提醒只送私訊。
