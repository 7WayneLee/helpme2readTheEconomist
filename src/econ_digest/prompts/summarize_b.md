為每篇文章寫 B 級詳細摘要，總計約 600–900 個中文字。每個 article_id 恰好一次。
headline_zh：50 字內最重要結論；key_points：4–6 項，各 1–2 句；argument：claim 論旨、evidence 2–4 項具體證據、counterpoints 0–2 項原文的反方與回應、conclusion 結論；taiwan_implications：1–3 個具體影響，自行推導標記（推論）。若原文與台灣無關，審慎指出可供台灣讀者比較的面向，不強行聲稱直接影響。
若輸入含 leader，另加 leader_stance，2–3 句，以「作者主張：」開頭，交代經濟學人立場的論點與建議。
格式（陣列僅示意，實際符合數量）：{"articles":[{"article_id":"a1","headline_zh":"重要結論","key_points":["重點"],"argument":{"claim":"論旨","evidence":["證據"],"counterpoints":[],"conclusion":"結論"},"taiwan_implications":["（推論）影響"]}]}
文章：$articles
