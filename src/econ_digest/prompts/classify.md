逐篇判斷台灣關聯與分類。等級定義：$levels
注意 1 是台灣本身、2 是台灣與國際、3 是其他國家新聞中有提到台灣或有具體關聯，數字不是重要性排序。先判斷原文是否實質討論台灣：一段敘述、歷史事件、比較、政策或對台灣的政治訊息，都至少為 3，不需要另推測今日對台灣的影響。例：原文明載 1998 年美中元首熱線是在 1996 年台海危機後建立，即為 3，taiwan_link 如實寫這段歷史，不延伸成 AI 危機將如何衝擊台灣。
路過提及台灣（只列在國家清單，或借用台灣研究作其他國家的例子）為 0，但 mentions_taiwan=true。原文沒提台灣時，等級 3 必須有具體且有原文依據的機制：具名政策、台灣的貿易或供應鏈曝險、安全承諾、原文明列的台灣邦交國。不能只因題材是美中關係、晶片、AI、東亞安全或中國經濟就列為 3。泛論「中國影響力擴大，所以台灣受影響」為 0；不能把拉美整體民意當成台灣邦交國的外交決策。
中國／中共針對台灣的政治訊息、宣傳、統戰論述或兩岸身分認同框架（如「兩岸共享文化傳承」、統一言論、對台灣邦交國施壓），即使只占少量篇幅，也實質涉及台灣安全與政治，應為 3；台灣若是主題或主要參與者則依定義為 1 或 2。僅把台灣當例子、資料來源或市場，而未觸及實質台灣議題（如印度占星投資文章引用台灣投資人研究），維持 0 且 mentions_taiwan=true。
分類只能擇一：$categories
每個輸入 id 恰好回傳一次 article_id。taiwan_mention_kind 必填：substantive（實質討論，等級 1–3）、incidental（路過提及，等級 0）、none（未提及）；前兩者 mentions_taiwan=true。凡有提及台灣或判為非零等級，taiwan_evidence 必須逐字摘錄輸入的一個原文句子，供核對依據；其餘為 null。
taiwan_link 在等級 1–3 必須是一句具體正體中文。substantive 如實陳述原文如何談台灣，不加「（推論）」；none 的間接關聯是待查證的暫定判斷，須標記「（推論）」並說明具體機制，不能只說「可能影響台灣」，證據不足才可降為 0。原文實質討論台灣的文章，後續 grounding 不可降為 0。等級 0 為 null。title_zh 用自然的台灣新聞標題，避免逐字翻譯。訊號片段來自全文，開頭只是輔助，不要漏讀訊號。
格式：{"articles":[{"article_id":"a1","taiwan_level":3,"mentions_taiwan":true,"taiwan_mention_kind":"substantive","taiwan_evidence":"The presidential hotline was established in 1998 after the Taiwan Strait crisis of 1996.","taiwan_link":"原文回顧 1996 年台海危機後，美中在 1998 年建立元首熱線。","category":"tech","title_zh":"美盼建AI危機熱線　中國態度冷淡"}]}
文章：$articles
