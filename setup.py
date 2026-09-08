#!/usr/bin/env python3
"""
初回セットアップ: Twitter 認証情報と List ID を設定する。
"""
import json
from pathlib import Path

config_dir = Path.home() / ".hermes-twitter"
config_dir.mkdir(exist_ok=True)
config_path = config_dir / "config.json"

print("=== Hermes Twitter セットアップ ===")
username = input("Twitterユーザー名 (@なし): ").strip()
email    = input("メールアドレス: ").strip()
password = input("パスワード: ").strip()
list_id  = input("Twitter List ID (空白でスキップ): ").strip()

config = {
    "username": username,
    "email": email,
    "password": password,
    "list_id": list_id or "",
}

config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False))
print(f"\n✓ 設定を保存しました: {config_path}")
print("次回から fetch_list.py で取得できます。")
