# Restock

Autonomous operations layer for vending machines: a demo MVP.
The AI forecasts per-machine demand and drafts purchase orders;
guardrails (a $200 spend cap, a cost × 1.3 margin floor, and an audit
log) and the owner make the final call. Inspired by Anthropic's
Project Vend.

## Layout

- `backend/generate_data.py`: synthetic fleet data: 10 machines, 8 SKUs,
  90 days of sales → `data/*.csv`
- `backend/forecast.py`: simple moving average adjusted by day of week
  (no ML) → `data/forecast.json` with avg daily sales and predicted
  stockout dates
- `frontend/index.html`: public cinematic landing page (no build step)
- `frontend/login.html`: login gate with salted-hash credential checks.
  Demo accounts: `owner` / `vend2026` and `admin` / `admin2026`
- `frontend/app.html`: the operator console; requires login. Dashboard
  with fleet totals and per-machine stats, market recommendations per
  machine, inventory and forecasts, draft orders with a confirm step,
  and the audit log

## Run

```
python3 backend/generate_data.py
python3 backend/forecast.py
python3 -m http.server 8000
```

Then open <http://localhost:8000/frontend/> for the landing page and
log in with `owner` / `vend2026` to reach the console. Machine M03
(Riverside Gym) is seeded to stock out within days; M07's draft order
exceeds the spend cap to demo the guardrail. Approvals persist to
localStorage and appear in the Audit Log.

The login is a client-side demo gate for the pitch, not real security.
