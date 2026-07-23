"""Forecast engine for the Restock demo. No ML.

Reads data/sales.csv + data/inventory.csv and computes, per machine/SKU:
  - avg daily sales: simple moving average over the last 28 days
  - day-of-week factors: (avg for that weekday over 90 days) / overall avg
  - predicted stockout date: walk forward day by day, subtracting expected
    demand (avg x that day's weekday factor) until stock runs out

Writes data/forecast.json with everything the frontend needs.
"""

import csv
import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MA_WINDOW = 28
HORIZON = 60  # stop simulating past this many days


def read_csv(name):
    with open(DATA_DIR / name, newline="") as f:
        return list(csv.DictReader(f))


def main():
    machines = read_csv("machines.csv")
    skus = {r["sku_id"]: r for r in read_csv("skus.csv")}
    inventory = {(r["machine_id"], r["sku_id"]): int(r["current_stock"])
                 for r in read_csv("inventory.csv")}

    # sales[(machine, sku)] -> list of (date, units)
    sales = defaultdict(list)
    for r in read_csv("sales.csv"):
        sales[(r["machine_id"], r["sku_id"])].append(
            (datetime.strptime(r["date"], "%Y-%m-%d").date(), int(r["units_sold"])))

    today = date.today()
    out_machines = []
    for m in machines:
        mid = m["machine_id"]
        sku_rows = []
        for sid, sku in skus.items():
            rows = sorted(sales[(mid, sid)])
            recent = [u for d, u in rows if d >= today - timedelta(days=MA_WINDOW)]
            avg = sum(recent) / len(recent) if recent else 0.0

            # Day-of-week factors over the full history.
            by_dow = defaultdict(list)
            for d, u in rows:
                by_dow[d.weekday()].append(u)
            overall = sum(u for _, u in rows) / len(rows) if rows else 0.0
            dow_factor = [
                (sum(by_dow[w]) / len(by_dow[w]) / overall) if overall and by_dow[w] else 1.0
                for w in range(7)
            ]

            # Walk forward until expected cumulative demand exhausts stock.
            stock = float(inventory[(mid, sid)])
            stockout_date, days_until = None, None
            remaining = stock
            for i in range(1, HORIZON + 1):
                day = today + timedelta(days=i)
                remaining -= avg * dow_factor[day.weekday()]
                if remaining <= 0:
                    stockout_date, days_until = day.isoformat(), i
                    break

            sku_rows.append({
                "sku_id": sid,
                "name": sku["name"],
                "category": sku["category"],
                "unit_cost": float(sku["unit_cost"]),
                "unit_price": float(sku["unit_price"]),
                "current_stock": int(stock),
                "avg_daily_sales": round(avg, 2),
                "dow_factor": [round(x, 3) for x in dow_factor],
                "stockout_date": stockout_date,       # null = beyond horizon
                "days_until_stockout": days_until,    # null = beyond horizon
            })

        out_machines.append({
            "machine_id": mid,
            "name": m["name"],
            "location": m["location"],
            "location_type": m["location_type"],
            "skus": sku_rows,
        })

    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": today.isoformat(),
        "horizon_days": HORIZON,
        "machines": out_machines,
    }
    with open(DATA_DIR / "forecast.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {DATA_DIR / 'forecast.json'}")


if __name__ == "__main__":
    main()
