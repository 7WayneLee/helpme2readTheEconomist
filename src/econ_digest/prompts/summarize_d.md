為每篇文章寫 D 級簡要摘要。每個 article_id 恰好一次。headline_zh：50 字內最重要結論；summary_zh：2–3 句、80–150 個中文字，說明事件、關鍵原因與結果，保留重要名稱及數字。輸入只有開頭約 600 字及末段，勿編造中間內容。
若輸入含 leader，另加 leader_stance，2–3 句，以「社論主張：」開頭，交代其論點與建議。
格式：{"articles":[{"article_id":"a1","headline_zh":"重要結論","summary_zh":"第一句交代事件與原因。第二句交代結果或文章的論點。"}]}
文章：$articles
