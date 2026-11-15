"""日本市場の分析に使う、未調整の日足価格を取得する。"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import math
import time
from urllib.parse import quote

import requests

JST = timezone(timedelta(hours=9))
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def fetch_symbol(symbol):
    """取引所の日時に対応する日足だけを返し、欠損を補間しない。"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}"
    last_error = None
    for attempt in range(3):
        try:
            response = requests.get(url, params={"range": "3mo", "interval": "1d", "includePrePost": "false"}, headers=HEADERS, timeout=20)
            response.raise_for_status()
            chart = response.json()["chart"]
            item = chart["result"][0]
            bars = item["indicators"]["quote"][0]
            rows = []
            for i, stamp in enumerate(item.get("timestamp", [])):
                values = {key: (bars.get(key) or [])[i] for key in ("open", "close")}
                if any(v is None or not math.isfinite(float(v)) or float(v) <= 0 for v in values.values()):
                    continue
                rows.append({"date": datetime.fromtimestamp(stamp, JST).date().isoformat(), **{k: float(v) for k, v in values.items()}})
            return sorted(rows, key=lambda row: row["date"])
        except (requests.RequestException, ValueError, KeyError, TypeError, IndexError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(attempt + 1)
    print(f"株価取得失敗: {symbol}: {last_error}")
    return []


def build_summaries(raw, analysis_date, fetch=fetch_symbol):
    """日本株の取得率と日付を検証し、確定終値の比較を作成する。"""
    labels = {}
    for key in ("sectors", "semiconductor_jp", "topix100"):
        labels.update(raw.get(key, {}))
    symbols = {s for s in labels if s.endswith('.T')} | {"^N225", "1306.T", "2644.T"}
    topix = set(raw.get("topix100", {}))
    if not topix:
        raise ValueError("TOPIX100 の銘柄定義が空です")
    fetched = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(fetch, symbol): symbol for symbol in symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                fetched[symbol] = future.result()
            except Exception as exc:
                print(f"株価取得失敗: {symbol}: {exc}")
    intraday = {"date": analysis_date, "source": "Yahoo Finance 日足（未調整）", "tickers": {}}
    daily = {"latest_date": analysis_date, "source": "Yahoo Finance 日足（未調整）", "tickers": {}}
    index_rows = [row for row in fetched.get("^N225", []) if row["date"] <= analysis_date]
    if len(index_rows) < 2 or index_rows[-1]["date"] != analysis_date:
        raise ValueError("日経平均の当日と前営業日のデータがありません")
    previous_market_date = index_rows[-2]["date"]
    for symbol, rows in fetched.items():
        rows = [r for r in rows if r["date"] <= analysis_date]
        if len(rows) < 2 or rows[-1]["date"] != analysis_date or rows[-2]["date"] != previous_market_date:
            continue
        current, previous = rows[-1], rows[-2]
        close, opening, prev = current["close"], current["open"], previous["close"]
        pct = lambda p: round((close / p - 1) * 100, 2) if p else None
        intraday["tickers"][symbol] = {"name": labels.get(symbol, symbol), "date": analysis_date, "open": round(opening, 2), "close": round(close, 2), "previous_close": round(prev, 2), "previous_date": previous["date"], "intraday_pct": pct(opening), "daily_pct": pct(prev)}
        daily["tickers"][symbol] = {"name": labels.get(symbol, symbol), "date": analysis_date, "latest": round(close, 2), "daily_pct": pct(prev), "weekly_pct": pct(rows[-6]["close"]) if len(rows) >= 6 else None, "monthly_pct": pct(rows[-21]["close"]) if len(rows) >= 21 else None}
    missing_required = {"^N225", "1306.T", "2644.T"} - intraday["tickers"].keys()
    missing_topix = topix - intraday["tickers"].keys()
    if missing_required or len(missing_topix) > len(topix) * 0.05:
        raise ValueError(f"当日株価の検証失敗: 必須={sorted(missing_required)}, TOPIX100欠損={len(missing_topix)}/{len(topix)} {sorted(missing_topix)}")
    intraday["missing_topix100"] = sorted(missing_topix)
    ranking = sorted((intraday["tickers"][s] | {"symbol": s} for s in topix if s in intraday["tickers"]), key=lambda item: (-item["daily_pct"], item["symbol"]))
    intraday["topix100_ranking_high"] = ranking[:20]
    intraday["topix100_ranking_low"] = list(reversed(ranking[-20:]))
    print(f"日本株当日終値を検証: TOPIX100 {len(topix)-len(missing_topix)}/{len(topix)}, {analysis_date}")
    return intraday, daily


def fetch_us_futures(now=None):
    """米国先物は継続限月の最新値と時刻を明示する。"""
    now = now or datetime.now(timezone.utc)
    result = {}
    for symbol, name in (("NQ=F", "NQmain"), ("ES=F", "ESmain"), ("YM=F", "YMmain")):
        try:
            response = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}", params={"range": "5d", "interval": "5m"}, headers=HEADERS, timeout=20)
            response.raise_for_status()
            item = response.json()["chart"]["result"][0]
            meta = item["meta"]
            stamp = datetime.fromtimestamp(meta["regularMarketTime"], timezone.utc)
            price = float(meta["regularMarketPrice"])
            previous = float(meta["previousClose"])
            if not (0 <= (now - stamp).total_seconds() <= 86400 and math.isfinite(price) and price > 0 and previous > 0):
                continue
            result[symbol] = {"name": name, "latest": price, "as_of_jst": stamp.astimezone(JST).isoformat(), "previous_close": previous, "daily_pct": round((price / previous - 1) * 100, 2), "source": "Yahoo Finance 継続限月"}
        except (requests.RequestException, ValueError, KeyError, TypeError, IndexError) as exc:
            print(f"米国先物取得失敗: {symbol}: {exc}")
    return result
