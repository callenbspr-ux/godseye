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
    "iran", "hormuz", "strait", "persian gulf", "tehran", "escalat",
    "sanctions", "ceasefire", "nuclear", "tanker", "middle east",
    "russia", "ukraine", "nato", "kyiv", "moscow", "putin",
    "taiwan", "china", "pla", "tsmc", "south china sea",
    "north korea", "kim jong", "icbm",
    "election", "senate", "midterm", "congress",
    "oil price", "crude", "brent", "wti", "opec", "natural gas",
    "gold price", "bullion", "precious metal", "safe haven",
    "stock market", "s&p 500", "wall street", "dow jones", "nasdaq",
    "earnings", "recession", "bear market", "market crash",
    "federal reserve", "interest rate", "rate cut", "inflation", "cpi",
    "dollar index", "dxy", "tariff", "trade war",
    "bitcoin", "ethereum", "crypto", "btc", "blackrock etf",
    "nvidia", "ai stocks", "semiconductor", "big tech",
]

# Per-instrument keywords for tagging headlines
INSTRUMENT_KEYWORDS = {
    "XAUUSD":  ["gold", "xauusd", "bullion", "precious metal", "GC=F", "safe haven", "gold price"],
    "WTI":     ["wti", "crude oil", "oil price", "opec", "hormuz", "brent", "petroleum", "barrel"],
    "SPX":     ["s&p 500", "spx", "stock market", "wall street", "earnings", "equities"],
    "NASDAQ":  ["nasdaq", "tech stock", "ai stock", "semiconductor", "nvidia", "magnificent 7", "qqq"],
    "BTC":     ["bitcoin", "btc", "crypto", "blackrock etf", "strategic reserve", "coinbase"],
    "ETH":     ["ethereum", "eth ", "defi", "layer 2", "staking"],
    "DXY":     ["dollar index", "dxy", "greenback", "dollar strength", "us dollar", "forex"],
    "DOW":     ["dow jones", "djia", "dow 30", "blue chip", "industrials"],
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
    """Search Polymarket Gamma API across keyword batches, deduplicate."""
    markets  = []
    seen_ids = set()

    for kw in POLY_SEARCH_TERMS:
        url = (
            "https://gamma-api.polymarket.com/markets"
            f"?active=true&closed=false&limit=20&offset=0"
            f"&search={urllib.parse.quote(kw)}"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "GODSEYE/3.0"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = json.loads(resp.read().decode())

            for m in data:
                mid = m.get("id", "")
                if mid in seen_ids:
                    continue
                q = m.get("question", "").lower()
                if not any(k in q for k in POLY_RELEVANT_KEYWORDS):
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

                markets.append({
                    "id":        mid,
                    "question":  m.get("question", ""),
                    "slug":      m.get("slug", ""),
                    "outcomes":  outcomes,
                    "prices":    prices,
                    "volume":    m.get("volume", 0),
                    "liquidity": m.get("liquidity", 0),
                    "endDate":   m.get("endDate", ""),
                    "url":       f"https://polymarket.com/event/{m.get('slug', '')}",
                })
        except urllib.error.HTTPError as e:
            print(f"  [Polymarket] HTTP {e.code} for '{kw}'", file=sys.stderr)
        except Exception as e:
            print(f"  [Polymarket] Error for '{kw}': {e}", file=sys.stderr)

    markets.sort(key=lambda x: float(x.get("volume", 0) or 0), reverse=True)
    return markets[:30]


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

                headlines.append({
                    "source":      feed["name"],
                    "title":       title,
                    "desc":        clean_desc,
                    "link":        link,
                    "pubDate":     pub,
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

def generate_trading_signals(prices, headlines, poly_markets):
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
        miro_base = MIROFISH_BULLISH.get(inst, 50) / 100.0
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
            "mirofish_base":     MIROFISH_BULLISH.get(inst),
            "day_change_pct":    p["day_change_pct"],
            "timestamp":         datetime.now(timezone.utc).isoformat(),
        })

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

def score_polymarket_signals(markets):
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
        })

    return sorted(signals, key=lambda x: x["divergence"], reverse=True)


# ═════════════════════════════════════════════════════════════════════════════
# CHART DATA
# ═════════════════════════════════════════════════════════════════════════════

def build_chart_data(prices, markets):
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
    miro_arr = [MIROFISH_BULLISH.get(i, 50) for i in instruments]
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
# OUTPUT
# ═════════════════════════════════════════════════════════════════════════════

def write_output(prices, gold_spot, markets, headlines, trading_signals, poly_signals, chart_data):
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

    print("\n📊  Generating trading signals...")
    trading_signals = generate_trading_signals(prices, headlines, markets)
    for s in trading_signals:
        arrow = "🟢" if s["direction"] == "BUY" else ("🔴" if s["direction"] == "SELL" else "⚪")
        print(f"    {arrow} {s['instrument']:<8} {s['direction']:<8} {s['confidence']:<6} "
              f"Entry: ${s['entry']:>10,.2f}  Move: {s['expected_move_pct']:+.2f}%  Vol: {s['volatility']}")

    print("\n🔮  Scoring Polymarket signals...")
    poly_signals = score_polymarket_signals(markets)
    print(f"    Generated {len(poly_signals)} signals")

    print("\n📉  Building chart data...")
    chart_data = build_chart_data(prices, markets)

    print("\n💾  Writing output...")
    write_output(prices, gold_spot, markets, headlines, trading_signals, poly_signals, chart_data)

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
