import json, os
import streamlit as st
import pandas as pd

from engine import compute
from utils import to_excel_bytes, to_pdf_bytes
from input_formats import parse_money, parse_percent, fmt_money, fmt_number, fmt_percent

st.set_page_config(page_title="Treehouse Deal Calculator v3.1 (hints-in-JSON)", layout="wide")

# Optional key
if os.getenv("APP_KEY"):
    gate = st.text_input("Enter access key", type="password")
    if gate != os.getenv("APP_KEY"):
        st.stop()

st.title("Treehouse Ventures • Deal Calculator (Web v3.1)")
st.caption("Formatted inputs/outputs • hover hints • Definitions • JSON export with _hints")

def money_input(label: str, value: float, key: str, help: str = "") -> float:
    default_str = fmt_money(value, 2)
    s = st.text_input(label, value=default_str, key=key, help=help)
    val, ok = parse_money(s, default=value)
    if not ok:
        st.warning(f"'{label}' is not a valid amount. Example: {fmt_money(3000000,0)}")
        return value
    return val

def percent_input(label: str, value_pct: float, key: str, help: str = "") -> float:
    default_str = fmt_percent(value_pct, 2)
    s = st.text_input(label, value=default_str, key=key, help=help)
    val, ok = parse_percent(s, default=value_pct)
    if not ok:
        st.warning(f"'{label}' is not a valid percent. Example: {fmt_percent(10.0)}")
        return value_pct
    return val

H = {
    "purchase_price": "**What you pay for the business at closing.** Example: Enter 3,000,000 for a $3M deal. *Impact:* Higher price raises required funding and debt service.",
    "closing_costs": "**Fees and transaction costs paid at closing.** Example: Legal, diligence, lender fees totaling 150,000. *Impact:* Increases total cash needed at close.",
    "wc_months": "**Months of operating expenses you want as a buffer.** Example: 3 months. *Impact:* More buffer = safer runway but higher cash need.",
    "wc_monthly_opex": "**Your average monthly operating expenses.** Example: 60,000. *Impact:* Drives the size of the buffer (months × OpEx).",

    "hist_sde": "**Seller’s Discretionary Earnings (historical annual).** Example: 900,000. *Impact:* Starting point for cash flow to service debt and pay dividends.",
    "gm_salary": "**Salary to replace the owner’s time.** Example: 180,000. *Impact:* Reduces SDE available after you hire management.",
    "normalized_adj": "**Ongoing add-backs or deductions.** Example: Remove one-time legal fees +30,000. *Impact:* Adjusts SDE to a sustainable level.",

    "maint_capex": "**Annual spend to maintain the business.** Example: 50,000. *Impact:* Reduces CFADS—understating it can inflate dividends.",
    "growth_capex": "**Annual investments to grow (optional).** Example: 100,000 for new equipment. *Impact:* Lowers FCFE today for potential future gains.",

    "revenue_y1": "**Expected Year-1 revenue.** Example: 4,500,000. *Impact:* Used with COGS% to model working capital needs (AR/Inv/AP).",
    "cogs_pct": "**COGS as % of revenue.** Example: 55%. *Impact:* Affects inventory/AP and free cash flow via ΔNWC.",

    "ar_days": "**Average days to collect invoices (AR Days).** Example: Net-30 → 30. *Impact:* Higher AR days ties up more cash in receivables.",
    "inv_days": "**Average days you hold inventory.** Example: 15. *Impact:* More inventory days = more cash tied up.",
    "ap_days": "**Average days to pay suppliers (AP Days).** Example: 20. *Impact:* Higher AP days frees cash but may strain suppliers.",

    "investor_pct": "**Ownership percentage for this investor.** Example: 25%. *Impact:* Controls their share of dividends and exit economics.",
    "investor_contrib": "**Cash this investor puts in at close.** Example: 175,000. *Impact:* Adds to Sources; used for payback and equity multiple.",

    "sba_principal": "**Loan amount from SBA lender.** Example: 1,800,000. *Impact:* Larger loans raise debt service and DSCR pressure.",
    "sba_rate": "**SBA loan annual interest rate.** Example: 10.00%. *Impact:* Higher rates increase payments, lowering FCFE.",
    "sba_term": "**SBA loan term in months.** Example: 120. *Impact:* Longer terms reduce monthly payment but extend debt.",
    "sba_io": "**Months of interest-only on SBA.** Example: 0. *Impact:* Lowers early payments but backloads principal.",

    "seller_principal": "**Seller-financed note amount.** Example: 450,000. *Impact:* Reduces upfront cash needed; adds another payment stream.",
    "seller_rate": "**Seller note annual interest rate.** Example: 6.00%. *Impact:* Cost of the seller financing.",
    "seller_term": "**Seller note term in months.** Example: 60. *Impact:* Shorter term means higher monthly payments.",
    "seller_standby": "**Months with no seller payments (interest accrues).** Example: 24. *Impact:* Improves early cash flow; increases later balance.",

    "sde_growth": "**Annual growth applied to SDE/Revenue (Y2–Y5).** Example: 3.00%. *Impact:* Drives future CFADS and dividends.",

    "retain_pct": "**Share of FCFE kept in the business before dividends.** Example: 10%. *Impact:* Builds cash cushion; slows investor payback.",
    "refi": "**Refinance SBA in a future year with new rate/term.** Example: Year 3 at 8.5%. *Impact:* Can lower debt service and improve DSCR.",

    "SDE": "**Seller’s Discretionary Earnings per period.** Example: $75,000/mo on $900k/yr. *Impact:* Core cash engine that funds everything else.",
    "CFADS": "**Cash Flow Available for Debt Service** = SDE − Maint CapEx − ΔNWC. *Impact:* If this shrinks, DSCR falls and risk rises.",
    "FCFE": "**Free Cash Flow to Equity** = CFADS − Debt Service − Growth CapEx. *Impact:* Funds dividends and retained cash.",
    "DSCR": "**Debt Service Coverage Ratio** = CFADS / Debt Service. *Impact:* Lenders want ≥1.25×; lower is risky.",
    "Debt Service": "**Total required loan payments** (SBA + Seller). *Impact:* The fixed hurdle CFADS must clear.",
    "Distributable": "**Cash available to pay investors** (after retention). *Impact:* Drives investor dividends.",
    "Retained": "**Positive FCFE held in the business.** *Impact:* Builds runway and resilience.",
    "Cash Balance": "**Cumulative cash on hand** (starts with the buffer). *Impact:* Safety net to survive bumps.",
    "Follow-on Inflow": "**Additional equity injected during operations.** *Impact:* Temporarily boosts cash and speeds payback."
}

DEFAULT = {
    "purchase_price": 3000000.0, "closing_costs": 150000.0,
    "wc_months": 3, "wc_monthly_opex": 60000.0,
    "hist_sde": 900000.0, "gm_salary": 180000.0, "normalized_adj": 30000.0,
    "maint_capex": 50000.0, "growth_capex": 0.0,
    "revenue_y1": 4500000.0, "cogs_pct": 55.0,
    "nwc_days": {"ar": 30, "ap": 20, "inv": 15},
    "investors": [
        {"name":"Sponsor", "pct":60.0, "contribution":420000.0},
        {"name":"Angel 1", "pct":25.0, "contribution":175000.0},
        {"name":"Angel 2", "pct":15.0, "contribution":105000.0},
    ],
    "follow_on": [
        {"name":"Angel 1","year":2,"month":1,"amount":25000.0},
        {"name":"Sponsor","year":3,"month":6,"amount":50000.0}
    ],
    "sba_principal":1800000.0,"sba_rate":10.0,"sba_term_months":120,"sba_io_months":0,
    "seller_principal":450000.0,"seller_rate":6.0,"seller_term_months":60,"seller_standby_months":24,
    "sde_growth_pct":3.0,"retain_pct":10.0,
    "refi":{"enable":False,"year":3,"new_rate_pct":8.5,"new_term_months":120}
}

if "library" not in st.session_state:
    st.session_state["library"] = {}
cfg = st.session_state.get("cfg", DEFAULT)

# Sidebar: definitions + library + export/import
with st.sidebar:
    st.header("ⓘ Definitions (Quick Guide)")
    with st.expander("Deal Setup Terms", expanded=False):
        st.markdown("\n".join([
            f"- **Purchase price** — {H['purchase_price']}",
            f"- **Closing costs** — {H['closing_costs']}",
            f"- **WC buffer (months)** — {H['wc_months']}",
            f"- **Monthly OpEx** — {H['wc_monthly_opex']}",
        ]))
    with st.expander("SDE & Operations", expanded=False):
        st.markdown("\n".join([
            f"- **Historical SDE** — {H['hist_sde']}",
            f"- **GM salary** — {H['gm_salary']}",
            f"- **Normalized adj.** — {H['normalized_adj']}",
            f"- **Maintenance CapEx** — {H['maint_capex']}",
            f"- **Growth CapEx** — {H['growth_capex']}",
            f"- **Revenue Y1** — {H['revenue_y1']}",
            f"- **COGS %** — {H['cogs_pct']}",
            f"- **AR / Inv / AP Days** — {H['ar_days']} / {H['inv_days']} / {H['ap_days']}",
        ]))
    with st.expander("Funding & Investors", expanded=False):
        st.markdown("\n".join([
            f"- **SBA Loan** — {H['sba_principal']} | {H['sba_rate']} | {H['sba_term']} | {H['sba_io']}",
            f"- **Seller Note** — {H['seller_principal']} | {H['seller_rate']} | {H['seller_term']} | {H['seller_standby']}",
            f"- **Investors** — {H['investor_pct']} | {H['investor_contrib']}",
            f"- **Retained %** — {H['retain_pct']}",
            f"- **Refinance** — {H['refi']}",
        ]))

    st.markdown("---")
    st.header("Scenario Library")
    name = st.text_input("Scenario name")
    if st.button("Save to Library") and name:
        st.session_state["library"][name] = json.loads(json.dumps(cfg))
        st.success(f"Saved '{name}'")
    pick = st.selectbox("Load scenario", ["-- select --"] + list(st.session_state["library"].keys()))
    if pick and pick != "-- select --":
        st.session_state["cfg"] = json.loads(json.dumps(st.session_state["library"][pick]))
        st.experimental_rerun()

    st.markdown("---")
    up = st.file_uploader("Import JSON", type=["json"], help="Load either classic config JSON or the new format with _hints.")
    if up:
        try:
            data = json.loads(up.getvalue().decode("utf-8"))
            if isinstance(data, dict) and "config" in data:
                st.session_state["cfg"] = data["config"]
            else:
                st.session_state["cfg"] = data
            st.success("Scenario loaded.")
            st.experimental_rerun()
        except Exception as e:
            st.error(f"Could not parse JSON: {e}")

    export_payload = {
        "_meta": {"app": "Treehouse Deal Calculator", "version": "3.1", "exported_by": "Treehouse Ventures"},
        "config": cfg,
        "_hints": H
    }
    st.download_button("Export JSON (with _hints)", data=json.dumps(export_payload, indent=2),
                       file_name="treehouse_scenario_with_hints.json", use_container_width=True)

    st.caption("Your export now includes a `_hints` block so others see the same tooltips.")

# Tabs & inputs (same as v3.1 UI) — abbreviated here for brevity
tabs = st.tabs(["Deal Setup", "Pro-forma SDE & NWC", "Investors", "Debt & Funding", "Follow-on", "Advanced"])

with tabs[0]:
    st.subheader("Uses at Close")
    cfg["purchase_price"] = money_input("Purchase price (EV)", cfg["purchase_price"], key="pp", help=H["purchase_price"])
    cfg["closing_costs"] = money_input("Closing costs & fees", cfg["closing_costs"], key="cc", help=H["closing_costs"])
    cfg["wc_months"] = st.number_input("Working-capital buffer (months)", 0, value=int(cfg["wc_months"]), step=1, help=H["wc_months"])
    cfg["wc_monthly_opex"] = money_input("Monthly OpEx for buffer", cfg["wc_monthly_opex"], key="wcmo", help=H["wc_monthly_opex"])

with tabs[1]:
    st.subheader("SDE & Revenue / NWC Days")
    col1, col2 = st.columns(2)
    with col1:
        cfg["hist_sde"] = money_input("Historical SDE (annual)", cfg["hist_sde"], key="sde", help=H["hist_sde"])
        cfg["gm_salary"] = money_input("Replacement GM salary (annual)", cfg["gm_salary"], key="gm", help=H["gm_salary"])
        cfg["normalized_adj"] = money_input("Normalized ongoing adjustments (annual)", cfg["normalized_adj"], key="adj", help=H["normalized_adj"])
        cfg["sde_growth_pct"] = percent_input("Annual SDE growth % (Y2–Y5)", cfg["sde_growth_pct"], key="sdeg", help=H["sde_growth"])
    with col2:
        cfg["revenue_y1"] = money_input("Revenue Year 1", cfg["revenue_y1"], key="rev", help=H["revenue_y1"])
        cfg["cogs_pct"] = percent_input("COGS % of revenue", cfg["cogs_pct"], key="cogs", help=H["cogs_pct"])
        n1, n2, n3 = st.columns(3)
        cfg["nwc_days"]["ar"] = n1.number_input("AR Days", 0, value=int(cfg["nwc_days"]["ar"]), step=1, help=H["ar_days"])
        cfg["nwc_days"]["inv"] = n2.number_input("Inventory Days", 0, value=int(cfg["nwc_days"]["inv"]), step=1, help=H["inv_days"])
        cfg["nwc_days"]["ap"] = n3.number_input("AP Days", 0, value=int(cfg["nwc_days"]["ap"]), step=1, help=H["ap_days"])

with tabs[2]:
    st.subheader("Investors (up to 5)")
    invs = []
    for i in range(5):
        default = cfg["investors"][i] if i < len(cfg["investors"]) else {"name": f"Investor {i+1}", "pct": 0.0, "contribution": 0.0}
        with st.expander(f"Investor {i+1}", expanded=(i < len(cfg["investors"]))):
            name = st.text_input("Name", value=str(default["name"]), key=f"name{i}", help="Investor display name for tables.")
            pct = percent_input("Ownership %", float(default["pct"]), key=f"pct{i}", help=H["investor_pct"])
            contrib = money_input("Equity contribution ($ at close)", float(default["contribution"]), key=f"contrib{i}", help=H["investor_contrib"])
            invs.append({"name": name, "pct": pct, "contribution": contrib})
    cfg["investors"] = [x for x in invs if x["pct"] > 0 or x["contribution"] > 0]

with tabs[3]:
    st.subheader("SBA Loan")
    cfg["sba_principal"] = money_input("SBA principal", cfg["sba_principal"], key="sbap", help=H["sba_principal"])
    cfg["sba_rate"] = percent_input("SBA annual interest rate %", cfg["sba_rate"], key="sbar", help=H["sba_rate"])
    cfg["sba_term_months"] = st.number_input("SBA term (months)", 1, value=int(cfg["sba_term_months"]), step=1, help=H["sba_term"])
    cfg["sba_io_months"] = st.number_input("SBA interest-only months", 0, value=int(cfg["sba_io_months"]), step=1, help=H["sba_io"])

    st.subheader("Seller Note")
    cfg["seller_principal"] = money_input("Seller note principal", cfg["seller_principal"], key="selp", help=H["seller_principal"])
    cfg["seller_rate"] = percent_input("Seller note annual interest rate %", cfg["seller_rate"], key="selr", help=H["seller_rate"])
    cfg["seller_term_months"] = st.number_input("Seller note term (months)", 1, value=int(cfg["seller_term_months"]), step=1, help=H["seller_term"])
    cfg["seller_standby_months"] = st.number_input("Seller standby months (interest accrues)", 0, value=int(cfg["seller_standby_months"]), step=1, help=H["seller_standby"])

with tabs[4]:
    st.subheader("Follow-on Contributions")
    st.caption("Add additional equity injections by Year/Month.")
    df_fo = pd.DataFrame(cfg.get("follow_on", []) or [{"name":"", "year":1, "month":1, "amount":0.0}])
    edited = st.data_editor(df_fo, num_rows="dynamic", use_container_width=True,
        column_config={
            "name": st.column_config.TextColumn("Investor Name", help="Choose an existing investor's name."),
            "year": st.column_config.NumberColumn("Year", help="Year (1–5) when cash is injected.", step=1),
            "month": st.column_config.NumberColumn("Month", help="Month (1–12) within the year.", step=1),
            "amount": st.column_config.NumberColumn("Amount", help="Dollar amount to inject.", format="$%,.0f"),
        })
    cfg["follow_on"] = edited.to_dict(orient="records")

with tabs[5]:
    st.subheader("Advanced Options")
    cfg["retain_pct"] = percent_input("Retain % of FCFE before distributions", cfg["retain_pct"], key="ret", help=H["retain_pct"])
    with st.expander("Refinance (SBA)", expanded=False):
        en = st.checkbox("Enable refinance", value=bool(cfg["refi"]["enable"]), help=H["refi"])
        cfg["refi"]["enable"] = en
        if en:
            cfg["refi"]["year"] = st.number_input("Refi year (2–5)", 2, 5, value=int(cfg["refi"]["year"]), step=1)
            cfg["refi"]["new_rate_pct"] = percent_input("New SBA rate %", float(cfg["refi"]["new_rate_pct"]), key="refir")
            cfg["refi"]["new_term_months"] = st.number_input("New SBA term (months)", 12, value=int(cfg["refi"]["new_term_months"]), step=1)

st.session_state["cfg"] = cfg

outs = compute(cfg)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Uses @ Close", fmt_money(outs["total_uses"], 0))
m2.metric("Total Sources @ Close", fmt_money(outs["total_sources"], 0))
m3.metric("Sources - Uses", fmt_money(outs["total_sources"] - outs["total_uses"], 0))
m4.metric("Pro-forma SDE (Y1)", fmt_money(outs["proforma_sde_y1"], 0))

st.markdown("### Year 1 • Monthly Cash Flow")
df_y1 = pd.DataFrame(outs["y1"])
col_config_y1 = {
    "Month": st.column_config.NumberColumn("Month"),
    "SDE": st.column_config.NumberColumn("SDE", help=H["SDE"], format="$%,.0f"),
    "Maint CapEx": st.column_config.NumberColumn("Maint CapEx", help=H["maint_capex"], format="$%,.0f"),
    "Growth CapEx": st.column_config.NumberColumn("Growth CapEx", help=H["growth_capex"], format="$%,.0f"),
    "SBA Payment": st.column_config.NumberColumn("SBA Payment", help="Monthly SBA loan payment.", format="$%,.0f"),
    "Seller Payment": st.column_config.NumberColumn("Seller Payment", help="Monthly seller note payment.", format="$%,.0f"),
    "Debt Service": st.column_config.NumberColumn("Debt Service", help=H["Debt Service"], format="$%,.0f"),
    "CFADS": st.column_config.NumberColumn("CFADS", help=H["CFADS"], format="$%,.0f"),
    "FCFE": st.column_config.NumberColumn("FCFE", help=H["FCFE"], format="$%,.0f"),
    "Follow-on Inflow": st.column_config.NumberColumn("Follow-on Inflow", help=H["Follow-on Inflow"], format="$%,.0f"),
    "Retained": st.column_config.NumberColumn("Retained", help=H["Retained"], format="$%,.0f"),
    "Distributable": st.column_config.NumberColumn("Distributable", help=H["Distributable"], format="$%,.0f"),
    "Cash Balance": st.column_config.NumberColumn("Cash Balance", help=H["Cash Balance"], format="$%,.0f"),
}
for c in df_y1.columns:
    if isinstance(c, str) and c.startswith("Dividend •"):
        col_config_y1[c] = st.column_config.NumberColumn(c, help="Pro-rata investor dividend for the month.", format="$%,.0f")
st.dataframe(df_y1, use_container_width=True, column_config=col_config_y1)

st.markdown("### Years 1–5 • Annual Summary")
df_y = pd.DataFrame(outs["years"])
col_config_y = {
    "Year": st.column_config.NumberColumn("Year"),
    "Pro-forma SDE": st.column_config.NumberColumn("Pro-forma SDE", help=H["SDE"], format="$%,.0f"),
    "ΔNWC": st.column_config.NumberColumn("ΔNWC", help="Change in working capital; positive means cash outflow.", format="$%,.0f"),
    "Maint CapEx": st.column_config.NumberColumn("Maint CapEx", help=H["maint_capex"], format="$%,.0f"),
    "Growth CapEx": st.column_config.NumberColumn("Growth CapEx", help=H["growth_capex"], format="$%,.0f"),
    "SBA Debt Service": st.column_config.NumberColumn("SBA Debt Service", help="Total SBA payments in the year.", format="$%,.0f"),
    "Seller Debt Service": st.column_config.NumberColumn("Seller Debt Service", help="Total seller note payments in the year.", format="$%,.0f"),
    "Total Debt Service": st.column_config.NumberColumn("Total Debt Service", help=H["Debt Service"], format="$%,.0f"),
    "CFADS": st.column_config.NumberColumn("CFADS", help=H["CFADS"], format="$%,.0f"),
    "FCFE": st.column_config.NumberColumn("FCFE", help=H["FCFE"], format="$%,.0f"),
    "Follow-on Inflow": st.column_config.NumberColumn("Follow-on Inflow", help=H["Follow-on Inflow"], format="$%,.0f"),
    "Retained": st.column_config.NumberColumn("Retained", help=H["Retained"], format="$%,.0f"),
    "Distributable": st.column_config.NumberColumn("Distributable", help=H["Distributable"], format="$%,.0f"),
    "DSCR": st.column_config.NumberColumn("DSCR", help=H["DSCR"], format="%.2f"),
}
for c in df_y.columns:
    if isinstance(c, str) and c.startswith("Investor Dividend •"):
        col_config_y[c] = st.column_config.NumberColumn(c, help="Pro-rata investor dividend for the year.", format="$%,.0f")
st.dataframe(df_y, use_container_width=True, column_config=col_config_y)

st.markdown("### Investor Summary (5 years)")
df_inv = pd.DataFrame(outs["investors"])
col_config_inv = {
    "Investor": st.column_config.TextColumn("Investor"),
    "Ownership %": st.column_config.NumberColumn("Ownership %", help=H["investor_pct"], format="%.2f%%"),
    "Contributed (incl. follow-ons)": st.column_config.NumberColumn("Contributed (incl. follow-ons)", help=H["investor_contrib"], format="$%,.0f"),
    "Total Dividends (5y)": st.column_config.NumberColumn("Total Dividends (5y)", help="Total dividends paid to this investor over 5 years.", format="$%,.0f"),
    "Equity Multiple (5y)": st.column_config.NumberColumn("Equity Multiple (5y)", help="Total dividends divided by contributed capital. >1.0× means paid back.", format="%.2f"),
    "Payback Year": st.column_config.TextColumn("Payback Year", help="First year cumulative dividends exceed contributed capital."),
}
st.dataframe(df_inv, use_container_width=True, column_config=col_config_inv)

st.markdown("### Download Results")
def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")
c1, c2, c3, c4 = st.columns(4)
with c1: st.download_button("CSV • Year 1 Monthly", data=to_csv_bytes(df_y1), file_name="year1_monthly.csv", use_container_width=True)
with c2: st.download_button("CSV • Years 1–5 Annual", data=to_csv_bytes(df_y), file_name="years1_5_annual.csv", use_container_width=True)
with c3:
    excel = to_excel_bytes({"Year1_Monthly": df_y1, "Years1_5_Annual": df_y, "Investor_Summary": df_inv})
    st.download_button("Excel • All Tabs", data=excel, file_name="treehouse_outputs.xlsx", use_container_width=True)
with c4:
    metrics = {
        "Total Uses @ Close": fmt_money(outs["total_uses"], 0),
        "Total Sources @ Close": fmt_money(outs["total_sources"], 0),
        "Pro-forma SDE (Y1)": fmt_money(outs["proforma_sde_y1"], 0),
    }
    pdf = to_pdf_bytes("Treehouse Deal — Snapshot", metrics, {"Year 1 Monthly": df_y1, "Investor Summary": df_inv})
    st.download_button("PDF • Snapshot", data=pdf, file_name="treehouse_snapshot.pdf", use_container_width=True)
