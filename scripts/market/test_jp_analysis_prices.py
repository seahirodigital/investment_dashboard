import unittest

from jp_analysis_prices import build_summaries


class PriceValidationTest(unittest.TestCase):
    def setUp(self):
        self.raw = {"topix100": {"7203.T": "トヨタ"}, "sectors": {"^N225": "日経平均"}}
        self.rows = [{"date": "2026-11-12", "open": 95, "close": 100}, {"date": "2026-11-13", "open": 110, "close": 120}]

    def test_previous_close_and_rankings(self):
        intraday, daily = build_summaries(self.raw, "2026-11-13", fetch=lambda symbol: self.rows)
        price = intraday["tickers"]["7203.T"]
        self.assertEqual(price["daily_pct"], 20.0)
        self.assertEqual(price["intraday_pct"], 9.09)
        self.assertEqual(daily["tickers"]["7203.T"]["latest"], 120)
        self.assertEqual(intraday["topix100_ranking_high"][0]["symbol"], "7203.T")

    def test_stale_today_is_rejected(self):
        with self.assertRaises(ValueError):
            build_summaries(self.raw, "2026-11-14", fetch=lambda symbol: self.rows)

    def test_missing_previous_trading_day_is_rejected(self):
        def fetch(symbol):
            if symbol == "7203.T":
                return [{"date": "2026-11-11", "open": 95, "close": 100}, self.rows[-1]]
            return self.rows
        with self.assertRaises(ValueError):
            build_summaries(self.raw, "2026-11-13", fetch=fetch)


if __name__ == "__main__":
    unittest.main()
