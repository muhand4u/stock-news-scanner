import os
import requests
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")

if not API_KEY:
    print("Error: API key not found. Add it to .env")
    exit()

url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&apikey={API_KEY}"

response = requests.get(url)
data = response.json()

if "feed" not in data:
    print("Error:", data)
    exit()

articles = data["feed"]

ticker_scores = defaultdict(float)
ticker_counts = defaultdict(int)

MIN_ARTICLES = 2
MIN_RELEVANCE = 0.3
MIN_SENTIMENT = 0.05

for article in articles:
    for t in article.get("ticker_sentiment", []):
        ticker = t["ticker"]
        score = float(t["ticker_sentiment_score"])
        relevance = float(t["relevance_score"])

        if relevance < MIN_RELEVANCE:
            continue

        if abs(score) < MIN_SENTIMENT:
            continue

        weighted_score = score * relevance

        ticker_scores[ticker] += weighted_score
        ticker_counts[ticker] += 1

filtered = {
    ticker: score
    for ticker, score in ticker_scores.items()
    if ticker_counts[ticker] >= MIN_ARTICLES
}

sorted_tickers = sorted(filtered.items(), key=lambda x: x[1], reverse=True)

print("\n=== Top Bullish Stocks ===")
for ticker, score in sorted_tickers[:5]:
    print(f"{ticker}: {score:.3f} (articles: {ticker_counts[ticker]})")

print("\n=== Top Bearish Stocks ===")
for ticker, score in sorted_tickers[-5:]:
    print(f"{ticker}: {score:.3f} (articles: {ticker_counts[ticker]})")