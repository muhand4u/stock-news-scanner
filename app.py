import os
import requests
import pandas as pd
import yfinance as yf
import streamlit as st
from collections import defaultdict
from dotenv import load_dotenv
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

load_dotenv()

API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")

st.set_page_config(
    page_title="Stock News Sentiment Scanner",
    layout="wide"
)

st.title("📈 Stock News Sentiment Scanner")
st.write("Scans market news and ranks bullish/bearish stocks using Alpha Vantage sentiment data.")

def get_current_price(ticker):
    try:
        data = yf.download(ticker, period="2d", interval="1d", progress=False)

        if data.empty:
            return 0.0

        return data["Close"].iloc[-1].item()

    except:
        return 0.0

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


def get_volume_data(ticker):
    try:
        data = yf.download(ticker, period="30d", interval="1d", progress=False)

        if len(data) < 21:
            return 0.0, 0, 0

        today_volume = data["Volume"].iloc[-1].item()
        avg_volume = data["Volume"].iloc[-21:-1].mean().item()

        if avg_volume == 0:
            return 0.0, today_volume, avg_volume

        volume_ratio = today_volume / avg_volume

        return volume_ratio, today_volume, avg_volume

    except:
        return 0.0, 0, 0

def get_price_history(ticker):
    try:
        data = yf.download(ticker, period="3mo", interval="1d", progress=False)

        if data.empty:
            return None

        return data["Close"]

    except:
        return None

def save_signal_history(df):
    history_file = Path("signal_history.csv")

    if df.empty:
        return

    df_to_save = df.copy()
    df_to_save["Scan Time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if history_file.exists():
        old_df = pd.read_csv(history_file)
        combined_df = pd.concat([old_df, df_to_save], ignore_index=True)
    else:
        combined_df = df_to_save

    combined_df.to_csv(history_file, index=False)

def fetch_and_score_news(limit=100, min_articles=2, min_relevance=0.75, min_sentiment=0.10, display_timezone="America/Los_Angeles"):
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
        article_time_display = "Unknown time"

        if time_str:
            published_time = datetime.strptime(time_str, "%Y%m%dT%H%M%S")
            published_time = published_time.replace(tzinfo=timezone.utc)
            
            article_time_display = published_time.astimezone(
                ZoneInfo(display_timezone)
            ).strftime("%b %d, %Y %I:%M %p")

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
            ticker_titles[ticker].append((title, weighted_score, relevance, article_time_display))

    rows = []

    for ticker, total_score in ticker_scores.items():
        count = ticker_counts[ticker]

        if count < min_articles:
            continue

        avg_score = total_score / count
        final_score = avg_score * (1 + (count - 1) * 0.5)

        trend = get_price_trend(ticker)
        volume_ratio, today_volume, avg_volume = get_volume_data(ticker)
        current_price = get_current_price(ticker)

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

        for title, weighted_score, relevance, article_time in sorted_titles:
            if title not in seen:
                clean_titles.append(f"({relevance:.2f}) [{article_time}] {title}")
                seen.add(title)

        top_headlines = "\n".join(clean_titles[:3]) if clean_titles else "No high-relevance headlines available."

        rows.append({
            "Ticker": ticker,
            "Signal": sentiment,
            "Final Score": round(final_score, 3),
            "Articles": count,
            "Price at Scan": current_price,
            "Price Trend 5D": trend,
            "Volume Ratio": volume_ratio,
            "Today Volume": int(today_volume),
            "Avg Volume 20D": int(avg_volume),
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

timezone_options = {
    "Pacific Time - San Diego / Los Angeles": "America/Los_Angeles",
    "Eastern Time - New York": "America/New_York",
    "Central Time - Chicago": "America/Chicago",
    "Mountain Time - Denver": "America/Denver",
    "UTC": "UTC",
    "London": "Europe/London",
    "Dubai": "Asia/Dubai",
    "Baghdad": "Asia/Baghdad",
}

selected_timezone_label = st.sidebar.selectbox(
    "Display Time Zone",
    list(timezone_options.keys())
)

selected_timezone = timezone_options[selected_timezone_label]


st.sidebar.header("Result Filters")

signal_filter = st.sidebar.selectbox(
    "Signal Type",
    ["All", "Bullish", "Bearish"]
)

confirmed_only = st.sidebar.checkbox("Confirmed by Price only")

high_volume_only = st.sidebar.checkbox("High Volume only (>= 1.5x)")

min_final_score = st.sidebar.slider(
    "Minimum Absolute Final Score",
    0.0, 2.0, 0.0, step=0.05
)


run_scan = st.button("Run Scan")

if run_scan:
    scan_time = datetime.now(ZoneInfo(selected_timezone)).strftime("%b %d, %Y %I:%M %p")
    st.info(f"Scan Time: {scan_time}")
    st.caption(f"Displayed timezone: {selected_timezone_label}")

    with st.spinner("Scanning market news..."):
        df, error = fetch_and_score_news(
            limit=limit,
            min_articles=min_articles,
            min_relevance=min_relevance,
            min_sentiment=min_sentiment,
            display_timezone=selected_timezone
        )

    if error:
        st.error(error)
    elif df.empty:
        st.warning("No stocks matched the current filters.")
    else:
        save_signal_history(df)

        filtered_df = df.copy() 

        if signal_filter != "All":
            filtered_df = filtered_df[filtered_df["Signal"] == signal_filter]
        if confirmed_only:
            filtered_df = filtered_df[filtered_df["Confirmed by Price"] == "Yes"]
        if high_volume_only:
            filtered_df = filtered_df[filtered_df["Volume Ratio"] >= 1.5]
        filtered_df = filtered_df[filtered_df["Final Score"].abs() >= min_final_score]

        bullish_df = filtered_df[filtered_df["Signal"] == "Bullish"].copy()
        bearish_df = filtered_df[filtered_df["Signal"] == "Bearish"].copy()

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Stocks Found", len(filtered_df))
        col2.metric("Bullish Stocks", len(bullish_df))
        col3.metric("Bearish Stocks", len(bearish_df))

        def signal_badge(signal, confirmed, volume_ratio):
            if signal == "Bullish" and confirmed == "Yes":
                return "🟢 Bullish Confirmed"
            elif signal == "Bullish":
                return "🟡 Bullish Not Confirmed"
            elif signal == "Bearish" and confirmed == "Yes":
                return "🔴 Bearish Confirmed"
            else:
                return "🟠 Bearish Not Confirmed"

        def show_stock_cards(title, data):
            st.subheader(title)

            if data.empty:
                st.write("No stocks found.")
                return

            for _, row in data.iterrows():
                badge = signal_badge(
                    row["Signal"],
                    row["Confirmed by Price"],
                    row["Volume Ratio"]
                )

                with st.expander(
                    f"{badge} | {row['Ticker']} | Score: {row['Final Score']} | Articles: {row['Articles']}"
                ):
                    st.write(f"**Signal:** {row['Signal']}")
                    st.write(f"**Price at Scan:** ${row['Price at Scan']:.2f}")
                    st.write(f"**Price Trend 5D:** {row['Price Trend 5D']:.2%}")
                    st.write(f"**Volume Ratio:** {row['Volume Ratio']:.2f}x")
                    if row["Volume Ratio"] >= 1.5:
                        st.write("🔥 **High volume interest**")
                    else:
                        st.write("⚪ Normal/low volume")
                    st.write(f"**Today Volume:** {row['Today Volume']:,}")
                    st.write(f"**Avg Volume 20D:** {row['Avg Volume 20D']:,}")
                    st.write(f"**Confirmed by Price:** {row['Confirmed by Price']}")

                    price_history = get_price_history(row["Ticker"])

                    if price_history is not None:
                        st.line_chart(price_history)
                    else:
                        st.write("No price chart available.")

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

        st.subheader("Signal History")
        history_file = Path("signal_history.csv")
        if history_file.exists():
            history_df = pd.read_csv(history_file)
            st.dataframe(history_df.tail(50), use_container_width=True)
        else:
            st.write("No history saved yet.")
        
else:
    st.write("Click **Run Scan** to start.")