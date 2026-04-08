#!/usr/bin/env python3
"""
GODSEYE Live Data Pipeline v3
==============================
Fetches prices, Polymarket markets, news, and generates:
  - Trading signals (BUY/SELL with entry price, expected % move)
  - Polymarket signals (divergence from MiroFish probabilities)

Data sources (all free, no API keys):
  - Yahoo Finance (unofficial v8 chart API)
  - FreeGoldAPI.com (daily gold spot)
  - Polymarket Gamma API (prediction markets)
  - RSS feeds (Reuters, AP, BBC, Al Jazeera, CNBC, MarketWatch, etc.)

Output: data/live_data.json — consumed by index.html on GitHub Pages
Run:    python3 fetch_live_data.py
Auto:   GitHub Actions cron every 30 min
"""

import json
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import os
import re
import sys
import math

# ── OUTPUT ───────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "data", "live_data.json")

TIMEOUT = 15  # seconds per HTTP request

# ── INSTRUMENTS ──────────────────────────────────────────────────────────────
# Tradable instruments (generate BUY/SELL signals)
TRADABLE = {
    "XAUUSD":  {"yahoo": "GC=F",     "label": "Gold",      "dec": 2, "prefix": "$", "atr_pct": 1.5},
    "WTI":     {"yahoo": "CL=F",     "label": "WTI Crude", "dec": 2, "prefix": "$", "atr_pct": 3.0},
    "SPX":     {"yahoo": "^GSPC",    "label": "S&P 500",   "dec": 2, "prefix": "",  "atr_pct": 1.2},
    "NASDAQ":  {"yahoo": "^IXIC",    "label": "NASDAQ",    "dec": 2, "prefix": "",  "atr_pct": 1.8},
    "BTC":     {"yahoo": "BTC-USD",  "label": "Bitcoin",   "dec": 0, "prefix": "$", "atr_pct": 4.0},
    "ETH":     {"yahoo": "ETH-USD",  "label": "Ethereum",  "dec": 2, "prefix": "$", "atr_pct": 5.0},
}

# Barometer instruments (display only, no trading signals)
BAROMETERS = {
    "DXY":     {"yahoo": "DX-Y.NYB", "label": "Dollar Index", "dec": 3, "prefix": ""},
    "VIX":     {"yahoo": "^VIX",     "label": "VIX",          "dec": 2, "prefix": ""},
    "10Y":     {"yahoo": "^TNX",     "label": "10Y Yield",    "dec": 2, "prefix": ""},
    "DOW":     {"yahoo": "^DJI",     "label": "Dow Jones",    "dec": 2, "prefix": ""},
}

ALL_SYMBOLS = {}
ALL_SYMBOLS.update({k: v["yahoo"] for k, v in TRADABLE.items()})
ALL_SYMBOLS.update({k: v["yahoo"] for k, v in BAROMETERS.items()})

# ── POLYMARKET ───────────────────────────────────────────────────────────────
POLY_SEARCH_TERMS = [
    "iran", "hormuz", "oil", "crude", "russia", "ukraine", "nato",
    "ceasefire", "taiwan", "china", "north korea", "nuclear",
    "election", "senate", "republican", "democrat",
    "gold", "bullion", "S&P", "stock market", "recession", "nasdaq",
    "Fed", "interest rate", "inflation", "tariff", "rate cut",
    "dollar", "DXY", "bitcoin", "ethereum", "crypto",
    "opec", "brent", "natural gas",
]

POLY_RELEVANT_KEYWORDS = [
    "iran", "hormuz", "strait", "oil", "brent", "crude", "opec",
    "nuclear", "trump", "persian gulf", "sanctions",
    "russia", "ukraine", "nato", "kyiv", "moscow", "ceasefire",
    "taiwan", "china", "pla", "tsmc", "semiconductor",
    "north korea", "kim jong", "icbm",
    "election", "senate", "republican", "democrat", "midterm",
    "gold", "bullion", "s&p", "spx", "stock market", "dow", "nasdaq",
    "recession", "bear market", "fed", "interest rate", "rate cut",
    "inflation", "cpi", "tariff", "trade war",
    "dollar", "dxy", "bitcoin", "btc", "ethereum", "crypto",
]

# ── NEWS ─────────────────────────────────────────────────────────────────────
NEWS_FEEDS = [
    {"name": "Reuters Business",   "url": "https://feeds.reuters.com/reuters/businessNews"},
    {"name": "Reuters World",      "url": "https://feeds.reuters.com/Reuters/worldNews"},
    {"name": "AP Top News",        "url": "https://feeds.feedburner.com/associatedpress/APRS"},
    {"name": "BBC World",          "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
    {"name": "Al Jazeera",         "url": "https://www.aljazeera.com/xml/rss/all.xml"},
    {"name": "CNBC Markets",       "url": "https://www.cnbc.com/id/15839069/device/rss/rss.html"},
    {"name": "CNBC Economy",       "url": "https://www.cnbc.com/id/20910258/device/rss/rss.html"},
    {"name": "MarketWatch",        "url": "https://feeds.marketwatch.com/marketwatch/topstories/"},
    {"name": "Yahoo Finance News", "url": "https://finance.yahoo.com/news/rssindex"},
    {"name": "Investing.com",      "url": "https://www.investing.com/rss/news.rss"},
]

GLOBAL_NEWS_KEYWORDS = [
    # Geopolitics / Middle East
    "iran", "hormuz", "strait", "persian gulf", "tehran", "escalat",
    "sanctions", "ceasefire", "nuclear", "tanker", "middle east",
    "israel", "gaza", "hezbollah", "hamas", "red sea", "houthi",
    # Russia / Ukraine / NATO
    "russia", "ukraine", "nato", "kyiv", "moscow", "putin", "zelensky",
    "missile strike", "drone attack", "war",
    # Asia / Taiwan / China
    "taiwan", "china", "pla", "tsmc", "south china sea", "xi jinping",
    "north korea", "kim jong", "icbm", "hypersonic",
    # US Politics / Policy
    "trump", "biden", "election", "senate", "congress", "white house",
    "executive order", "tariff", "trade war", "trade deal",
    # Interest Rates / Fed / Macro
    "federal reserve", "fed rate", "interest rate", "rate cut", "rate hike",
    "fomc", "jerome powell", "basis point", "yield curve",
    "inflation", "cpi", "pce", "core inflation", "deflation",
    "gdp", "recession", "soft landing", "hard landing", "stagflation",
    "unemployment", "jobs report", "nonfarm payroll",
    # Oil / Energy
    "oil price", "crude", "brent", "wti", "opec", "natural gas",
    "energy crisis", "pipeline", "refinery",
    # Gold / XAUUSD
    "gold price", "bullion", "precious metal", "safe haven", "gold rally",
    "central bank gold", "gold reserves",
    # Equities / US500 / NAS100
    "stock market", "s&p 500", "s&p500", "us500", "wall street",
    "dow jones", "nasdaq", "nas100", "qqq", "russell 2000",
    "earnings", "earnings beat", "earnings miss", "guidance",
    "bear market", "bull market", "market crash", "correction",
    "volatility", "vix", "risk off", "risk on",
    # DXY / Dollar / FX
    "dollar index", "dxy", "us dollar", "dollar strength", "dollar weakness",
    "euro", "yen", "gbp", "forex", "currency",
    # Crypto
    "bitcoin", "ethereum", "crypto", "btc", "blackrock etf",
    "strategic reserve", "coinbase", "crypto regulation",
    # Tech / AI
    "nvidia", "ai stocks", "semiconductor", "big tech", "magnificent 7",
    "apple", "microsoft", "google", "meta earnings",
]

# Per-instrument keywords for tagging headlines
INSTRUMENT_KEYWORDS = {
    "XAUUSD":  ["gold", "xauusd", "bullion", "precious metal", "safe haven", "gold price",
                "gold rally", "central bank gold", "gold reserves", "xau"],
    "WTI":     ["wti", "crude oil", "oil price", "opec", "hormuz", "brent", "petroleum",
                "barrel", "energy crisis", "refinery", "pipeline", "oil supply"],
    "SPX":     ["s&p 500", "s&p500", "spx", "us500", "stock market", "wall street",
                "earnings", "equities", "bear market", "bull market", "s&p"],
    "NASDAQ":  ["nasdaq", "nas100", "qqq", "tech stock", "ai stock", "semiconductor",
                "nvidia", "magnificent 7", "big tech", "apple", "microsoft", "google"],
    "BTC":     ["bitcoin", "btc", "crypto", "blackrock etf", "strategic reserve",
                "coinbase", "crypto regulation", "digital asset"],
    "ETH":     ["ethereum", "eth ", "defi", "layer 2", "staking", "smart contract"],
    "DXY":     ["dollar index", "dxy", "greenback", "dollar strength", "dollar weakness",
                "us dollar", "forex", "currency", "dollar rally", "dollar selloff"],
    "DOW":     ["dow jones", "djia", "dow 30", "blue chip", "industrials"],
    "VIX":     ["vix", "volatility index", "fear gauge", "market fear", "risk off"],
    "10Y":     ["10-year", "10 year", "treasury yield", "bond yield", "yield curve",
                "10y yield", "t-note", "fomc", "federal reserve"],
}

# Sentiment words
BULLISH_WORDS = {
    "XAUUSD": ["safe haven", "uncertainty", "inflation", "war", "crisis", "buying", "rally", "rate cut"],
    "WTI":    ["opec cut", "hormuz", "supply disruption", "shortage", "attack", "war", "escalat"],
    "SPX":    ["earnings beat", "rate cut", "rally", "growth", "bull", "ai boom", "buyback"],
    "NASDAQ": ["ai boom", "earnings beat", "rate cut", "growth", "rally", "chip demand"],
    "BTC":    ["halving", "etf inflow", "rate cut", "adoption", "institutional", "strategic reserve"],
    "ETH":    ["defi", "upgrade", "staking", "rate cut", "layer 2", "adoption"],
}
BEARISH_WORDS = {
    "XAUUSD": ["rate hike", "dollar strength", "risk on", "sell off", "drop"],
    "WTI":    ["ceasefire", "hormuz open", "opec increase", "demand drop", "recession", "supply surge"],
    "SPX":    ["earnings miss", "recession", "rate hike", "selloff", "crash", "tariff"],
    "NASDAQ": ["earnings miss", "rate hike", "regulation", "antitrust", "selloff", "recession"],
    "BTC":    ["rate hike", "regulation", "ban", "crash", "security breach", "selloff"],
    "ETH":    ["rate hike", "regulation", "hack", "exploit", "selloff"],
}
GENERIC_BULLISH = ["open", "deal", "agreement", "ease", "calm", "ceasefire", "talks", "rally", "beat"]
GENERIC_BEARISH = ["strike", "attack", "close", "war", "escalat", "block", "bomb", "missile",
                   "crash", "recession", "miss", "tariff", "sanction"]


# ═════════════════════════════════════════════════════════════════════════════
# DATA FETCHERS
# ═════════════════════════════════════════════════════════════════════════════

def fetch_yahoo_price(name, symbol):
    """Fetch price data from Yahoo Finance unofficial v8 API."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.parse.quote(symbol)}?interval=1d&range=5d"
    )
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 GODSEYE/3.0",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = json.loads(resp.read().decode())

        result = raw.get("chart", {}).get("result", [])
        if not result:
            return None
        meta = result[0].get("meta", {})

        price      = meta.get("regularMarketPrice")
        prev_close = meta.get("previousClose") or meta.get("chartPreviousClose")
        high52     = meta.get("fiftyTwoWeekHigh")
        low52      = meta.get("fiftyTwoWeekLow")

        day_change = day_change_pct = None
        if price is not None and prev_close:
            day_change     = round(price - prev_close, 4)
            day_change_pct = round((day_change / prev_close) * 100, 2)

        # Last 5 days OHLC + closes for sparkline and future candle charts
        closes = []
        ohlc = []
        timestamps = []
        try:
            quotes = result[0].get("indicators", {}).get("quote", [{}])[0]
            raw_closes = quotes.get("close", [])
            raw_opens  = quotes.get("open", [])
            raw_highs  = quotes.get("high", [])
            raw_lows   = quotes.get("low", [])
            raw_ts     = result[0].get("timestamp", [])

            closes = [round(c, 4) for c in raw_closes if c is not None]

            # Build OHLC array for candle charts (TradingView Lightweight Charts format)
            for i in range(len(raw_closes)):
                try:
                    o = raw_opens[i] if i < len(raw_opens) else None
                    h = raw_highs[i] if i < len(raw_highs) else None
                    l = raw_lows[i]  if i < len(raw_lows)  else None
                    c = raw_closes[i]
                    t = raw_ts[i]    if i < len(raw_ts)    else None
                    if all(v is not None for v in [o, h, l, c]):
                        ohlc.append({
                            "time":  t,
                            "open":  round(o, 4),
                            "high":  round(h, 4),
                            "low":   round(l, 4),
                            "close": round(c, 4),
                        })
                except Exception:
                    pass
        except Exception:
            pass

        # Intraday high/low for ATR approximation
        intraday_high = meta.get("regularMarketDayHigh")
        intraday_low  = meta.get("regularMarketDayLow")

        return {
            "name":           name,
            "symbol":         symbol,
            "price":          round(price, 4) if price else None,
            "prev_close":     round(prev_close, 4) if prev_close else None,
            "day_change":     day_change,
            "day_change_pct": day_change_pct,
            "high_52w":       round(high52, 4) if high52 else None,
            "low_52w":        round(low52, 4) if low52 else None,
            "intraday_high":  round(intraday_high, 4) if intraday_high else None,
            "intraday_low":   round(intraday_low, 4) if intraday_low else None,
            "closes_5d":      closes,
            "ohlc_5d":        ohlc,   # For future TradingView-style candle charts
            "fetchedAt":      datetime.now(timezone.utc).isoformat(),
        }
    except urllib.error.HTTPError as e:
        print(f"  [Yahoo] HTTP {e.code} for {symbol} ({name})", file=sys.stderr)
    except Exception as e:
        print(f"  [Yahoo] Error for {symbol} ({name}): {e}", file=sys.stderr)
    return None


def fetch_all_prices():
    """Fetch prices for all instruments."""
    prices = {}
    for name, symbol in ALL_SYMBOLS.items():
        print(f"    Fetching {name} ({symbol})...", end=" ", flush=True)
        data = fetch_yahoo_price(name, symbol)
        if data:
            prices[name] = data
            pct = f"{data['day_change_pct']:+.2f}%" if data["day_change_pct"] is not None else "N/A"
            print(f"${data['price']}  {pct}")
        else:
            print("FAILED")
    return prices


def fetch_gold_spot():
    """Fetch daily gold spot from FreeGoldAPI."""
    try:
        req = urllib.request.Request("https://freegoldapi.com/data/latest.json",
                                     headers={"User-Agent": "GODSEYE/3.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
        if data and isinstance(data, list):
            return {"date": data[-1].get("date"), "price": data[-1].get("price"), "source": "freegoldapi.com"}
    except Exception as e:
        print(f"  [FreeGoldAPI] Error: {e}", file=sys.stderr)
    return None


# ── POLYMARKET ───────────────────────────────────────────────────────────────

def fetch_polymarket_markets():
    """Fetch Polymarket events via Gamma API — events endpoint gives correct slugs."""
    markets  = []
    seen_ids = set()

    # ── Step 1: Fetch from /events endpoint (gives real event-level slugs) ──
    event_search_terms = [
        "iran", "oil", "russia", "ukraine", "gold", "bitcoin", "nasdaq",
        "interest rate", "fed", "tariff", "china", "taiwan", "trump",
        "ceasefire", "election", "inflation", "recession", "dollar",
    ]

    for kw in event_search_terms:
        url = (
            "https://gamma-api.polymarket.com/events"
            f"?active=true&closed=false&limit=15"
            f"&search={urllib.parse.quote(kw)}"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "GODSEYE/3.0"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                events = json.loads(resp.read().decode())

            for ev in events:
                # Each event has a slug and contains multiple markets
                event_slug = ev.get("slug", "")
                event_title = ev.get("title", "") or ev.get("description", "")
                ev_lower = event_title.lower()

                # Filter for relevant events
                if not any(k in ev_lower for k in POLY_RELEVANT_KEYWORDS):
                    continue

                # Use event slug for URL — this is the correct Polymarket URL
                poly_url = f"https://polymarket.com/event/{event_slug}" if event_slug else "https://polymarket.com/markets"

                # Pull markets from within the event
                ev_markets = ev.get("markets", [])
                if not ev_markets:
                    # Event with no sub-markets — treat event itself as a market
                    eid = ev.get("id", event_slug)
                    if eid in seen_ids:
                        continue
                    seen_ids.add(eid)

                    volume = ev.get("volume", 0) or 0
                    try:
                        volume = float(volume)
                    except Exception:
                        volume = 0

                    markets.append({
                        "id":        eid,
                        "question":  event_title[:160],
                        "slug":      event_slug,
                        "outcomes":  ["Yes", "No"],
                        "prices":    [],
                        "volume":    volume,
                        "liquidity": float(ev.get("liquidity", 0) or 0),
                        "endDate":   ev.get("endDate", ""),
                        "url":       poly_url,
                    })
                    continue

                for m in ev_markets:
                    mid = m.get("id", "")
                    if mid in seen_ids:
                        continue
                    q = m.get("question", "") or event_title
                    q_lower = q.lower()
                    if not any(k in q_lower for k in POLY_RELEVANT_KEYWORDS):
                        # Still accept if the parent event is relevant
                        if not any(k in ev_lower for k in POLY_RELEVANT_KEYWORDS):
                            continue
                    seen_ids.add(mid)

                    raw_prices   = m.get("outcomePrices", "[]")
                    outcomes_raw = m.get("outcomes", '["Yes","No"]')
                    try:
                        prices = [float(p) for p in json.loads(raw_prices)]
                    except Exception:
                        prices = []
                    try:
                        outcomes = json.loads(outcomes_raw)
                    except Exception:
                        outcomes = ["Yes", "No"]

                    volume = m.get("volume", 0) or ev.get("volume", 0) or 0
                    try:
                        volume = float(volume)
                    except Exception:
                        volume = 0

                    markets.append({
                        "id":        mid,
                        "question":  q[:160],
                        "slug":      event_slug,          # Always use event-level slug
                        "outcomes":  outcomes,
                        "prices":    prices,
                        "volume":    volume,
                        "liquidity": float(m.get("liquidity", 0) or 0),
                        "endDate":   m.get("endDate", "") or ev.get("endDate", ""),
                        "url":       poly_url,            # Always event-level URL
                    })

        except urllib.error.HTTPError as e:
            print(f"  [Polymarket/events] HTTP {e.code} for '{kw}'", file=sys.stderr)
        except Exception as e:
            print(f"  [Polymarket/events] Error for '{kw}': {e}", file=sys.stderr)

    # ── Step 2: Deduplicate and sort by volume ──
    # Remove duplicates that slipped through (same question)
    seen_q = set()
    unique = []
    for m in markets:
        qkey = m["question"][:50].lower().strip()
        if qkey not in seen_q:
            seen_q.add(qkey)
            unique.append(m)

    unique.sort(key=lambda x: float(x.get("volume", 0) or 0), reverse=True)
    print(f"    [Polymarket] {len(unique)} unique markets from /events endpoint")
    return unique[:35]


# ── NEWS RSS ─────────────────────────────────────────────────────────────────

def classify_sentiment(title, desc, instrument=None):
    """Classify headline sentiment for an instrument or globally."""
    combined = (title + " " + desc).lower()

    if instrument and instrument in BULLISH_WORDS:
        bull = sum(1 for w in BULLISH_WORDS[instrument] if w in combined)
        bear = sum(1 for w in BEARISH_WORDS.get(instrument, []) if w in combined)
    else:
        bull = sum(1 for w in GENERIC_BULLISH if w in combined)
        bear = sum(1 for w in GENERIC_BEARISH if w in combined)

    if bear > bull:
        return "bearish"
    elif bull > bear:
        return "bullish"
    return "neutral"


def fetch_news_headlines():
    """Parse RSS feeds and filter for relevant headlines."""
    headlines = []

    for feed in NEWS_FEEDS:
        try:
            req = urllib.request.Request(feed["url"],
                                         headers={"User-Agent": "GODSEYE/3.0 RSS"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                raw = resp.read()

            root = ET.fromstring(raw)
            channel = root.find("channel")
            items = channel.findall("item") if channel is not None else root.findall("{http://www.w3.org/2005/Atom}entry")

            for item in items[:40]:
                title = (getattr(item.find("title"), "text", None) or
                         getattr(item.find("{http://www.w3.org/2005/Atom}title"), "text", None) or "").strip()
                desc = (getattr(item.find("description"), "text", None) or
                        getattr(item.find("{http://www.w3.org/2005/Atom}summary"), "text", None) or "").strip()
                link = (getattr(item.find("link"), "text", None) or
                        (item.find("{http://www.w3.org/2005/Atom}link") or {}).get("href", "") or "").strip()
                pub = (getattr(item.find("pubDate"), "text", None) or
                       getattr(item.find("{http://www.w3.org/2005/Atom}updated"), "text", None) or "").strip()

                combined = (title + " " + desc).lower()
                if not any(k in combined for k in GLOBAL_NEWS_KEYWORDS):
                    continue

                clean_desc = re.sub(r"<[^>]+>", "", desc)[:250].strip()
                sentiment = classify_sentiment(title, clean_desc)

                # Tag which instruments this touches
                tagged = []
                for inst, kws in INSTRUMENT_KEYWORDS.items():
                    if any(k in combined for k in kws):
                        tagged.append(inst)

                # Parse pubDate to ISO timestamp for "X ago" display
                pub_iso = ""
                try:
                    from email.utils import parsedate_to_datetime
                    pub_iso = parsedate_to_datetime(pub).isoformat()
                except Exception:
                    try:
                        # Try ISO format directly
                        pub_iso = pub
                    except Exception:
                        pub_iso = ""

                headlines.append({
                    "source":      feed["name"],
                    "title":       title,
                    "desc":        clean_desc,
                    "link":        link,
                    "pubDate":     pub,
                    "pubISO":      pub_iso,
                    "sentiment":   sentiment,
                    "instruments": tagged,
                })
        except Exception as e:
            print(f"  [News] Error fetching {feed['name']}: {e}", file=sys.stderr)

    # Deduplicate
    seen = set()
    unique = []
    for h in headlines:
        key = h["title"][:60].lower()
        if key not in seen:
            seen.add(key)
            unique.append(h)

    unique.sort(key=lambda h: (len(h["instruments"]) == 0, h["pubDate"]))
    return unique[:30]


# ═════════════════════════════════════════════════════════════════════════════
# TRADING SIGNAL GENERATION
# ═════════════════════════════════════════════════════════════════════════════

# MiroFish base probabilities (bullish %) per instrument
# UPDATE after each MiroFish simulation run
MIROFISH_BULLISH = {
    "XAUUSD": 81,  "WTI": 68,  "SPX": 62,  "NASDAQ": 58,
    "BTC": 83,     "ETH": 75,  "DXY": 48,  "DOW": 55,
}

def generate_trading_signals(prices, headlines, poly_markets, mirofish_debates=None):
    """
    Generate trading signals for each tradable instrument.
    Uses: current price, news sentiment, Polymarket divergence, ATR-based targets.

    Each signal has:
      - direction: BUY / SELL / NEUTRAL
      - entry: current price
      - expected_move_pct: expected % move based on volatility + signal strength
      - volatility: HIGH / MEDIUM / LOW
      - confidence: HIGH / MEDIUM / LOW
      - reasons: list of contributing factors
    """
    signals = []

    # Override MiroFish probabilities with latest debate consensus if available
    effective_mirofish = dict(MIROFISH_BULLISH)
    if mirofish_debates and "debates" in mirofish_debates:
        for inst_key, debate in mirofish_debates["debates"].items():
            if "consensus_bullish_pct" in debate:
                effective_mirofish[inst_key] = debate["consensus_bullish_pct"]

    for inst, cfg in TRADABLE.items():
        p = prices.get(inst)
        if not p or p["price"] is None:
            continue

        price = p["price"]
        atr_pct = cfg["atr_pct"]
        reasons = []

        # ── 1) News sentiment score (-1 to +1)
        inst_headlines = [h for h in headlines if inst in h.get("instruments", [])]
        bull_count = sum(1 for h in inst_headlines if h["sentiment"] == "bullish")
        bear_count = sum(1 for h in inst_headlines if h["sentiment"] == "bearish")
        total_news = bull_count + bear_count
        news_score = 0
        if total_news > 0:
            news_score = (bull_count - bear_count) / total_news
            if abs(news_score) > 0.3:
                direction_word = "bullish" if news_score > 0 else "bearish"
                reasons.append(f"News sentiment {direction_word} ({bull_count}B/{bear_count}S)")

        # ── 2) Polymarket divergence
        miro_base = effective_mirofish.get(inst, 50) / 100.0
        poly_score = 0
        poly_prob = None
        poly_url = None
        poly_question = None

        # Find relevant Polymarket markets
        inst_kws = [k.lower() for k in INSTRUMENT_KEYWORDS.get(inst, [])]
        for m in poly_markets:
            q = m["question"].lower()
            if not m["prices"] or len(m["prices"]) < 1:
                continue
            if any(kw in q for kw in inst_kws):
                poly_yes = m["prices"][0]
                divergence = poly_yes - miro_base
                if abs(divergence) > 0.10:
                    poly_score = divergence
                    poly_prob = round(poly_yes * 100, 1)
                    poly_url = m["url"]
                    poly_question = m["question"]
                    reasons.append(f"Polymarket {poly_prob}% vs MiroFish {miro_base*100:.0f}% ({abs(divergence)*100:.0f}pt gap)")
                break

        # ── 3) Day momentum
        momentum_score = 0
        if p["day_change_pct"] is not None:
            if abs(p["day_change_pct"]) > 1.5:
                momentum_score = 0.3 if p["day_change_pct"] > 0 else -0.3
                reasons.append(f"Momentum {p['day_change_pct']:+.2f}% today")

        # ── 4) DXY inverse correlation (for gold, oil, equities)
        dxy_score = 0
        dxy_data = prices.get("DXY")
        if dxy_data and dxy_data["day_change_pct"] is not None:
            if inst in ("XAUUSD", "BTC", "ETH") and abs(dxy_data["day_change_pct"]) > 0.5:
                # Dollar up = bearish for gold/crypto
                dxy_score = -0.2 if dxy_data["day_change_pct"] > 0 else 0.2
                reasons.append(f"DXY barometer {dxy_data['day_change_pct']:+.2f}%")

        # ── 5) VIX fear gauge
        vix_score = 0
        vix_data = prices.get("VIX")
        if vix_data and vix_data["price"] is not None:
            vix_val = vix_data["price"]
            if vix_val > 30:
                if inst == "XAUUSD":
                    vix_score = 0.2  # High VIX = bullish gold
                    reasons.append(f"VIX elevated ({vix_val:.1f}) — risk-off favors gold")
                elif inst in ("SPX", "NASDAQ"):
                    vix_score = -0.2  # High VIX = bearish equities
                    reasons.append(f"VIX elevated ({vix_val:.1f}) — risk-off")

        # ── Composite score (-1 to +1)
        raw_score = (news_score * 0.30) + (poly_score * 0.30) + (momentum_score * 0.20) + (dxy_score * 0.10) + (vix_score * 0.10)

        # Direction
        if raw_score > 0.15:
            direction = "BUY"
        elif raw_score < -0.15:
            direction = "SELL"
        else:
            direction = "NEUTRAL"

        # Confidence
        abs_score = abs(raw_score)
        if abs_score > 0.40:
            confidence = "HIGH"
        elif abs_score > 0.20:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        # Expected move: ATR-based, scaled by signal strength
        # Stronger signals → expect larger moves in direction
        expected_move_pct = round(atr_pct * min(abs_score * 2.5, 1.5), 2)
        if direction == "SELL":
            expected_move_pct = -expected_move_pct

        # Volatility assessment
        if atr_pct >= 4.0:
            volatility = "HIGH"
        elif atr_pct >= 2.0:
            volatility = "MEDIUM"
        else:
            volatility = "LOW"

        if not reasons:
            reasons.append("No strong directional catalyst")

        signals.append({
            "instrument":        inst,
            "label":             cfg["label"],
            "direction":         direction,
            "confidence":        confidence,
            "entry":             price,
            "expected_move_pct": expected_move_pct,
            "volatility":        volatility,
            "score":             round(raw_score, 3),
            "reasons":           reasons,
            "news_count":        len(inst_headlines),
            "bull_headlines":    bull_count,
            "bear_headlines":    bear_count,
            "polymarket_prob":   poly_prob,
            "polymarket_url":    poly_url,
            "polymarket_question": poly_question,
            "mirofish_base":     effective_mirofish.get(inst),
            "mirofish_debate":   None,  # Will be populated below
            "day_change_pct":    p["day_change_pct"],
            "timestamp":         datetime.now(timezone.utc).isoformat(),
        })

        # Attach MiroFish debate context if available
        if mirofish_debates and "debates" in mirofish_debates:
            inst_debate = mirofish_debates["debates"].get(inst)
            if inst_debate:
                signals[-1]["mirofish_debate"] = {
                    "consensus_pct":    inst_debate.get("consensus_bullish_pct"),
                    "agents_bullish":   inst_debate.get("agents_bullish"),
                    "agents_bearish":   inst_debate.get("agents_bearish"),
                    "agents_neutral":   inst_debate.get("agents_neutral"),
                    "top_narrative":    inst_debate.get("top_narrative"),
                    "skeptic_counter":  inst_debate.get("skeptic_counter"),
                    "sentiment_by_round": inst_debate.get("sentiment_by_round"),
                    "timestamp":        mirofish_debates.get("timestamp"),
                }

    # Sort by absolute score (strongest signals first)
    signals.sort(key=lambda s: abs(s["score"]), reverse=True)
    return signals


# ═════════════════════════════════════════════════════════════════════════════
# POLYMARKET SIGNAL SCORING (MiroFish divergence)
# ═════════════════════════════════════════════════════════════════════════════

MIROFISH_SCENARIO = {
    "deal": 0.18, "limited": 0.52, "escalation": 0.30,
}
MIROFISH_INSTRUMENT_MAP = {
    "gold": 0.81, "bullion": 0.81, "oil": 0.72, "wti": 0.68, "brent": 0.72,
    "crude": 0.68, "s&p": 0.62, "spx": 0.62, "stock": 0.58, "dow": 0.55,
    "nasdaq": 0.58, "tech": 0.55, "semiconductor": 0.22, "tsmc": 0.20,
    "dollar": 0.48, "dxy": 0.48, "bitcoin": 0.83, "btc": 0.83,
    "ethereum": 0.75, "eth": 0.75, "crypto": 0.78,
    "ukraine": 0.60, "russia": 0.62, "taiwan": 0.68,
    "north korea": 0.55, "election": 0.50, "senate": 0.47,
}

def score_polymarket_signals(markets, mirofish_debates=None):
    """Score Polymarket markets against MiroFish probabilities."""
    signals = []

    for m in markets[:25]:
        if not m["prices"] or len(m["prices"]) < 2:
            continue
        poly_yes = m["prices"][0]
        q = m["question"].lower()

        miro_p = None
        if any(w in q for w in ["open", "deal", "agree", "ceasefire", "end", "reopen"]):
            miro_p = MIROFISH_SCENARIO["deal"]
        elif any(w in q for w in ["strike", "attack", "limited", "tactical"]):
            miro_p = MIROFISH_SCENARIO["limited"]
        elif any(w in q for w in ["war", "escalat", "close", "block", "invade"]):
            miro_p = MIROFISH_SCENARIO["escalation"]
        else:
            for key, val in MIROFISH_INSTRUMENT_MAP.items():
                if key in q:
                    miro_p = val
                    break

        if miro_p is None:
            miro_p = 0.50  # Default neutral

        divergence = round(abs(poly_yes - miro_p) * 100, 1)
        if poly_yes < miro_p - 0.10:
            direction = "YES likely"
        elif poly_yes > miro_p + 0.10:
            direction = "NO likely"
        else:
            direction = "VOLATILE"

        confidence = "HIGH" if divergence >= 25 else ("MEDIUM" if divergence >= 15 else "LOW")

        # Check if any debate has relevant context for this market
        poly_debate_context = None
        if mirofish_debates and "debates" in mirofish_debates:
            q_lower = m["question"].lower()
            for inst_key, debate in mirofish_debates["debates"].items():
                inst_kws = {
                    "XAUUSD": ["gold", "bullion"],
                    "WTI": ["oil", "crude", "wti", "brent"],
                    "SPX": ["s&p", "spx", "stock"],
                    "NASDAQ": ["nasdaq", "tech"],
                    "BTC": ["bitcoin", "btc", "crypto"],
                    "ETH": ["ethereum", "eth"],
                }
                if any(kw in q_lower for kw in inst_kws.get(inst_key, [])):
                    poly_debate_context = {
                        "instrument": inst_key,
                        "consensus_pct": debate.get("consensus_bullish_pct"),
                        "top_narrative": debate.get("top_narrative"),
                        "skeptic_counter": debate.get("skeptic_counter"),
                    }
                    break

        signals.append({
            "question":        m["question"][:120],
            "polymarket_prob": round(poly_yes * 100, 1),
            "mirofish_prob":   round(miro_p * 100, 1),
            "divergence":      divergence,
            "direction":       direction,
            "confidence":      confidence,
            "volume":          m.get("volume", 0),
            "url":             m["url"],
            "endDate":         m.get("endDate", ""),
            "mirofish_debate": poly_debate_context,
        })

    return sorted(signals, key=lambda x: x["divergence"], reverse=True)


# ═════════════════════════════════════════════════════════════════════════════
# CHART DATA
# ═════════════════════════════════════════════════════════════════════════════

def build_chart_data(prices, markets, mirofish_debates=None):
    """Build chart datasets for dashboard visualization."""
    cat_map = {
        "XAUUSD":  ["gold", "xauusd", "bullion"],
        "WTI":     ["wti", "crude", "oil price", "brent", "hormuz", "opec"],
        "SPX":     ["s&p", "spx", "stock market", "rate cut"],
        "NASDAQ":  ["nasdaq", "tech", "qqq", "semiconductor"],
        "BTC":     ["bitcoin", "btc", "crypto", "halving"],
        "ETH":     ["ethereum", "eth", "defi"],
        "DXY":     ["dollar", "dxy", "greenback", "election"],
        "DOW":     ["dow jones", "djia"],
    }

    poly_probs = {k: None for k in cat_map}
    for m in markets:
        q = m["question"].lower()
        if not m.get("prices"):
            continue
        for label, keywords in cat_map.items():
            if poly_probs[label] is not None:
                continue
            if any(kw in q for kw in keywords):
                poly_probs[label] = round(m["prices"][0] * 100, 1)

    instruments = list(cat_map.keys())
    effective_mirofish = dict(MIROFISH_BULLISH)
    if mirofish_debates and "debates" in mirofish_debates:
        for inst_key, debate in mirofish_debates["debates"].items():
            if "consensus_bullish_pct" in debate:
                effective_mirofish[inst_key] = debate["consensus_bullish_pct"]
    miro_arr = [effective_mirofish.get(i, 50) for i in instruments]
    poly_arr = [poly_probs[i] for i in instruments]

    # Price cards for dashboard
    price_cards = []
    all_inst = {**TRADABLE, **BAROMETERS}
    for name, cfg in all_inst.items():
        p = prices.get(name)
        if p:
            price_cards.append({
                "name":           name,
                "label":          cfg["label"],
                "symbol":         p["symbol"],
                "price":          p["price"],
                "day_change":     p["day_change"],
                "day_change_pct": p["day_change_pct"],
                "high_52w":       p["high_52w"],
                "low_52w":        p["low_52w"],
                "closes_5d":      p["closes_5d"],
                "tradable":       name in TRADABLE,
                "barometer":      name in BAROMETERS,
            })
        else:
            price_cards.append({"name": name, "label": cfg["label"], "price": None, "error": "fetch_failed"})

    return {
        "instruments": instruments,
        "mirofish":    miro_arr,
        "polymarket":  poly_arr,
        "price_cards": price_cards,
    }


# ═════════════════════════════════════════════════════════════════════════════
# MIROFISH DEBATES
# ═════════════════════════════════════════════════════════════════════════════

def load_mirofish_debates():
    """Load the latest MiroFish agent debate data if available."""
    debate_file = os.path.join(SCRIPT_DIR, "data", "mirofish_debates.json")
    if os.path.exists(debate_file):
        try:
            with open(debate_file, "r", encoding="utf-8") as f:
                debates = json.load(f)
            print(f"    Loaded MiroFish debates from {debates.get('timestamp', 'unknown')}")
            return debates
        except Exception as e:
            print(f"    [MiroFish] Error loading debates: {e}", file=sys.stderr)
    else:
        print("    [MiroFish] No debate file found — using static probabilities")
    return None


# ═════════════════════════════════════════════════════════════════════════════
# OUTPUT
# ═════════════════════════════════════════════════════════════════════════════

def write_output(prices, gold_spot, markets, headlines, trading_signals, poly_signals, chart_data, mirofish_debates=None):
    now_utc     = datetime.now(timezone.utc).isoformat()
    now_display = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    payload = {
        "fetchedAt":       now_utc,
        "fetchedDisplay":  now_display,
        "prices":          prices,
        "gold_spot":       gold_spot,
        "polymarketMarkets": markets,
        "headlines":       headlines,
        "tradingSignals":  trading_signals,
        "polySignals":     poly_signals,
        "chartData":       chart_data,
        "mirofishDebates": mirofish_debates,
    }

    # Ensure data directory exists
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    kb = os.path.getsize(OUTPUT_FILE) / 1024
    print(f"\n✅  live_data.json written ({kb:.1f} KB)")
    print(f"    Prices: {len(prices)} instruments")
    print(f"    Markets: {len(markets)} Polymarket markets")
    print(f"    Headlines: {len(headlines)} filtered headlines")
    print(f"    Trading Signals: {len(trading_signals)}")
    print(f"    Poly Signals: {len(poly_signals)}")
    print(f"    → {OUTPUT_FILE}")


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("  GODSEYE Live Data Pipeline v3")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    print("\n📈  Fetching prices...")
    prices = fetch_all_prices()
    print(f"    Got {len(prices)}/{len(ALL_SYMBOLS)} instruments")

    print("\n🥇  Fetching gold spot...")
    gold_spot = fetch_gold_spot()
    if gold_spot:
        print(f"    Gold spot: ${gold_spot['price']}")
    else:
        print("    FreeGoldAPI unavailable")

    print("\n🔮  Fetching Polymarket...")
    markets = fetch_polymarket_markets()
    print(f"    Found {len(markets)} relevant markets")

    print("\n📰  Fetching news...")
    headlines = fetch_news_headlines()
    print(f"    Found {len(headlines)} filtered headlines")

    print("\n🐟  Loading MiroFish debates...")
    mirofish_debates = load_mirofish_debates()

    print("\n📊  Generating trading signals...")
    trading_signals = generate_trading_signals(prices, headlines, markets, mirofish_debates)
    for s in trading_signals:
        arrow = "🟢" if s["direction"] == "BUY" else ("🔴" if s["direction"] == "SELL" else "⚪")
        print(f"    {arrow} {s['instrument']:<8} {s['direction']:<8} {s['confidence']:<6} "
              f"Entry: ${s['entry']:>10,.2f}  Move: {s['expected_move_pct']:+.2f}%  Vol: {s['volatility']}")

    print("\n🔮  Scoring Polymarket signals...")
    poly_signals = score_polymarket_signals(markets, mirofish_debates)
    print(f"    Generated {len(poly_signals)} signals")

    print("\n📉  Building chart data...")
    chart_data = build_chart_data(prices, markets, mirofish_debates)

    print("\n💾  Writing output...")
    write_output(prices, gold_spot, markets, headlines, trading_signals, poly_signals, chart_data, mirofish_debates)

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
