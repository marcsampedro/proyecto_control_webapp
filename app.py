import os
from datetime import date, datetime
from decimal import Decimal
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from dateutil.relativedelta import relativedelta

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///data.db")
if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgres://"):
    app.config["SQLALCHEMY_DATABASE_URI"] = app.config["SQLALCHEMY_DATABASE_URI"].replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")
db = SQLAlchemy(app)

class MonthlyRecord(db.Model):
    __tablename__ = "monthly_records"
    id = db.Column(db.Integer, primary_key=True)
    mes = db.Column(db.Date, nullable=False, index=True, unique=True)
    forecast_1 = db.Column(db.Numeric(14,2), default=0)
    facturado_2 = db.Column(db.Numeric(14,2), default=0)
    pdt_incurrir_3 = db.Column(db.Numeric(14,2), default=0)
    inc_pdte_factura_4 = db.Column(db.Numeric(14,2), default=0)
    ajuste_fc = db.Column(db.Numeric(14,2), default=0)
    new_forecast = db.Column(db.Numeric(14,2), default=0)
    real_mas_deuda_pend = db.Column(db.Numeric(14,2), default=0)
    comentarios = db.Column(db.Text, nullable=True)
    @property
    def restante_calc(self):
        def to_num(v): return Decimal(v or 0)
        return (to_num(self.facturado_2)+to_num(self.pdt_incurrir_3)+to_num(self.inc_pdte_factura_4))-to_num(self.forecast_1)

class EvolucionBolsa(db.Model):
    __tablename__ = "evolucion_bolsa"
    id = db.Column(db.Integer, primary_key=True)
    mes = db.Column(db.Date, nullable=False, index=True, unique=True)
    incremento = db.Column(db.Numeric(14,2), default=0)
    acumulado = db.Column(db.Numeric(14,2), default=0)

def parse_month(s):
    if isinstance(s, (date, datetime)):
        return date(s.year, s.month, 1)
    if isinstance(s, str):
        for f in ["%Y-%m-%d","%Y-%m-%d %H:%M:%S","%d/%m/%Y","%m/%Y","%Y-%m"]:
            try:
                dt = datetime.strptime(s.strip(), f)
                return date(dt.year, dt.month, 1)
            except: pass
    t = date.today()
    return date(t.year, t.month, 1)

@app.route("/", methods=["GET"])
def dashboard():
    # Obtener filtros de la query string
    desde_str = request.args.get("desde")
    hasta_str = request.args.get("hasta")

    # Inicializar por defecto en abril 2025
    if not desde_str:
        desde_str = "2025-04"

    def parse_month_param(s):
        if not s:
            return None
        try:
            return datetime.strptime(s, "%Y-%m").date()
        except ValueError:
            return None

    desde = parse_month_param(desde_str)
    hasta = parse_month_param(hasta_str)

    # Query base
    query = MonthlyRecord.query
    query_evo = EvolucionBolsa.query

    if desde:
        query = query.filter(MonthlyRecord.mes >= desde)
        query_evo = query_evo.filter(EvolucionBolsa.mes >= desde)
    if hasta:
        query = query.filter(MonthlyRecord.mes <= hasta)
        query_evo = query_evo.filter(EvolucionBolsa.mes <= hasta)

    # Datos para tarjetas
    total_forecast = query.with_entities(func.coalesce(func.sum(MonthlyRecord.forecast_1), 0)).scalar()
    total_facturado = query.with_entities(func.coalesce(func.sum(MonthlyRecord.facturado_2), 0)).scalar()
    total_pendiente = query.with_entities(func.coalesce(func.sum(MonthlyRecord.pdt_incurrir_3 + MonthlyRecord.inc_pdte_factura_4), 0)).scalar()
    wip = (total_forecast or 0) - (total_facturado or 0)
    wip_calculado = wip - (total_pendiente or 0)

    # Serie por mes
    rows = query.order_by(MonthlyRecord.mes).all()
    serie = [{
        "mes": r.mes.strftime("%Y-%m"),
        "forecast": float(r.forecast_1 or 0),
        "facturado": float(r.facturado_2 or 0),
        "pdt_incurrir": float(r.pdt_incurrir_3 or 0),
        "inc_pdte_factura": float(r.inc_pdte_factura_4 or 0),
        "restante": float(r.restante_calc),
        "new_forecast": float(r.new_forecast or 0),
        "real_mas_deuda_pend": float(r.real_mas_deuda_pend or 0),
    } for r in rows]

    # Evolución bolsa
    evo = query_evo.order_by(EvolucionBolsa.mes).all()
    evo_serie = [{
        "mes": r.mes.strftime("%Y-%m"),
        "incremento": float(r.incremento or 0),
        "acumulado": float(r.acumulado or 0)
    } for r in evo]

    return render_template(
        "dashboard.html",
        total_forecast=total_forecast,
        total_facturado=total_facturado,
        total_pendiente=total_pendiente,
        serie=serie,
        evo_serie=evo_serie,
        desde=desde_str or "",
        hasta=hasta_str or "",
        wip=wip,
        wip_calculado=wip_calculado
    )



@app.route("/records")
def records_list():
    rows = MonthlyRecord.query.order_by(MonthlyRecord.mes.desc()).all()
    return render_template("records.html", rows=rows)

from flask import request, redirect, url_for, flash, jsonify
@app.route("/records/new", methods=["POST"])
def records_new():
    r = MonthlyRecord(
        mes=parse_month(request.form.get("mes")),
        forecast_1=request.form.get("forecast_1") or 0,
        facturado_2=request.form.get("facturado_2") or 0,
        pdt_incurrir_3=request.form.get("pdt_incurrir_3") or 0,
        inc_pdte_factura_4=request.form.get("inc_pdte_factura_4") or 0,
        ajuste_fc=request.form.get("ajuste_fc") or 0,
        new_forecast=request.form.get("new_forecast") or 0,
        real_mas_deuda_pend=request.form.get("real_mas_deuda_pend") or 0,
        comentarios=request.form.get("comentarios") or None,
    )
    db.session.add(r); db.session.commit(); flash("Mes añadido correctamente","success")
    return redirect(url_for("records_list"))

@app.route("/records/<int:rid>/edit", methods=["POST"])
def records_edit(rid):
    r = MonthlyRecord.query.get_or_404(rid)
    r.mes=parse_month(request.form.get("mes"))
    for f in ["forecast_1","facturado_2","pdt_incurrir_3","inc_pdte_factura_4","ajuste_fc","new_forecast","real_mas_deuda_pend","comentarios"]:
        setattr(r, f, request.form.get(f) or 0 if f!="comentarios" else request.form.get(f) or None)
    db.session.commit(); flash("Mes actualizado","success")
    return redirect(url_for("records_list"))

@app.route("/records/<int:rid>/delete", methods=["POST"])
def records_delete(rid):
    r = MonthlyRecord.query.get_or_404(rid)
    db.session.delete(r); db.session.commit(); flash("Mes eliminado","info")
    return redirect(url_for("records_list"))

@app.route("/evolucion")
def evolucion_list():
    rows = EvolucionBolsa.query.order_by(EvolucionBolsa.mes.desc()).all()
    return render_template("evolucion.html", rows=rows)

@app.route("/evolucion/new", methods=["POST"])
def evolucion_new():
    mes = parse_month(request.form.get("mes"))
    incremento = float(request.form.get("incremento") or 0)

    # Buscar mes anterior
    mes_anterior = (mes.replace(day=1) - relativedelta(months=1))
    anterior = EvolucionBolsa.query.filter_by(mes=mes_anterior).first()
    acumulado_anterior = float(anterior.acumulado or 0) if anterior else 0

    acumulado = acumulado_anterior + incremento + 1

    r = EvolucionBolsa(mes=mes, incremento=incremento, acumulado=acumulado)
    db.session.add(r)
    db.session.commit()
    flash("Entrada añadida con acumulado calculado", "success")
    return redirect(url_for("evolucion_list"))


@app.route("/evolucion/<int:rid>/edit", methods=["POST"])
def evolucion_edit(rid):
    r = EvolucionBolsa.query.get_or_404(rid)
    r.mes = parse_month(request.form.get("mes"))
    r.incremento = float(request.form.get("incremento") or 0)

    # Recalcular acumulado
    mes_anterior = (r.mes.replace(day=1) - relativedelta(months=1))
    anterior = EvolucionBolsa.query.filter_by(mes=mes_anterior).first()
    acumulado_anterior = float(anterior.acumulado or 0) if anterior else 0

    r.acumulado = acumulado_anterior + r.incremento

    db.session.commit()
    flash("Entrada actualizada con acumulado recalculado", "success")
    return redirect(url_for("evolucion_list"))


@app.route("/evolucion/<int:rid>/delete", methods=["POST"])
def evolucion_delete(rid):
    r = EvolucionBolsa.query.get_or_404(rid)
    db.session.delete(r); db.session.commit(); flash("Entrada eliminada","info")
    return redirect(url_for("evolucion_list"))

@app.route("/api/serie")
def api_serie():
    rows = MonthlyRecord.query.order_by(MonthlyRecord.mes).all()
    return jsonify([{ "mes": r.mes.strftime("%Y-%m"), "forecast": float(r.forecast_1 or 0), "facturado": float(r.facturado_2 or 0), "pdt_incurrir": float(r.pdt_incurrir_3 or 0), "inc_pdte_factura": float(r.inc_pdte_factura_4 or 0), "restante": float(r.restante_calc), "new_forecast": float(r.new_forecast or 0), "real_mas_deuda_pend": float(r.real_mas_deuda_pend or 0) } for r in rows])

@app.route("/api/evolucion")
def api_evolucion():
    rows = EvolucionBolsa.query.order_by(EvolucionBolsa.mes).all()
    return jsonify([{ "mes": r.mes.strftime("%Y-%m"), "incremento": float(r.incremento or 0), "acumulado": float(r.acumulado or 0) } for r in rows])

@app.cli.command("init-db")
def init_db():
    db.create_all(); print("DB inicializada")

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
