# Smart DCA — S&P 500 Analyzer

ระบบวิเคราะห์จังหวะซื้อ/ขายแบบ Smart DCA สำหรับหุ้น S&P 500

## โครงสร้างไฟล์

```
smart_dca/
├── score_engine.py   # Core: คำนวณ composite score
├── backtest.py       # Backtesting: เปรียบเทียบ 3 strategies
├── dashboard.py      # Streamlit UI dashboard
└── requirements.txt
```

## ติดตั้ง

```bash
pip install -r requirements.txt
```

## วิธีรัน

### 1. ทดสอบ Score Engine
```bash
python score_engine.py
```
ผลที่ได้:
```
============================================================
Ticker    Price    RSI  Score  Action
============================================================
AAPL    $182.50   42.3   6.15  BUY_NORMAL
NVDA    $875.20   38.1   7.80  BUY_HEAVY
MSFT    $415.00   65.2   3.20  WAIT
============================================================
```

### 2. รัน Backtest
```bash
python backtest.py
```

### 3. เปิด Dashboard
```bash
streamlit run dashboard.py
```
แล้วเปิด http://localhost:8501

## Logic การให้คะแนน (0–10)

| Score | Action | ความหมาย |
|-------|--------|----------|
| 8–10  | BUY_HEAVY  | ซื้อ 2x ของแผนปกติ |
| 6–7.9 | BUY_NORMAL | ซื้อตามแผนปกติ |
| 4–5.9 | WAIT       | รอก่อน ไม่ซื้อเดือนนี้ |
| 0–3.9 | SKIP       | ข้ามเดือนนี้ |

## Indicators ที่ใช้

- **RSI (30%)** — ยิ่ง oversold ยิ่งดี
- **MA Position (25%)** — ราคาต่ำกว่า MA200 ยิ่งดี
- **MACD (20%)** — Bullish crossover = ดี
- **Volume (15%)** — Volume spike + ราคาลง = โอกาส
- **Bollinger Bands (10%)** — ใกล้ lower band = ดี

## ⚠️ Disclaimer
ระบบนี้เป็นเครื่องมือช่วยวิเคราะห์เท่านั้น ไม่ใช่คำแนะนำทางการเงิน
ผลย้อนหลังไม่รับประกันผลในอนาคต
