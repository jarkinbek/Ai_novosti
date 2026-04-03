import os
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN        = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "YOUR_ANTHROPIC_API_KEY_HERE")

# ── RSS Feeds (в основном русскоязычные) ──────────────────────────────────────
RSS_FEEDS = {
    "politics": [
        "https://rsshub.app/sputniknews/kz/ru",          # Sputnik Казахстан (RU)
        "https://rsshub.app/sputniknews/kg/ru",          # Sputnik Кыргызстан (RU)
        "https://rss.dw.com/rdf/rss-ru-all",             # Deutsche Welle RU
        "https://feeds.bbci.co.uk/russian/rss.xml",      # BBC Русская служба
        "https://www.aljazeera.com/xml/rss/all.xml",     # Al Jazeera
    ],
    "economy": [
        "https://rsshub.app/sputniknews/kz/ru",
        "https://rss.dw.com/rdf/rss-ru-eko",             # DW экономика RU
        "https://feeds.bbci.co.uk/news/business/rss.xml",
        "https://feeds.reuters.com/reuters/businessNews",
    ],
    "world": [
        "https://feeds.bbci.co.uk/russian/rss.xml",
        "https://rss.dw.com/rdf/rss-ru-all",
        "https://rsshub.app/sputniknews/kg/ru",
        "https://feeds.reuters.com/reuters/worldNews",
    ],
    "asia": [
        "https://sputniknews.uz/export/rss2/archive/index.xml",
        "https://sputnik.kz/export/rss2/archive/index.xml",
        "https://sputnik.kg/export/rss2/archive/index.xml",
        "https://sputnik.tj/export/rss2/archive/index.xml",
        "https://feeds.bbci.co.uk/news/world/asia/rss.xml",
        "https://rss.dw.com/rdf/rss-ru-all",
    ],
    "europe": [
        "https://rss.dw.com/rdf/rss-ru-all",
        "https://feeds.bbci.co.uk/russian/rss.xml",
        "https://feeds.bbci.co.uk/news/world/europe/rss.xml",
        "https://feeds.reuters.com/reuters/worldNews",
    ],
    "usa": [
        "https://feeds.bbci.co.uk/russian/rss.xml",
        "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml",
        "https://rss.dw.com/rdf/rss-ru-all",
        "https://feeds.reuters.com/reuters/worldNews",
    ],
}