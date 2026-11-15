"""Dropbox APIのルートと指定済みファイルの存在を確認する。"""

import json
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
    account = requests.post("https://api.dropboxapi.com/2/users/get_current_account", headers=headers, timeout=30)
    if account.ok:
        root_id = account.json().get("root_info", {}).get("root_namespace_id")
        if root_id:
            rooted_headers = dict(headers, **{"Dropbox-API-Path-Root": json.dumps({".tag": "root", "root": root_id})})
            rooted = requests.post("https://api.dropboxapi.com/2/files/list_folder", headers=rooted_headers, json={"path": "", "limit": 100}, timeout=30)
            print(f"アカウントルートへのアクセス: HTTP {rooted.status_code}")
            if rooted.ok:
                print("アカウントルートの項目数:", len(rooted.json().get("entries", [])))
    else:
        print(f"アカウントルート情報: HTTP {account.status_code}")
    result = requests.post("https://api.dropboxapi.com/2/files/list_folder", headers=headers, json={"path": "", "limit": 100}, timeout=30)
    if not result.ok:
        print(f"ルート一覧確認: HTTP {result.status_code}")
        return
    entries = result.json().get("entries", [])
    expected = {"アプリ", "apps", "remotely-save", "option_analysis", ".obsidian"}
    print("ルート項目数:", len(entries))
    print("ルートの対象フォルダ:", sorted(e["name"] for e in entries if e.get("name", "").casefold() in expected))
    for prefix in ("/アプリ", "/Apps"):
        path = prefix + "/remotely-save/Obsidian4dropbox/10_investment_insight/investment_insight.md"
        item = requests.post("https://api.dropboxapi.com/2/files/get_metadata", headers=headers, json={"path": path}, timeout=30)
        print(f"既存の投資ノート {prefix}: {'確認' if item.ok else '見つからないかアクセス不可'} (HTTP {item.status_code})")


if __name__ == "__main__":
    main()
