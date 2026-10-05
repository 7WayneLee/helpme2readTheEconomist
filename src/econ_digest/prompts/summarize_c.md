為每篇文章寫 C 級重點摘要，總計約 250–400 個中文字。每個 article_id 恰好一次。headline_zh：50 字內最重要結論；key_points：3–5 項，保留原文重要事實、因果與立場，避免空泛。
若輸入含 leader，另加 leader_stance，2–3 句，以「社論主張：」開頭，交代其論點與建議。
格式（陣列僅示意，實際符合數量）：{"articles":[{"article_id":"a1","headline_zh":"重要結論","key_points":["重點一","重點二","重點三"]}]}
文章：$articles
