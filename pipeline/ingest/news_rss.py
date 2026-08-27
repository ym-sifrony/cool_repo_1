"""L0: periodic crawl of a fixed list of news RSS feeds (spec.md's chosen design --
a fixed source list, not a paid general-purpose search API). Fetches article text
only; extraction happens separately in quote_extractor.py.
"""
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "ConceptMapBot/0.1 (civic research project; contact: y.m.sifrony100@gmail.com)"
}
REQUEST_DELAY_SECONDS = 1.0

FEEDS = [
    {"platform": "ynet", "url": "https://www.ynet.co.il/Integration/StoryRss2.xml"},
    {"platform": "walla", "url": "https://rss.walla.co.il/feed/1?type=main"},
    {"platform": "maariv", "url": "https://www.maariv.co.il/rss/rsschadashot"},
    {"platform": "mako", "url": "https://rcs.mako.co.il/rss/news-israel.xml"},
    {"platform": "globes", "url": "https://www.globes.co.il/webservice/rss/rssfeeder.asmx/FeederNode?iID=2"},
    {"platform": "arutz7", "url": "https://www.inn.co.il/Rss.aspx"},
    {"platform": "kikar", "url": "https://www.kikar.co.il/feed"},
    {"platform": "srugim", "url": "https://www.srugim.co.il/feed"},
    {"platform": "jdn", "url": "https://www.jdn.co.il/feed/"},
    {"platform": "bhol", "url": "https://www.bhol.co.il/feed"},
    {"platform": "channel14", "url": "https://www.now14.co.il/feed"},  # articles resolve to c14.co.il
    {"platform": "tovnews", "url": "https://tovnews.co.il/feed"},
    {"platform": "kan", "url": "https://www.kan.org.il/api/newsflash/v2/Newsflash"},
    {"platform": "haokets", "url": "https://haokets.org/feed"},
    # davar1 / mekomit / themarker / kan's own site homepage: all return 403 on
    # a plain GET -- blocked, same rule as makorrishon (don't try to circumvent).
    # makorrishon: feed itself blocks bots (Akamai "Access Denied").
    # israelhayom: feed loads fine, but every article page returns 403 --
    # same rule applies (don't try to circumvent a block).
    # calcalist / themarker / jpost (Hebrew) / haaretz: no working RSS URL found (404s)
    # or blocked outright (403 on the homepage itself for haaretz/themarker) --
    # not pursued further.
    # n12: no distinct feed found (n12.co.il/feed and /rss both serve plain HTML,
    # not XML) -- same parent company/content pool as mako, already covered.
]


@dataclass
class Article:
    title: str
    url: str
    pub_date: str
    platform: str


def fetch_feed(feed: dict) -> list[Article]:
    resp = requests.get(feed["url"], headers=HEADERS, timeout=30)
    resp.raise_for_status()
    content = resp.content
    # kan.org.il's own feed declares encoding="utf-16" in the XML prolog while
    # actually sending UTF-8 bytes -- a real mismatch on their end, not ours.
    # ET respects the declaration and fails to parse, so fix just that string;
    # a no-op for every well-formed feed that doesn't contain it.
    content = content.replace(b'encoding="utf-16"', b'encoding="utf-8"')
    root = ET.fromstring(content)

    articles = []
    for item in root.iterfind(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        if title and link:
            articles.append(Article(title, link, pub_date, feed["platform"]))
    return articles


def fetch_article_text(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    article = soup.find("article") or soup
    return article.get_text(separator="\n", strip=True)


def fetch_all_articles(per_feed_limit: int | None = None) -> list[Article]:
    """per_feed_limit caps articles taken from EACH feed before combining --
    a global slice on the combined list would just take the first feed's
    articles over and over, since feeds are typically much bigger than the cap."""
    articles = []
    for feed in FEEDS:
        try:
            feed_articles = fetch_feed(feed)
        except Exception as exc:  # noqa: BLE001
            print(f"skip feed {feed['platform']}: {exc}")
            continue
        articles.extend(feed_articles[:per_feed_limit] if per_feed_limit else feed_articles)
        time.sleep(REQUEST_DELAY_SECONDS)
    return articles


if __name__ == "__main__":
    for a in fetch_all_articles():
        print(f"[{a.platform}] {a.pub_date} {a.title}  {a.url}")
