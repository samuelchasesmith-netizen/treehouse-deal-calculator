# engine.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any
import copy

def pmt(monthly_rate: float, nper: int, pv: float) -> float:
    if nper <= 0: return 0.0
    if monthly_rate == 0: return pv / nper
    return (monthly_rate * pv) / (1 - (1 + monthly_rate) ** (-nper))

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
        bal = float(self.principal)
        r = float(self.annual_rate_pct) / 100.0 / 12.0
        sched: List[Dict[str, float]] = []
        for _ in range(max(0, self.standby_months)):
            m = start_month + len(sched)
            interest = bal * r
            if self.accrue_during_standby: bal += interest
            sched.append({"month": m, "phase": "standby", "begin_balance": round(bal - interest,2),
                          "payment": 0.0, "interest": round(interest,2), "principal": 0.0, "end_balance": round(bal,2)})
        for _ in range(max(0, self.interest_only_months)):
            m = start_month + len(sched)
            interest = bal * r
            sched.append({"month": m, "phase": "interest_only", "begin_balance": round(bal,2),
                          "payment": round(interest,2), "interest": round(interest,2), "principal": 0.0, "end_balance": round(bal,2)})
        rem = max(0, int(self.term_months) - self.standby_months - self.interest_only_months)
        if rem > 0:
            pay = pmt(r, rem, bal)
            for _ in range(rem):
                m = start_month + len(sched)
                interest = bal * r
                principal = pay - interest
                if principal > bal: principal, pay = bal, interest + bal
                bal -= principal
                sched.append({"month": m, "phase": "amortization", "begin_balance": round(bal+principal,2),
                              "payment": round(pay,2), "interest": round(interest,2), "principal": round(principal,2), "end_balance": round(bal,2)})
        return sched[:months]

def stitch_refi(original: List[Dict[str,float]], refi_month: int, new_rate_pct: float, new_term_months: int) -> List[Dict[str,float]]:
    if refi_month <= 0: return original
    rem_bal = None
    for row in original:
        if row["month"] == refi_month:
            rem_bal = row["end_balance"]; break
    if rem_bal is None: return original
    new = LoanSchedule("Refi", rem_bal, new_rate_pct, new_term_months, 0, 0, False).build(months=600, start_month=refi_month+1)
    return [r for r in original if r["month"] <= refi_month] + new

def compute(config: Dict[str, Any]) -> Dict[str, Any]:
    cfg = copy.deepcopy(config)
    investors = cfg.get("investors", [])
    investor_pcts = [float(i.get("pct", 0))/100.0 for i in investors]
    investor_equity_initial = [float(i.get("contribution", 0)) for i in investors]
    follow_ons = cfg.get("follow_on", [])

    wc_buf = float(cfg.get("wc_months",0))*float(cfg.get("wc_monthly_opex",0))
    total_uses = float(cfg["purchase_price"]) + float(cfg["closing_costs"]) + wc_buf
    total_sources = sum(investor_equity_initial) + float(cfg["sba_principal"]) + float(cfg["seller_principal"])

    sde_y1 = float(cfg["hist_sde"]) - float(cfg["gm_salary"]) + float(cfg["normalized_adj"])
    sde_growth = float(cfg.get("sde_growth_pct",0))/100.0

    sba = LoanSchedule("SBA", float(cfg["sba_principal"]), float(cfg["sba_rate"]), int(cfg["sba_term_months"]), int(cfg.get("sba_io_months",0)), 0, False).build(600)
    seller = LoanSchedule("Seller", float(cfg["seller_principal"]), float(cfg["seller_rate"]), int(cfg["seller_term_months"]), 0, int(cfg.get("seller_standby_months",0)), True).build(600)
    if cfg.get("refi",{}).get("enable", False):
        rm = int(cfg["refi"].get("year",3))*12
        sba = stitch_refi(sba, rm, float(cfg["refi"].get("new_rate_pct", cfg["sba_rate"])), int(cfg["refi"].get("new_term_months", cfg["sba_term_months"])))
    sba = [r for r in sba if r["month"]<=60]; seller = [r for r in seller if r["month"]<=60]

    maint_m = float(cfg.get("maint_capex",0))/12.0
    growth_m = float(cfg.get("growth_capex",0))/12.0
    retain = float(cfg.get("retain_pct",0))/100.0
    sde_m = sde_y1/12.0
    monthly = []
    cash = wc_buf

    # map follow-ons to month index
    follow_by_month = {}
    for fo in follow_ons:
        y = int(fo.get("year",1)); m = int(fo.get("month",1")); amt = float(fo.get("amount",0))
        name = fo.get("name","")
        idx = (y-1)*12 + m
        follow_by_month.setdefault(idx, []).append({"name": name, "amount": amt})

    investor_total_contrib = investor_equity_initial[:]

    for m in range(1, 13):
        sba_row = sba[m-1] if m-1 < len(sba) else {"payment":0.0}
        seller_row = seller[m-1] if m-1 < len(seller) else {"payment":0.0}
        debt_service = sba_row["payment"] + seller_row["payment"]
        cfads = sde_m - maint_m
        fcfe = cfads - debt_service - growth_m

        inflow = 0.0
        for fo in follow_by_month.get(m, []):
            inflow += fo["amount"]
            for idx, inv in enumerate(investors):
                if inv.get("name","") == fo["name"]:
                    investor_total_contrib[idx] += fo["amount"]

        distributable = max(0.0, (fcfe + inflow) * (1 - retain))
        retained_amt = max(0.0, (fcfe + inflow)) - distributable if (fcfe + inflow) > 0 else 0.0
        cash += retained_amt + ((fcfe + inflow) - max(0.0, (fcfe + inflow)))

        row = {"Month": m, "SDE": round(sde_m,2), "Maint CapEx": round(maint_m,2), "Growth CapEx": round(growth_m,2),
               "SBA Payment": round(sba_row["payment"],2), "Seller Payment": round(seller_row["payment"],2),
               "Debt Service": round(debt_service,2), "CFADS": round(cfads,2), "FCFE": round(fcfe,2),
               "Follow-on Inflow": round(inflow,2), "Retained": round(retained_amt,2), "Distributable": round(distributable,2), "Cash Balance": round(cash,2)}
        for idx, inv in enumerate(investors):
            row[f"Dividend • {inv.get('name','Inv '+str(idx+1))}"] = round(distributable*investor_pcts[idx],2)
        monthly.append(row)

    # annual with ΔNWC and follow-ons
    def nwc_from_days(rev: float, cogs_ratio: float, ar_d: int, ap_d: int, inv_d: int) -> float:
        cogs = rev * cogs_ratio
        ar = rev * (ar_d/365.0); inv = cogs * (inv_d/365.0); ap = cogs * (ap_d/365.0)
        return ar + inv - ap

    sde_a = sde_y1; revenue = float(cfg.get("revenue_y1",0.0)); cogs_pct = float(cfg.get("cogs_pct",50.0))/100.0
    ar_d = int(cfg.get("nwc_days",{}).get("ar",0)); ap_d = int(cfg.get("nwc_days",{}).get("ap",0)); inv_d = int(cfg.get("nwc_days",{}).get("inv",0))
    nwc_prev = nwc_from_days(revenue, cogs_pct, ar_d, ap_d, inv_d)
    years = []; inv_cum_div = [0.0 for _ in investors]; inv_payback = [None for _ in investors]

    for y in range(1,6):
        if y>1: sde_a *= (1+sde_growth); revenue *= (1+sde_growth)
        start, end = (y-1)*12, (y-1)*12+12
        sba_ann = sum(r["payment"] for r in sba[start:end] if start < len(sba))
        seller_ann = sum(r["payment"] for r in seller[start:end] if start < len(seller))
        total_debt = sba_ann + seller_ann
        nwc_curr = nwc_from_days(revenue, cogs_pct, ar_d, ap_d, inv_d)
        delta_nwc = 0.0 if y==1 else (nwc_curr - nwc_prev); nwc_prev = nwc_curr

        inflow = 0.0
        for m in range(start+1, end+1):
            for fo in follow_by_month.get(m, []):
                inflow += fo["amount"]
                # investor_total_contrib counted during monthly Y1; beyond Y1 we still count contributions for payback
                for idx, inv in enumerate(investors):
                    if inv.get("name","") == fo["name"]:
                        investor_total_contrib[idx] += fo["amount"] if m > 12 else 0.0

        cfads_a = sde_a - float(cfg.get("maint_capex",0)) - delta_nwc
        fcfe_a = cfads_a - total_debt - float(cfg.get("growth_capex",0))
        retain = float(cfg.get("retain_pct",0))/100.0
        distributable_a = max(0.0, (fcfe_a + inflow) * (1 - retain))
        retained_a = max(0.0, (fcfe_a + inflow)) - distributable_a if (fcfe_a + inflow) > 0 else 0.0

        row = {"Year": y, "Pro-forma SDE": round(sde_a,0), "ΔNWC": round(delta_nwc,0), "Maint CapEx": round(float(cfg.get("maint_capex",0)),0),
               "Growth CapEx": round(float(cfg.get("growth_capex",0)),0), "SBA Debt Service": round(sba_ann,0),
               "Seller Debt Service": round(seller_ann,0), "Total Debt Service": round(total_debt,0),
               "CFADS": round(cfads_a,0), "FCFE": round(fcfe_a,0), "Follow-on Inflow": round(inflow,0),
               "Retained": round(retained_a,0), "Distributable": round(distributable_a,0)}
        dscr = (cfads_a/total_debt) if total_debt>0 else None
        row["DSCR"] = round(dscr,2) if dscr else "N/A"

        for idx, inv in enumerate(investors):
            div = distributable_a * investor_pcts[idx]
            inv_cum_div[idx] += div
            row[f"Investor Dividend • {inv.get('name','Inv '+str(idx+1))}"] = round(div,0)
            if inv_cum_div[idx] >= investor_total_contrib[idx] and investor_total_contrib[idx] > 0 and inv_payback[idx] is None:
                inv_payback[idx] = y

        years.append(row)

    summary = []
    for idx, inv in enumerate(investors):
        equity = investor_total_contrib[idx]; cumdiv = inv_cum_div[idx]
        multiple = (cumdiv/equity) if equity>0 else None
        summary.append({"Investor": inv.get("name", f"Investor {idx+1}"),
                        "Ownership %": round(inv.get("pct",0.0),2),
                        "Contributed (incl. follow-ons)": round(equity,0),
                        "Total Dividends (5y)": round(cumdiv,0),
                        "Equity Multiple (5y)": round(multiple,2) if multiple is not None else "N/A",
                        "Payback Year": inv_payback[idx] if inv_payback[idx] is not None else ">5"})
    return {"working_cap_buffer": round(wc_buf,2), "total_uses": round(total_uses,2), "total_sources": round(total_sources,2),
            "proforma_sde_y1": round(sde_y1,2), "y1": monthly, "years": years, "investors": summary}
