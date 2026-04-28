import os
import requests
from collections import defaultdict
from dotenv import load_dotenv
from datetime import datetime, timezone

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
ticker_titles = defaultdict(list)

seen_titles = set()

MIN_ARTICLES = 2
MIN_RELEVANCE = 0.3
MIN_SENTIMENT = 0.05

for article in articles:
    title = article.get("title", "")

    # skip duplicate article titles
    if title in seen_titles:
        continue
    seen_titles.add(title)

    time_str = article.get("time_published")

    if time_str:
        published_time = datetime.strptime(time_str, "%Y%m%dT%H%M%S")
        published_time = published_time.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        hours_old = (now - published_time).total_seconds() / 3600

        time_weight = max(0.3, 1 - (hours_old / 48))
    else:
        time_weight = 1

    for t in article.get("ticker_sentiment", []):
        ticker = t["ticker"]
        score = float(t["ticker_sentiment_score"])
        relevance = float(t["relevance_score"])

        if relevance < MIN_RELEVANCE:
            continue

        if abs(score) < MIN_SENTIMENT:
            continue

        weighted_score = score * relevance * time_weight

        ticker_scores[ticker] += weighted_score
        ticker_counts[ticker] += 1
        ticker_titles[ticker].append(title)

filtered = {}

for ticker, total_score in ticker_scores.items():
    count = ticker_counts[ticker]

    if count < MIN_ARTICLES:
        continue

    avg_score = total_score / count
    final_score = avg_score * (1 + (count - 1) * 0.5)

    filtered[ticker] = final_score

bullish = sorted(
    [(ticker, score) for ticker, score in filtered.items() if score > 0],
    key=lambda x: x[1],
    reverse=True
)

bearish = sorted(
    [(ticker, score) for ticker, score in filtered.items() if score < 0],
    key=lambda x: x[1]
)

print("\n=== Top Bullish Stocks ===")
for ticker, score in bullish[:5]:
    print(f"\n{ticker}: {score:.3f} (articles: {ticker_counts[ticker]})")
    print("Reasons:")
    for title in ticker_titles[ticker][:3]:
        print(f"  - {title}")

print("\n=== Top Bearish Stocks ===")
for ticker, score in bearish[:5]:
    print(f"\n{ticker}: {score:.3f} (articles: {ticker_counts[ticker]})")
    print("Reasons:")
    for title in ticker_titles[ticker][:3]:
        print(f"  - {title}")