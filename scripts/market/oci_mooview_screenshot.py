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
# 初回確認で採用する固定列幅。毎回現在幅へ2/3を掛けず、常に同じ境界へ戻す。
CAPTURE_COLUMN_WIDTHS_PX = (483, 417)
# 上段左右の高さを揃え、下段チャートの開始位置も固定する。
CAPTURE_TOP_ROW_HEIGHT_PX = 442
KLINE_PRELOAD_BATCH_LIMIT = 55
KLINE_PRELOAD_COOLDOWN_SECONDS = 30
DISPLAY_RANGE_TIMEFRAMES = {
    "d": "5m",
    "w": "30m",
}
WEEKLY_REFRESH_ATTEMPTS = 5
WEEKLY_REFRESH_INTERVAL_SECONDS = 60


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


def _preload_capture_chart_candles(
    base_url: str,
    *,
    minimum_chart_count: int,
    display_range: str,
) -> tuple[
    dict[str, list[dict[str, Any]]],
    dict[str, int],
    dict[str, Any],
    dict[str, Any],
]:
    session = requests.Session()
    session.headers.update({"User-Agent": "investment-dashboard-oci-capture/1.0"})
    workspace_response = session.get(
        f"{base_url}/api/workspace-settings?profile=desktop",
        timeout=30,
    )
    workspace_response.raise_for_status()
    workspace = workspace_response.json()
    settings = workspace.get("settings") or {}
    panels = (settings.get("panels") or [])[:minimum_chart_count]
    if len(panels) < minimum_chart_count:
        raise RuntimeError(
            f"OCI共有設定の撮影対象チャートが不足しています: {len(panels)}画面"
        )

    basket_sections: dict[str, list[str]] = {}
    for tab in settings.get("watchlistTabs") or []:
        for section in tab.get("sections") or []:
            section_id = str(section.get("id") or "")
            if section_id:
                basket_sections[section_id] = [
                    str(symbol)
                    for symbol in (section.get("symbols") or [])
                    if str(symbol).strip()
                ]

    targets: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for panel in panels:
        timeframe = DISPLAY_RANGE_TIMEFRAMES[display_range]
        raw_symbols = [
            str(panel.get("symbol") or ""),
            *(str(symbol) for symbol in (panel.get("comparisonSymbols") or [])),
        ]
        for raw_symbol in raw_symbols:
            basket_members = (
                basket_sections.get(raw_symbol[7:], [])
                if raw_symbol.startswith("BASKET:")
                else [raw_symbol]
            )
            for member_symbol in basket_members:
                for operand in _stored_symbol_operands(member_symbol):
                    target = (operand, timeframe)
                    if target in seen:
                        continue
                    seen.add(target)
                    targets.append(target)

    cache: dict[str, list[dict[str, Any]]] = {}
    timestamps: dict[str, int] = {}
    failures: list[dict[str, str]] = []
    fetched: list[dict[str, Any]] = []

    print(f"[取得] 撮影対象4チャートの時系列データを先行取得します: {len(targets)}銘柄")
    for index, (symbol, timeframe) in enumerate(targets, start=1):
        if index > 1 and (index - 1) % KLINE_PRELOAD_BATCH_LIMIT == 0:
            print(
                "[待機] OCIのKLine負荷を抑えるため、"
                f"{KLINE_PRELOAD_COOLDOWN_SECONDS}秒待機します。"
            )
            time.sleep(KLINE_PRELOAD_COOLDOWN_SECONDS)
        try:
            primary_error = ""
            data: dict[str, Any] = {}
            candles: Any = None
            source_timeframe = timeframe
            try:
                response = session.post(
                    f"{base_url}/api/moomoo/kline",
                    json={"symbol": symbol, "timeframe": timeframe, "reqNum": 150},
                    timeout=50,
                )
                response.raise_for_status()
                data = response.json()
                candles = data.get("candles") if isinstance(data, dict) else None
            except Exception as exc:
                primary_error = str(exc)

            primary_valid = (
                isinstance(data, dict)
                and data.get("success") is True
                and isinstance(candles, list)
                and len(candles) >= 10
            )
            if not primary_valid and display_range == "w":
                fallback_response = session.post(
                    f"{base_url}/api/moomoo/kline",
                    json={"symbol": symbol, "timeframe": "1d", "reqNum": 30},
                    timeout=50,
                )
                fallback_response.raise_for_status()
                fallback_data = fallback_response.json()
                fallback_candles = (
                    fallback_data.get("candles")
                    if isinstance(fallback_data, dict)
                    else None
                )
                if (
                    isinstance(fallback_data, dict)
                    and fallback_data.get("success") is True
                    and isinstance(fallback_candles, list)
                    and len(fallback_candles) >= 4
                ):
                    data = fallback_data
                    candles = fallback_candles
                    source_timeframe = "1d"
                    print(
                        f"[補完] {symbol}の30分足を取得できないため、"
                        "週次表示へ日足を使用します。"
                    )

            if (
                not isinstance(data, dict)
                or data.get("success") is not True
                or not isinstance(candles, list)
                or len(candles) < (4 if source_timeframe == "1d" else 10)
            ):
                detail = primary_error or json.dumps(
                    data,
                    ensure_ascii=False,
                )[:500]
                raise RuntimeError(detail)

            cache_key = f"{symbol}-{timeframe}"
            cache[cache_key] = candles[-180:]
            timestamps[cache_key] = int(time.time() * 1000)
            fetched.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "sourceTimeframe": source_timeframe,
                    "candleCount": len(candles),
                }
            )
            print(
                f"[成功] 先行取得 {index}/{len(targets)}: "
                f"{symbol} {timeframe} {len(candles)}本"
                + (
                    f"（{source_timeframe}補完）"
                    if source_timeframe != timeframe
                    else ""
                )
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
        "displayRange": display_range,
        "timeframe": DISPLAY_RANGE_TIMEFRAMES[display_range],
        "targetCount": len(targets),
        "successCount": len(fetched),
        "failureCount": len(failures),
        "fetched": fetched,
        "failures": failures,
    }, workspace


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

          const readValue = (key) => new Promise((resolve, reject) => {
            const transaction = database.transaction('values', 'readonly');
            const request = transaction.objectStore('values').get(key);
            request.onsuccess = () => resolve(request.result || {});
            request.onerror = () => reject(request.error);
          });
          const existingCache = await readValue('candles');
          const existingTimestamps = await readValue('meta');
          const mergedCache = {
            ...(existingCache && typeof existingCache === 'object' ? existingCache : {}),
            ...cache,
          };
          const mergedTimestamps = {
            ...(existingTimestamps && typeof existingTimestamps === 'object' ? existingTimestamps : {}),
            ...timestamps,
          };

          await new Promise((resolve, reject) => {
            const transaction = database.transaction('values', 'readwrite');
            const store = transaction.objectStore('values');
            store.put(mergedCache, 'candles');
            store.put(mergedTimestamps, 'meta');
            transaction.oncomplete = () => resolve();
            transaction.onerror = () => reject(transaction.error);
            transaction.onabort = () => reject(transaction.error);
          });
          database.close();
          return Object.keys(mergedCache).length;
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
              const evaluableSeries = series.filter((line) => line.pointCount >= 4);
              const variedSeries = evaluableSeries.filter(
                (line) => line.ySpread >= 2 && line.uniqueYCount >= 3
              );
              return {
                x: rect.x + window.scrollX,
                y: rect.y + window.scrollY,
                width: rect.width,
                height: rect.height,
                seriesCount: series.length,
                denseSeriesCount: denseSeries.length,
                evaluableSeriesCount: evaluableSeries.length,
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


def _select_display_range(
    page: Page,
    *,
    display_range: str,
    minimum_chart_count: int,
) -> dict[str, Any]:
    target_menu_text = "今週" if display_range == "w" else "今日"
    target_label = display_range.upper()

    for panel_index in range(minimum_chart_count):
        panels = page.locator('[id^="chart-panel-container-"]')
        if panels.count() < minimum_chart_count:
            raise RuntimeError(
                f"D/W選択に必要なチャートが不足しています: {panels.count()}画面"
            )
        panel = panels.nth(panel_index)
        dropdown = panel.locator('button[title="D/W表示を選択"]')
        dropdown.wait_for(state="visible", timeout=10000)
        dropdown.click(timeout=10000)
        menu_item = page.get_by_role("button").filter(has_text=target_menu_text)
        menu_item.wait_for(state="visible", timeout=10000)
        menu_item.click(timeout=10000)
        page.wait_for_timeout(350)

    state = page.evaluate(
        """({ expectedCount }) => {
          const panels = Array.from(
            document.querySelectorAll('[id^="chart-panel-container-"]')
          ).slice(0, expectedCount);
          return {
            labels: panels.map((panel) => {
              const dropdown = panel.querySelector('button[title="D/W表示を選択"]');
              const labelButton = dropdown?.previousElementSibling;
              return (labelButton?.textContent || '').trim();
            }),
          };
        }""",
        {"expectedCount": minimum_chart_count},
    )
    labels = state.get("labels") or []
    if len(labels) < minimum_chart_count or any(
        label != target_label for label in labels
    ):
        raise RuntimeError(
            "D/W表示の固定に失敗しました: "
            + json.dumps(
                {
                    "expected": target_label,
                    "actual": labels,
                },
                ensure_ascii=False,
            )
        )

    print(
        f"[成功] 撮影対象{minimum_chart_count}チャートの表示範囲を"
        f"{target_label}へ固定しました。"
    )
    return {
        "value": display_range,
        "label": target_label,
        "panelLabels": labels,
    }


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


def _refresh_chart_data(
    page: Page,
    *,
    display_range: str,
    timeout_seconds: int,
    daily_wait_seconds: int,
) -> dict[str, int]:
    attempts = WEEKLY_REFRESH_ATTEMPTS if display_range == "w" else 1
    wait_seconds = (
        WEEKLY_REFRESH_INTERVAL_SECONDS
        if display_range == "w"
        else daily_wait_seconds
    )
    for attempt in range(1, attempts + 1):
        print(
            f"[更新] チャートデータ更新 {attempt}/{attempts} を実行します。"
        )
        _click_refresh_and_wait(
            page,
            timeout_seconds=timeout_seconds,
            wait_seconds=wait_seconds,
        )
    return {
        "attempts": attempts,
        "intervalSeconds": wait_seconds,
    }


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
                    "evaluableSeriesCount": chart.get(
                        "evaluableSeriesCount",
                        0,
                    ),
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
        "[成功] 撮影対象4チャートに十分な時系列点と値動きを確認しました: "
        + json.dumps(charts, ensure_ascii=False)
    )
    return state


def _apply_fixed_capture_layout(page: Page) -> dict[str, Any]:
    target_widths = list(CAPTURE_COLUMN_WIDTHS_PX)
    page.evaluate(
        """({ targetWidths, topRowHeight }) => {
          targetWidths.forEach((width, index) => {
            const column = document.getElementById(`col-group-${index}`);
            if (!column) {
              throw new Error(`チャート列が見つかりません: col-group-${index}`);
            }
            const fixedWidth = `${width}px`;
            column.style.setProperty('flex', `0 0 ${fixedWidth}`, 'important');
            column.style.setProperty('width', fixedWidth, 'important');
            column.style.setProperty('min-width', fixedWidth, 'important');
            column.style.setProperty('max-width', fixedWidth, 'important');
          });

          const firstColumn = document.getElementById('col-group-0');
          if (firstColumn?.parentElement) {
            firstColumn.parentElement.style.setProperty('justify-content', 'flex-start', 'important');
          }

          const chartPanels = Array.from(
            document.querySelectorAll('[id^="chart-panel-container-"]')
          ).slice(0, 4);
          [0, 2].forEach((panelIndex) => {
            const panel = chartPanels[panelIndex];
            if (!panel) {
              throw new Error(`上段チャートが見つかりません: DOM順序${panelIndex}`);
            }
            const fixedHeight = `${topRowHeight}px`;
            panel.style.setProperty('flex', `0 0 ${fixedHeight}`, 'important');
            panel.style.setProperty('height', fixedHeight, 'important');
            panel.style.setProperty('min-height', fixedHeight, 'important');
            panel.style.setProperty('max-height', fixedHeight, 'important');
          });

          window.dispatchEvent(new Event('resize'));
        }""",
        {
            "targetWidths": target_widths,
            "topRowHeight": CAPTURE_TOP_ROW_HEIGHT_PX,
        },
    )
    page.wait_for_timeout(2000)

    state = page.evaluate(
        """({ targetWidths, topRowHeight }) => {
          const toBox = (element) => {
            const rect = element.getBoundingClientRect();
            return {
              x: rect.x + window.scrollX,
              y: rect.y + window.scrollY,
              width: rect.width,
              height: rect.height,
            };
          };
          const columns = targetWidths.map((_, index) => {
            const column = document.getElementById(`col-group-${index}`);
            if (!column) return null;
            return toBox(column);
          });
          const panels = Array.from(
            document.querySelectorAll('[id^="chart-panel-container-"]')
          ).slice(0, 4).map((panel) => {
            const chartSvg = Array.from(panel.querySelectorAll('svg'))
              .map((svg) => ({ element: svg, box: toBox(svg) }))
              .sort((left, right) => (
                right.box.width * right.box.height - left.box.width * left.box.height
              ))[0];
            return {
              id: panel.id,
              ...toBox(panel),
              chart: chartSvg?.box || null,
            };
          });
          return {
            targetWidths,
            topRowHeight,
            columns,
            panels,
            pageWidth: Math.max(
              document.documentElement.scrollWidth,
              document.body?.scrollWidth || 0,
              window.innerWidth
            ),
            pageHeight: Math.max(
              document.documentElement.scrollHeight,
              document.body?.scrollHeight || 0,
              window.innerHeight
            ),
          };
        }""",
        {
            "targetWidths": target_widths,
            "topRowHeight": CAPTURE_TOP_ROW_HEIGHT_PX,
        },
    )

    if len(state.get("panels") or []) < 4:
        raise RuntimeError(
            "固定幅撮影に必要な4チャートを確認できませんでした: "
            + json.dumps(state, ensure_ascii=False)[:1000]
        )
    for index, target_width in enumerate(target_widths):
        actual_width = float(state["columns"][index]["width"])
        if abs(actual_width - target_width) > 3:
            raise RuntimeError(
                f"列{index + 1}の固定幅反映に失敗しました: "
                f"期待={target_width}px、実際={actual_width}px"
            )
    for panel_index in (0, 2):
        actual_height = float(state["panels"][panel_index]["height"])
        if abs(actual_height - CAPTURE_TOP_ROW_HEIGHT_PX) > 3:
            raise RuntimeError(
                f"上段チャート{panel_index + 1}の固定高反映に失敗しました: "
                f"期待={CAPTURE_TOP_ROW_HEIGHT_PX}px、実際={actual_height}px"
            )

    print(
        "[成功] チャート境界を固定サイズへ移動し、SVGを再描画しました: "
        + json.dumps(
            {
                "columns": state["columns"],
                "topRowHeight": state["topRowHeight"],
            },
            ensure_ascii=False,
        )
    )
    return state


def _panel_clip(
    layout_state: dict[str, Any],
    panel_indices: tuple[int, ...],
) -> dict[str, float]:
    panels = layout_state.get("panels") or []
    selected = [panels[index] for index in panel_indices]
    left = max(0.0, min(panel["x"] for panel in selected))
    top = max(0.0, min(panel["y"] for panel in selected))
    right = min(
        float(layout_state["pageWidth"]),
        max(panel["x"] + panel["width"] for panel in selected),
    )
    bottom = min(
        float(layout_state["pageHeight"]),
        max(panel["y"] + panel["height"] for panel in selected),
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
    display_range: str,
) -> dict[str, Any]:
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "oci_mooview_capture_result.json"
    viewport_path = output_dir / "oci_mooview_viewport.png"
    us_market_path = output_dir / "us_market_top_charts.png"
    jp_sector_path = output_dir / "jp_market_sector_chart.png"
    jp_semiconductor_path = output_dir / "jp_market_semiconductor_charts.png"
    weekly_jp_sector_path = output_dir / "weekend_jp_sector_tpx_w.png"
    weekly_us_sector_path = output_dir / "weekend_us_sector_spy_w.png"
    weekly_semiconductor_tpx_path = output_dir / "weekend_semiconductor_tpx_w.png"
    weekly_semiconductor_sector_path = (
        output_dir / "weekend_semiconductor_sector_w.png"
    )
    error_path = output_dir / "oci_mooview_error.png"

    result: dict[str, Any] = {
        "baseUrl": base_url,
        "capturedAtUtc": datetime.now(timezone.utc).isoformat(),
        "outputDirectory": str(output_dir),
        "displayRange": display_range,
        "success": False,
    }

    print(f"[開始] OCI MooViewを検証します: {base_url}")
    print(f"[出力先] {output_dir}")
    result["marketData"] = _verify_market_data(
        base_url,
        timeout_seconds,
        probe_symbols,
    )
    (
        preloaded_cache,
        preloaded_timestamps,
        preload_summary,
        workspace_snapshot,
    ) = _preload_capture_chart_candles(
        base_url,
        minimum_chart_count=4,
        display_range=display_range,
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

            def isolate_shared_workspace(route, request) -> None:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(workspace_snapshot, ensure_ascii=False),
                )
                if request.method.upper() == "PUT":
                    print(
                        "[保護] 撮影中のD/W切替によるOCI共有設定の保存を"
                        "ブラウザー内で遮断しました。"
                    )

            context.route(
                "**/api/workspace-settings**",
                isolate_shared_workspace,
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
                minimum_chart_count=4,
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
                minimum_chart_count=4,
            )
            display_range_state = _select_display_range(
                page,
                display_range=display_range,
                minimum_chart_count=4,
            )
            refresh_state = _refresh_chart_data(
                page,
                display_range=display_range,
                timeout_seconds=timeout_seconds,
                daily_wait_seconds=refresh_wait_seconds,
            )
            if display_range == "w":
                final_cache_timestamps = {
                    cache_key: int(time.time() * 1000)
                    for cache_key in preloaded_cache
                }
                final_merged_cache_count = _inject_candle_cache(
                    page,
                    preloaded_cache,
                    final_cache_timestamps,
                )
                print(
                    "[成功] 5回更新で取得したデータを保持し、"
                    "先行取得済みの週次履歴を最終マージしました: "
                    f"{final_merged_cache_count}件"
                )
                page.reload(wait_until="domcontentloaded", timeout=90000)
                page.evaluate("window.scrollTo(0, 0)")
                _wait_for_chart_shells(
                    page,
                    timeout_seconds=timeout_seconds,
                    minimum_chart_count=4,
                )
                display_range_state = _select_display_range(
                    page,
                    display_range=display_range,
                    minimum_chart_count=4,
                )
                page.wait_for_timeout(refresh_wait_seconds * 1000)
                refresh_state["finalMergedCacheCount"] = final_merged_cache_count
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
                "refresh": refresh_state,
                "injectedCandleCacheCount": injected_count,
                "displayRange": display_range_state,
            }
            try:
                _assert_chart_data_ready(
                    chart_state,
                    minimum_chart_count=4,
                )
            except Exception:
                page.screenshot(path=str(error_path), full_page=False)
                result["errorScreenshot"] = str(error_path)
                raise

            layout_state = _apply_fixed_capture_layout(page)
            # DOM順は左上、左下、右上、右下。
            us_market_clip = _panel_clip(layout_state, (0, 2))
            jp_sector_clip = _panel_clip(layout_state, (0,))
            jp_semiconductor_clip = _panel_clip(layout_state, (1, 3))
            individual_panel_clips = {
                "jpSectorTpx": _panel_clip(layout_state, (0,)),
                "semiconductorTpx": _panel_clip(layout_state, (1,)),
                "usSectorSpy": _panel_clip(layout_state, (2,)),
                "semiconductorSector": _panel_clip(layout_state, (3,)),
            }
            page.screenshot(path=str(viewport_path), full_page=False)
            page.screenshot(path=str(us_market_path), clip=us_market_clip)
            page.screenshot(path=str(jp_sector_path), clip=jp_sector_clip)
            page.screenshot(path=str(jp_semiconductor_path), clip=jp_semiconductor_clip)
            if display_range == "w":
                page.screenshot(
                    path=str(weekly_jp_sector_path),
                    clip=individual_panel_clips["jpSectorTpx"],
                )
                page.screenshot(
                    path=str(weekly_semiconductor_tpx_path),
                    clip=individual_panel_clips["semiconductorTpx"],
                )
                page.screenshot(
                    path=str(weekly_us_sector_path),
                    clip=individual_panel_clips["usSectorSpy"],
                )
                page.screenshot(
                    path=str(weekly_semiconductor_sector_path),
                    clip=individual_panel_clips["semiconductorSector"],
                )
            result["browser"].update({
                "fixedCaptureLayout": layout_state,
                "captureClips": {
                    "usMarket": us_market_clip,
                    "jpSector": jp_sector_clip,
                    "jpSemiconductor": jp_semiconductor_clip,
                    "individualPanels": individual_panel_clips,
                },
            })
            result["files"] = {
                "viewport": str(viewport_path),
                "usMarket": str(us_market_path),
                "jpSector": str(jp_sector_path),
                "jpSemiconductor": str(jp_semiconductor_path),
                "result": str(result_path),
            }
            if display_range == "w":
                result["files"]["weeklyPanels"] = {
                    "jpSectorTpx": str(weekly_jp_sector_path),
                    "usSectorSpy": str(weekly_us_sector_path),
                    "semiconductorTpx": str(weekly_semiconductor_tpx_path),
                    "semiconductorSector": str(weekly_semiconductor_sector_path),
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
        if "workspace_snapshot" in locals():
            try:
                final_workspace_response = requests.get(
                    f"{base_url}/api/workspace-settings?profile=desktop",
                    timeout=30,
                )
                final_workspace_response.raise_for_status()
                final_workspace = final_workspace_response.json()
                initial_revision = workspace_snapshot.get("revision")
                final_revision = final_workspace.get("revision")
                result["workspaceProtection"] = {
                    "initialRevision": initial_revision,
                    "finalRevision": final_revision,
                    "unchangedDuringCapture": initial_revision == final_revision,
                }
                if initial_revision == final_revision:
                    print(
                        "[成功] 撮影前後でOCI共有設定のrevisionが変わって"
                        f"いないことを確認しました: {initial_revision}"
                    )
                else:
                    print(
                        "[注意] 撮影中にOCI共有設定が別クライアントから"
                        f"更新されました: {initial_revision} -> {final_revision}"
                    )
            except Exception as workspace_exc:
                result["workspaceProtection"] = {
                    "error": str(workspace_exc),
                }
                print(
                    "[注意] 撮影後のOCI共有設定revisionを確認できませんでした: "
                    f"{workspace_exc}"
                )
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print(f"[成功] 米国株記事用の上段2チャートを撮影しました: {us_market_path}")
    print(f"[成功] 日本株記事用のJPセクターチャートを撮影しました: {jp_sector_path}")
    print(f"[成功] 日本株記事用の下段2チャートを撮影しました: {jp_semiconductor_path}")
    if display_range == "w":
        print(
            "[成功] 週末記事用のW表示4チャートを個別撮影しました: "
            f"{weekly_jp_sector_path}, {weekly_us_sector_path}, "
            f"{weekly_semiconductor_tpx_path}, {weekly_semiconductor_sector_path}"
        )
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
        "--display-range",
        choices=sorted(DISPLAY_RANGE_TIMEFRAMES),
        default="d",
        help="全4チャートのD/W表示。日次はd、週末はwを指定する",
    )
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
        display_range=args.display_range,
    )


if __name__ == "__main__":
    main()
