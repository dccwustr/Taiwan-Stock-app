"""Regression tests for bugs found in the 2026-11-03 data audit. Fixtures are real API rows."""
import os, sys, unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("FLOW_DB", "/tmp/flow_test_unused.db")
import widget as w

TW = timezone(timedelta(hours=8))
# 2026-11-02 T86 for 2330, as returned by TWSE
T86_2330 = ['2330', '台積電          ', '18,715,868', '33,720,882', '-15,005,014', '0', '0', '0',
            '3,754,223', '72,000', '3,682,223', '1,885,893', '567,000', '548,100', '18,900',
            '2,029,402', '162,409', '1,866,993', '-9,436,898']
TPEX_ROW = ['00411A', '主動統一前沿科技', '188,000', '1,220,600', '-1,032,600', '0', '0', '0',
            '188,000', '1,220,600', '-1,032,600', '0', '0', '0', '0', '0', '0',
            '2,722,000', '6,773,195', '-4,051,195', '2,722,000', '6,773,195', '-4,051,195', '-5,083,795']


class Insti(unittest.TestCase):
    def test_t86_columns(self):
        r = w._parse_t86_rows([T86_2330])["2330.TW"]
        self.assertAlmostEqual(r["foreign"], -15005.014)
        self.assertAlmostEqual(r["trust"], 3682.223)     # the old code read column 7 → 0
        self.assertAlmostEqual(r["dealer"], 1885.893)
        self.assertAlmostEqual(r["total"], -9436.898)
        self.assertAlmostEqual(r["foreign"] + r["trust"] + r["dealer"], r["total"], places=3)

    def test_tpex_columns(self):
        r = w._parse_tpex_insti_rows([TPEX_ROW])["00411A.TW"]
        self.assertAlmostEqual(r["foreign"] + r["trust"] + r["dealer"], r["total"], places=3)
        self.assertAlmostEqual(r["trust"], 0.0)

    def test_streak(self):
        self.assertEqual(w.calc_trust_streak({"a": [5, 3, -1, 4]})["a"], 2)


class Limits(unittest.TestCase):
    # official MIS values seen on 2026-11-03: (prev, up, down)
    CASES = [(2330, 2560, 2100), (251, 276, 226), (760, 836, 684)]

    def test_limits_match_official(self):
        for prev, up, down in self.CASES:
            self.assertEqual(w._tw_limit_up(prev), up, prev)
            self.assertEqual(w._tw_limit_down(prev), down, prev)

    def test_small_tick_no_float_noise(self):
        self.assertEqual(w._tw_limit_up(10.0), 11.0)
        self.assertEqual(w._tw_limit_down(10.0), 9.0)


class Misc(unittest.TestCase):
    def test_strip_suffix(self):
        self.assertEqual(w._strip_suffix("6488.TWO"), "6488")
        self.assertEqual(w._strip_suffix("2330.TW"), "2330")

    def test_mis_quote_parsing(self):
        self.assertEqual(w._mis_first("2305.0000_2300.0000_"), 2305.0)
        self.assertIsNone(w._mis_first("-"))
        self.assertIsNone(w._mis_first(None))

    def test_quarterly_parse_no_longer_empty(self):
        cols = pd.to_datetime(["2026-09-30", "2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30"])
        stmt = pd.DataFrame({c: [v, v * .5] for c, v in zip(cols, [150, 120, 110, 105, 100])},
                            index=["Total Revenue", "Gross Profit"], dtype=float)
        out = w._parse_quarterly_stmt(stmt)
        self.assertAlmostEqual(out["rev_qoq"], .25)
        self.assertAlmostEqual(out["rev_yoy_q"], .5)
        self.assertEqual(out["gm_trend"], "stable")

    def test_official_revenue_beats_yahoo(self):
        fund = {"X.TW": {"rev_growth": -0.165, "monthly_rev_ytd_yoy": 44.6, "monthly_rev_yoy": 496.0}}
        b = w.calc_fundamental_bonus("X.TW", fund, {})
        self.assertAlmostEqual(b["rev_yoy"], 44.6)
        self.assertTrue(any("累計營收年增" in l for l in b["labels"]))

    def test_net_margin_label(self):
        b = w.calc_fundamental_bonus("X.TW", {"X.TW": {"profit_margin": .42}}, {})
        self.assertTrue(any("高淨利率" in l for l in b["labels"]))
        self.assertFalse(any("高毛利" in l for l in b["labels"]))


class Volume(unittest.TestCase):
    def test_session_fraction(self):
        self.assertEqual(w._session_fraction(datetime(2026, 11, 3, 14, 0, tzinfo=TW)), 1.0)
        self.assertEqual(w._session_fraction(datetime(2026, 11, 7, 10, 0, tzinfo=TW)), 1.0)  # Saturday
        self.assertAlmostEqual(w._session_fraction(datetime(2026, 11, 3, 10, 25, tzinfo=TW)), .423, 3)

    def test_partial_bar_projected(self):
        idx = pd.date_range("2026-10-30", periods=3)
        vol = pd.Series([100.0, 100.0, 42.3], index=idx)
        now = datetime(2026, 11, 1, 10, 25, tzinfo=TW)   # same date as the last bar; a Sunday → full day
        self.assertEqual(w._latest_volume_full_day(vol, now), 42.3)
        now = datetime(2026, 11, 3, 10, 25, tzinfo=TW)   # last bar is not today → untouched
        self.assertEqual(w._latest_volume_full_day(vol, now), 42.3)
        idx2 = pd.date_range("2026-11-01", periods=3)
        self.assertAlmostEqual(w._latest_volume_full_day(pd.Series([100., 100., 42.3], index=idx2), now), 100.0, 0)


class Indicators(unittest.TestCase):
    def test_kd_matches_taiwan_formula(self):
        rng = np.random.default_rng(0)
        c = 100 + rng.normal(0, 1, 80).cumsum()
        df = pd.DataFrame({"High": c + 1, "Low": c - 1, "Close": c})
        rsv = 100 * (df.Close - df.Low.rolling(9).min()) / (df.High.rolling(9).max() - df.Low.rolling(9).min())
        k = d = None
        for x in rsv.dropna():
            k = x if k is None else k * 2 / 3 + x / 3
            d = k if d is None else d * 2 / 3 + k / 3
        out = w.calc_stochastic(df)
        self.assertAlmostEqual(out["K"], k, 1)
        self.assertAlmostEqual(out["D"], d, 1)

    def test_rsi_wilder(self):
        c = pd.Series(np.r_[np.linspace(100, 120, 20), np.linspace(120, 110, 10)])
        d = c.diff().dropna()
        up, dn = d.clip(lower=0).iloc[0], (-d).clip(lower=0).iloc[0]
        for u, v in zip(d.clip(lower=0).iloc[1:], (-d).clip(lower=0).iloc[1:]):
            up, dn = up * 13 / 14 + u / 14, dn * 13 / 14 + v / 14
        self.assertAlmostEqual(w.calc_rsi(c), 100 - 100 / (1 + up / dn), 6)


class FlowClassify(unittest.TestCase):
    def setUp(self):
        import flow_collector as fc
        self.fc = fc
        self.prev = {"ask": 101.0, "bid": 100.0, "z": 100.5, "sign": 0}

    def test_price_fallbacks(self):
        self.assertEqual(self.fc.est_price("-", "-", 101.0, 100.0), 100.5)
        self.assertEqual(self.fc.est_price("99", "-", 101.0, 100.0), 99.0)
        self.assertEqual(self.fc.est_price("-", "98", 101.0, 100.0), 98.0)
        self.assertEqual(self.fc.est_price("-", "-", None, 100.0), 100.0)   # limit-locked
        self.assertIsNone(self.fc.est_price("-", "-", None, None))

    def test_trade_price_rule(self):
        self.assertEqual(self.fc.classify(True, 101.0, self.prev, 102, 101, False), 1)
        self.assertEqual(self.fc.classify(True, 100.0, self.prev, 101, 100, False), -1)

    def test_quote_only_rule(self):
        self.assertEqual(self.fc.classify(False, 101.5, self.prev, 102, 101, False), 1)   # bid lifted to old ask
        self.assertEqual(self.fc.classify(False, 99.5, self.prev, 100, 99, False), -1)    # ask dropped to old bid
        self.assertEqual(self.fc.classify(False, 100.5, self.prev, 101, 100, False), 0)   # unchanged


class News(unittest.TestCase):
    def test_bad_news_earns_no_catalyst(self):
        bad = [{"title": "鴻海遭砍單 第四季營收下修", "summary": "", "time": "09:00", "source": "x"}]
        good = [{"title": "鴻海接獲重大訂單", "summary": "", "time": "09:00", "source": "x"}]
        self.assertEqual(w.analyze_catalysts(bad)[0].get("2317.TW", 0), 0)
        self.assertGreater(w.analyze_catalysts(good)[0].get("2317.TW", 0), 0)

    def test_headlines_not_duplicated(self):
        n = [{"title": "台積電 AI 伺服器 NVIDIA 需求強", "summary": "", "time": "09:00", "source": "x"}]
        _, h = w.analyze_catalysts(n)
        self.assertEqual(len(h), len(set(h)))


class PickLog(unittest.TestCase):
    def test_old_csv_is_migrated_not_misaligned(self):
        import csv, tempfile, pick_log
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "log.csv")
            old = [c for c in pick_log.FIELDS if c != "generated_at"]
            with open(p, "w", encoding="utf-8", newline="") as f:
                wr = csv.DictWriter(f, fieldnames=old)
                wr.writeheader()
                wr.writerow({"date": "2026-11-02", "ticker": "A.TW", "score": 70, "mkt_penalty": -8})
            res = {"date": "2026-11-03", "generated_at": "2026-11-03 08:46 TST",
                   "market_direction": {"label": "x", "penalty": -5},
                   "top_picks": [{"ticker": "B.TW", "score": 80}]}
            self.assertEqual(pick_log.append_picks(res, p), 1)
            self.assertEqual(pick_log.append_picks(res, p), 0)
            rows = list(csv.DictReader(open(p, encoding="utf-8")))
            self.assertEqual(rows[0]["generated_at"], "")
            self.assertEqual(rows[0]["mkt_penalty"], "-8")
            self.assertEqual(rows[1]["generated_at"], "2026-11-03 08:46 TST")
            self.assertEqual(rows[1]["mkt_penalty"], "-5")

    def test_forward_entry_timing(self):
        import forward_test as ft
        df = pd.DataFrame({"Open": [10., 20., 30.], "Close": [11., 21., 33.]},
                          index=pd.to_datetime(["2026-11-03", "2026-11-04", "2026-11-05"]))
        self.assertTrue(ft._is_premarket("2026-11-03 08:46 TST"))
        self.assertFalse(ft._is_premarket("2026-11-03 13:10 TST"))
        self.assertFalse(ft._is_premarket(""))
        self.assertAlmostEqual(ft._ret(df, "2026-11-03", 1, 0.0, True), 10.0)    # same-day open→close
        self.assertAlmostEqual(ft._ret(df, "2026-11-03", 1, 0.0, False), 5.0)    # next-day open→close


class EntryPoints(unittest.TestCase):
    """Every deployed entry file must at least compile with its names resolved."""
    def test_guard_names_are_imported(self):
        import ast
        for f in [ROOT / "app.py"] + list((ROOT / "pages").glob("*.py")):
            src = f.read_text("utf-8")
            if "_refresh_local_modules" not in src:
                continue
            names = set()
            for n in ast.walk(ast.parse(src)):
                if isinstance(n, ast.Import):
                    names |= {a.asname or a.name.split(".")[0] for a in n.names}
            self.assertLessEqual({"os", "sys"}, names, f.name)


class Universe(unittest.TestCase):
    def test_not_buyable_stays_watchable(self):
        self.assertIn("2758.TW", w.PICKS_EXCLUDE)
        self.assertIn("2758.TW", w.TECH_UNIVERSE)

    def test_known_names(self):
        for t, n in [("6285.TW", "啟碁"), ("6412.TW", "群電"), ("6214.TW", "精誠"), ("3617.TW", "碩天"),
                     ("4162.TW", "智擎"), ("4105.TW", "東洋"), ("2883.TW", "凱基金")]:
            self.assertEqual(w.TECH_UNIVERSE[t]["name"], n)
        for dead in ("6510.TW", "3519.TW", "4166.TW", "4110.TW", "5371.TW"):
            self.assertNotIn(dead, w.TECH_UNIVERSE)


if __name__ == "__main__":
    unittest.main()
