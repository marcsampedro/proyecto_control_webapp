import os
from datetime import date, datetime
from decimal import Decimal
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from dateutil.relativedelta import relativedelta

app = Flask(__name__)
# --- Filtro Jinja para mostrar importes con color y formato europeo ---
@app.template_filter("euro")
def format_euro(value):
    """Formatea un número al estilo europeo y marca en rojo si es negativo."""
    try:
        val = float(value or 0)
    except Exception:
        val = 0.0
    formatted = "{:,.2f}".format(abs(val)).replace(",", "X").replace(".", ",").replace("X", ".")
    color = "text-danger" if val < 0 else "text-dark"
    sign = "-" if val < 0 else ""
    return f'<span class="{color}">{sign}{formatted} €</span>'

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

    # --- Datos base del dashboard ---
    query = MonthlyRecord.query
    query_evo = EvolucionBolsa.query

    if desde:
        query = query.filter(MonthlyRecord.mes >= desde)
        query_evo = query_evo.filter(EvolucionBolsa.mes >= desde)
    if hasta:
        query = query.filter(MonthlyRecord.mes <= hasta)
        query_evo = query_evo.filter(EvolucionBolsa.mes <= hasta)

    # Total histórico (todos los registros)
    
    total_forecast = query.with_entities(func.coalesce(func.sum(MonthlyRecord.forecast_1), 0)).scalar()
    total_facturado = query.with_entities(func.coalesce(func.sum(MonthlyRecord.facturado_2), 0)).scalar()
    total_pendiente = query.with_entities(func.coalesce(func.sum(MonthlyRecord.pdt_incurrir_3 + MonthlyRecord.inc_pdte_factura_4), 0)).scalar()

    # --- Cálculo del WIP base ---
    wip = (total_forecast or 0) - (total_facturado or 0)

    # --- Incorporar el total_general del Prepagado ---
    try:
        registros_prepagado = Prepagado.query.all()
        resumen = {}
        for r in registros_prepagado:
            resumen.setdefault(r.bolsa, {"saldo": 0, "consumo": 0, "prefacturado": 0})
            if r.tipo == "saldo":
                resumen[r.bolsa]["saldo"] += float(r.importe or 0)
            elif r.tipo == "consumo":
                resumen[r.bolsa]["consumo"] += float(r.importe or 0)
            elif r.tipo == "prefacturado":
                resumen[r.bolsa]["prefacturado"] += float(r.importe or 0)
        for bolsa, datos in resumen.items():
            datos["restante"] = datos["saldo"] - datos["consumo"] - datos["prefacturado"]
        total_general_prepagado = sum(datos["restante"] for datos in resumen.values())
    except Exception:
        total_general_prepagado = 0

    # --- WIP total combinado ---
    wip_total = float(wip or 0) + float(total_general_prepagado or 0)

    # --- WIP calculado ---
    wip_calculado = wip_total - float(total_pendiente or 0)

    print("Total Forecast:", total_forecast, "Total Facturado:", total_facturado)

    # --- Datos para las gráficas ---
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
        wip=wip,  # 👈 se usa el WIP con prepagado incluido
        wip_calculado=wip_calculado,
        total_general_prepagado=total_general_prepagado
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

from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from flask import send_file
import matplotlib
matplotlib.use("Agg")  # ✅ evita abrir ventanas GUI
import matplotlib.pyplot as plt


@app.route("/informe-pdf")
def generar_informe_pdf():
    from reportlab.lib.utils import ImageReader

    desde_str = request.args.get("desde", "2025-04")
    hasta_str = request.args.get("hasta", "")

    # === 1️⃣ Datos principales ===
    total_forecast = db.session.query(func.coalesce(func.sum(MonthlyRecord.forecast_1), 0)).scalar()
    total_facturado = db.session.query(func.coalesce(func.sum(MonthlyRecord.facturado_2), 0)).scalar()
    total_pendiente = db.session.query(func.coalesce(func.sum(MonthlyRecord.pdt_incurrir_3 + MonthlyRecord.inc_pdte_factura_4), 0)).scalar()
    wip = (total_forecast or 0) - (total_facturado or 0)
    wip_calculado = wip - (total_pendiente or 0)

    # === 2️⃣ Datos para las gráficas ===
    serie_rows = MonthlyRecord.query.order_by(MonthlyRecord.mes).all()
    evo_rows = EvolucionBolsa.query.order_by(EvolucionBolsa.mes).all()

    meses = [r.mes.strftime("%Y-%m") for r in serie_rows]
    facturado = [float(r.facturado_2 or 0) for r in serie_rows]
    forecast = [float(r.forecast_1 or 0) for r in serie_rows]
    pendiente = [float((r.pdt_incurrir_3 or 0) + (r.inc_pdte_factura_4 or 0)) for r in serie_rows]

    meses_evo = [r.mes.strftime("%Y-%m") for r in evo_rows]
    incremento = [float(r.incremento or 0) for r in evo_rows]
    acumulado = [float(r.acumulado or 0) for r in evo_rows]

    # === 3️⃣ Crear las gráficas como imágenes en memoria ===
    imgs = []

    def fig_to_img(fig):
        buf = BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf

    # Gráfica 1: Serie Mensual
    fig1, ax1 = plt.subplots(figsize=(6, 3))
    ax1.plot(meses, forecast, label="Forecast (1)", color="#6c63ff")
    ax1.plot(meses, facturado, label="Facturado (2)", color="#00b894")
    ax1.plot(meses, pendiente, label="Pendiente (3+4)", color="#e17055")
    ax1.axhline(0, color="red", linewidth=1)
    ax1.set_title("Serie Mensual")
    ax1.tick_params(axis="x", rotation=45)
    ax1.legend()
    imgs.append(fig_to_img(fig1))

    # Gráfica 2: Evolución Bolsa
    fig2, ax2 = plt.subplots(figsize=(6, 3))
    ax2.plot(meses_evo, incremento, label="Incremento", color="#0984e3")
    ax2.plot(meses_evo, acumulado, label="Acumulado", color="#6c5ce7")
    ax2.axhline(0, color="red", linewidth=1)
    ax2.set_title("Evolución de la Bolsa Mensual")
    ax2.tick_params(axis="x", rotation=45)
    ax2.legend()
    imgs.append(fig_to_img(fig2))

    # === 4️⃣ Generar PDF ===
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Cabecera
    # --- Cabecera con logo corporativo ---
    from reportlab.lib.utils import ImageReader

    # Fondo azul corporativo
    c.setFillColor(colors.HexColor("#003366"))
    c.rect(0, height - 2 * cm, width, 2 * cm, fill=1, stroke=0)

    # Cargar logo desde static/img/
    try:
        logo_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "static", "img", "nttdata_logo.png")
        if os.path.exists(logo_path):
            logo = ImageReader(logo_path)
            # El logo mide 3,5 cm de ancho y se posiciona bien dentro de la franja azul
            c.drawImage(
                logo,
                width - 5 * cm,          # margen derecho
                height - 1.8 * cm,       # vertical centrado
                width=3.5 * cm,
                preserveAspectRatio=True,
                mask='auto'
            )
        else:
            print(f"⚠️ Logo no encontrado en: {logo_path}")
    except Exception as e:
        print("⚠️ No se pudo cargar el logo:", e)

    # Título a la izquierda
    c.setFillColor(colors.blue)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(2 * cm, height - 1.3 * cm, "Informe Económico del Proyecto")


    c.setFillColor(colors.black)
    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, height - 3 * cm, f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    c.drawString(2 * cm, height - 3.5 * cm, f"Periodo: desde {desde_str} hasta {hasta_str or 'actualidad'}")

    # Tarjetas resumen estilo panel
    y_start = height - 6 * cm
    card_data = [
        ("Total Forecast", total_forecast, colors.HexColor("#6c63ff")),
        ("Total Facturado", total_facturado, colors.HexColor("#00b894")),
        ("WIP", wip, colors.HexColor("#17a2b8")),
        ("Pendiente", total_pendiente, colors.HexColor("#e17055")),
        ("WIP Calculado", wip_calculado, colors.HexColor("#007bff")),
    ]

    card_width = (width - 4 * cm) / 2.2
    x_positions = [2 * cm, width / 2 + 0.2 * cm]
    y = y_start

    c.setFont("Helvetica", 11)
    for i, (label, val, color) in enumerate(card_data):
        x = x_positions[i % 2]
        if i > 0 and i % 2 == 0:
            y -= 2.2 * cm
        c.setStrokeColor(color)
        c.setLineWidth(1)
        c.roundRect(x, y, card_width, 1.6 * cm, 6, stroke=1, fill=0)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(x + 0.4 * cm, y + 1.1 * cm, label)
        c.setFont("Helvetica", 10)
        importe = "{:,.2f} €".format(val).replace(",", "X").replace(".", ",").replace("X", ".")
        c.drawRightString(x + card_width - 0.4 * cm, y + 0.5 * cm, importe)

    # Nueva página para las gráficas
    for i, img in enumerate(imgs):
        img_reader = ImageReader(img)
        y_pos = height - (i + 1) * (height / 2) - 2 * cm
        c.drawImage(img_reader, 2 * cm, y_pos, width=17 * cm, preserveAspectRatio=True, mask='auto')
        c.showPage()

    # Pie
    c.setFont("Helvetica-Oblique", 9)
    c.setFillColor(colors.grey)
    c.drawString(2 * cm, 1.5 * cm, "Generado automáticamente desde el panel de Control Económico")

    c.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"informe_economico_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
        mimetype="application/pdf"
    )

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)

class Prepagado(db.Model):
    __tablename__ = "prepagado"
    id = db.Column(db.Integer, primary_key=True)
    bolsa = db.Column(db.String(50), nullable=False)  # Ej: "Samsung", "New App"
    concepto = db.Column(db.String(100), nullable=True)  # Ej: "Consumo mayo", "Prefacturado"
    mes = db.Column(db.String(20), nullable=True)  # Ej: "mayo", "junio"
    importe = db.Column(db.Numeric(14, 2), default=0)
    tipo = db.Column(db.String(20), nullable=False, default="consumo")  # consumo / prefacturado / saldo

# --- CRUD Prepagado ---
@app.route("/prepagado")
def prepagado_list():
    registros = Prepagado.query.order_by(Prepagado.bolsa, Prepagado.id).all()

    resumen = {}
    for r in registros:
        resumen.setdefault(r.bolsa, {"saldo": 0, "consumo": 0, "prefacturado": 0})
        if r.tipo == "saldo":
            resumen[r.bolsa]["saldo"] += float(r.importe or 0)
        elif r.tipo == "consumo":
            resumen[r.bolsa]["consumo"] += float(r.importe or 0)
        elif r.tipo == "prefacturado":
            resumen[r.bolsa]["prefacturado"] += float(r.importe or 0)

    for bolsa, datos in resumen.items():
        datos["restante"] = datos["saldo"] - datos["consumo"] - datos["prefacturado"]

    # Cálculo total general
    total_general = sum(datos["restante"] for datos in resumen.values())

    return render_template(
        "prepagado.html",
        registros=registros,
        resumen=resumen,
        total_general=total_general
    )


@app.route("/prepagado/new", methods=["POST"])
def prepagado_new():
    bolsa = request.form.get("bolsa")
    concepto = request.form.get("concepto")
    mes = request.form.get("mes")
    tipo = request.form.get("tipo")
    importe = request.form.get("importe")

    try:
        importe = float(importe or 0)
    except ValueError:
        importe = 0.0

    nuevo = Prepagado(
        bolsa=bolsa,
        concepto=concepto or "",
        mes=mes or "",
        tipo=tipo,
        importe=importe
    )
    db.session.add(nuevo)
    db.session.commit()
    flash("Registro añadido correctamente", "success")
    return redirect(url_for("prepagado_list"))


@app.route("/prepagado/<int:rid>/edit", methods=["POST"])
def prepagado_edit(rid):
    r = Prepagado.query.get_or_404(rid)
    r.bolsa = request.form.get("bolsa")
    r.mes = request.form.get("mes")
    r.concepto = request.form.get("concepto")
    r.tipo = request.form.get("tipo")
    try:
        r.importe = float(request.form.get("importe") or 0)
    except ValueError:
        r.importe = 0.0
    db.session.commit()
    flash("Registro actualizado correctamente", "success")
    return redirect(url_for("prepagado_list"))


@app.route("/prepagado/<int:rid>/delete", methods=["POST"])
def prepagado_delete(rid):
    r = Prepagado.query.get_or_404(rid)
    db.session.delete(r)
    db.session.commit()
    flash("Registro eliminado", "info")
    return redirect(url_for("prepagado_list"))

