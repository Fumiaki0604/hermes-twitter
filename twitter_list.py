#!/Users/apple/.local/bin/python3.11
"""
Twitter リストのタイムラインを取得してDiscordに直接投稿するスクリプト。
"""
import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from twikit import Client


def _load_dotenv():
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "")
DISCORD_CHANNEL_ID = os.environ.get("DISCORD_CHANNEL_ID", "")

CONFIG_PATH = Path.home() / ".hermes-twitter" / "config.json"
COOKIES_PATH = Path.home() / ".hermes-twitter" / "cookies.json"

LM_STUDIO_BASE = "http://localhost:1234"
LM_MODEL = "qwen/qwen3.6-35b-a3b"
TOP_PICK_COUNT = 3  # 📌 を付ける件数

MAX_PER_USER = 3
FETCH_COUNT = 50
SHOW_TOTAL = 10


def load_config():
    if not CONFIG_PATH.exists():
        print("ERROR: config not found.", file=sys.stderr)
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text())


def fetch_list_tweets(list_id: str) -> list[dict]:
    client = Client(language="ja-JP")
    client.load_cookies(str(COOKIES_PATH))

    tweets = client.get_list_tweets(list_id, count=FETCH_COUNT)

    user_counts = defaultdict(int)
    results = []
    for tweet in tweets:
        sn = tweet.user.screen_name
        if user_counts[sn] >= MAX_PER_USER:
            continue
        user_counts[sn] += 1

        rt = getattr(tweet, "retweeted_tweet", None)
        results.append({
            "id": tweet.id,
            "user": tweet.user.name,
            "screen_name": sn,
            "avatar": tweet.user.profile_image_url,
            "text": tweet.full_text or tweet.text,
            "likes": tweet.favorite_count,
            "retweets": tweet.retweet_count,
            "is_rt": rt is not None,
            "rt_user": rt.user.screen_name if rt else None,
            "rt_user_name": rt.user.name if rt else None,
            "rt_avatar": rt.user.profile_image_url if rt else None,
            "rt_text": (rt.full_text or rt.text) if rt else None,
            "rt_likes": rt.favorite_count if rt else 0,
            "rt_retweets": rt.retweet_count if rt else 0,
        })

        if len(results) >= SHOW_TOTAL:
            break

    return results


def _lm_studio_request(system: str, user: str, max_tokens: int) -> str:
    payload = json.dumps({
        "model": LM_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        f"{LM_STUDIO_BASE}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as res:
        data = json.load(res)
    return data["choices"][0]["message"]["content"].strip()


def rank_by_importance(tweets: list[dict]) -> list[dict]:
    """LLMにAI/テック業界の重要度を判定させ、重要な順に並べ替える。失敗時は元の順序のまま返す。"""
    if not tweets:
        return tweets

    numbered = "\n".join(
        f"{i+1}. @{t['screen_name']}: "
        f"{(t['rt_text'] if t['is_rt'] and t['rt_text'] else t['text'])[:200]}"
        f" (❤{t['rt_likes'] if t['is_rt'] else t['likes']} "
        f"🔁{t['rt_retweets'] if t['is_rt'] else t['retweets']})"
        for i, t in enumerate(tweets)
    )
    system = (
        "You rank tweets for an AI/tech news digest by how important and worth reading they are "
        "for someone tracking AI and tech industry developments. "
        "Prioritize: concrete news (releases, research, funding, major announcements), "
        "insightful technical commentary, high engagement as a secondary signal. "
        "Deprioritize: personal chatter, vague one-liners, jokes without substance, ads. "
        "Answer with ONLY a JSON array of the tweet numbers, most important first, "
        "including every number exactly once. Example: [3, 1, 5, 2, 4]"
    )
    try:
        raw = _lm_studio_request(system, numbered, max_tokens=4000)
        if not raw:
            raw = _lm_studio_request(system, numbered, max_tokens=8000)
        start = raw.find("[")
        end = raw.rfind("]") + 1
        order = json.loads(raw[start:end])
        seen = set()
        ranked = []
        for n in order:
            idx = n - 1
            if 0 <= idx < len(tweets) and idx not in seen:
                seen.add(idx)
                ranked.append(tweets[idx])
        for i, t in enumerate(tweets):
            if i not in seen:
                ranked.append(t)
        return ranked
    except Exception as e:
        print(f"[rank] failed, keeping original order: {e}", file=sys.stderr)
        return tweets


def build_embeds(tweets: list[dict], top_pick_count: int = 0) -> list[dict]:
    embeds = []
    for i, t in enumerate(tweets):
        url = f"https://twitter.com/{t['screen_name']}/status/{t['id']}"

        pin = "📌 " if i < top_pick_count else ""

        if t["is_rt"] and t["rt_text"]:
            rt_text = t["rt_text"].replace("\n", " ")
            if len(rt_text) > 200:
                rt_text = rt_text[:200] + "…"
            embed = {
                "color": 0x1D9BF0,  # Twitter blue for RT
                "author": {
                    "name": f"{pin}🔁 {t['user']} (@{t['screen_name']}) がリツイート",
                    "icon_url": t["avatar"],
                },
                "description": (
                    f"**@{t['rt_user']}** ({t['rt_user_name']})\n"
                    f"{rt_text}"
                ),
                "footer": {
                    "text": f"❤ {t['rt_likes']}  🔁 {t['rt_retweets']}"
                },
                "url": url,
            }
        else:
            text = t["text"].replace("\n", " ")
            if len(text) > 200:
                text = text[:200] + "…"
            embed = {
                "color": 0x17BF63,  # green for original
                "author": {
                    "name": f"{pin}{t['user']} (@{t['screen_name']})",
                    "icon_url": t["avatar"],
                },
                "description": text,
                "footer": {
                    "text": f"❤ {t['likes']}  🔁 {t['retweets']}"
                },
                "url": url,
            }
        embeds.append(embed)
    return embeds


def post_to_discord(header: str, embeds: list[dict]):
    api_url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
    headers = {
        "Authorization": f"Bot {DISCORD_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "HermesBot/1.0",
    }

    # ヘッダーメッセージ
    data = json.dumps({"content": header}).encode("utf-8")
    urllib.request.urlopen(urllib.request.Request(api_url, data=data, headers=headers, method="POST"))

    # Embedは10件ずつ
    for i in range(0, len(embeds), 10):
        chunk = embeds[i:i+10]
        data = json.dumps({"embeds": chunk}).encode("utf-8")
        urllib.request.urlopen(urllib.request.Request(api_url, data=data, headers=headers, method="POST"))


def main():
    if not DISCORD_TOKEN or not DISCORD_CHANNEL_ID:
        print("ERROR: DISCORD_TOKEN / DISCORD_CHANNEL_ID not set (check .env).", file=sys.stderr)
        sys.exit(1)

    cfg = load_config()
    list_id = cfg.get("list_id")
    if not list_id:
        print("ERROR: list_id not set in config.json", file=sys.stderr)
        sys.exit(1)

    now = datetime.now().strftime("%Y/%m/%d %H:%M")
    tweets = fetch_list_tweets(list_id)
    tweets = rank_by_importance(tweets)
    embeds = build_embeds(tweets, top_pick_count=TOP_PICK_COUNT)
    post_to_discord(f"**📋 Twitterリスト更新 ({now})** — 重要度順", embeds)
    print(f"Discord に投稿しました ({len(tweets)}件)")


if __name__ == "__main__":
    main()
