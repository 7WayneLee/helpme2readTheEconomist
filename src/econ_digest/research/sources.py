"""The explicitly approved evidence source registry."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Site:
    key: str
    outlet: str
    url: str
    rss: str = ''


DOMESTIC = (
    Site('pts', '公視', 'https://news.pts.org.tw/search/{query}', 'https://news.pts.org.tw/xml/newsfeed.xml'),
    Site('udn', '聯合', 'https://udn.com/search/word/2/{query}', 'https://udn.com/rssfeed/news/2/6638?ch=news'),
    Site('ltn', '自由', 'https://search.ltn.com.tw/list?keyword={query}', 'https://news.ltn.com.tw/rss/politics.xml'),
)
INTERNATIONAL = (
    Site('bbc_asia', 'BBC', 'https://feeds.bbci.co.uk/news/world/asia/rss.xml'),
    Site('bbc_zh', 'BBC 中文', 'https://feeds.bbci.co.uk/zhongwen/trad/rss.xml'),
    Site('dw', 'DW 中文', 'https://rss.dw.com/rdf/rss-chi-all'),
    Site('rfi', 'RFI 中文', 'https://www.rfi.fr/cn/rss'),
    Site('guardian', 'The Guardian', 'https://www.theguardian.com/world/taiwan/rss'),
)
GOVERNMENT = (
    Site('mofa', '外交部', 'https://www.mofa.gov.tw/News.aspx?n=95&sms=73'),
    Site('mnd', '國防部', 'https://www.mnd.gov.tw/news/pressreleaselist'),
    Site('mnd', '國防部', 'https://www.mnd.gov.tw/news/plaactlist'),
    Site('president', '總統府', 'https://www.president.gov.tw/Page/35'),
    Site('ey', '行政院', 'https://www.ey.gov.tw/Page/6485009ABEC1CB9C'),
    Site('dgbas', '主計總處', 'https://www.stat.gov.tw/News.aspx?n=3703&sms=10980'),
    Site('cec', '中選會', 'https://www.cec.gov.tw/central'),
)
CNA_RSS = 'https://feeds.feedburner.com/rsscna/politics'
