#!/Users/apple/.local/bin/python3.11
"""
Twitter リストのタイムラインを取得して要約出力するスクリプト。
Hermes cron から呼び出される。
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from twikit import Client

CONFIG_PATH = Path.home() / ".hermes-twitter" / "config.json"
COOKIES_PATH = Path.home() / ".hermes-twitter" / "cookies.json"


def load_config():
    if not CONFIG_PATH.exists():
        print("ERROR: config not found. Run setup.py first.", file=sys.stderr)
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text())


def fetch_list_tweets(list_id: str, count: int = 20) -> list[dict]:
    client = Client(language="ja-JP")
    client.load_cookies(str(COOKIES_PATH))

    tweets = client.get_list_tweets(list_id, count=count)

    results = []
    for tweet in tweets:
        results.append({
            "user": tweet.user.name,
            "screen_name": tweet.user.screen_name,
            "tweet_id": str(tweet.id),
            "text": tweet.full_text or tweet.text,
            "likes": tweet.favorite_count,
            "retweets": tweet.retweet_count,
            "created_at": str(tweet.created_at),
        })
    return results


def format_output(tweets: list[dict], max_items: int = 10) -> str:
    now = datetime.now().strftime("%Y/%m/%d %H:%M")
    lines = [f"📋 Twitterリスト更新 ({now})\n"]

    for i, t in enumerate(tweets[:max_items], 1):
        text = t["text"].replace("\n", " ")
        if len(text) > 100:
            text = text[:100] + "…"
        url = f"https://x.com/{t['screen_name']}/status/{t['tweet_id']}" if t.get("tweet_id") else ""
        lines.append(
            f"{i}. @{t['screen_name']} ({t['user']})\n"
            + (f"   URL: {url}\n" if url else "")
            + f"   {text}\n"
            f"   ❤ {t['likes']}  🔁 {t['retweets']}"
        )

    return "\n\n".join(lines)


def main():
    cfg = load_config()
    list_id = cfg.get("list_id")
    if not list_id:
        print("ERROR: list_id not set in config.json", file=sys.stderr)
        sys.exit(1)

    tweets = fetch_list_tweets(list_id)
    print(format_output(tweets))


if __name__ == "__main__":
    main()
