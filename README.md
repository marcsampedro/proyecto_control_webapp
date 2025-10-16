# Control Económico del Proyecto — Web App

App web lista para desplegar en Render. Permite CRUD mensual, gráficas (Chart.js) y una tabla de **Evolución de la bolsa mensual**. Incluye importador desde tu Excel `CONTROL_789.xlsx` (hoja `Resumen`).

## 1) Ejecutar en local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export FLASK_APP=app.py
python app.py  # http://localhost:5000
```

## 2) Inicializar la base de datos

```bash
flask --app app.py init-db
```

## 3) Importar desde el Excel

Coloca tu archivo en la ruta indicada o usa `XLSX_PATH`:

```bash
# Por defecto busca /mnt/data/CONTROL_789.xlsx
python import_from_excel.py

# O especifica ruta/hoja
XLSX_PATH=/ruta/a/CONTROL_789.xlsx XLSX_SHEET=Resumen python import_from_excel.py
```

> El importador detecta automáticamente la tabla principal y la sección "Evolución de la bolsa mensual".

## 4) Desplegar en Render

1. Crea un repo con estos archivos (o sube el `.zip` directamente a un nuevo repo).
2. En Render → **New +** → **Web Service** → **Build from repo**.
3. Render detectará Python y usará:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
4. (Opcional) Añade PostgreSQL y configura `DATABASE_URL`.
