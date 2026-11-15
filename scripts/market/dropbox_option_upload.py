"""Gemini分析結果をDropbox APIに保存し、内容のハッシュを検証する。"""

import hashlib
import json
import os
import unicodedata

import requests

DROPBOX_DIRECTORY = "/アプリ/remotely-save/Obsidian4dropbox/10_investment_insight/100_daily/option"


def content_hash(data):
    combined = hashlib.sha256()
    for index in range(0, len(data), 4 * 1024 * 1024):
        combined.update(hashlib.sha256(data[index:index + 4 * 1024 * 1024]).digest())
    return combined.hexdigest()


def upload_option_report(report_text, date_string, environ=None, session=requests):
    environ = os.environ if environ is None else environ
    keys = ("DROPBOX_APP_KEY", "DROPBOX_APP_SECRET", "DROPBOX_REFRESH_TOKEN")
    credentials = {key: environ.get(key, "").strip() for key in keys}
    missing = [key for key in keys if not credentials[key]]
    if missing:
        raise RuntimeError(f"Dropbox認証のGitHub Secretsが未設定です: {', '.join(missing)}")
    compact = date_string.replace("-", "")
    if len(compact) != 8 or not compact.isdigit():
        raise ValueError("分析日付はYYYY-MM-DD形式で指定してください")
    data = report_text.encode("utf-8")
    if not data.strip():
        raise ValueError("Dropboxに保存する分析結果が空です")
    token_response = session.post(
        "https://api.dropboxapi.com/oauth2/token",
        data={"grant_type": "refresh_token", "refresh_token": credentials["DROPBOX_REFRESH_TOKEN"]},
        auth=(credentials["DROPBOX_APP_KEY"], credentials["DROPBOX_APP_SECRET"]),
        timeout=30,
    )
    if not token_response.ok:
        try:
            error_data = token_response.json()
            error_code = error_data.get("error", "")
            description = error_data.get("error_description", "")
        except ValueError:
            error_code = ""
            description = ""
        if error_code not in {"invalid_request", "invalid_client", "invalid_grant", "unauthorized_client", "unsupported_grant_type", "invalid_scope"}:
            error_code = "unknown"
        description = str(description).lower()
        categories = [word for word in ("malformed", "expired", "revoked", "invalid", "mismatch", "not found", "app key", "refresh token") if word in description]
        raise RuntimeError(f"Dropbox認証に失敗しました: HTTP {token_response.status_code}, error={error_code}, 分類={categories}")
    token = token_response.json().get("access_token")
    if not token:
        raise RuntimeError("Dropbox認証応答にアクセストークンがありません")
    folder = environ.get("DROPBOX_OPTION_DIRECTORY", DROPBOX_DIRECTORY).rstrip("/")
    path = unicodedata.normalize("NFC", f"{folder}/{compact}_option_analysis.md")
    response = session.post(
        "https://content.dropboxapi.com/2/files/upload",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/octet-stream", "Dropbox-API-Arg": json.dumps({"path": path, "mode": "add", "autorename": False, "mute": False}, ensure_ascii=True)},
        data=data,
        timeout=60,
    )
    if not response.ok:
        raise RuntimeError(f"Dropbox保存に失敗しました: HTTP {response.status_code}。保存先や同名ファイルを確認してください")
    metadata = response.json()
    if metadata.get("content_hash") != content_hash(data):
        raise RuntimeError("Dropbox保存結果の内容ハッシュが一致しません")
    print(f"✅ Dropboxに分析結果を保存・照合しました: {metadata.get('path_display', path)}")
    return metadata
