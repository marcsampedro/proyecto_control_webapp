import os, pandas as pd
from datetime import date, datetime
from app import db, MonthlyRecord, EvolucionBolsa, app

SRC = os.getenv("XLSX_PATH", "/mnt/data/CONTROL_789.xlsx")
SHEET = os.getenv("XLSX_SHEET", "Resumen")

def normalize_month(x):
    if isinstance(x, (date, datetime)): return date(x.year, x.month, 1)
    if isinstance(x, str):
        for fmt in ("%Y-%m-%d","%Y-%m-%d %H:%M:%S","%Y-%m","%d/%m/%Y"):
            try:
                dt = datetime.strptime(x.strip().split(" ")[0], fmt); return date(dt.year, dt.month, 1)
            except: pass
    return None

def to_num(x):
    try: return float(x)
    except: return 0.0

def run():
    xls = pd.ExcelFile(SRC); df = xls.parse(SHEET)
    # Main table detection (expects column with label 'mes')
    hdr = None
    for i, v in enumerate(df.iloc[:,1].astype(str).tolist()):
        if v.strip().lower() == "mes": hdr = i; break
    if hdr is None: raise RuntimeError("No encuentro cabecera de la tabla principal (columna 'mes').")
    end = hdr + 1
    while end < len(df):
        val = str(df.iloc[end,1])
        if val.strip().upper() == "TOTAL": break
        end += 1
    main = df.iloc[hdr+1:end, 1:]
    main.columns = ["mes","forecast_1","facturado_2","pdt_incurrir_3","inc_pdte_factura_4","restante_formula","ajuste_fc","new_forecast","real_mas_deuda_pend","comentarios","extra"]

    # Evolución table (optional)
    evo = None
    for i in range(len(df)):
        if "evolución de la bolsa mensual" in str(df.iloc[i,1]).strip().lower():
            hdr2 = i + 2
            evo = df.iloc[hdr2+1:, 1:4].copy()
            evo.columns = ["mes","incremento","acumulado"]
            evo = evo[~evo["mes"].isna()]
            break

    with app.app_context():
        for _, row in main.iterrows():
            m = normalize_month(row["mes"])
            if not m: continue
            rec = MonthlyRecord.query.filter_by(mes=m).first() or MonthlyRecord(mes=m)
            rec.forecast_1 = to_num(row["forecast_1"]); rec.facturado_2 = to_num(row["facturado_2"])
            rec.pdt_incurrir_3 = to_num(row["pdt_incurrir_3"]); rec.inc_pdte_factura_4 = to_num(row["inc_pdte_factura_4"])
            rec.ajuste_fc = to_num(row["ajuste_fc"]); rec.new_forecast = to_num(row["new_forecast"])
            rec.real_mas_deuda_pend = to_num(row["real_mas_deuda_pend"]); rec.comentarios = str(row.get("comentarios") or "")[:500]
            db.session.add(rec)
        if evo is not None:
            for _, row in evo.iterrows():
                m = normalize_month(row["mes"])
                if not m: continue
                ent = EvolucionBolsa.query.filter_by(mes=m).first() or EvolucionBolsa(mes=m)
                ent.incremento = to_num(row["incremento"]); ent.acumulado = to_num(row["acumulado"]); db.session.add(ent)
        db.session.commit(); print("Importación completada.")

if __name__ == "__main__":
    run()
