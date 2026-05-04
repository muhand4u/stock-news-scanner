'''
1. Load API key
2. Get news from Alpha Vantage
3. Remove duplicate articles
4. Calculate how recent each article is
5. Read ticker sentiment
6. Filter weak signals
7. Score each stock
8. Require at least 2 articles
9. Rank bullish and bearish stocks
10. Print the reasons
'''

# Import necessary libraries
import os # to read from computer 
import requests # to connect to Alpha Vantage API
from collections import defaultdict # Make dictionaries for counting and storing scores
from dotenv import load_dotenv # to load environment variables from .env file
from datetime import datetime, timezone # to handle article publication times and calculate how old the articles are
import yfinance as yf # to get stock data (not used in this code but can be useful for future improvements)
from datetime import datetime, timezone

# Function to get the price trend of a stock over the last 5 days.
def get_price_trend(ticker):
    try:
        data = yf.download(ticker, period="5d", interval="1d", progress=False)
        
        if len(data) < 2:
            return 0.0

        start = data["Close"].iloc[0].item()
        end = data["Close"].iloc[-1].item()
        
        return (end - start) / start  # now always float

    except:
        return 0.0

# Function to get the volume ratio of today's volume compared to the average volume of the last 20 days. 
# This can help identify unusual trading activity that may confirm the sentiment from the news.
def get_volume_ratio(ticker):
    try:
        data = yf.download(ticker, period="30d", interval="1d", progress=False)

        if len(data) < 21:
            return 0.0

        today_volume = data["Volume"].iloc[-1].item()
        avg_volume = data["Volume"].iloc[-21:-1].mean().item()

        if avg_volume == 0:
            return 0.0

        return today_volume / avg_volume

    except:
        return 0.0


# Load API key from .env file
load_dotenv()
API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")

if not API_KEY:
    print("Error: API key not found. Add it to .env")
    exit()

# Connect to Alpha Vantage API and get news sentiment data
#url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&apikey={API_KEY}"
url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&limit=100&apikey={API_KEY}"

# Send request and parse response
response = requests.get(url)
data = response.json()

# Check if news are existing in the response
if "feed" not in data:
    print("Error:", data)
    exit()

# Store articles
articles = data["feed"]

# Create storage dictionaries
ticker_scores = defaultdict(float) # total sentiment score per stock
ticker_counts = defaultdict(int) # Number of articles per stock
ticker_titles = defaultdict(list) # Article titles that explain the score

# Track seen article titles to avoid duplicates
seen_titles = set()

# Define thresholds for filtering articles and calculating scores
MIN_ARTICLES = 2 # Minimum number of articles mentioning a stock to consider it
MIN_RELEVANCE = 0.75 # Ignore weak mentions.
MIN_SENTIMENT = 0.10 # Ignore almost-neutral sentiment.
MIN_RELEVANCE_FOR_HEADLINE = 0.75 # Minimum relevance score for an article headline

# Define weights for different news sources. More reputable sources get higher weight. 
# This can be adjusted based on your preferences and experience with the quality of news from each source.
SOURCE_WEIGHTS = {
    "Reuters": 1.5,
    "Bloomberg": 1.5,
    "MarketWatch": 1.3,
    "Wall Street Journal": 1.4,
    "CNBC": 1.2,
    "Investing.com": 1.0,
    "Benzinga": 0.9,
    "Motley Fool": 0.8,
}

# Loop through articles and calculate weighted sentiment scores for each stock ticker
for article in articles:
    # Get the source of the article and apply a weight based on the source. 
    # If the source is not in our predefined list, use a default weight of 1.0.
    source = article.get("source", "")
    source_weight = SOURCE_WEIGHTS.get(source, 1.0)
    
    # Get the title of the article, default to empty string if not available
    title = article.get("title", "") 

    # skip duplicate article titles
    if title in seen_titles:
        continue
    seen_titles.add(title)
    
    # Get article publish time 
    time_str = article.get("time_published")

    # weight the article depending on how recent it is. More recent articles have more weight, older articles have less weight. 
    # Articles older than 48 hours get a minimum weight of 0.3 to avoid completely ignoring them.
    if time_str:
        published_time = datetime.strptime(time_str, "%Y%m%dT%H%M%S")
        published_time = published_time.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        hours_old = (now - published_time).total_seconds() / 3600

        time_weight = max(0.3, 1 - (hours_old / 48))
    else:
        time_weight = 1

    # check if the article has ticker sentiment data and loop through each ticker mentioned in the article
    for t in article.get("ticker_sentiment", []):
        ticker = t["ticker"] # Get the stock ticker symbol mentioned in the article      
        score = float(t["ticker_sentiment_score"]) #bullish or bearish sentiment score for the ticker in this article
        relevance = float(t["relevance_score"]) # How important thee ticker is to the article. 

        if relevance < MIN_RELEVANCE: # if the ticker is not relevant enough to the article, skip it
            continue

        if abs(score) < MIN_SENTIMENT: # if the sentiment score is too close to neutral, skip it
            continue
        
        weighted_score = score * relevance * time_weight * source_weight # Calculate the weighted score for this ticker in this article

        ticker_scores[ticker] += weighted_score
        ticker_counts[ticker] += 1

        # Only add headline if strong enough
        if relevance >= MIN_RELEVANCE_FOR_HEADLINE:
            ticker_titles[ticker].append((title, weighted_score, relevance))


# After processing all articles, calculate the average score for each ticker and apply a multiplier based on the number of articles mentioning that ticker. 
# This way, tickers mentioned in more articles get a higher final score, but we still require a minimum number of articles to consider a ticker valid.
filtered = {}

for ticker, total_score in ticker_scores.items():
    count = ticker_counts[ticker]

    if count < MIN_ARTICLES:
        continue

    avg_score = total_score / count
    final_score = avg_score * (1 + (count - 1) * 0.5)

    filtered[ticker] = final_score

# list bullish stocks (positive scores) and bearish stocks (negative scores), sorted by score. Show the top 5 of each.
bullish = sorted(
    [(ticker, score) for ticker, score in filtered.items() if score > 0],
    key=lambda x: x[1],
    reverse=True
)

bearish = sorted(
    [(ticker, score) for ticker, score in filtered.items() if score < 0],
    key=lambda x: x[1]
)

# Print the results with explanations (article titles) for the top 5 bullish and bearish stocks
now = datetime.now(timezone.utc)
local_time = now.astimezone()  # convert to your local time

print(f"\n=== Scan Time: {local_time.strftime('%b %d, %Y %I:%M %p')} ===")
print(f"Total Articles Processed: {len(articles)}")

print("\n=== Top Bullish Stocks ===")
for ticker, score in bullish[:5]:
    trend = get_price_trend(ticker)
    volume_ratio = get_volume_ratio(ticker)

    print(f"\n{ticker}: {score:.3f} (articles: {ticker_counts[ticker]})")
    print(f"Price Trend (5d): {trend:.2%}")

    # Print trend confirmation
    if trend > 0:
        print("✔ Confirmed by price")
    else:
        print("⚠ Not confirmed")
    
    # Print volume confirmation
    print(f"Volume Ratio: {volume_ratio:.2f}x")
    if volume_ratio >= 1.5:
        print("🔥 High volume interest")
    else:
        print("Normal/low volume")

    # sort headlines by impact (highest score first)
    sorted_titles = sorted(
        ticker_titles[ticker],
        key=lambda x: x[1],
        reverse=True
    )

    # remove duplicates while keeping order
    seen = set()
    clean_titles = []

    for title, weighted_score, relevance in sorted_titles:
        if title not in seen:
            clean_titles.append((title, relevance))
            seen.add(title)

    if not clean_titles:
        print("Reasons: No high-relevance headlines available.")
    else:
        print("Reasons:")
        for title, relevance in clean_titles[:3]:
            print(f"  - ({relevance:.2f}) {title}")

print("\n=== Top Bearish Stocks ===")
for ticker, score in bearish[:5]:
    trend = get_price_trend(ticker)
    volume_ratio = get_volume_ratio(ticker)

    print(f"\n{ticker}: {score:.3f} (articles: {ticker_counts[ticker]})")
    print(f"Price Trend (5d): {trend:.2%}")

    # Print trend confirmation  
    if trend < 0:
        print("✔ Confirmed by price")
    else:
        print("⚠ Not confirmed")
    
    # Print volume confirmation
    print(f"Volume Ratio: {volume_ratio:.2f}x")
    if volume_ratio >= 1.5:
        print("🔥 High volume interest")
    else:
        print("Normal/low volume")


    # sort headlines by impact (highest score first)
    sorted_titles = sorted(
        ticker_titles[ticker],
        key=lambda x: x[1],
        reverse=True
    )

    # remove duplicates while keeping order
    seen = set()
    clean_titles = []

    for title, weighted_score, relevance in sorted_titles:
        if title not in seen:
            clean_titles.append((title, relevance))
            seen.add(title)

    if not clean_titles:
        print("Reasons: No high-relevance headlines available.")
    else:
        print("Reasons:")
        for title, relevance in clean_titles[:3]:
            print(f"  - ({relevance:.2f}) {title}")


