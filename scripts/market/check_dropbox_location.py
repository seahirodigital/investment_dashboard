"""Dropbox APIのルートと指定済みファイルの存在を確認する。"""

import os
import requests


def main():
    response = requests.post(
        "https://api.dropboxapi.com/oauth2/token",
        data={"grant_type": "refresh_token", "refresh_token": os.environ["DROPBOX_REFRESH_TOKEN"].strip()},
        auth=(os.environ["DROPBOX_APP_KEY"].strip(), os.environ["DROPBOX_APP_SECRET"].strip()),
        timeout=30,
    )
    response.raise_for_status()
    headers = {"Authorization": "Bearer " + response.json()["access_token"]}
    result = requests.post("https://api.dropboxapi.com/2/files/list_folder", headers=headers, json={"path": "", "limit": 100}, timeout=30)
    if not result.ok:
        print(f"ルート一覧確認: HTTP {result.status_code}")
        return
    entries = result.json().get("entries", [])
    expected = {"アプリ", "apps", "remotely-save", "option_analysis"}
    print("ルートの対象フォルダ:", sorted(e["name"] for e in entries if e.get("name", "").casefold() in expected))
    for prefix in ("/アプリ", "/Apps"):
        path = prefix + "/remotely-save/Obsidian4dropbox/10_investment_insight/investment_insight.md"
        item = requests.post("https://api.dropboxapi.com/2/files/get_metadata", headers=headers, json={"path": path}, timeout=30)
        print(f"既存の投資ノート {prefix}: {'確認' if item.ok else '見つからないかアクセス不可'} (HTTP {item.status_code})")


if __name__ == "__main__":
    main()
