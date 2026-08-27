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
    root = ET.fromstring(resp.content)

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


def fetch_all_articles() -> list[Article]:
    articles = []
    for feed in FEEDS:
        articles.extend(fetch_feed(feed))
        time.sleep(REQUEST_DELAY_SECONDS)
    return articles


if __name__ == "__main__":
    for a in fetch_all_articles():
        print(f"[{a.platform}] {a.pub_date} {a.title}  {a.url}")
