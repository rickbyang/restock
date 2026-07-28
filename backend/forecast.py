"""Forecast engine for the Restock demo. No ML.

Reads data/sales.csv + data/inventory.csv and computes, per machine/SKU:
  - avg daily sales: simple moving average over the last 28 days
  - day-of-week factors: (avg for that weekday over 90 days) / overall avg
  - predicted stockout date: walk forward day by day, subtracting expected
    demand (avg x that day's weekday factor) until stock runs out
  - 30-day analytics per SKU and per machine (units, revenue, profit,
    margin, 14-day trend) for the dashboard
  - rule-based market recommendations per machine (expand facings,
    reprice under-margin SKUs, swap slow movers, weekend prep)

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


def recommend(sku_rows, location_type):
    """Rule-based market recommendations for one machine, best-first."""
    recs = []
    by_units = sorted(sku_rows, key=lambda s: s["units_30d"], reverse=True)
    top = by_units[0]

    # expand the runaway seller
    if top["avg_daily_sales"] >= 3.5:
        recs.append({
            "type": "EXPAND",
            "title": f"Add a second facing of {top['name']}",
            "detail": (f"Top seller at {top['avg_daily_sales']}/day and "
                       f"${top['revenue_30d']:.0f} revenue in 30 days. A second row "
                       f"halves its stockout risk."),
        })

    # reprice anything under the margin floor
    for s in sku_rows:
        if s["unit_price"] < s["unit_cost"] * 1.3:
            floor = s["unit_cost"] * 1.3
            recs.append({
                "type": "REPRICE",
                "title": f"Raise {s['name']} to at least ${floor:.2f}",
                "detail": (f"Selling at ${s['unit_price']:.2f} on a ${s['unit_cost']:.2f} "
                           f"cost is a {s['margin_pct']:.0f}% margin, under the 1.3x floor."),
            })

    # weekend prep where the lift is real
    lifted = [s for s in sku_rows if s["weekend_lift_pct"] >= 12 and s["avg_daily_sales"] >= 2]
    if lifted and location_type in ("gym", "transit"):
        s = max(lifted, key=lambda x: x["weekend_lift_pct"])
        recs.append({
            "type": "PREP",
            "title": f"Stock {s['name']} by Friday",
            "detail": (f"Weekend demand runs {s['weekend_lift_pct']:.0f}% above the "
                       f"weekly average at this location."),
        })

    # swap out the slow, thin-margin tail
    slow = [s for s in sku_rows if s["avg_daily_sales"] < 1.6 and s["margin_pct"] < 50]
    if slow:
        s = min(slow, key=lambda x: x["units_30d"])
        recs.append({
            "type": "SWAP",
            "title": f"Consider replacing {s['name']}",
            "detail": (f"Slowest earner: {s['units_30d']} units in 30 days at "
                       f"{s['margin_pct']:.0f}% margin. A faster SKU earns the slot back."),
        })

    # celebrate momentum
    riser = max(sku_rows, key=lambda s: s["trend_pct"])
    if riser["trend_pct"] >= 15 and riser["units_30d"] >= 20:
        recs.append({
            "type": "TREND",
            "title": f"{riser['name']} is heating up",
            "detail": (f"Sales up {riser['trend_pct']:.0f}% in the last two weeks. "
                       f"Watch cover; consider a price test."),
        })

    return recs[:4]


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

            # 30-day analytics and a 14d-vs-prior-14d trend
            cost_f, price_f = float(sku["unit_cost"]), float(sku["unit_price"])
            u30 = sum(u for d, u in rows if d >= today - timedelta(days=30))
            u14 = sum(u for d, u in rows if d >= today - timedelta(days=14))
            u14_prior = sum(u for d, u in rows
                            if today - timedelta(days=28) <= d < today - timedelta(days=14))
            trend = (u14 / u14_prior - 1) if u14_prior else 0.0
            margin = (price_f - cost_f) / price_f if price_f else 0.0
            weekend_lift = (dow_factor[5] + dow_factor[6]) / 2 - 1

            sku_rows.append({
                "sku_id": sid,
                "name": sku["name"],
                "category": sku["category"],
                "unit_cost": cost_f,
                "unit_price": price_f,
                "current_stock": int(stock),
                "avg_daily_sales": round(avg, 2),
                "dow_factor": [round(x, 3) for x in dow_factor],
                "stockout_date": stockout_date,       # null = beyond horizon
                "days_until_stockout": days_until,    # null = beyond horizon
                "units_30d": u30,
                "revenue_30d": round(u30 * price_f, 2),
                "profit_30d": round(u30 * (price_f - cost_f), 2),
                "margin_pct": round(margin * 100, 1),
                "trend_pct": round(trend * 100, 1),
                "weekend_lift_pct": round(weekend_lift * 100, 1),
            })

        # machine-level rollup
        units_30d = sum(s["units_30d"] for s in sku_rows)
        revenue_30d = round(sum(s["revenue_30d"] for s in sku_rows), 2)
        profit_30d = round(sum(s["profit_30d"] for s in sku_rows), 2)
        top = max(sku_rows, key=lambda s: s["units_30d"])
        w_margin = (profit_30d / revenue_30d * 100) if revenue_30d else 0.0
        m_trend = (sum(s["units_30d"] for s in sku_rows) and
                   sum(s["trend_pct"] * s["units_30d"] for s in sku_rows) / units_30d)

        out_machines.append({
            "machine_id": mid,
            "name": m["name"],
            "location": m["location"],
            "location_type": m["location_type"],
            "units_30d": units_30d,
            "revenue_30d": revenue_30d,
            "profit_30d": profit_30d,
            "avg_margin_pct": round(w_margin, 1),
            "trend_pct": round(m_trend or 0.0, 1),
            "top_sku": top["name"],
            "top_sku_daily": top["avg_daily_sales"],
            "recommendations": recommend(sku_rows, m["location_type"]),
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
