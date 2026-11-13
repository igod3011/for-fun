"""Research Engine (Crypto Strategy Discovery Engine): finds, tests and ranks ways to make money. It never trades.

  python -m memebot.research.run            score every registered hypothesis, write memebot/research/RANKING.md
  python -m memebot.research.run --offline  only use data already on disk

score.py       one scorer and one set of gates for every hypothesis (net expectancy, CI, time halves, Monte Carlo)
data.py        data sources: the collector's cohort, Binance public futures data (cached in research_data/)
hypotheses.py  the registry: each hypothesis states its mechanism and its kill criterion BEFORE it is scored
"""
