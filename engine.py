from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any
import copy

# ----------------------------
# Helper functions
# ----------------------------
def pmt(rate: float, nper: int, pv: float) -> float:
    """Calculate loan payment (monthly)."""
    if nper <= 0:
        return 0.0
    if rate == 0:
        return pv / nper
    return (rate * pv) / (1 - (1 + rate) ** (-nper))


@dataclass
class LoanSchedule:
    name: str
    principal: float
    annual_rate_pct: float
    term_months: int
    interest_only_months: int = 0
    standby_months: int = 0
    accrue_during_standby: bool = True

    def build(self, months: int = 60, start_month: int = 1) -> List[Dict[str, float]]:
        """Generate loan schedule for each month."""
        bal = float(self.principal)
        r = float(self.annual_rate_pct) / 100 / 12
        sched: List[Dict[str, float]] = []

        # Standby period
        for _ in range(self.standby_months):
            m = start_month + len(sched)
            interest = bal * r
            if self.accrue_during_standby:
                bal += interest
            sched.append({
                "month": m,
                "phase": "standby",
                "begin_balance": round(bal - interest, 2),
                "payment": 0.0,
                "interest": round(interest, 2),
                "principal": 0.0,
                "end_balance": round(bal, 2)
            })

        # Interest-only period
        for _ in range(self.interest_only_months):
            m = start_month + len(sched)
            interest = bal * r
            sched.append({
                "month": m,
                "phase": "interest_only",
                "begin_balance": round(bal, 2),
                "payment": round(interest, 2),
                "interest": round(interest, 2),
                "principal": 0.0,
                "end_balance": round(bal, 2)
            })

        # Amortization period
        remaining_term = max(0, self.term_months - self.interest_only_months - self.standby_months)
        if remaining_term > 0:
            payment = pmt(r, remaining_term, bal)
            for _ in range(remaining_term):
                m = start_month + len(sched)
                interest = bal * r
                principal = payment - interest
                if principal > bal:
                    principal = bal
                    payment = interest + principal
                bal -= principal
                sched.append({
                    "month": m,
                    "phase": "amortization",
                    "begin_balance": round(bal + principal, 2),
                    "payment": round(payment, 2),
                    "interest": round(interest, 2),
                    "principal": round(principal, 2),
                    "end_balance": round(bal, 2)
                })
        return sched[:months]


def stitch_refi(original: List[Dict[str, float]], refi_month: int,
                new_rate_pct: float, new_term_months: int) -> List[Dict[str, float]]:
    """Stitch a refinance schedule starting at refi_month."""
    if refi_month <= 0:
        return original
    rem_bal = None
    for row in original:
        if row["month"] == refi_month:
            rem_bal = row["end_balance"]
            break
    if rem_bal is None:
        return original

    new_loan = LoanSchedule("Refi", rem_bal, new_rate_pct, new_term_months)
    new_sched = new_loan.build(months=600, start_month=refi_month + 1)
    return [r for r in original if r["month"] <= refi_month] + new_sched


# ----------------------------
# Core compute function
# ----------------------------
def compute(config: Dict[str, Any]) -> Dict[str, Any]:
    """Compute simplified Treehouse deal cashflow summary."""
    cfg = copy.deepcopy(config)

    # --- Basic variables ---
    purchase = float(cfg.get("purchase_price", 0))
    closing = float(cfg.get("closing_costs", 0))
    wc_buf = float(cfg.get("wc_months", 0)) * float(cfg.get("wc_monthly_opex", 0))
    total_uses = purchase + closing + wc_buf

    investors = cfg.get("investors", [])
    investor_equity = [float(i.get("contribution", 0)) for i in investors]
    investor_pcts = [float(i.get("pct", 0)) / 100 for i in investors]
    total_sources = sum(investor_equity) + float(cfg.get("sba_principal", 0)) + float(cfg.get("seller_principal", 0))

    # --- Pro-forma SDE ---
    sde_y1 = float(cfg.get("hist_sde", 0)) - float(cfg.get("gm_salary", 0)) + float(cfg.get("normalized_adj", 0))
    maint_capex = float(cfg.get("maint_capex", 0))
    growth_capex = float(cfg.get("growth_capex", 0))
    retain_pct = float(cfg.get("retain_pct", 0)) / 100

    # --- Build loans ---
    sba = LoanSchedule("SBA", float(cfg.get("sba_principal", 0)), float(cfg.get("sba_rate", 0)),
                       int(cfg.get("sba_term_months", 0)), int(cfg.get("sba_io_months", 0))).build(60)
    seller = LoanSchedule("Seller", float(cfg.get("seller_principal", 0)), float(cfg.get("seller_rate", 0)),
                          int(cfg.get("seller_term_months", 0)), 0,
                          int(cfg.get("seller_standby_months", 0)), True).build(60)

    # --- Month 1-12 simple summary (no refi or ΔNWC for brevity) ---
    sde_m = sde_y1 / 12
    maint_m = maint_capex / 12
    growth_m = growth_capex / 12
    monthly = []
    cash = wc_buf
    for m in range(1, 13):
        sba_row = sba[m - 1] if m - 1 < len(sba) else {"payment": 0.0}
        seller_row = seller[m - 1] if m - 1 < len(seller) else {"payment": 0.0}
        debt_service = sba_row["payment"] + seller_row["payment"]
        cfads = sde_m - maint_m
        fcfe = cfads - debt_service - growth_m
        distributable = max(0.0, fcfe * (1 - retain_pct))
        retained = max(0.0, fcfe) - distributable if fcfe > 0 else 0.0
        cash += retained
        row = {
            "Month": m,
            "SDE": round(sde_m, 2),
            "Debt Service": round(debt_service, 2),
            "CFADS": round(cfads, 2),
            "FCFE": round(fcfe, 2),
            "Retained": round(retained, 2),
            "Distributable": round(distributable, 2),
            "Cash Balance": round(cash, 2)
        }
        for idx, inv in enumerate(investors):
            row[f"Dividend • {inv.get('name', f'Investor {idx+1}') }"] = round(distributable * investor_pcts[idx], 2)
        monthly.append(row)

    # --- Return simple outputs ---
    return {
        "working_cap_buffer": round(wc_buf, 2),
        "total_uses": round(total_uses, 2),
        "total_sources": round(total_sources, 2),
        "proforma_sde_y1": round(sde_y1, 2),
        "y1": monthly,
        "years": [],
        "investors": investors
    }
