為每篇文章寫 A 級深度解析，總計約 1,200–2,000 個中文字，不計英文引文。每個 article_id 恰好一次。欄位：
headline_zh：50 字內，最重要的一個結論。
background：150–250 字，為何此刻報導、原文依賴的背景。
structure：4–8 項，照段落順序，每項以「第 1–2 段：」等有效段落範圍開頭，呈現文章推進。
argument：claim 論旨；evidence 3–6 項，每項含具體資料或例子；counterpoints 1–3 項，說明原文提及的反方意見及回應。原文未提反方時，明說未提，並補最明顯的反對理由，標記（編者補充）；conclusion 結論。
key_data：3–6 個原文明載的數字及單位；資料不足時可使用原文明載日期、票數、人數，絕不可補造。
quotes：2–4 個承載論旨或生動的英文句子／片語，en 必須逐字出現在原文，zh 忠實翻譯。
stance：100–200 字，以「立場分析：」明確標示，分析《經濟學人》的立場、觀察角度、可能淡化的面向。
taiwan_implications：2–4 個具體影響（安全、經濟、外交、社會），自行推導者標記（推論）。若原文與台灣無關，審慎指出可供台灣讀者比較的面向，不強行聲稱直接影響。
further_questions：1–2 個讀者可追問的問題。
若輸入含 leader，另外輸出 leader_stance，2–3 句，以「作者主張：」開頭，交代經濟學人立場的論點與建議；其餘欄位仍聚焦主報導。
格式（陣列省略部分示意，實際須符合上述數量）：{"articles":[{"article_id":"a1","headline_zh":"最重要的結論","background":"背景","structure":["第 1–2 段：開場"],"argument":{"claim":"論旨","evidence":["具體證據"],"counterpoints":["反方與回應"],"conclusion":"結論"},"key_data":["原文數字與單位"],"quotes":[{"en":"verbatim source phrase","zh":"忠實譯文"}],"stance":"立場分析：分析","taiwan_implications":["（推論）具體影響"],"further_questions":["追問？"]}]}
文章：$articles
