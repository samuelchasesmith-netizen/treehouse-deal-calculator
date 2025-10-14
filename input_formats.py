import re
from typing import Tuple

MONEY_RE = re.compile(r"[,\s$]")
PCT_RE = re.compile(r"[,\s%]")

def parse_money(s: str, default: float = 0.0) -> Tuple[float, bool]:
    if s is None:
        return default, True
    try:
        clean = MONEY_RE.sub("", str(s))
        if clean.strip() == "":
            return default, True
        return float(clean), True
    except Exception:
        return default, False

def parse_percent(s: str, default: float = 0.0) -> Tuple[float, bool]:
    if s is None:
        return default, True
    try:
        clean = PCT_RE.sub("", str(s))
        if clean.strip() == "":
            return default, True
        return float(clean), True
    except Exception:
        return default, False

def fmt_money(v: float, decimals: int = 0) -> str:
    if v is None:
        v = 0.0
    return f"${v:,.{decimals}f}"

def fmt_number(v: float, decimals: int = 0) -> str:
    if v is None:
        v = 0.0
    return f"{v:,.{decimals}f}"

def fmt_percent(v: float, decimals: int = 2) -> str:
    if v is None:
        v = 0.0
    return f"{v:.{decimals}f}%"
