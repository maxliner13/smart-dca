"""
Smart DCA Backtester (v2 — fixed timezone issue)
"""

import pandas as pd
import numpy as np
from score_engine import SmartDCAScorer, DCAConfig
from dataclasses import dataclass
from typing import List


@dataclass
class BacktestConfig:
    monthly_budget: float   = 500.0
    buy_heavy_mult: float   = 2.0
    buy_normal_mult: float  = 1.0
    wait_mult: float        = 0.0
    skip_mult: float        = 0.0
    enable_sell: bool       = True
    sell_partial_pct: float = 0.30
    sell_heavy_pct: float   = 0.60
    trailing_stop: float    = 0.08


class SmartDCABacktester:
    def __init__(self, scorer: SmartDCAScorer, bt_config: BacktestConfig = None):
        self.scorer = scorer
        self.bt     = bt_config or BacktestConfig()

    def run(self, ticker: str, start_date: str = "2020-01-01", end_date: str = None) -> dict:
        df = self.scorer.fetch_data(ticker, period="5y")
        df = self.scorer.calculate_indicators(df)
        df = df.dropna(subset=["RSI", "MA50"])

        # ── fix timezone-aware index ──────────────────────────────────────
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)

        df = df[df.index >= pd.Timestamp(start_date)]
        if end_date:
            df = df[df.index <= pd.Timestamp(end_date)]

        if df.empty:
            raise ValueError(f"ไม่มีข้อมูลในช่วง {start_date}")

        smart_results = self._run_smart_dca(df)
        naive_results = self._run_naive_dca(df)
        bnh_results   = self._run_buy_and_hold(df)

        return {
            "ticker":       ticker,
            "start_date":   df.index[0].strftime("%Y-%m-%d"),
            "end_date":     df.index[-1].strftime("%Y-%m-%d"),
            "smart_dca":    smart_results,
            "naive_dca":    naive_results,
            "buy_and_hold": bnh_results,
            "df":           df,
            "trades_df":    pd.DataFrame(smart_results["trades"]),
        }

    def _monthly_first_days(self, df: pd.DataFrame):
        """ดึง index วันแรกของแต่ละเดือน (timezone-safe)"""
        df = df.copy()
        df["_ym"] = df.index.to_period("M")
        return df.groupby("_ym").apply(lambda x: x.index[0]).values

    def _run_smart_dca(self, df: pd.DataFrame) -> dict:
        cfg    = self.bt
        scorer = self.scorer

        cash_invested = 0.0
        shares        = 0.0
        trades        = []
        peak_price    = 0.0
        saved_cash    = 0.0

        for dt in self._monthly_first_days(df):
            row       = df.loc[dt]
            prev_idx  = df.index.get_loc(dt)
            prev_close = df.iloc[prev_idx - 1]["Close"] if prev_idx > 0 else None

            scores = scorer.calculate_composite_score(row, prev_close)
            score  = scores["score_composite"]
            rsi    = float(row.get("RSI", 50))
            price  = float(row["Close"])
            peak_price = max(peak_price, price)

            saved_cash += cfg.monthly_budget

            # Trailing stop
            if cfg.enable_sell and shares > 0 and price < peak_price * (1 - cfg.trailing_stop):
                proceeds  = shares * price
                trades.append({"date": dt, "action": "TRAILING_STOP",
                                "price": price, "shares": shares,
                                "proceeds": proceeds, "score": score})
                shares     = 0.0
                peak_price = price
                continue

            action = scorer.get_action(score, rsi)

            if action in ("BUY_HEAVY", "BUY_NORMAL"):
                mult   = cfg.buy_heavy_mult if action == "BUY_HEAVY" else cfg.buy_normal_mult
                invest = min(saved_cash, cfg.monthly_budget * mult)
                bought = invest / price
                shares        += bought
                cash_invested += invest
                saved_cash    -= invest
                trades.append({"date": dt, "action": action,
                                "price": price, "shares": bought,
                                "amount_invested": invest, "score": score})

            elif cfg.enable_sell and action == "SELL_PARTIAL" and shares > 0:
                sell     = shares * cfg.sell_partial_pct
                proceeds = sell * price
                shares        -= sell
                cash_invested  = max(cash_invested - proceeds, 0)
                trades.append({"date": dt, "action": "SELL_PARTIAL",
                                "price": price, "shares": sell,
                                "proceeds": proceeds, "score": score})

            elif cfg.enable_sell and action == "SELL_HEAVY" and shares > 0:
                sell     = shares * cfg.sell_heavy_pct
                proceeds = sell * price
                shares        -= sell
                cash_invested  = max(cash_invested - proceeds, 0)
                trades.append({"date": dt, "action": "SELL_HEAVY",
                                "price": price, "shares": sell,
                                "proceeds": proceeds, "score": score})

        final_price  = float(df.iloc[-1]["Close"])
        final_value  = shares * final_price + saved_cash
        total_return = (final_value - cash_invested) / cash_invested * 100 if cash_invested > 0 else 0

        return {"final_value": round(final_value, 2),
                "cash_invested": round(cash_invested, 2),
                "total_return_pct": round(total_return, 2),
                "shares_held": round(shares, 4),
                "trades": trades,
                "num_trades": len(trades)}

    def _run_naive_dca(self, df: pd.DataFrame) -> dict:
        cfg    = self.bt
        shares = 0.0
        cash_invested = 0.0

        for dt in self._monthly_first_days(df):
            price          = float(df.loc[dt, "Close"])
            shares        += cfg.monthly_budget / price
            cash_invested += cfg.monthly_budget

        final_value  = shares * float(df.iloc[-1]["Close"])
        total_return = (final_value - cash_invested) / cash_invested * 100

        return {"final_value": round(final_value, 2),
                "cash_invested": round(cash_invested, 2),
                "total_return_pct": round(total_return, 2),
                "shares_held": round(shares, 4)}

    def _run_buy_and_hold(self, df: pd.DataFrame) -> dict:
        cfg          = self.bt
        months       = len(self._monthly_first_days(df))
        total_budget = cfg.monthly_budget * months
        first_price  = float(df.iloc[0]["Close"])
        shares       = total_budget / first_price
        final_value  = shares * float(df.iloc[-1]["Close"])
        total_return = (final_value - total_budget) / total_budget * 100

        return {"final_value": round(final_value, 2),
                "cash_invested": round(total_budget, 2),
                "total_return_pct": round(total_return, 2),
                "shares_held": round(shares, 4)}


def print_report(result: dict):
    t = result["ticker"]
    print(f"\n{'='*55}")
    print(f"  Backtest: {t}  |  {result['start_date']} → {result['end_date']}")
    print(f"{'='*55}")
    print(f"{'Strategy':<20} {'ลงทุน':>10} {'มูลค่าสุดท้าย':>14} {'ผลตอบแทน':>10}")
    print(f"{'-'*55}")
    for key, label in [("smart_dca","Smart DCA"),("naive_dca","Naive DCA"),("buy_and_hold","Buy & Hold")]:
        r = result[key]
        print(f"{label:<20} ${r['cash_invested']:>9,.0f} ${r['final_value']:>13,.0f} {r['total_return_pct']:>+9.1f}%")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    scorer     = SmartDCAScorer()
    backtester = SmartDCABacktester(scorer)
    for ticker in ["AAPL", "NVDA", "MSFT"]:
        try:
            result = backtester.run(ticker, start_date="2021-01-01")
            print_report(result)
        except Exception as e:
            print(f"{ticker}: ERROR — {e}")
