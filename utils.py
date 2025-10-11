# utils.py
import io
import pandas as pd
from typing import Dict
from openpyxl import Workbook
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

def to_excel_bytes(tabs: Dict[str, pd.DataFrame]) -> bytes:
    wb = Workbook(); wb.remove(wb.active)
    for name, df in tabs.items():
        ws = wb.create_sheet(title=name[:31])
        ws.append(list(df.columns))
        for _, row in df.iterrows():
            ws.append(list(row.values))
    bio = io.BytesIO(); wb.save(bio); return bio.getvalue()

def to_pdf_bytes(title: str, metrics: Dict[str,str], tables: Dict[str, pd.DataFrame]) -> bytes:
    bio = io.BytesIO(); c = canvas.Canvas(bio, pagesize=LETTER)
    W, H = LETTER; y = H-50
    c.setFont("Helvetica-Bold", 14); c.drawString(40, y, title); y -= 20
    c.setFont("Helvetica", 9)
    for k,v in metrics.items():
        c.drawString(40, y, f"{k}: {v}"); y -= 12
        if y < 80: c.showPage(); y = H-50
    for name, df in tables.items():
        if y < 100: c.showPage(); y = H-50
        c.setFont("Helvetica-Bold", 12); c.drawString(40, y, name); y -= 16
        c.setFont("Helvetica", 8)
        cols = list(df.columns)
        header = " | ".join(str(x) for x in cols[:6])
        c.drawString(40, y, header); y -= 12
        for i in range(min(25, len(df))):
            row = " | ".join(str(df.iloc[i, j]) for j in range(min(6, len(cols))))
            c.drawString(40, y, row[:110]); y -= 10
            if y < 80: c.showPage(); y = H-50
        y -= 6
    c.save(); return bio.getvalue()
