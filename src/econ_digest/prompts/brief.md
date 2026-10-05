輸入 politics 與 business 的每個段落各是一則新聞。各清單須原順序一對一回傳，不能合併、拆分或遺漏。text_zh：一句、80 個中文字內，保留重要人名、數字、地點；taiwan_related：涉及台灣或直接影響台灣才為 true。不要因只是全球新聞就勉強標記。
格式：{"politics":[{"text_zh":"一則政治新聞。","taiwan_related":false}],"business":[{"text_zh":"一則商業新聞。","taiwan_related":true}]}
新聞段落：$items
