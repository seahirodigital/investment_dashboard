"""OCI上のMooViewを検証し、株価データ描画後の画面を撮影する。"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import requests
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


DEFAULT_BASE_URL = "https://mooview-oci.taild87712.ts.net"
DEFAULT_PROBE_SYMBOLS = ("JP.1306", "US.VOO")
API_RETRY_INTERVAL_SECONDS = 5


def _normalize_base_url(value: str) -> str:
    base_url = value.strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError(f"HTTPSのMooView URLを指定してください: {value}")
    return base_url


def _request_json_with_retry(
    session: requests.Session,
    *,
    url: str,
    payload: dict[str, Any],
    timeout_seconds: int,
    deadline: float,
    validator: Callable[[dict[str, Any]], bool],
    label: str,
) -> dict[str, Any]:
    attempt = 0
    last_error = "応答がありません"

    while time.monotonic() < deadline:
        attempt += 1
        try:
            response = session.post(url, json=payload, timeout=timeout_seconds)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError(f"JSONオブジェクトではありません: {type(data).__name__}")
            if validator(data):
                print(f"[成功] {label}: {url}（試行{attempt}回）")
                return data
            last_error = json.dumps(data, ensure_ascii=False)[:500]
        except Exception as exc:
            last_error = str(exc)

        print(
            f"[待機] {label}が未完了です。"
            f"{API_RETRY_INTERVAL_SECONDS}秒後に再試行します: {last_error}"
        )
        time.sleep(API_RETRY_INTERVAL_SECONDS)

    raise RuntimeError(f"{label}の待機時間を超過しました: {last_error}")


def _verify_market_data(
    base_url: str,
    timeout_seconds: int,
    probe_symbols: tuple[str, ...],
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    session = requests.Session()
    session.headers.update({"User-Agent": "investment-dashboard-oci-capture/1.0"})

    status = _request_json_with_retry(
        session,
        url=f"{base_url}/api/moomoo/status",
        payload={},
        timeout_seconds=20,
        deadline=deadline,
        validator=lambda data: data.get("connected") is True,
        label="OpenD接続確認",
    )

    probes: list[dict[str, Any]] = []
    for symbol in probe_symbols:
        quote = _request_json_with_retry(
            session,
            url=f"{base_url}/api/moomoo/quote",
            payload={"symbol": symbol},
            timeout_seconds=35,
            deadline=deadline,
            validator=lambda data: (
                data.get("success") is True
                and isinstance(data.get("price"), (int, float))
            ),
            label=f"{symbol}の実価格取得",
        )
        kline = _request_json_with_retry(
            session,
            url=f"{base_url}/api/moomoo/kline",
            payload={"symbol": symbol, "timeframe": "1d", "reqNum": 2},
            timeout_seconds=50,
            deadline=deadline,
            validator=lambda data: (
                data.get("success") is True
                and isinstance(data.get("candles"), list)
                and len(data["candles"]) >= 1
            ),
            label=f"{symbol}の日足取得",
        )
        candles = kline.get("candles") or []
        probes.append(
            {
                "symbol": symbol,
                "price": quote.get("price"),
                "candleCount": len(candles),
                "lastCandle": candles[-1] if candles else None,
            }
        )

    return {
        "connected": status.get("connected"),
        "opendHost": status.get("opendHost"),
        "opendPort": status.get("opendPort"),
        "probes": probes,
    }


def _normalize_storage_symbol(raw_symbol: str) -> str:
    symbol = raw_symbol.strip().upper()
    if symbol.startswith("US."):
        return symbol[3:]
    if symbol.endswith(".US"):
        return symbol[:-3]
    if symbol.endswith(".T"):
        return f"JP.{symbol[:-2]}"
    if symbol.endswith(".JP"):
        return f"JP.{symbol[:-3]}"
    if symbol.startswith("JP."):
        return symbol
    if re.fullmatch(r"\d{3,5}[A-Z]?", symbol):
        return f"JP.{symbol}"
    return symbol


def _stored_symbol_operands(raw_symbol: str) -> list[str]:
    symbol = raw_symbol.strip()
    if not symbol or symbol.startswith("BASKET:"):
        return []
    return [
        normalized
        for normalized in (
            _normalize_storage_symbol(part)
            for part in re.split(r"[+\-*/]", symbol)
        )
        if normalized
    ]


def _preload_top_chart_candles(
    base_url: str,
    *,
    minimum_chart_count: int,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int], dict[str, Any]]:
    session = requests.Session()
    session.headers.update({"User-Agent": "investment-dashboard-oci-capture/1.0"})
    workspace_response = session.get(
        f"{base_url}/api/workspace-settings?profile=desktop",
        timeout=30,
    )
    workspace_response.raise_for_status()
    workspace = workspace_response.json()
    panels = ((workspace.get("settings") or {}).get("panels") or [])[:minimum_chart_count]
    if len(panels) < minimum_chart_count:
        raise RuntimeError(
            f"OCI共有設定の上段チャートが不足しています: {len(panels)}画面"
        )

    targets: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for panel in panels:
        timeframe = str(panel.get("timeframe") or "5m")
        raw_symbols = [
            str(panel.get("symbol") or ""),
            *(str(symbol) for symbol in (panel.get("comparisonSymbols") or [])),
        ]
        for raw_symbol in raw_symbols:
            for operand in _stored_symbol_operands(raw_symbol):
                target = (operand, timeframe)
                if target in seen:
                    continue
                seen.add(target)
                targets.append(target)

    cache: dict[str, list[dict[str, Any]]] = {}
    timestamps: dict[str, int] = {}
    failures: list[dict[str, str]] = []
    fetched: list[dict[str, Any]] = []

    print(f"[取得] 上段2チャート用の時系列データを先行取得します: {len(targets)}銘柄")
    for index, (symbol, timeframe) in enumerate(targets, start=1):
        try:
            response = session.post(
                f"{base_url}/api/moomoo/kline",
                json={"symbol": symbol, "timeframe": timeframe, "reqNum": 150},
                timeout=50,
            )
            response.raise_for_status()
            data = response.json()
            candles = data.get("candles") if isinstance(data, dict) else None
            if (
                not isinstance(data, dict)
                or data.get("success") is not True
                or not isinstance(candles, list)
                or len(candles) < 10
            ):
                raise RuntimeError(json.dumps(data, ensure_ascii=False)[:500])

            cache_key = f"{symbol}-{timeframe}"
            cache[cache_key] = candles[-180:]
            timestamps[cache_key] = int(time.time() * 1000)
            fetched.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "candleCount": len(candles),
                }
            )
            print(
                f"[成功] 先行取得 {index}/{len(targets)}: "
                f"{symbol} {timeframe} {len(candles)}本"
            )
        except Exception as exc:
            failures.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "error": str(exc),
                }
            )
            print(
                f"[許容] 先行取得 {index}/{len(targets)}: "
                f"{symbol} {timeframe} は取得できませんでした: {exc}"
            )

    if len(fetched) < 3:
        raise RuntimeError(
            "上段チャートの先行取得成功数が不足しています: "
            + json.dumps(
                {
                    "success": len(fetched),
                    "failure": len(failures),
                },
                ensure_ascii=False,
            )
        )

    return cache, timestamps, {
        "workspaceRevision": workspace.get("revision"),
        "targetCount": len(targets),
        "successCount": len(fetched),
        "failureCount": len(failures),
        "fetched": fetched,
        "failures": failures,
    }


def _inject_candle_cache(
    page: Page,
    cache: dict[str, list[dict[str, Any]]],
    timestamps: dict[str, int],
) -> int:
    return page.evaluate(
        """async ({ cache, timestamps }) => {
          const database = await new Promise((resolve, reject) => {
            const request = indexedDB.open('mooview_chart_candles_cache_v1', 1);
            request.onupgradeneeded = () => {
              if (!request.result.objectStoreNames.contains('values')) {
                request.result.createObjectStore('values');
              }
            };
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
          });

          await new Promise((resolve, reject) => {
            const transaction = database.transaction('values', 'readwrite');
            const store = transaction.objectStore('values');
            store.put(cache, 'candles');
            store.put(timestamps, 'meta');
            transaction.oncomplete = () => resolve();
            transaction.onerror = () => reject(transaction.error);
            transaction.onabort = () => reject(transaction.error);
          });
          database.close();
          return Object.keys(cache).length;
        }""",
        {"cache": cache, "timestamps": timestamps},
    )


def _chart_state(page: Page) -> dict[str, Any]:
    return page.evaluate(
        """() => {
          const bodyText = document.body?.innerText || '';
          const chartSvgs = Array.from(document.querySelectorAll('svg'))
            .map((svg) => {
              const rect = svg.getBoundingClientRect();
              const series = Array.from(svg.querySelectorAll('polyline[points]'))
                .map((line) => {
                  const points = (line.getAttribute('points') || '')
                    .trim()
                    .split(/\s+/)
                    .filter(Boolean)
                    .map((point) => {
                      const values = point.split(',');
                      return {
                        x: Number(values[0]),
                        y: Number(values[1]),
                      };
                    })
                    .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
                  const yValues = points.map((point) => point.y);
                  const ySpread = yValues.length > 0
                    ? Math.max(...yValues) - Math.min(...yValues)
                    : 0;
                  const uniqueYCount = new Set(
                    yValues.map((value) => Math.round(value * 10) / 10)
                  ).size;
                  return {
                    pointCount: points.length,
                    ySpread,
                    uniqueYCount,
                  };
                })
                .filter((line) => line.pointCount >= 2);
              const denseSeries = series.filter((line) => line.pointCount >= 10);
              const variedSeries = denseSeries.filter(
                (line) => line.ySpread >= 2 && line.uniqueYCount >= 4
              );
              return {
                x: rect.x + window.scrollX,
                y: rect.y + window.scrollY,
                width: rect.width,
                height: rect.height,
                seriesCount: series.length,
                denseSeriesCount: denseSeries.length,
                variedSeriesCount: variedSeries.length,
                minimumPointCount: series.length > 0
                  ? Math.min(...series.map((line) => line.pointCount))
                  : 0,
                maximumPointCount: series.length > 0
                  ? Math.max(...series.map((line) => line.pointCount))
                  : 0,
              };
            })
            .filter((chart) => chart.width >= 500 && chart.height >= 250)
            .sort((left, right) => left.y - right.y || left.x - right.x);

          return {
            url: window.location.href,
            title: document.title,
            bodyErrorVisible: bodyText.includes('画面が真っ黒になる代わりに'),
            chartCount: chartSvgs.length,
            charts: chartSvgs,
          };
        }"""
    )


def _wait_for_chart_shells(
    page: Page,
    *,
    timeout_seconds: int,
    minimum_chart_count: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_state: dict[str, Any] = {}

    while time.monotonic() < deadline:
        try:
            last_state = _chart_state(page)
        except Exception as exc:
            print(f"[待機] 共有設定反映後の画面再読込を待っています: {exc}")
            page.wait_for_timeout(2000)
            continue
        charts = last_state.get("charts") or []
        if (
            last_state.get("bodyErrorVisible") is False
            and len(charts) >= minimum_chart_count
        ):
            print(f"[成功] チャート枠を確認しました: {len(charts)}画面")
            return last_state

        print(f"[待機] チャート枠を待っています: 画面数={len(charts)}")
        page.wait_for_timeout(2000)

    raise RuntimeError(
        "比較チャート枠の表示待機時間を超過しました: "
        + json.dumps(last_state, ensure_ascii=False)[:1000]
    )


def _click_refresh_and_wait(
    page: Page,
    *,
    timeout_seconds: int,
    wait_seconds: int,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error = "更新ボタンが見つかりません"

    while time.monotonic() < deadline:
        try:
            refresh_button = page.get_by_role("button", name="更新", exact=True).first
            refresh_button.wait_for(state="visible", timeout=5000)
            refresh_button.click(timeout=5000)
            print(f"[操作] 更新ボタンを押しました。{wait_seconds}秒待機します。")
            page.wait_for_timeout(wait_seconds * 1000)
            return
        except PlaywrightTimeoutError as exc:
            last_error = str(exc)
            page.wait_for_timeout(1000)
        except Exception as exc:
            last_error = str(exc)
            page.wait_for_timeout(1000)

    raise RuntimeError(f"更新ボタンを押せませんでした: {last_error}")


def _assert_chart_data_ready(
    state: dict[str, Any],
    *,
    minimum_chart_count: int,
) -> dict[str, Any]:
    charts = (state.get("charts") or [])[:minimum_chart_count]
    failures: list[dict[str, Any]] = []

    for index, chart in enumerate(charts, start=1):
        series_count = int(chart.get("seriesCount", 0))
        required_varied_count = max(3, int(series_count * 0.7))
        varied_series_count = int(chart.get("variedSeriesCount", 0))
        if varied_series_count < required_varied_count:
            failures.append(
                {
                    "chart": index,
                    "seriesCount": series_count,
                    "denseSeriesCount": chart.get("denseSeriesCount", 0),
                    "variedSeriesCount": varied_series_count,
                    "requiredVariedCount": required_varied_count,
                    "minimumPointCount": chart.get("minimumPointCount", 0),
                    "maximumPointCount": chart.get("maximumPointCount", 0),
                }
            )

    if len(charts) < minimum_chart_count or failures:
        raise RuntimeError(
            "更新後も比較系列が直線状態です。撮影成功として扱いません: "
            + json.dumps(
                {
                    "chartCount": len(charts),
                    "failures": failures,
                },
                ensure_ascii=False,
            )
        )

    print(
        "[成功] 上段2チャートに十分な時系列点と値動きを確認しました: "
        + json.dumps(charts, ensure_ascii=False)
    )
    return state


def _top_chart_clip(
    chart_state: dict[str, Any],
    *,
    viewport_width: int,
    viewport_height: int,
) -> dict[str, float]:
    charts = (chart_state.get("charts") or [])[:2]
    if len(charts) < 2:
        raise RuntimeError("上段2チャートの撮影範囲を計算できませんでした。")

    left = max(0.0, min(chart["x"] for chart in charts) - 12.0)
    top = max(0.0, min(chart["y"] for chart in charts) - 44.0)
    right = min(
        float(viewport_width),
        max(chart["x"] + chart["width"] for chart in charts) + 12.0,
    )
    bottom = min(
        float(viewport_height),
        max(chart["y"] + chart["height"] for chart in charts) + 12.0,
    )
    return {
        "x": left,
        "y": top,
        "width": max(1.0, right - left),
        "height": max(1.0, bottom - top),
    }


def capture_mooview(
    *,
    base_url: str,
    output_dir: Path,
    timeout_seconds: int,
    refresh_wait_seconds: int,
    viewport_width: int,
    viewport_height: int,
    probe_symbols: tuple[str, ...],
) -> dict[str, Any]:
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "oci_mooview_capture_result.json"
    viewport_path = output_dir / "oci_mooview_viewport.png"
    top_charts_path = output_dir / "oci_mooview_top_charts.png"
    error_path = output_dir / "oci_mooview_error.png"

    result: dict[str, Any] = {
        "baseUrl": base_url,
        "capturedAtUtc": datetime.now(timezone.utc).isoformat(),
        "outputDirectory": str(output_dir),
        "success": False,
    }

    print(f"[開始] OCI MooViewを検証します: {base_url}")
    print(f"[出力先] {output_dir}")
    result["marketData"] = _verify_market_data(
        base_url,
        timeout_seconds,
        probe_symbols,
    )
    preloaded_cache, preloaded_timestamps, preload_summary = _preload_top_chart_candles(
        base_url,
        minimum_chart_count=2,
    )
    result["preload"] = preload_summary

    api_responses = {
        "total": 0,
        "success": 0,
        "failure": 0,
        "failureUrls": [],
    }
    console_errors: list[str] = []

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": viewport_width, "height": viewport_height},
                locale="ja-JP",
                timezone_id="Asia/Tokyo",
            )
            page = context.new_page()

            def track_response(response) -> None:
                if "/api/moomoo/" not in response.url:
                    return
                api_responses["total"] += 1
                if 200 <= response.status < 300:
                    api_responses["success"] += 1
                else:
                    api_responses["failure"] += 1
                    api_responses["failureUrls"].append(
                        {"status": response.status, "url": response.url}
                    )

            def track_console(message) -> None:
                if message.type == "error" and len(console_errors) < 30:
                    console_errors.append(message.text[:500])

            page.on("response", track_response)
            page.on("console", track_console)
            page.goto(base_url, wait_until="domcontentloaded", timeout=90000)
            page.evaluate("window.scrollTo(0, 0)")

            _wait_for_chart_shells(
                page,
                timeout_seconds=timeout_seconds,
                minimum_chart_count=2,
            )
            injected_count = _inject_candle_cache(
                page,
                preloaded_cache,
                preloaded_timestamps,
            )
            print(f"[成功] ブラウザーへ時系列キャッシュを投入しました: {injected_count}件")
            page.reload(wait_until="domcontentloaded", timeout=90000)
            page.evaluate("window.scrollTo(0, 0)")
            _wait_for_chart_shells(
                page,
                timeout_seconds=timeout_seconds,
                minimum_chart_count=2,
            )
            _click_refresh_and_wait(
                page,
                timeout_seconds=timeout_seconds,
                wait_seconds=refresh_wait_seconds,
            )
            chart_state = _chart_state(page)
            result["browser"] = {
                "page": chart_state,
                "apiResponses": api_responses,
                "consoleErrors": console_errors,
                "viewport": {
                    "width": viewport_width,
                    "height": viewport_height,
                },
                "refreshWaitSeconds": refresh_wait_seconds,
                "injectedCandleCacheCount": injected_count,
            }
            try:
                _assert_chart_data_ready(
                    chart_state,
                    minimum_chart_count=2,
                )
            except Exception:
                page.screenshot(path=str(error_path), full_page=False)
                result["errorScreenshot"] = str(error_path)
                raise

            page.screenshot(path=str(viewport_path), full_page=False)
            clip = _top_chart_clip(
                chart_state,
                viewport_width=viewport_width,
                viewport_height=viewport_height,
            )
            page.screenshot(path=str(top_charts_path), clip=clip)
            result["browser"].update({
                "topChartClip": clip,
            })
            result["files"] = {
                "viewport": str(viewport_path),
                "topCharts": str(top_charts_path),
                "result": str(result_path),
            }
            result["success"] = True

            context.close()
            browser.close()
    except Exception as exc:
        result["error"] = str(exc)
        if "page" in locals():
            try:
                result["browser"] = {
                    "page": _chart_state(page),
                    "apiResponses": api_responses,
                    "consoleErrors": console_errors,
                    "viewport": {
                        "width": viewport_width,
                        "height": viewport_height,
                    },
                    "refreshWaitSeconds": refresh_wait_seconds,
                }
                page.screenshot(path=str(error_path), full_page=False)
                result["errorScreenshot"] = str(error_path)
            except Exception:
                pass
        raise
    finally:
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print(f"[成功] 上段比較チャートを撮影しました: {top_charts_path}")
    print(f"[成功] 画面全体を撮影しました: {viewport_path}")
    print(f"[成功] 診断結果を書き出しました: {result_path}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OCI上のMooViewで実データ取得を待ち、比較チャートを撮影する"
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--refresh-wait-seconds", type=int, default=10)
    parser.add_argument("--viewport-width", type=int, default=1800)
    parser.add_argument("--viewport-height", type=int, default=1000)
    parser.add_argument(
        "--probe-symbols",
        default=",".join(DEFAULT_PROBE_SYMBOLS),
        help="実価格と日足を確認する銘柄をカンマ区切りで指定する",
    )
    args = parser.parse_args()

    if args.timeout_seconds < 30:
        parser.error("--timeout-seconds は30以上を指定してください。")
    if not 10 <= args.refresh_wait_seconds <= 30:
        parser.error("--refresh-wait-seconds は10以上30以下を指定してください。")
    if args.viewport_width < 1200 or args.viewport_height < 700:
        parser.error("撮影領域は幅1200以上、高さ700以上を指定してください。")

    probe_symbols = tuple(
        symbol.strip()
        for symbol in args.probe_symbols.split(",")
        if symbol.strip()
    )
    if not probe_symbols:
        parser.error("--probe-symbols に1銘柄以上を指定してください。")

    capture_mooview(
        base_url=_normalize_base_url(args.base_url),
        output_dir=Path(args.output_dir),
        timeout_seconds=args.timeout_seconds,
        refresh_wait_seconds=args.refresh_wait_seconds,
        viewport_width=args.viewport_width,
        viewport_height=args.viewport_height,
        probe_symbols=probe_symbols,
    )


if __name__ == "__main__":
    main()
