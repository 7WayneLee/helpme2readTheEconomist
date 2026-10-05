為程度「$level」的讀者製作讀前與精讀指南，英文引文逐字取自下列文章。
cefr：文章難度 A2/B1/B2/C1/C2。
pre_reading_zh：150–250 個中文字，補背景並提示閱讀時觀察 2–3 件事，不揭露結論。
vocabulary：恰好 $vocab_count 個實用 B2–C1 單字，不含專有名詞。word 使用字典原形（lemma），動詞用原形、名詞用單數，例如 shunned→shun、collided→collide；pos 僅 n./v./adj./adv./phr.；meaning_zh 是此處詞義；example_en 是包含原形或其變化形的原文句子，逐字複製，超過 40 個字可用 … 刪節至 40 字以內，勿改寫；note_zh 說明搭配詞、近義詞或用法，原文詞形與 word 不同時須明確註記，例如「原文為過去式 shunned」或「原文為過去式 went」。
phrases：恰好 $phrase_count 個慣用語、片語動詞或搭配詞，phrase 使用原文形式，meaning_zh 解釋，example_en 包含該片語且逐字取自原文，至多 40 字（可用 … 刪節）。不重複詞項。
sentences：2–3 個最難的完整原文句子，sentence_en 逐字；breakdown_zh 拆解主句、修飾語、插入子句；translation_zh 忠實翻譯。
writing_notes_zh：1–2 點本文寫作技巧，如標題雙關、反諷、隱喻、結構，必須有原文依據。
quiz：恰好 3 題英文理解問題 question，answer 用正體中文並引用「第 3 段」等實際段落號碼。
不要輸出 word_count 或 reading_minutes，程式會計算。
格式（陣列僅示意，實際符合數量）：{"cefr":"B2","pre_reading_zh":"背景與觀察提示","vocabulary":[{"word":"resolve","pos":"n.","meaning_zh":"決心","example_en":"verbatim sentence containing resolve","note_zh":"常見搭配"}],"phrases":[{"phrase":"in turn","meaning_zh":"進而","example_en":"verbatim example containing in turn"}],"sentences":[{"sentence_en":"verbatim sentence","breakdown_zh":"主句與修飾語","translation_zh":"忠實翻譯"}],"writing_notes_zh":["寫作技巧"],"quiz":[{"question":"What is the main concern?","answer":"第 3 段指出……"}]}
文章：$article
