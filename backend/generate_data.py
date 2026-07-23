"""Generate synthetic vending fleet data for the Restock demo.

Writes data/machines.csv, data/skus.csv, data/sales.csv (90 days),
and data/inventory.csv (current stock per machine/SKU).

Deterministic (seeded). Machine M03 is seeded so its best seller
(Energy Drink) stocks out within ~2 days; M07 is seeded so its draft
order exceeds the $200 spend cap.
"""

import csv
import math
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(42)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DAYS = 90

MACHINES = [
    ("M01", "Acme HQ Lobby", "412 Market St", "office", 1.00),
    ("M02", "TechPark Tower 2", "88 Innovation Way", "office", 0.90),
    ("M03", "Riverside Gym", "230 River Rd", "gym", 1.10),
    ("M04", "City Hospital ER Wing", "1 Hospital Dr", "hospital", 0.80),
    ("M05", "State U Library", "500 Campus Loop", "campus", 1.00),
    ("M06", "State U Dorm West", "512 Campus Loop", "campus", 0.90),
    ("M07", "Central Station Concourse", "1 Station Plaza", "transit", 1.30),
    ("M08", "Airport Gate B12", "Terminal B", "transit", 1.20),
    ("M09", "Downtown Fitness Club", "77 2nd Ave", "gym", 0.85),
    ("M10", "Northside Office Park", "9600 North Blvd", "office", 0.70),
]

# sku_id, name, category, unit_cost, unit_price, base daily demand
# S5 Protein Bar is priced below cost x 1.3 to exercise the margin-floor flag.
SKUS = [
    ("S1", "Cola Classic", "beverage", 0.75, 2.00, 3.5),
    ("S2", "Sparkling Water", "beverage", 0.60, 1.75, 2.0),
    ("S3", "Sea Salt Chips", "snack", 0.55, 1.50, 2.5),
    ("S4", "Chocolate Bar", "snack", 0.90, 2.25, 2.2),
    ("S5", "Protein Bar", "snack", 1.40, 1.75, 1.5),
    ("S6", "Trail Mix", "snack", 1.10, 2.50, 1.2),
    ("S7", "Energy Drink", "beverage", 1.60, 3.50, 2.0),
    ("S8", "Instant Noodles", "meal", 0.80, 2.00, 1.4),
]

# Day-of-week demand multipliers by location type (Mon=0 .. Sun=6).
DOW = {
    "office":   [1.20, 1.20, 1.20, 1.20, 1.10, 0.30, 0.20],
    "gym":      [1.10, 1.00, 1.00, 1.00, 0.90, 1.30, 1.20],
    "transit":  [1.10, 1.10, 1.10, 1.10, 1.10, 0.80, 0.80],
    "campus":   [1.15, 1.15, 1.15, 1.15, 1.05, 0.60, 0.50],
    "hospital": [1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.00],
}

# Final mean-daily-sales overrides (machine, sku) -> mu.
MU_OVERRIDES = {
    ("M03", "S7"): 6.0,  # M03's best seller
    ("M07", "S1"): 6.5,
    ("M07", "S2"): 3.0,
    ("M07", "S4"): 4.0,
    ("M07", "S6"): 3.0,
    ("M07", "S7"): 5.5,
    ("M07", "S8"): 3.0,
}

# Current stock expressed in days of expected demand. Defaults are healthy;
# overrides create the demo's red/yellow/cap-exceeded scenarios.
STOCK_DAYS_OVERRIDES = {
    ("M03", "S7"): 1.8,   # red: stocks out in ~2 days
    ("M03", "S5"): 5.0,
    ("M03", "S3"): 6.0,
    ("M02", "S4"): 5.5,   # yellow machine
    ("M06", "S8"): 6.0,   # yellow machine
    ("M07", "S1"): 4.5,   # yellow machine whose order busts the $200 cap
    ("M07", "S2"): 6.0,
    ("M07", "S4"): 4.5,
    ("M07", "S6"): 5.0,
    ("M07", "S7"): 5.0,
    ("M07", "S8"): 6.0,
}


def mu_for(machine_id, traffic, sku_id, base_mu):
    return MU_OVERRIDES.get((machine_id, sku_id), base_mu * traffic)


def main():
    DATA_DIR.mkdir(exist_ok=True)
    today = date.today()
    start = today - timedelta(days=DAYS)

    with open(DATA_DIR / "machines.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["machine_id", "name", "location", "location_type"])
        for mid, name, loc, ltype, _ in MACHINES:
            w.writerow([mid, name, loc, ltype])

    with open(DATA_DIR / "skus.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sku_id", "name", "category", "unit_cost", "unit_price"])
        for sid, name, cat, cost, price, _ in SKUS:
            w.writerow([sid, name, cat, f"{cost:.2f}", f"{price:.2f}"])

    with open(DATA_DIR / "sales.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "machine_id", "sku_id", "units_sold"])
        for d in range(DAYS):
            day = start + timedelta(days=d)
            for mid, _, _, ltype, traffic in MACHINES:
                dow_mult = DOW[ltype][day.weekday()]
                for sid, _, _, _, _, base_mu in SKUS:
                    mu = mu_for(mid, traffic, sid, base_mu) * dow_mult
                    units = max(0, round(random.gauss(mu, math.sqrt(max(mu, 0.1)))))
                    w.writerow([day.isoformat(), mid, sid, units])

    with open(DATA_DIR / "inventory.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["machine_id", "sku_id", "current_stock"])
        for mid, _, _, ltype, traffic in MACHINES:
            for sid, _, _, _, _, base_mu in SKUS:
                mu = mu_for(mid, traffic, sid, base_mu)
                days = STOCK_DAYS_OVERRIDES.get((mid, sid), random.uniform(10, 25))
                w.writerow([mid, sid, max(1, round(mu * days))])

    print(f"Wrote machines.csv, skus.csv, sales.csv, inventory.csv to {DATA_DIR}")


if __name__ == "__main__":
    main()
