替每篇呈現「經濟學人立場」的 leader 文章找到同一期明確討論同一主題的報導，候選報導不含 leader。僅共享「經濟」「中國」等大方向不足以配對；沒有清楚對應就回傳 null。每個 leader id 恰好回傳一次 article_id，每個 companion_id 最多用一次，且須來自候選清單。
格式：{"pairs":[{"article_id":"leader1","companion_id":"article2"},{"article_id":"leader2","companion_id":null}]}
經濟學人立場：$leaders
候選報導：$candidates
