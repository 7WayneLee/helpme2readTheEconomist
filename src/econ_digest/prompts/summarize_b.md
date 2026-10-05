為每篇文章寫 B 級詳細摘要，總計約 600–900 個中文字。每個 article_id 恰好一次。
headline_zh：30–60 個中文字的一個完整自然句子，說出最重要結論，使用一般標點，以「。」結尾，不用全形空格連接子句，須與標題不同；key_points：4–6 項，各 1–2 句；argument：claim 論旨、evidence 2–4 項具體證據、counterpoints 0–2 項原文的反方與回應、conclusion 結論；taiwan_implications：可選，0–3 項。只有原文、提供的台灣事實檔或證據支持具體機制時才寫；否則輸出空清單 []，絕不湊數或強拉台灣關聯。自行推導者標記（推論），仍須有具體依據。
若輸入含 leader，另加 leader_stance，2–3 句，以「作者主張：」開頭，交代經濟學人立場的論點與建議。
格式（陣列僅示意，實際符合數量）：{"articles":[{"article_id":"a1","headline_zh":"重要結論","key_points":["重點"],"argument":{"claim":"論旨","evidence":["證據"],"counterpoints":[],"conclusion":"結論"},"taiwan_implications":["（推論）影響"]}]}
文章：$articles
