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
        # Standby phase
        for _ in range(max(0, self.standby_months)):
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
        # Interest-only phase
        for _ in range(max(0, self.interest_only_months)):
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
        # Amortization
        rem = max(0, int(self.term_months) - self.standby_months - self.interest_only_months)
        if rem > 0:
            pay = pmt(r, rem, bal)
            for _ in range(rem):
                m = start_month + len(sched)
                interest = bal * r
                principal = pay - interest
                if principal > bal:
                    principal, pay = bal, interest + bal
                bal -= principal
                sched.append({
                    "month": m,
                    "phase": "amortization",
                    "begin_balance": round(bal + principal, 2),
                    "payment": round(pay, 2),
                    "interest": round(interest, 2),
                    "principal": round(principal, 2),
                    "end_balance": round(bal, 2)
                })
        return sched[:months]

def stitch_refi(original: List[Dict[str, float]], refi_month: int, new_rate_pct: float, new_term_months: int) -> List[Dict[str, float]]:

