# app.py
import os, json
import streamlit as st
import pandas as pd
from engine import compute
from utils import to_excel_bytes, to_pdf_bytes

st.set_page_config(page_title="Treehouse Deal Calculator v3", layout="wide")
if os.getenv("APP_KEY"):
    key = st.text_input("Enter access key", type="password")
    if key != os.getenv("APP_KEY"):
        st.stop()

st.title("Treehouse Ventures • Deal Calculator (Web v3)")
st.caption("Scenario Library • Follow-on Contributions • PDF Export")

if "library" not in st.session_state:
    st.session_state["library"] = {}

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
cfg = st.session_state.get("cfg", DEFAULT)

with st.sidebar:
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
    up = st.file_uploader("Import JSON", type=["json"])
    if up:
        st.session_state["cfg"] = json.loads(up.getvalue().decode("utf-8"))
        st.experimental_rerun()
    st.download_button("Export JSON", data=json.dumps(cfg, indent=2), file_name="treehouse_scenario.json")

tabs = st.tabs(["Deal Setup", "Pro-forma SDE & NWC", "Investors", "Debt & Funding", "Follow-on Contributions", "Advanced"])

with tabs[0]:
    st.subheader("Uses at Close")
    cfg["purchase_price"] = st.number_input("Purchase price (EV)", 0.0, value=float(cfg["purchase_price"]), step=1000.0, format="%.2f")
    cfg["closing_costs"] = st.number_input("Closing costs & fees", 0.0, value=float(cfg["closing_costs"]), step=1000.0, format="%.2f")
    cfg["wc_months"] = st.number_input("Working-capital buffer (months of OpEx)", 0, value=int(cfg["wc_months"]), step=1)
    cfg["wc_monthly_opex"] = st.number_input("Monthly OpEx for buffer", 0.0, value=float(cfg["wc_monthly_opex"]), step=1000.0, format="%.2f")

with tabs[1]:
    st.subheader("SDE & Revenue / NWC Days")
    col1, col2 = st.columns(2)
    with col1:
        cfg["hist_sde"] = st.number_input("Historical SDE (annual)", 0.0, value=float(cfg["hist_sde"]), step=1000.0, format="%.2f")
        cfg["gm_salary"] = st.number_input("Replacement GM salary (annual)", 0.0, value=float(cfg["gm_salary"]), step=1000.0, format="%.2f")
        cfg["normalized_adj"] = st.number_input("Normalized ongoing adjustments (annual)", -1_000_000.0, value=float(cfg["normalized_adj"]), step=1000.0, format="%.2f")
        cfg["sde_growth_pct"] = st.number_input("Annual SDE growth % (Y2–Y5)", 0.0, value=float(cfg["sde_growth_pct"]), step=0.1, format="%.2f")
    with col2:
        cfg["revenue_y1"] = st.number_input("Revenue Year 1", 0.0, value=float(cfg["revenue_y1"]), step=1000.0, format="%.2f")
        cfg["cogs_pct"] = st.number_input("COGS % of revenue", 0.0, 100.0, value=float(cfg["cogs_pct"]), step=0.5, format="%.2f")
        n1, n2, n3 = st.columns(3)
        cfg["nwc_days"]["ar"] = n1.number_input("AR Days", 0, value=int(cfg["nwc_days"]["ar"]), step=1)
        cfg["nwc_days"]["inv"] = n2.number_input("Inventory Days", 0, value=int(cfg["nwc_days"]["inv"]), step=1)
        cfg["nwc_days"]["ap"] = n3.number_input("AP Days", 0, value=int(cfg["nwc_days"]["ap"]), step=1)

with tabs[2]:
    st.subheader("Investors (up to 5)")
    invs = []
    for i in range(5):
        default = cfg["investors"][i] if i < len(cfg["investors"]) else {"name": f"Investor {i+1}", "pct": 0.0, "contribution": 0.0}
        with st.expander(f"Investor {i+1}", expanded=(i < len(cfg["investors"]))):
            name_i = st.text_input("Name", value=str(default["name"]), key=f"name{i}")
            pct_i = st.number_input("Ownership %", 0.0, 100.0, value=float(default["pct"]), step=0.1, format="%.2f", key=f"pct{i}")
            contrib_i = st.number_input("Equity contribution ($)", 0.0, value=float(default["contribution"]), step=1000.0, format="%.2f", key=f"contrib{i}")
            invs.append({"name": name_i, "pct": pct_i, "contribution": contrib_i})
    cfg["investors"] = [x for x in invs if x["pct"] > 0 or x["contribution"] > 0]

with tabs[3]:
    st.subheader("SBA Loan")
    cfg["sba_principal"] = st.number_input("SBA principal", 0.0, value=float(cfg["sba_principal"]), step=1000.0, format="%.2f")
    cfg["sba_rate"] = st.number_input("SBA annual interest rate %", 0.0, value=float(cfg["sba_rate"]), step=0.1, format="%.2f")
    cfg["sba_term_months"] = st.number_input("SBA term (months)", 1, value=int(cfg["sba_term_months"]), step=1)
    cfg["sba_io_months"] = st.number_input("SBA interest-only months", 0, value=int(cfg["sba_io_months"]), step=1)

    st.subheader("Seller Note")
    cfg["seller_principal"] = st.number_input("Seller note principal", 0.0, value=float(cfg["seller_principal"]), step=1000.0, format="%.2f")
    cfg["seller_rate"] = st.number_input("Seller note annual interest rate %", 0.0, value=float(cfg["seller_rate"]), step=0.1, format="%.2f")
    cfg["seller_term_months"] = st.number_input("Seller note term (months)", 1, value=int(cfg["seller_term_months"]), step=1)
    cfg["seller_standby_months"] = st.number_input("Seller standby months (no payments; interest accrues)", 0, value=int(cfg["seller_standby_months"]), step=1)

with tabs[4]:
    st.subheader("Follow-on Contributions")
    st.caption("Per-investor injections by Year/Month (cash inflow; improves payback)")
    df = pd.DataFrame(cfg.get("follow_on", []) or [{"name":"", "year":1, "month":1, "amount":0.0}])
    edited = st.data_editor(df, num_rows="dynamic", use_container_width=True)
    cfg["follow_on"] = edited.to_dict(orient="records")

with tabs[5]:
    st.subheader("Advanced Options")
    col1, col2 = st.columns(2)
    cfg["retain_pct"] = col1.number_input("Retain % of FCFE before distributions", 0.0, 100.0, value=float(cfg["retain_pct"]), step=1.0)
    en = col2.checkbox("Enable refinance (SBA)", value=bool(cfg["refi"]["enable"]))
    cfg["refi"]["enable"] = en
    if en:
        cfg["refi"]["year"] = col2.number_input("Refi year", 2, 5, value=int(cfg["refi"]["year"]), step=1)
        cfg["refi"]["new_rate_pct"] = col2.number_input("New SBA rate %", 0.0, value=float(cfg["refi"]["new_rate_pct"]), step=0.1)
        cfg["refi"]["new_term_months"] = col2.number_input("New SBA term (months)", 12, value=int(cfg["refi"]["new_term_months"]), step=1)

# Compute
outs = compute(cfg)

# Metrics
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Uses @ Close", f"${outs['total_uses']:,.0f}")
m2.metric("Total Sources @ Close", f"${outs['total_sources']:,.0f}")
m3.metric("Sources - Uses", f"${outs['total_sources']-outs['total_uses']:,.0f}")
m4.metric("Pro-forma SDE (Y1)", f"${outs['proforma_sde_y1']:,.0f}")

st.markdown("### Year 1 • Monthly Cash Flow")
df_y1 = pd.DataFrame(outs["y1"]); st.dataframe(df_y1, use_container_width=True)

st.markdown("### Years 1–5 • Annual Summary")
df_y = pd.DataFrame(outs["years"]); st.dataframe(df_y, use_container_width=True)

st.markdown("### Investor Summary (5 years)")
df_inv = pd.DataFrame(outs["investors"]); st.dataframe(df_inv, use_container_width=True)

st.markdown("### Download")
def to_csv_bytes(df): return df.to_csv(index=False).encode("utf-8")
c1, c2, c3, c4 = st.columns(4)
with c1: st.download_button("CSV • Year 1 Monthly", data=to_csv_bytes(df_y1), file_name="year1_monthly.csv", use_container_width=True)
with c2: st.download_button("CSV • Years 1–5 Annual", data=to_csv_bytes(df_y), file_name="years1_5_annual.csv", use_container_width=True)
with c3:
    excel = to_excel_bytes({"Year1_Monthly": df_y1, "Years1_5_Annual": df_y, "Investor_Summary": df_inv})
    st.download_button("Excel • All Tabs", data=excel, file_name="treehouse_outputs.xlsx", use_container_width=True)
with c4:
    metrics = {
        "Total Uses @ Close": f"${outs['total_uses']:,.0f}",
        "Total Sources @ Close": f"${outs['total_sources']:,.0f}",
        "Pro-forma SDE (Y1)": f"${outs['proforma_sde_y1']:,.0f}",
    }
    pdf = to_pdf_bytes("Treehouse Deal — Snapshot", metrics, {"Year 1 Monthly": df_y1, "Investor Summary": df_inv})
    st.download_button("PDF • Snapshot", data=pdf, file_name="treehouse_snapshot.pdf", use_container_width=True)
