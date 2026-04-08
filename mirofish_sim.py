#!/usr/bin/env python3
"""
MiroFish Multi-Agent Debate Simulator for GODSEYE Market Intelligence Dashboard
Simulates per-instrument debates and outputs structured JSON for dashboard consumption.
"""

import json
import os
import random
import datetime
import math
from typing import Dict, List, Any

# Instrument definitions
INSTRUMENTS = {
    "XAUUSD": {"label": "Gold", "base_bullish": 81},
    "WTI": {"label": "WTI Crude", "base_bullish": 68},
    "SPX": {"label": "S&P 500", "base_bullish": 62},
    "NASDAQ": {"label": "NASDAQ", "base_bullish": 58},
    "BTC": {"label": "Bitcoin", "base_bullish": 83},
    "ETH": {"label": "Ethereum", "base_bullish": 75},
}

AGENTS = ["Macro Bull", "Technical Bear", "Geopolitical Analyst", "Retail Sentiment", "Contrarian", "Quant", "Risk Manager"]

# Agent weights for consensus calculation
AGENT_WEIGHTS = {
    "Macro Bull": 0.20,
    "Technical Bear": 0.18,
    "Geopolitical Analyst": 0.17,
    "Retail Sentiment": 0.12,
    "Contrarian": 0.15,
    "Quant": 0.10,
    "Risk Manager": 0.08,
}

# Argument templates per agent per instrument
ARGUMENT_TEMPLATES = {
    "XAUUSD": {
        "Macro Bull": [
            "Central banks remain substantial accumulators despite elevated prices. Structural demand from reserve diversification drives gold above $2,450.",
            "Real yields turning negative across developed markets create a tailwind. Gold rerating from $2,400 to $2,600 is justified on 2-3 year horizon.",
            "Rate cut cycle beginning in Q3 removes the final headwind. Historical correlation suggests 8-12% upside once Fed pivots.",
            "Geopolitical fragmentation keeps central banks defensive. Gold's percentage of reserves near historic lows—accumulation theme intact.",
        ],
        "Technical Bear": [
            "Resistance at $2,420 has rejected twice in three weeks. RSI divergence on 4H chart warns of exhaustion before new highs.",
            "Options positioning shows dealer short building—typical setup for mean reversion. Support test at $2,350 likely before continuation.",
            "Overbought conditions on the daily timeframe (RSI 72) and declining volume into strength. Volatility compression suggests a 3-5% pullback imminent.",
            "Downtrend in USD has been the hidden driver. Once dollar stabilizes, gold loses 40-50% of recent move. Test $2,380 on DXY stabilization.",
        ],
        "Geopolitical Analyst": [
            "Middle East tension escalation remains the biggest upside catalyst. Any Iran-Israel flare-up sends gold to $2,550+ immediately.",
            "Russia-Ukraine deadlock supports extended risk premium. Central Bank demand in non-US aligned nations creates permanent bid under gold.",
            "Taiwan strait remains tinderbox. De-escalation could mean 5% pullback, but baseline assumption is continued elevated tensions supporting gold.",
            "Sanctions regime becoming entrenched—non-Western nations holding more gold is structural trend. BRICS dedollarization supports gold above $2,400.",
        ],
        "Retail Sentiment": [
            "Gold is the hot crowded trade right now. Everyone's grandma is asking their broker about gold ETFs. FOMO driving younger retail into GLD.",
            "Social media sentiment on precious metals hitting 3-year highs. Retail momentum often precedes institutional rotation—bullish signal.",
            "Rate cut expectations have retail excited about inflation hedges. Gold fund flows positive for 8 weeks straight—crowd energy strong.",
            "Geopolitical headlines dominating retail news cycles. Fear of conflict drives retail bid. When headlines fade, retail dumps positions quickly.",
        ],
        "Contrarian": [
            "Crowded long positioning suggests fade. Commercial hedgers still short, but small specs now massively long—classic reversal setup.",
            "Gold at multi-year highs after 12-month rally. Mean reversion would target $2,200-$2,250 within 6 months. Valuation stretched.",
            "Technical deterioration despite higher prices. Volume declining, breadth weakening. Early warning of mean reversion starting.",
            "Macro Bull case priced in. If rates don't cut as aggressively as expected, gold falls 10%. Unlikely to get $2,600 print.",
        ],
        "Quant": [
            "Historical correlation: gold rallies 73% of the time when real yields fall below -0.5%. Current regime matches Q3 2020 setup. Statistical edge favors long.",
            "90-day realized vol at 14% — below 1Y average of 18%. Low vol regimes historically precede large directional moves. Risk/reward skewed to upside.",
            "Cross-asset signal: when DXY 30-day momentum turns negative AND VIX is above 20, gold has a 68% win rate over the following 30 days.",
            "Options market pricing 2% monthly move. Skew heavily toward calls. Systematic flows into gold ETFs historically front-run spot moves by 3-5 days.",
        ],
        "Risk Manager": [
            "Primary risk: unexpected Fed hawkishness. If CPI prints above 3.5% twice consecutively, gold faces $150-200 headwind. Stop discipline at $2,320 critical.",
            "Tail risk scenario: coordinated G7 gold leasing to suppress prices during dollar crisis. Low probability (5%) but catastrophic. Size accordingly.",
            "Geopolitical risk premium currently $80-120/oz above fundamental value. Peace resolution would cause sharp unwinding. Risk-adjusted entry requires tight stops.",
            "Correlation breakdown risk: gold-equity correlation has turned positive 3 times since 2000 during deleveraging events. Not a pure safe haven in crash scenarios.",
        ],
    },
    "WTI": {
        "Macro Bull": [
            "OPEC+ cuts holding strong. Supply tightness supports $80+ WTI through summer driving season and hurricane risk.",
            "Refinery margins remain healthy, supporting crude demand. Seasonal demand surge entering spring—WTI likely to hold $75-$85 range.",
            "Geopolitical risk in Red Sea keeps shipping costs elevated and supply uncertain. This premium justifies $80+ baseline.",
            "Chinese economic reopening continuing to drive demand. PMI data improving steadily. Asian crude flows north drive WTI to $85.",
        ],
        "Technical Bear": [
            "Resistance at $82.50 has become a ceiling. Three failed breaks in past four weeks. Breakdown below $78 targets $74 support.",
            "Divergence between WTI and Brent widening. WTI technicals weakening while Brent holds firm. Mean reversion toward $76-$77 likely.",
            "Volume declining into recent rallies. MACD rolling over on daily chart. Lower high setup—pullback to $75 before continuation.",
            "Chart pattern showing bearish engulfing. Sell signal on break below 20-day MA. $74 is next technical target.",
        ],
        "Geopolitical Analyst": [
            "Houthi attacks remain unpredictable but periodic. Risk premium of $3-4/bbl justified until Red Sea stabilizes.",
            "Iran nuclear talks at impasse—sanctions regime holding. Any breakthrough removes significant supply uncertainty. But status quo supports crude.",
            "Russia production holding despite sanctions. Venezuelan output still capped. North Sea maintenance schedules support supply tightness.",
            "Gaza conflict could spread to broader regional conflagration. Oil markets will price 10-15% premium if Iran-Israel escalates.",
        ],
        "Retail Sentiment": [
            "Crude rallies getting headlines. Retail finally talking about oil again after 2 years of ignoring it. Momentum building.",
            "Shipping companies and airlines raising guidance. Retail noticing. Crowded long positioning in oil ETFs hitting 6-month highs.",
            "Gasoline prices at pump ticking up. Consumer anxiety returning. Could trigger demand destruction if WTI stays $80+.",
            "Oil stock seasonality strong heading into summer. Retail rotating into energy sector. Momentum trade still intact.",
        ],
        "Contrarian": [
            "Everyone is bullish crude. OPEC cuts already priced in. Supply destruction from recession would hit demand anyway.",
            "Demand destruction risk underestimated. If US recession hits, crude cracks to $60. Currently no buffer for bad macro data.",
            "Geopolitical risk premium gets repriced lower when conflict doesn't escalate. Bets on Middle East war are losing trades.",
            "Refinery runs declining—demand really weakening. Market ignoring bearish demand signals. Test $74-$75 imminent.",
        ],
        "Quant": [
            "WTI-Brent spread compression suggests US export pressure building. SPR at 40-year low limits government buffer. Supply-side statistical edge.",
            "Seasonal pattern: WTI averages +4.2% in April over 20Y history. Refinery turnaround season reducing crude demand — but gasoline crack spread expanding.",
            "CTA positioning at -2 sigma vs 1Y mean. Systematic shorts vulnerable to squeeze. Every $2 rally above $80 triggers estimated $3.2B in buybacks.",
            "EIA inventory draw of 3.8M bbls vs expectations of 1.2M. 3-week trend of beats. Statistical momentum building.",
        ],
        "Risk Manager": [
            "OPEC+ compliance risk: Libya, Kazakhstan, Iraq historically over-produce. 20% probability of compliance failure adding 500K bbl/day supply overhang.",
            "Demand destruction risk: if WTI sustains above $90, historical evidence shows airline/trucking demand contracts within 90 days. Self-limiting rally.",
            "Contango structure building — suggests market sees near-term oversupply. Rolling costs erode long positions in futures. Prefer spot exposure if available.",
            "Geopolitical risk premium double-edged: Hormuz closure scenario priced 40% in options. Resolution removes premium faster than escalation adds it.",
        ],
    },
    "SPX": {
        "Macro Bull": [
            "Earnings growth accelerating. Tech mega-caps showing operating leverage. 2026 PEG ratio justified given growth profile.",
            "Soft landing scenario now the consensus. Fed will cut rates in Q3. Risk-off premium should decompress. S&P 5,500+ target.",
            "Passive flows and buyback calendar strong through Q2. Corporate America still confident on growth. Bid under equities intact.",
            "Valuation reset lower in 2024 created opportunity. Now you're paying 20x for 8% growth. Still cheap relative to bonds at 4% risk-free.",
        ],
        "Technical Bear": [
            "Breadth divergence screaming. Equal-weight index lagging by 600 bps. Only mega-cap 7 driving index. Fragile rally structure.",
            "Resistance at 5,500 has been tested twice with no follow-through. VIX compression near 12 year lows—complacency warning.",
            "Distribution days accumulating. Chart pattern suggests pullback to 5,250-5,300 zone on any macro headline.",
            "Overbought conditions on multiple timeframes. 5% pullback would be healthy. Any miss in earnings triggers 8-10% correction.",
        ],
        "Geopolitical Analyst": [
            "Equity risk premium too low given geopolitical fragmentation. Taiwan, Ukraine, Middle East all elevated. Should be trading lower.",
            "Sanctions regime hurting Tech supply chains but market ignoring. Semiconductor export restrictions becoming structural headwind.",
            "Rates market pricing zero recession risk. Any conflict shock could flip sentiment fast. Better to be defensive now.",
            "China tensions simmering. Tech sector vulnerability to Taiwan escalation is asymmetric. Equity hedge warranted.",
        ],
        "Retail Sentiment": [
            "Retail FOMO on mega-cap stocks reaching fever pitch. Everyone loaded up on NVDA, MSFT, TSLA. Breadth collapse reflects crowding.",
            "Robo advisors and 401k flows pushing passive money into top holdings. Liquidity for trash names has disappeared.",
            "Financial influencers pounding the table on Tech AI narrative. Retail momentum trade overdone. Correction coming.",
            "After two years of losses, retail finally bullish again. Capitulation bottom was in. New rally leg should attract more buyers.",
        ],
        "Contrarian": [
            "Sentiment indicators suggest fade. Put/call ratios at extremes. Everyone bullish. Classic reversal setup. S&P 5,200 target.",
            "If earnings disappoint even slightly, multiple compression takes S&P 10-12% lower. Valuation assumes perfection. Risky near highs.",
            "Margin debt elevated again. Leverage will be forced to unwind on any volatility spike. Crash risk elevated.",
            "Economic data has been slowing. Market not discounting recession risk properly. Mega-cap strength masking weakness.",
        ],
        "Quant": [
            "Breadth deteriorating: only 38% of S&P 500 components above 50-day MA. Historical analog: when breadth falls below 40% mid-bull, index corrects 8-12% before resuming.",
            "Earnings revision breadth at -15%. Forward P/E at 21x — 1 SD above 20Y mean. Rate-adjusted valuation (equity risk premium) at 15Y low.",
            "Systematic positioning: CTA exposure near max long. Risk parity funds at high equity weight. Any vol spike triggers mechanical de-risking.",
            "Put/call ratio collapsed to 0.65. Extreme complacency historically precedes 5-8% corrections within 30 days. Vol surface pricing in continued calm.",
        ],
        "Risk Manager": [
            "Concentration risk: top 10 names = 35% of index. If any 2-3 miss earnings, index impact outsized vs historical norms. Earnings season binary risk.",
            "Credit spread early warning: HY spreads widening 50bps over 30 days historically precedes equity correction by 4-6 weeks. Monitor IG and HY spreads.",
            "Liquidity risk: market depth in S&P futures at 40% of pre-2022 levels. Thin markets amplify moves. Gap risk elevated on macro surprises.",
            "Pension fund rebalancing: end-of-quarter equity trim estimated at $40-60B. Systematic selling pressure over next 5 trading days.",
        ],
    },
    "NASDAQ": {
        "Macro Bull": [
            "AI adoption accelerating. Cloud capex cycles supporting mega-cap Tech profitability. Next 3-5 years look strong.",
            "Valuations reflect genuine technology revolution. Software margins 40-50% higher than historical average. Quality premium warranted.",
            "Fed pivot to cutting rates is Nasdaq tailor-made. Growth stocks outperform after rate cuts. 2026 could be a screamer.",
            "Energy transition and EV ramps creating secular tailwinds. Battery tech, semiconductors, autonomous driving—all driving Tech upside.",
        ],
        "Technical Bear": [
            "Nasdaq chart shows topping behavior. Lower highs on daily despite higher closes. Deteriorating momentum setup.",
            "Semiconductor index rolling over despite chip strength narrative. SOX index lagging Nasdaq significantly. Breadth deteriorating.",
            "Resistance at 18,500 has failed twice. Next test likely to break down toward 17,800-18,000 support zone.",
            "QQQ options show dealer short build. Options market positioning typical of mean reversion. 5-7% pullback likely.",
        ],
        "Geopolitical Analyst": [
            "Taiwan is 92% of advanced chip supply. Any China escalation creates supply catastrophe. Nasdaq vulnerable to single headline.",
            "Chip export restrictions already baked in but could tighten further. Tech supply chains need diversification that takes years.",
            "Military tensions create secular Tech demand (defense spending). But short-term headline risk remains asymmetric to upside.",
            "Cyber war risk elevated. Power grid attacks, data breaches could spike volatility. Tech hardware unaffected but sentiment fragile.",
        ],
        "Retail Sentiment": [
            "AI hype driving retail into Tech again after the losses of 2022. Everyone believes Nvidia, Tesla, Broadcom are going to 10x.",
            "Options market showing retail buying call spreads. New retail enthusiasm for Tech could extend rally meaningfully.",
            "Social media sentiment on meme stocks rebounding. Retail risk appetite returning. Could run to 19,000+ on momentum alone.",
            "Fear of missing out on AI rally is driving retail cash into QQQ. This is crowded but momentum can persist longer.",
        ],
        "Contrarian": [
            "Tech valuations still expensive even after rally. Paying 30x earnings for 10% growth is not attractive at this rate of return.",
            "Mega-cap Tech dominance leads to concentration risk. When rotation happens, it will be violent. Short Nasdaq, long small caps.",
            "AI capex cycle unsustainable without proof of ROI. If mega-cap tech fails to monetize AI, 40% downside comes fast.",
            "Market ignoring valuation risk. Beta to duration—when 10-year hits 5%, Tech faces headwind. Defensive positioning warranted.",
        ],
        "Quant": [
            "Mag-7 concentration at 33% of index weight. Historical analog: when top-7 concentration exceeds 30%, subsequent 12-month returns average +3% vs +14% for equal-weight.",
            "Semis (SOX) rolling over — historically leads NASDAQ by 6-8 weeks. AI capex cycle showing first signs of digestion in supply chain data.",
            "Options skew in QQQ: 25-delta put vol 4pts above call vol. Institutional hedge demand rising. Smart money protecting gains.",
            "NDX-SPX ratio at 1.8x — near 3Y high. Historically mean-reverts with NASDAQ underperforming. Rotation risk real.",
        ],
        "Risk Manager": [
            "AI capex cycle risk: hyperscaler CapEx totaling $350B in 2026. If ROI underwhelms by Q2 earnings, narrative shift could be violent. Concentration + sentiment = amplified downside.",
            "Duration risk elevated: NDX effective duration ~25Y equivalent. 50bps rate rise = 12% theoretical headwind. Rate sensitivity highest since 2021 peak.",
            "Single-stock concentration in top 5 holdings creates idiosyncratic risk. Any regulatory action against MSFT, GOOGL, or AAPL creates index-level impact.",
            "Short interest at multi-year low: 1.2% of float on average. No short-covering fuel for further rally. Asymmetric risk to downside.",
        ],
    },
    "BTC": {
        "Macro Bull": [
            "Bitcoin halving in April removes 50% of miner inflation. Historical data shows 10-12 month lag to price recognition. $100k+ incoming.",
            "Institutional adoption accelerating. Spot ETF approval proved institutional demand. MicroStrategy, Blackrock accumulating. Structural bid.",
            "Inflation fears resurfacing. Bitcoin narrative as inflation hedge gaining traction. Store of value thesis intact despite recent macro calm.",
            "Geopolitical fragmentation drives non-USD asset demand. Central banks diversifying into Bitcoin. BRICS narrative supporting crypto.",
        ],
        "Technical Bear": [
            "Parabolic move from $42k to $72k screams bubble. RSI 82, MACD overbought. Pullback to $55k likely before next leg.",
            "Resistance at $75k being tested but failing. Volume profile shows weak conviction. Sell-off could cascade to $50k support.",
            "On-chain metrics show whale distribution. Large holders trimming positions. Dead cat bounce setup. Be careful here.",
            "Bitcoin dominance declining. Altcoin strength suggests Bitcoin weakness coming. Rotation into altcoins = risk-off for Bitcoin.",
        ],
        "Geopolitical Analyst": [
            "Bitcoin adoption by non-US central banks continues. Russia, China, India narrative supports structural demand. Long-term bullish.",
            "Sanctions regime driving BRICS nations into crypto. Bitcoin as reserve asset narrative gaining credibility. $80k+ achievable.",
            "Regulatory risk in US still overhang. Any harsh crypto regulations could trigger 20-30% pullback. Watch SEC action carefully.",
            "Cyber warfare risk creates volatility. But Bitcoin as digital gold becomes more valuable in uncertain geopolitical environment.",
        ],
        "Retail Sentiment": [
            "Bitcoin hype reaching fever pitch on social media. Every retail trader calling for six figures by year-end. FOMO massive.",
            "Retail call buying at highs. Options markets show extreme bullish sentiment. Risk/reward asymmetric to downside at these levels.",
            "Retail losing money on leverage trades. Every pullback gets bought on dip. Retail conviction still strong but leverage risky.",
            "Tiktok creators pounding the table on Bitcoin. New retail entrants buying tops. Classic bubble warning signs present.",
        ],
        "Contrarian": [
            "Halving is priced in already. New ATH before halving is unusual. Dump likely after the 'sell the news' event. Target $50k.",
            "Bitcoin utility case still unproven. Using Bitcoin to pay for coffee costs more in fees than it saves. Speculative asset only.",
            "Valuation detached from fundamentals. $72k Bitcoin requires $8 trillion+ market cap narrative. Unrealistic in current macro.",
            "Regulatory crackdown still possible. If US bans crypto, Bitcoin crashes. Risk/reward terrible at these levels. Fade the rally.",
        ],
        "Quant": [
            "On-chain: exchange outflows at 6-month high. Historically precedes 15-25% rallies. MVRV ratio at 1.8 — below overheated territory of 3.0.",
            "Realized vol at 45% vs implied vol 52%. Elevated vol risk premium suggests market makers are hedging — historically a contra-indicator for further downside.",
            "Hash rate at ATH. Miner capitulation absent. SOPR above 1.0 — coins being spent at profit, no panic selling detected.",
            "Funding rates normalized after de-leveraging. Open interest rebuild beginning. Setup mirrors pre-rally structure from Oct 2023.",
        ],
        "Risk Manager": [
            "Regulatory tail risk elevated: SEC and DOJ actions pending against 3 major exchanges. Binary event risk — could gap down 20-30% on adverse ruling.",
            "Mt. Gox repayment overhang: 140K BTC to be distributed. Large holders may sell. Flow risk real over next 60 days. Position sizing critical.",
            "Exchange solvency risk: concentration of BTC on top-3 exchanges creates systemic exposure. Cold storage allocation recommended for core positions.",
            "ETF outflow risk: if spot ETFs see sustained daily outflows >$500M, forced selling creates cascading pressure. Monitor daily flow data.",
        ],
    },
    "ETH": {
        "Macro Bull": [
            "Ethereum as settlement layer gaining institutional adoption. Layer 2 scaling solutions driving real utility. Valuation rerating happening.",
            "Staking yield providing 3-4% returns. Institutional treasury management considering ETH. Structural demand building.",
            "DeFi ecosystem growing exponentially. Ethereum network value increasing. Correlation to BTC declining—ETH has its own thesis.",
            "Shanghai upgrade proved staking works. Ethereum becoming more like a bond. Yield appeal extends buyer base beyond speculators.",
        ],
        "Technical Bear": [
            "Ethereum lagging Bitcoin despite fundamentals. Relative weakness suggests institutional preference for Bitcoin. $2,200 support test likely.",
            "Divergence between ETH and BTC widening. Chart shows lower highs. Breakout failed at $3,500. Retest of $2,500 coming.",
            "Volume declining into recent strength. MACD rolling over. Setup suggests 15-20% pullback. Shorter-term downtrend intact.",
            "Options market showing dealer short positioning. Typical reversal setup. Pullback to $2,200 before next run.",
        ],
        "Geopolitical Analyst": [
            "Ethereum faces regulatory risk if classified as security. SEC action could crater Ethereum worse than Bitcoin.",
            "Cryptocurrency regulation in G7 nations could hurt Ethereum adoption. But global crypto adoption continuing regardless.",
            "China's blockchain ambitions could support Ethereum narrative if they compete on innovation rather than ban.",
            "Cyber attacks on Ethereum network are ongoing risk. But security improving. Long-term fundamentals intact despite headline risk.",
        ],
        "Retail Sentiment": [
            "Retail FOMO on Ethereum after Bitcoin rally. Everyone loading up on ETH for leverage exposure to crypto. Momentum strong.",
            "Options buying suggests retail bullish. Call spreads at all-time highs. Retail trying to own more leverage with less capital.",
            "Social media Ethereum sentiment hitting 2-year highs. Retail convinced of yield thesis. New money flowing in.",
            "Ethereum cult growing on crypto Twitter. Religious fervor for Ethereum 2.0 narrative. Momentum extends a while longer likely.",
        ],
        "Contrarian": [
            "Ethereum utility case still weak. Token velocity declining. Overvalued relative to actual usage metrics. $1,500-$2,000 is fair value.",
            "Staking yield is negative real return. If inflation reaccelerates, yield becomes 0 in real terms. Bond substitute doesn't work.",
            "Regulatory overhang worse for Ethereum than Bitcoin. If SEC wins lawsuit, Ethereum tanks. Binary risk/reward unacceptable.",
            "Bitcoin dominance thesis suggests Ethereum underperforms. Own Bitcoin, not Ethereum. Liquidity could evaporate in risk-off.",
        ],
        "Quant": [
            "ETH/BTC ratio at 0.055 — near cycle low. Historically, ETH outperforms when this ratio rebounds from support. Statistical mean-reversion case.",
            "Gas fees declining — reduced network utilization. On-chain DEX volume down 35% from peak. Fundamental activity not supporting current price.",
            "Staking yield at 3.8% creates floor of institutional demand. Net supply deflationary since Merge. Long-term supply dynamics favorable.",
            "ETH futures basis (3-month annualized) at 8%. Healthy positive basis = organic demand, not leverage. Constructive for sustained rally.",
        ],
        "Risk Manager": [
            "Smart contract exploit risk: $8B locked in DeFi protocols. Historical rate: 2-3 major exploits per year causing 15-30% ETH selloffs.",
            "Regulatory classification risk: SEC's ETH security classification case unresolved. Adverse ruling would trigger exchange delistings and institutional exit.",
            "Bridge hack risk: cross-chain bridges hold $15B in ETH. Bridge exploits have historically caused 10-20% corrections within 48 hours.",
            "Staking concentration: top 3 validators control 35% of staked ETH. Centralization risk increasing. Potential regulatory target.",
        ],
    },
}

class MiroFishDebate:
    def __init__(self, instrument: str, market_data: Dict[str, Any]):
        self.instrument = instrument
        self.label = INSTRUMENTS[instrument]["label"]
        self.market_data = market_data
        self.agents_state = {agent: {"rounds": [], "final_position": None, "confidence": 0} for agent in AGENTS}
        self.sentiment_by_round = []

    def get_random_argument(self, agent: str, is_contrarian_round_1: bool = False) -> str:
        """Select argument template based on market conditions."""
        templates = ARGUMENT_TEMPLATES.get(self.instrument, {}).get(agent, ["Market conditions support continued movement."])
        return random.choice(templates)

    def run_round_1(self) -> Dict[str, Any]:
        """Initial positions based on base bullish bias and market data."""
        for agent in AGENTS:
            if agent == "Contrarian":
                position = "BEARISH"  # Contrarian starts bearish
                confidence = random.randint(70, 85)
            else:
                # Bias toward instrument base bullish %
                base_bullish = INSTRUMENTS[self.instrument]["base_bullish"]
                rand_val = random.randint(0, 100)
                if rand_val < base_bullish:
                    position = "BULLISH"
                    confidence = random.randint(70, 88)
                elif rand_val < base_bullish + 10:
                    position = "NEUTRAL"
                    confidence = random.randint(50, 70)
                else:
                    position = "BEARISH"
                    confidence = random.randint(65, 80)

            argument = self.get_random_argument(agent, is_contrarian_round_1=(agent == "Contrarian"))
            self.agents_state[agent]["rounds"].append({
                "round": 1,
                "position": position,
                "argument": argument
            })

        return self._calculate_sentiment()

    def run_round_2(self) -> Dict[str, Any]:
        """Cross-examination round where agents respond to aggregate positions."""
        round_1_sentiment = self._calculate_sentiment()
        majority_bullish = round_1_sentiment > 50

        for agent in AGENTS:
            current_position = self.agents_state[agent]["rounds"][-1]["position"]

            # If majority bullish and agent is bearish, strengthen counter-argument
            # If majority bearish and agent is bullish, sharpen the bull case
            if majority_bullish and current_position == "BEARISH":
                argument = self.get_random_argument(agent) + " However, near-term consolidation likely."
            elif not majority_bullish and current_position == "BULLISH":
                argument = self.get_random_argument(agent) + " This pullback presents opportunity."
            else:
                argument = self.get_random_argument(agent)

            # Slight probability of position shift in round 2
            position_shift = random.random()
            if position_shift < 0.15:
                current_position = self._shift_position(current_position, direction="soften")

            self.agents_state[agent]["rounds"].append({
                "round": 2,
                "position": current_position,
                "argument": argument
            })

        return self._calculate_sentiment()

    def run_round_3(self) -> Dict[str, Any]:
        """Final positions with potential consensus effects."""
        round_2_sentiment = self._calculate_sentiment()
        positions_r2 = [self.agents_state[agent]["rounds"][-1]["position"] for agent in AGENTS]
        bullish_count = positions_r2.count("BULLISH")

        # Consensus effect: if 4/5 agree, dissenter has 40% chance to soften
        if bullish_count >= 4:
            for agent in AGENTS:
                if self.agents_state[agent]["rounds"][-1]["position"] == "BEARISH":
                    if random.random() < 0.40:
                        self.agents_state[agent]["rounds"][-1]["position"] = "NEUTRAL"
        elif bullish_count <= 1:
            for agent in AGENTS:
                if self.agents_state[agent]["rounds"][-1]["position"] == "BULLISH":
                    if random.random() < 0.40:
                        self.agents_state[agent]["rounds"][-1]["position"] = "NEUTRAL"

        # Final arguments
        for agent in AGENTS:
            current_position = self.agents_state[agent]["rounds"][-1]["position"]
            argument = self.get_random_argument(agent)

            # Add conviction language
            if current_position == "BULLISH":
                argument += " Maintaining bullish conviction."
            elif current_position == "BEARISH":
                argument += " Bearish thesis intact."
            else:
                argument += " Balanced view warranted here."

            self.agents_state[agent]["rounds"].append({
                "round": 3,
                "position": current_position,
                "argument": argument
            })
            self.agents_state[agent]["final_position"] = current_position
            self.agents_state[agent]["confidence"] = random.randint(70, 88)

        return self._calculate_sentiment()

    def run_round_4(self) -> Dict[str, Any]:
        """Stress test round — each agent applies their worst-case scenario."""
        for agent in AGENTS:
            current_position = self.agents_state[agent]["rounds"][-1]["position"]
            argument = self.get_random_argument(agent)

            # Add stress test language
            if current_position == "BULLISH":
                argument += " But stress test worst-case: if macro deteriorates 50%, support at -10%."
            elif current_position == "BEARISH":
                argument += " Stress test upside: if sentiment shift occurs, resistance at +8%."
            else:
                argument += " Stress test shows wide range of outcomes: -12% to +15% plausible."

            self.agents_state[agent]["rounds"].append({
                "round": 4,
                "position": current_position,
                "argument": argument
            })

        return self._calculate_sentiment()

    def run_round_5(self) -> Dict[str, Any]:
        """Final verdict round — agents give conviction rating (0-100) and summary."""
        for agent in AGENTS:
            current_position = self.agents_state[agent]["rounds"][-1]["position"]
            argument = self.get_random_argument(agent)

            # Add conviction rating language
            conviction_min = 65 if current_position in ["BULLISH", "BEARISH"] else 50
            conviction_max = 90 if current_position in ["BULLISH", "BEARISH"] else 75
            conviction = random.randint(conviction_min, conviction_max)

            if current_position == "BULLISH":
                argument += f" Final conviction: {conviction}% bullish. Key trade trigger: break of resistance."
            elif current_position == "BEARISH":
                argument += f" Final conviction: {conviction}% bearish. Key trade trigger: break of support."
            else:
                argument += f" Final conviction: {conviction}% on balanced view. Monitor both directions."

            self.agents_state[agent]["rounds"].append({
                "round": 5,
                "position": current_position,
                "argument": argument
            })
            self.agents_state[agent]["final_position"] = current_position
            self.agents_state[agent]["confidence"] = conviction

        return self._calculate_sentiment()

    def _calculate_sentiment(self) -> float:
        """Calculate weighted sentiment from current positions."""
        total_score = 0.0
        for agent in AGENTS:
            if self.agents_state[agent]["rounds"]:
                position = self.agents_state[agent]["rounds"][-1]["position"]
                if position == "BULLISH":
                    score = 100
                elif position == "BEARISH":
                    score = 0
                else:
                    score = 50
                weight = AGENT_WEIGHTS[agent]
                total_score += score * weight

        return total_score

    def _shift_position(self, current: str, direction: str = "soften") -> str:
        """Shift position toward center (soften) or maintain."""
        if direction == "soften":
            if current == "BULLISH":
                return "NEUTRAL" if random.random() < 0.5 else "BULLISH"
            elif current == "BEARISH":
                return "NEUTRAL" if random.random() < 0.5 else "BEARISH"
        return current

    def get_output(self) -> Dict[str, Any]:
        """Generate JSON output for this debate."""
        round_1_sent = self._get_sentiment_for_round(1)
        round_2_sent = self._get_sentiment_for_round(2)
        round_3_sent = self._get_sentiment_for_round(3)
        round_4_sent = self._get_sentiment_for_round(4)
        round_5_sent = self._get_sentiment_for_round(5)

        final_positions = [self.agents_state[agent]["final_position"] for agent in AGENTS]
        bullish_count = final_positions.count("BULLISH")
        bearish_count = final_positions.count("BEARISH")
        neutral_count = final_positions.count("NEUTRAL")

        # Generate narratives
        top_narrative = self._generate_top_narrative()
        skeptic_counter = self._generate_skeptic_counter()

        agents_output = []
        for agent in AGENTS:
            agents_output.append({
                "name": agent,
                "final_position": self.agents_state[agent]["final_position"],
                "confidence": self.agents_state[agent]["confidence"],
                "rounds": self.agents_state[agent]["rounds"]
            })

        return {
            "label": self.label,
            "consensus_bullish_pct": round(round_5_sent, 0),
            "agents_bullish": bullish_count,
            "agents_bearish": bearish_count,
            "agents_neutral": neutral_count,
            "top_narrative": top_narrative,
            "skeptic_counter": skeptic_counter,
            "sentiment_by_round": [round(round_1_sent, 0), round(round_2_sent, 0), round(round_3_sent, 0), round(round_4_sent, 0), round(round_5_sent, 0)],
            "agents": agents_output
        }

    def _get_sentiment_for_round(self, round_num: int) -> float:
        """Calculate sentiment for specific round."""
        total_score = 0.0
        for agent in AGENTS:
            if len(self.agents_state[agent]["rounds"]) >= round_num:
                position = self.agents_state[agent]["rounds"][round_num - 1]["position"]
                if position == "BULLISH":
                    score = 100
                elif position == "BEARISH":
                    score = 0
                else:
                    score = 50
                weight = AGENT_WEIGHTS[agent]
                total_score += score * weight
        return total_score

    def _generate_top_narrative(self) -> str:
        """Generate bullish narrative from macro bull and retail sentiment."""
        macro_bull_args = self.agents_state["Macro Bull"]["rounds"]
        if macro_bull_args:
            macro_arg = macro_bull_args[-1]["argument"]
            # Extract key phrase (take first 100 chars or first sentence)
            narrative = macro_arg[:120] + ("..." if len(macro_arg) > 120 else "")
            return narrative
        return "Market positioning favors continued strength."

    def _generate_skeptic_counter(self) -> str:
        """Generate bearish counter from technical bear."""
        tech_bear_args = self.agents_state["Technical Bear"]["rounds"]
        if tech_bear_args:
            tech_arg = tech_bear_args[-1]["argument"]
            counter = tech_arg[:120] + ("..." if len(tech_arg) > 120 else "")
            return counter
        return "Technical indicators suggest near-term pullback risk."


def load_market_data() -> Dict[str, Any]:
    """Load live market data if available, otherwise return defaults."""
    data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "live_data.json")
    if os.path.exists(data_path):
        try:
            with open(data_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def main():
    """Main simulation runner."""
    print("[MIROFISH] Starting multi-agent debate simulation...")

    # Seed RNG based on date for consistency within a day
    today = datetime.date.today()
    random.seed(today.toordinal())

    # Load market data
    market_data = load_market_data()
    print(f"[MIROFISH] Market data loaded. {len(market_data)} instruments in context.")

    # Ensure output directory exists
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(output_dir, exist_ok=True)

    # Run debates for each instrument
    debates_output = {}
    for instrument, metadata in INSTRUMENTS.items():
        print(f"[MIROFISH] Running 5-round debate for {instrument}...")

        debate = MiroFishDebate(instrument, market_data)

        # Run five rounds
        s1 = debate.run_round_1()
        print(f"  Round 1 (Initial): {s1:.0f}% bullish")

        s2 = debate.run_round_2()
        print(f"  Round 2 (Cross-exam): {s2:.0f}% bullish")

        s3 = debate.run_round_3()
        print(f"  Round 3 (Consensus): {s3:.0f}% bullish")

        s4 = debate.run_round_4()
        print(f"  Round 4 (Stress test): {s4:.0f}% bullish")

        s5 = debate.run_round_5()
        print(f"  Round 5 (Final verdict): {s5:.0f}% bullish")

        debates_output[instrument] = debate.get_output()

    # Generate output JSON
    timestamp = datetime.datetime.utcnow().isoformat() + "Z"
    output = {
        "timestamp": timestamp,
        "sim_metadata": {
            "version": "2.0",
            "agents_per_instrument": len(AGENTS),
            "rounds": 5,
            "total_debates": len(INSTRUMENTS)
        },
        "debates": debates_output
    }

    # Write to output file
    output_path = os.path.join(output_dir, "mirofish_debates.json")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n[MIROFISH] Simulation complete. Output written to {output_path}")
    print(f"[MIROFISH] Summary:")
    for instrument, debate in debates_output.items():
        consensus = debate["consensus_bullish_pct"]
        print(f"  {instrument}: {consensus:.0f}% bullish consensus")


if __name__ == "__main__":
    main()
