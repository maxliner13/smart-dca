"""
Smart DCA Backtester
====================
ทดสอบ strategy ย้อนหลัง เปรียบเทียบกับ naive DCA และ Buy & Hold
"""

import pandas as pd
import numpy as np
from score_engine import SmartDCAScorer, DCAConfig
from dataclasses import dataclass
from typing import List


@dataclass
class BacktestConfig:
    monthly_budget: float = 500.0       # เงินลงทุนต่อเดือน (USD)
    buy_heavy_mult: float = 2.0         # BUY_HEAVY = ลงทุน 2x
    buy_normal_mult: float = 1.0        # BUY_NORMAL = ลงทุน 1x
    wait_mult: float = 0.0              # WAIT = ไม่ซื้อ
    skip_mult: float = 0.0             # SKIP = ไม่ซื้อ

    # Sell rules
    enable_sell: bool = True
    sell_partial_pct: float = 0.30      # ขาย 30% เมื่อ SELL_PARTIAL
    sell_heavy_pct: float = 0.60        # ขาย 60% เมื่อ SELL_HEAVY
    trailing_stop: float = 0.08         # trailing stop 8%


class SmartDCABacktester:
    def __init__(self, scorer: SmartDCAScorer, bt_config: BacktestConfig = None):
        self.scorer = scorer
        self.bt = bt_config or BacktestConfig()

    def run(self, ticker: str, start_date: str = "2020-01-01", end_date: str = None) -> dict:
        """รัน backtest และส่งคืน performance metrics"""

        # ดึงข้อมูล
        df = self.scorer.fetch_data(ticker, period="5y")
        df = self.scorer.calculate_indicators(df)
        df = df.dropna(subset=["RSI", "MA50"])

        if end_date:
            df = df[df.index <= end_date]
        df = df[df.index >= start_date]

        if df.empty:
            raise ValueError(f"ไม่มีข้อมูลในช่วง {start_date} ถึง {end_date}")

        # รัน 3 strategies พร้อมกัน
        smart_results = self._run_smart_dca(df)
        naive_results = self._run_naive_dca(df)
        bnh_results   = self._run_buy_and_hold(df)

        return {
            "ticker":        ticker,
            "start_date":    df.index[0].strftime("%Y-%m-%d"),
            "end_date":      df.index[-1].strftime("%Y-%m-%d"),
            "smart_dca":     smart_results,
            "naive_dca":     naive_results,
            "buy_and_hold":  bnh_results,
            "df":            df,
            "trades_df":     pd.DataFrame(smart_results["trades"]),
        }

    def _run_smart_dca(self, df: pd.DataFrame) -> dict:
        """Smart DCA — ซื้อตาม score"""
        cfg = self.bt
        scorer = self.scorer

        cash_invested = 0.0
        shares = 0.0
        trades = []
        peak_price = 0.0
        monthly_cash = cfg.monthly_budget
        saved_cash = 0.0          # เงินที่ยังไม่ได้ใช้ (WAIT/SKIP เก็บสะสมไว้)

        # ดึง trading day แรกของแต่ละเดือน
        df["Month"] = df.index.to_period("M")
        monthly_idx = df.groupby("Month").apply(lambda x: x.index[0]).values

        for dt in monthly_idx:
            row = df.loc[dt]
            prev_idx = df.index.get_loc(dt)
            prev_close = df.iloc[prev_idx - 1]["Close"] if prev_idx > 0 else None

            scores = scorer.calculate_composite_score(row, prev_close)
            score  = scores["score_composite"]
            rsi    = row.get("RSI", 50)
            price  = row["Close"]
            peak_price = max(peak_price, price)

            # สะสมเงินรายเดือน
            saved_cash += monthly_cash

            # Trailing stop
            if cfg.enable_sell and shares > 0 and price < peak_price * (1 - cfg.trailing_stop):
                sell_shares = shares
                proceeds = sell_shares * price
                shares -= sell_shares
                trades.append({
                    "date": dt, "action": "TRAILING_STOP",
                    "price": price, "shares": sell_shares,
                    "proceeds": proceeds, "score": score
                })
                peak_price = price
                continue

            action = scorer.get_action(score, rsi)

            # Execute buy
            if action in ("BUY_HEAVY", "BUY_NORMAL"):
                mult = cfg.buy_heavy_mult if action == "BUY_HEAVY" else cfg.buy_normal_mult
                invest = min(saved_cash, monthly_cash * mult)
                bought_shares = invest / price
                shares += bought_shares
                cash_invested += invest
                saved_cash -= invest
                trades.append({
                    "date": dt, "action": action,
                    "price": price, "shares": bought_shares,
                    "amount_invested": invest, "score": score
                })

            # Execute sell
            elif cfg.enable_sell and action == "SELL_PARTIAL" and shares > 0:
                sell_shares = shares * cfg.sell_partial_pct
                proceeds = sell_shares * price
                shares -= sell_shares
                cash_invested = max(cash_invested - proceeds, 0)
                trades.append({
                    "date": dt, "action": "SELL_PARTIAL",
                    "price": price, "shares": sell_shares,
                    "proceeds": proceeds, "score": score
                })

            elif cfg.enable_sell and action == "SELL_HEAVY" and shares > 0:
                sell_shares = shares * cfg.sell_heavy_pct
                proceeds = sell_shares * price
                shares -= sell_shares
                cash_invested = max(cash_invested - proceeds, 0)
                trades.append({
                    "date": dt, "action": "SELL_HEAVY",
                    "price": price, "shares": sell_shares,
                    "proceeds": proceeds, "score": score
                })

        final_price = df.iloc[-1]["Close"]
        final_value = shares * final_price + saved_cash
        total_return = (final_value - cash_invested) / cash_invested * 100 if cash_invested > 0 else 0

        return {
            "final_value":    round(final_value, 2),
            "cash_invested":  round(cash_invested, 2),
            "total_return_pct": round(total_return, 2),
            "shares_held":    round(shares, 4),
            "trades":         trades,
            "num_trades":     len(trades),
        }

    def _run_naive_dca(self, df: pd.DataFrame) -> dict:
        """Naive DCA — ซื้อทุกเดือนเท่ากันโดยไม่ดู signal"""
        cfg = self.bt
        shares = 0.0
        cash_invested = 0.0

        df["Month"] = df.index.to_period("M")
        monthly_idx = df.groupby("Month").apply(lambda x: x.index[0]).values

        for dt in monthly_idx:
            price = df.loc[dt, "Close"]
            invest = cfg.monthly_budget
            shares += invest / price
            cash_invested += invest

        final_value = shares * df.iloc[-1]["Close"]
        total_return = (final_value - cash_invested) / cash_invested * 100

        return {
            "final_value":      round(final_value, 2),
            "cash_invested":    round(cash_invested, 2),
            "total_return_pct": round(total_return, 2),
            "shares_held":      round(shares, 4),
        }

    def _run_buy_and_hold(self, df: pd.DataFrame) -> dict:
        """Buy & Hold — ซื้อวันแรกวันเดียว แล้วถือไปเลย"""
        cfg = self.bt
        df["Month"] = df.index.to_period("M")
        months = df["Month"].nunique()
        total_budget = cfg.monthly_budget * months

        first_price = df.iloc[0]["Close"]
        shares = total_budget / first_price
        final_value = shares * df.iloc[-1]["Close"]
        total_return = (final_value - total_budget) / total_budget * 100

        return {
            "final_value":      round(final_value, 2),
            "cash_invested":    round(total_budget, 2),
            "total_return_pct": round(total_return, 2),
            "shares_held":      round(shares, 4),
        }


def print_report(result: dict):
    """พิมพ์ผล backtest แบบสวยงาม"""
    t = result["ticker"]
    print(f"\n{'='*55}")
    print(f"  Backtest: {t}  |  {result['start_date']} → {result['end_date']}")
    print(f"{'='*55}")
    print(f"{'Strategy':<20} {'ลงทุน':>10} {'มูลค่าสุดท้าย':>14} {'ผลตอบแทน':>10}")
    print(f"{'-'*55}")

    for key, label in [
        ("smart_dca",    "Smart DCA"),
        ("naive_dca",    "Naive DCA"),
        ("buy_and_hold", "Buy & Hold"),
    ]:
        r = result[key]
        print(
            f"{label:<20} "
            f"${r['cash_invested']:>9,.0f} "
            f"${r['final_value']:>13,.0f} "
            f"{r['total_return_pct']:>+9.1f}%"
        )

    print(f"{'='*55}")
    smart = result["smart_dca"]
    naive = result["naive_dca"]
    diff = smart["total_return_pct"] - naive["total_return_pct"]
    print(f"  Smart DCA vs Naive DCA: {diff:+.1f}% difference")

    if result.get("trades_df") is not None and not result["trades_df"].empty:
        tdf = result["trades_df"]
        buy_trades  = tdf[tdf["action"].str.contains("BUY", na=False)]
        sell_trades = tdf[tdf["action"].str.contains("SELL|STOP", na=False)]
        print(f"  Buy trades: {len(buy_trades)}  |  Sell/Stop trades: {len(sell_trades)}")
    print()


if __name__ == "__main__":
    scorer    = SmartDCAScorer()
    backtester = SmartDCABacktester(scorer)

    for ticker in ["AAPL", "NVDA", "MSFT"]:
        try:
            result = backtester.run(ticker, start_date="2021-01-01")
            print_report(result)
        except Exception as e:
            print(f"{ticker}: ERROR — {e}")
