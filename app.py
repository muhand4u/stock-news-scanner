import os
import requests
import pandas as pd
import yfinance as yf
import streamlit as st
from collections import defaultdict
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv()

API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")

st.set_page_config(
    page_title="Stock News Sentiment Scanner",
    layout="wide"
)

st.title("📈 Stock News Sentiment Scanner")
st.write("Scans market news and ranks bullish/bearish stocks using Alpha Vantage sentiment data.")


def get_price_trend(ticker):
    try:
        data = yf.download(ticker, period="5d", interval="1d", progress=False)

        if len(data) < 2:
            return 0.0

        start = data["Close"].iloc[0].item()
        end = data["Close"].iloc[-1].item()

        return (end - start) / start

    except:
        return 0.0


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

def fetch_and_score_news(limit=100, min_articles=2, min_relevance=0.75, min_sentiment=0.10):
    url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&limit={limit}&apikey={API_KEY}"

    response = requests.get(url)
    data = response.json()

    if "feed" not in data:
        return pd.DataFrame(), data

    articles = data["feed"]

    ticker_scores = defaultdict(float)
    ticker_counts = defaultdict(int)
    ticker_titles = defaultdict(list)
    seen_titles = set()

    source_weights = {
        "Reuters": 1.5,
        "Bloomberg": 1.5,
        "MarketWatch": 1.3,
        "Wall Street Journal": 1.4,
        "CNBC": 1.2,
        "Investing.com": 1.0,
        "Benzinga": 0.9,
        "Motley Fool": 0.8,
    }

    for article in articles:
        source = article.get("source", "")
        source_weight = source_weights.get(source, 1.0)

        title = article.get("title", "")

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

            if relevance < min_relevance:
                continue

            if abs(score) < min_sentiment:
                continue

            weighted_score = score * relevance * time_weight * source_weight

            ticker_scores[ticker] += weighted_score
            ticker_counts[ticker] += 1
            ticker_titles[ticker].append((title, weighted_score, relevance))

    rows = []

    for ticker, total_score in ticker_scores.items():
        count = ticker_counts[ticker]

        if count < min_articles:
            continue

        avg_score = total_score / count
        final_score = avg_score * (1 + (count - 1) * 0.5)

        trend = get_price_trend(ticker)
        volume_ratio = get_volume_ratio(ticker)

        if final_score > 0:
            sentiment = "Bullish"
            confirmed = "Yes" if trend > 0 else "No"
        else:
            sentiment = "Bearish"
            confirmed = "Yes" if trend < 0 else "No"

        sorted_titles = sorted(
            ticker_titles[ticker],
            key=lambda x: x[1],
            reverse=True
        )

        seen = set()
        clean_titles = []

        for title, weighted_score, relevance in sorted_titles:
            if title not in seen:
                clean_titles.append(f"({relevance:.2f}) {title}")
                seen.add(title)

        top_headlines = "\n".join(clean_titles[:3]) if clean_titles else "No high-relevance headlines available."

        rows.append({
            "Ticker": ticker,
            "Signal": sentiment,
            "Final Score": round(final_score, 3),
            "Articles": count,
            "Price Trend 5D": trend,
            "Volume Ratio": volume_ratio,
            "Confirmed by Price": confirmed,
            "Top Headlines": top_headlines
        })

    df = pd.DataFrame(rows)

    if not df.empty:
        df = df.sort_values("Final Score", ascending=False)

    return df, None


if not API_KEY:
    st.error("API key not found. Add ALPHA_VANTAGE_API_KEY to your .env file.")
    st.stop()


st.sidebar.header("Scanner Settings")

limit = st.sidebar.slider("Article Limit", 50, 1000, 100, step=50)
min_articles = st.sidebar.slider("Minimum Articles", 1, 5, 2)
min_relevance = st.sidebar.slider("Minimum Relevance", 0.0, 1.0, 0.75, step=0.05)
min_sentiment = st.sidebar.slider("Minimum Sentiment Strength", 0.0, 1.0, 0.10, step=0.05)

run_scan = st.button("Run Scan")

if run_scan:
    scan_time = datetime.now().strftime("%b %d, %Y %I:%M %p")
    st.info(f"Scan Time: {scan_time}")

    with st.spinner("Scanning market news..."):
        df, error = fetch_and_score_news(
            limit=limit,
            min_articles=min_articles,
            min_relevance=min_relevance,
            min_sentiment=min_sentiment
        )

    if error:
        st.error(error)
    elif df.empty:
        st.warning("No stocks matched the current filters.")
    else:
        bullish_df = df[df["Signal"] == "Bullish"].copy()
        bearish_df = df[df["Signal"] == "Bearish"].copy()

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Stocks Found", len(df))
        col2.metric("Bullish Stocks", len(bullish_df))
        col3.metric("Bearish Stocks", len(bearish_df))

        def show_stock_cards(title, data):
            st.subheader(title)

            if data.empty:
                st.write("No stocks found.")
                return

            for _, row in data.iterrows():
                with st.expander(f"{row['Ticker']} | Score: {row['Final Score']} | Articles: {row['Articles']}"):
                    st.write(f"**Signal:** {row['Signal']}")
                    st.write(f"**Price Trend 5D:** {row['Price Trend 5D']:.2%}")
                    st.write(f"**Volume Ratio:** {row['Volume Ratio']:.2f}x")
                    st.write(f"**Confirmed by Price:** {row['Confirmed by Price']}")

                    st.write("**Top Headlines:**")
                    for headline in row["Top Headlines"].split("\n"):
                        st.write(f"- {headline}")


        show_stock_cards(
            "Top Bullish Stocks",
            bullish_df.sort_values("Final Score", ascending=False)
        )

        show_stock_cards(
            "Top Bearish Stocks",
            bearish_df.sort_values("Final Score", ascending=True)
        )
else:
    st.write("Click **Run Scan** to start.")