# GODSEYE — Version History

## Backup Process

Before every significant change, tag the current state:

```bash
# 1. Tag the current version
git tag -a v1.x -m "Short description of this version"

# 2. Push the tag to GitHub (tags are permanent bookmarks)
git push --tags

# 3. To restore any version later:
git checkout v1.x
```

Tags are visible at: https://github.com/callenbspr-ux/godseye/tags

---

## Version Log

### v1.3 — UI/UX Redesign (2026-04-08)
- New wireframe-based layout: left panel (News + Insights) / right panel (Signal cards + Poly grid)
- Clickable instrument chart cards with modal expand
- Polymarket 4-column scrollable grid
- Actionable Insights synthesized panel
- OHLC data added to pipeline for future candle charts
- Responsive chart modal with Chart.js line chart

### v1.2 — Timestamps, Instrument Labels, How To Use (2026-04-08)
- Live timestamps on news articles ("2h ago", "just now")
- Instrument label pills on news (XAUUSD, WTI, BTC etc.)
- How To Use page with full workflow explanation
- Removed DXY barometer note from Trading Signals header
- Signal last-updated timestamp on Trading Signals card

### v1.1 — Initial Live Dashboard (2026-04-08)
- GitHub Pages + GitHub Actions pipeline deployed
- Live prices: XAUUSD, WTI, SPX, NASDAQ, BTC, ETH + barometers
- BUY/SELL/NEUTRAL trading signals with entry price + expected % move
- Polymarket MiroFish divergence signals
- RSS news feed (Reuters, AP, BBC, CNBC, MarketWatch)
- 30-min auto-update via GitHub Actions cron

### v1.0 — Initial Commit
- Static HTML dashboard skeleton
- Pipeline structure established
