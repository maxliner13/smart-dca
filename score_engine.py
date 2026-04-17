"""
Smart DCA Score Engine (v2 — ใช้ ta แทน pandas-ta)
====================================================
รองรับ Python 3.14 + pandas 2.2.3 + numpy 2.1.3
"""

import yfinance as yf
import pandas as pd
import numpy as np
import ta
from dataclasses import dataclass
from typing import Optional
import warnings
warnings.filterwarnings("ignore")


# ==================== Config ====================

@dataclass
class DCAConfig:
    rsi_oversold: float      = 30.0
    rsi_overbought: float    = 70.0
    ma_discount_pct: float   = 0.05
    volume_spike_mult: float = 2.0

    weight_rsi: float    = 0.30
    weight_ma: float     = 0.25
    weight_macd: float   = 0.20
    weight_volume: float = 0.15
    weight_bb: float     = 0.10

    score_buy_heavy: float  = 8.0
    score_buy_normal: float = 6.0
    score_wait: float       = 4.0

    rsi_sell_partial: float  = 72.0
    rsi_sell_heavy: float    = 80.0
    profit_target_1: float   = 0.15
    profit_target_2: float   = 0.25
    trailing_stop: float     = 0.08


# ==================== Score Engine ====================

class SmartDCAScorer:
    def __init__(self, config: DCAConfig = None):
        self.config = config or DCAConfig()

    def fetch_data(self, ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        stock = yf.Ticker(ticker)
        df = stock.history(period=period, interval=interval)
        if df.empty:
            raise ValueError(f"ไม่พบข้อมูลสำหรับ {ticker}")
        df.index = pd.to_datetime(df.index)
        return df

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        close = df["Close"]
        high  = df["High"]
        low   = df["Low"]
        vol   = df["Volume"]

        # RSI
        df["RSI"] = ta.momentum.RSIIndicator(close=close, window=14).rsi()

        # Moving Averages
        df["MA50"]  = ta.trend.SMAIndicator(close=close, window=50).sma_indicator()
        df["MA200"] = ta.trend.SMAIndicator(close=close, window=200).sma_indicator()
        df["EMA20"] = ta.trend.EMAIndicator(close=close, window=20).ema_indicator()

        # MACD
        macd_obj = ta.trend.MACD(close=close, window_slow=26, window_fast=12, window_sign=9)
        df["MACD"]        = macd_obj.macd()
        df["MACD_Signal"] = macd_obj.macd_signal()
        df["MACD_Hist"]   = macd_obj.macd_diff()

        # Bollinger Bands
        bb_obj = ta.volatility.BollingerBands(close=close, window=20, window_dev=2)
        df["BB_Upper"] = bb_obj.bollinger_hband()
        df["BB_Lower"] = bb_obj.bollinger_lband()
        df["BB_Mid"]   = bb_obj.bollinger_mavg()

        # Volume MA
        df["Vol_MA20"] = ta.trend.SMAIndicator(close=vol.astype(float), window=20).sma_indicator()

        return df

    def score_rsi(self, rsi: float) -> float:
        if pd.isna(rsi): return 5.0
        if rsi < 20:  return 10.0
        if rsi < 25:  return 9.0
        if rsi < 30:  return 8.0
        if rsi < 40:  return 6.5
        if rsi < 50:  return 5.0
        if rsi < 60:  return 3.5
        if rsi < 70:  return 2.0
        if rsi < 80:  return 1.0
        return 0.0

    def score_ma_position(self, price: float, ma50: float, ma200: float) -> float:
        if pd.isna(ma200):
            if pd.isna(ma50): return 5.0
            pct = (price - ma50) / ma50
        else:
            pct = (price - ma200) / ma200
        if pct < -0.20: return 10.0
        if pct < -0.15: return 9.0
        if pct < -0.10: return 8.0
        if pct < -0.05: return 7.0
        if pct <  0.00: return 6.0
        if pct <  0.05: return 4.5
        if pct <  0.10: return 3.0
        if pct <  0.20: return 2.0
        return 1.0

    def score_macd(self, macd: float, signal: float, hist: float) -> float:
        if pd.isna(macd) or pd.isna(signal): return 5.0
        if hist > 0 and macd > signal:
            return min(7.0 + min(abs(hist) * 100, 5.0), 10.0)
        if hist < 0 and macd < signal:
            return max(3.0 - min(abs(hist) * 100, 5.0), 0.0)
        return 5.0

    def score_volume(self, volume: float, vol_ma: float, price_change_pct: float) -> float:
        if pd.isna(vol_ma) or vol_ma == 0: return 5.0
        vol_ratio = volume / vol_ma
        if vol_ratio > 2.0 and price_change_pct < -0.02: return 9.0
        if vol_ratio > 1.5 and price_change_pct < -0.01: return 7.5
        if vol_ratio > 1.5: return 6.0
        if vol_ratio < 0.5: return 3.0
        return 5.0

    def score_bollinger(self, price: float, bb_lower: float, bb_upper: float) -> float:
        if pd.isna(bb_lower) or pd.isna(bb_upper): return 5.0
        band_range = bb_upper - bb_lower
        if band_range == 0: return 5.0
        position = (price - bb_lower) / band_range
        if position < 0:    return 10.0
        if position < 0.10: return 9.0
        if position < 0.25: return 7.5
        if position < 0.50: return 5.5
        if position < 0.75: return 4.0
        if position < 0.90: return 2.5
        return 1.0

    def calculate_composite_score(self, row: pd.Series, prev_close: Optional[float] = None) -> dict:
        cfg = self.config
        price = row["Close"]
        price_change_pct = (price - prev_close) / prev_close if prev_close else 0.0

        s_rsi  = self.score_rsi(row.get("RSI", float("nan")))
        s_ma   = self.score_ma_position(price, row.get("MA50", float("nan")), row.get("MA200", float("nan")))
        s_macd = self.score_macd(row.get("MACD", float("nan")), row.get("MACD_Signal", float("nan")), row.get("MACD_Hist", float("nan")))
        s_vol  = self.score_volume(row.get("Volume", 0), row.get("Vol_MA20", float("nan")), price_change_pct)
        s_bb   = self.score_bollinger(price, row.get("BB_Lower", float("nan")), row.get("BB_Upper", float("nan")))

        composite = (
            s_rsi  * cfg.weight_rsi  +
            s_ma   * cfg.weight_ma   +
            s_macd * cfg.weight_macd +
            s_vol  * cfg.weight_volume +
            s_bb   * cfg.weight_bb
        )

        return {
            "score_composite": round(composite, 2),
            "score_rsi":    round(s_rsi, 2),
            "score_ma":     round(s_ma, 2),
            "score_macd":   round(s_macd, 2),
            "score_volume": round(s_vol, 2),
            "score_bb":     round(s_bb, 2),
        }

    def get_action(self, score: float, rsi: float, profit_pct: Optional[float] = None) -> str:
        cfg = self.config
        if not pd.isna(rsi):
            if rsi > cfg.rsi_sell_heavy:   return "SELL_HEAVY"
            if rsi > cfg.rsi_sell_partial: return "SELL_PARTIAL"
        if profit_pct and profit_pct >= cfg.profit_target_2:
            return "SELL_PARTIAL"
        if score >= cfg.score_buy_heavy:  return "BUY_HEAVY"
        if score >= cfg.score_buy_normal: return "BUY_NORMAL"
        if score >= cfg.score_wait:       return "WAIT"
        return "SKIP"

    def analyze(self, ticker: str, period: str = "1y") -> dict:
        df = self.fetch_data(ticker, period=period)
        df = self.calculate_indicators(df)
        df = df.dropna(subset=["RSI"])
        if len(df) < 2:
            raise ValueError("ข้อมูลไม่เพียงพอ")

        last   = df.iloc[-1]
        prev   = df.iloc[-2]
        scores = self.calculate_composite_score(last, prev_close=prev["Close"])
        action = self.get_action(scores["score_composite"], last.get("RSI"))

        return {
            "ticker":  ticker,
            "date":    last.name.strftime("%Y-%m-%d"),
            "price":   round(float(last["Close"]), 2),
            "rsi":     round(float(last.get("RSI", float("nan"))), 1),
            "ma50":    round(float(last.get("MA50",  float("nan"))), 2),
            "ma200":   round(float(last.get("MA200", float("nan"))), 2),
            "macd":    round(float(last.get("MACD",  float("nan"))), 3),
            "action":  action,
            **scores,
            "df": df,
        }


# ==================== Quick Test ====================

if __name__ == "__main__":
    scorer = SmartDCAScorer()
    tickers = ["AAPL", "NVDA", "MSFT"]
    print(f"\n{'='*60}")
    print(f"{'Ticker':<8} {'Price':>8} {'RSI':>6} {'Score':>6} {'Action'}")
    print(f"{'='*60}")
    for ticker in tickers:
        try:
            r = scorer.analyze(ticker)
            print(f"{r['ticker']:<8} ${r['price']:>7.2f} {r['rsi']:>6.1f} {r['score_composite']:>6.2f} {r['action']}")
        except Exception as e:
            print(f"{ticker:<8} ERROR: {e}")
    print(f"{'='*60}\n")
