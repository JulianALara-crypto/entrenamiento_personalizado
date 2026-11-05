import math
import os
import json
import io
import zipfile
import re
import urllib.parse
from datetime import datetime, date

import pandas as pd
import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

URL_API = ("https://script.google.com/macros/s/AKfycbzEqkRmWqqSKuK_ILnRMdTbnj8cUsD4DQ4FpHK-6zHirPKFJ5z3aEjsrrMXsWh_Eaw/exec")


# ============================================================
# SESIÓN HTTP REUTILIZABLE
# Evita crear una conexión HTTP nueva en cada operación.
# ============================================================
API_SESSION = requests.Session()

def api_get(*args, **kwargs):
    return API_SESSION.get(*args, **kwargs)

def api_post(*args, **kwargs):
    return API_SESSION.post(*args, **kwargs)


def enviar_pago_api(cedula, valor, concepto, valor_compromiso, fecha_pago=None):
    """Guarda un abono usando la estructura de Pagos que ya existe en Google Sheets."""
    fecha_pago = fecha_pago or datetime.today().strftime("%d-%m-%Y")
    id_pago = f"{normalizar_cedula(cedula)}_{datetime.today().strftime('%Y%m%d%H%M%S%f')}"
    respuesta = api_post(
        URL_API,
        json={
            "action": "guardar_pago",
            "id_pago": str(id_pago),
            "cedula": str(cedula).strip(),
            "fecha_pago": str(fecha_pago),
            "valor": float(valor),
            "concepto": str(concepto).strip(),
            "valor_mensualidad": float(valor_compromiso),
        },
        timeout=30,
    )
    respuesta.raise_for_status()
    try:
        resultado = respuesta.json()
    except Exception:
        resultado = {}
    if resultado.get("status") == "error":
        raise RuntimeError(str(resultado.get("message", "Google Apps Script reportó un error")))
    return id_pago


def _extraer_ref_contrato(texto):
    m = re.search(r"REF\s*=\s*([A-Za-z0-9_-]+)", str(texto or ""), flags=re.I)
    return m.group(1) if m else ""


def _extraer_valor_contrato(texto):
    m = re.search(r"VALOR\s*=\s*([0-9]+(?:[.,][0-9]+)?)", str(texto or ""), flags=re.I)
    if not m:
        return 0.0
    try:
        return float(m.group(1).replace(".", "").replace(",", ".")) if "." in m.group(1) and len(m.group(1).split(".")[-1]) == 3 else float(m.group(1).replace(",", "."))
    except Exception:
        return 0.0


def construir_estado_cuenta(df_pagos, df_planes, cedula):
    """Devuelve compromisos separados por plan y deudas mensuales históricas detectables.

    Los contratos nuevos se identifican con REF/VALOR en observaciones del plan y REF
    en el concepto del pago. Los registros antiguos se agrupan por mes porque no tenían
    identificador de contrato. No inventa cobros en meses sin registro.
    """
    cedula_norm = normalizar_cedula(cedula)
    pagos = df_pagos.copy() if df_pagos is not None and not df_pagos.empty else pd.DataFrame()
    planes = df_planes.copy() if df_planes is not None and not df_planes.empty else pd.DataFrame()
    if not pagos.empty and "cedula" in pagos.columns:
        pagos = pagos[pagos["cedula"].apply(normalizar_cedula) == cedula_norm].copy()
    if not planes.empty and "cedula" in planes.columns:
        planes = planes[planes["cedula"].apply(normalizar_cedula) == cedula_norm].copy()
    if not pagos.empty:
        pagos["_valor_num"] = pd.to_numeric(pagos["valor"] if "valor" in pagos.columns else pd.Series(0, index=pagos.index), errors="coerce").fillna(0)
        pagos["_compromiso_num"] = pd.to_numeric(pagos["valor_mensualidad"] if "valor_mensualidad" in pagos.columns else pd.Series(0, index=pagos.index), errors="coerce").fillna(0)
        pagos["_concepto_txt"] = pagos.get("concepto", pd.Series(index=pagos.index, dtype=str)).fillna("").astype(str)
        pagos["_fecha_dt"] = pagos.get("fecha_pago", pd.Series(index=pagos.index, dtype=str)).apply(parsear_fecha)
    obligaciones = []
    refs_nuevas = set()
    if not planes.empty:
        for _, plan_row in planes.iterrows():
            obs = str(plan_row.get("observaciones", "") or "")
            ref = _extraer_ref_contrato(obs)
            valor = _extraer_valor_contrato(obs)
            if not ref or valor <= 0:
                continue
            refs_nuevas.add(ref)
            nombre_plan = str(plan_row.get("tipo_plan", "Plan contratado") or "Plan contratado")
            fecha = str(plan_row.get("fecha_inicio", "") or "")
            concepto_ref = f"REF={ref}"
            abonos = 0.0
            if not pagos.empty:
                mask_ref = pagos["_concepto_txt"].str.contains(re.escape(concepto_ref), case=False, regex=True)
                abonos = float(pagos.loc[mask_ref, "_valor_num"].sum())
            saldo = max(valor - abonos, 0.0)
            obligaciones.append({
                "clave": f"plan:{ref}", "tipo": "Plan", "descripcion": f"{nombre_plan} · {fecha}",
                "valor": valor, "pagado": abonos, "saldo": saldo, "ref": ref,
            })
    # Compatibilidad con pagos antiguos: calcular pendientes de los meses que sí tienen
    # al menos un movimiento y cuyo valor de mensualidad quedó guardado en la hoja.
    if not pagos.empty:
        legacy = pagos[~pagos["_concepto_txt"].str.contains(r"REF\s*=", case=False, regex=True)].copy()
        legacy = legacy[legacy["_fecha_dt"].notna() & (legacy["_compromiso_num"] > 0)]
        if not legacy.empty:
            legacy["_periodo"] = legacy["_fecha_dt"].dt.strftime("%Y-%m")
            for periodo, grupo in legacy.groupby("_periodo", sort=True):
                valor = float(grupo["_compromiso_num"].iloc[-1])
                pagado = float(grupo["_valor_num"].sum())
                saldo = max(valor - pagado, 0.0)
                if saldo > 0.001:
                    obligaciones.append({
                        "clave": f"legacy:{periodo}", "tipo": "Saldo anterior",
                        "descripcion": f"Registro histórico · {periodo}", "valor": valor,
                        "pagado": pagado, "saldo": saldo, "ref": "",
                    })
    obligaciones.sort(key=lambda x: (x["tipo"] != "Saldo anterior", x["descripcion"]))
    return obligaciones

def invalidar_cache_datos():
    """Invalida únicamente los cachés de datos de la aplicación."""
    try:
        cargar_usuarios_login.clear()
    except Exception:
        pass
    try:
        cargar_bd.clear()
    except Exception:
        pass


# ============================================================
# RUTA SEGURA DEL LOGO
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

ruta_logo = os.path.join(
    BASE_DIR,
    "logo.png"
)


# ============================================================
# CARGAR LOGO
# ============================================================

icono_pestana = None

if os.path.isfile(ruta_logo):
    try:
        icono_pestana = Image.open(
            ruta_logo
        )
    except Exception:
        icono_pestana = None


# ============================================================
# CONFIGURACIÓN STREAMLIT
# ============================================================

st.set_page_config(
    page_title="Personal Training y Evolution Tracker Julian Avila",
    page_icon=icono_pestana,
    layout="wide",
)


# ============================================================
# ESTILOS
# ============================================================

st.markdown(
    """
    <style>

    .stApp {
        background-color: #000000;
    }

    h1, h2, h3, h4 {
        color: #ffffff !important;
        text-align: center;
    }

    p, label, .stMarkdown {
        color: #dddddd !important;
    }

    div[data-testid="stDecoration"] {
        display: none;
    }

    .clase-card {
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #333333;
        background-color: #111111;
        margin-bottom: 15px;
    }

    .ui-section-title {
        color: #ffffff !important;
        text-align: center !important;
        font-weight: 700 !important;
        letter-spacing: 0.3px;
        margin-top: 0.7rem;
        margin-bottom: 1rem;
    }

    .ui-section-title .fi { color: #ffffff; }

    .ui-module-header {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 14px;
        padding: 12px 18px;
        margin: 10px 0 18px 0;
        border: 1px solid #252525;
        border-radius: 16px;
        background: linear-gradient(180deg, #111111 0%, #080808 100%);
        box-shadow: 0 6px 18px rgba(0,0,0,0.28);
    }

    .ui-module-icon {
        width: 58px;
        height: 58px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 15px;
        border: 1px solid #333333;
        background: #151515;
    }

    .ui-module-icon .fi { color: #ffffff; margin-right: 0 !important; }

    .ui-module-title {
        color: #ffffff;
        font-size: 1.35rem;
        font-weight: 700;
        line-height: 1.2;
    }

    .ui-attribution {
        display:none !important;
        text-align: center;
        color: #777777;
        font-size: 0.75rem;
        margin-top: 30px;
        padding: 12px 0;
        border-top: 1px solid #222222;
    }

    .ui-attribution a { color: #aaaaaa !important; text-decoration: none; }

    
    /* ==========================================================
       GLASS/WOW 3D - PALETA POR MÓDULO + CONTROLES DINÁMICOS
       Capa visual. No cambia la lógica de negocio.
       ========================================================== */
    :root {
        --ui-cyan: #22d3ee;
        --ui-blue: #38bdf8;
        --ui-violet: #a78bfa;
        --ui-green: #34d399;
        --ui-amber: #fbbf24;
        --ui-coral: #fb7185;
    }

    section[data-testid="stSidebar"] {
        background:
            radial-gradient(circle at 15% 10%, rgba(34,211,238,.055), transparent 24%),
            radial-gradient(circle at 85% 80%, rgba(167,139,250,.045), transparent 25%),
            linear-gradient(180deg, #08090c 0%, #030405 100%) !important;
        border-right: 1px solid rgba(255,255,255,.075) !important;
    }

    section[data-testid="stSidebar"] [role="radiogroup"] {
        gap: 7px !important;
    }

    section[data-testid="stSidebar"] [role="radiogroup"] > label {
        position: relative;
        min-height: 43px;
        padding: 9px 12px !important;
        margin: 0 !important;
        border: 1px solid rgba(255,255,255,.055) !important;
        border-radius: 13px !important;
        background: rgba(255,255,255,.018) !important;
        transition: transform .2s ease, background .2s ease, border-color .2s ease, box-shadow .2s ease !important;
        overflow: hidden;
    }

    section[data-testid="stSidebar"] [role="radiogroup"] > label:hover {
        transform: translateX(3px) !important;
        background: rgba(255,255,255,.045) !important;
        border-color: rgba(255,255,255,.12) !important;
    }

    section[data-testid="stSidebar"] [role="radiogroup"] > label:has(input:checked) {
        background: linear-gradient(90deg, rgba(34,211,238,.13), rgba(34,211,238,.035)) !important;
        border-color: rgba(34,211,238,.45) !important;
        box-shadow: 0 0 22px rgba(34,211,238,.10), inset 3px 0 0 rgba(34,211,238,.95) !important;
    }

    section[data-testid="stSidebar"] [role="radiogroup"] > label:nth-child(2):has(input:checked) {
        background: linear-gradient(90deg, rgba(167,139,250,.14), rgba(167,139,250,.035)) !important;
        border-color: rgba(167,139,250,.45) !important;
        box-shadow: 0 0 22px rgba(167,139,250,.10), inset 3px 0 0 rgba(167,139,250,.95) !important;
    }
    section[data-testid="stSidebar"] [role="radiogroup"] > label:nth-child(3):has(input:checked) {
        background: linear-gradient(90deg, rgba(52,211,153,.14), rgba(52,211,153,.035)) !important;
        border-color: rgba(52,211,153,.45) !important;
        box-shadow: 0 0 22px rgba(52,211,153,.10), inset 3px 0 0 rgba(52,211,153,.95) !important;
    }

    div[data-baseweb="input"] > div:focus-within,
    div[data-baseweb="textarea"] > div:focus-within,
    div[data-baseweb="select"] > div:focus-within {
        border-color: rgba(34,211,238,.65) !important;
        box-shadow: 0 0 0 1px rgba(34,211,238,.30), 0 0 22px rgba(34,211,238,.09), inset 0 2px 8px rgba(0,0,0,.48) !important;
    }

    div.stButton > button:hover,
    div.stFormSubmitButton > button:hover,
    div.stDownloadButton > button:hover {
        border-color: rgba(34,211,238,.52) !important;
        box-shadow: 0 14px 32px rgba(0,0,0,.55), 0 0 20px rgba(34,211,238,.08), inset 0 1px 0 rgba(255,255,255,.14) !important;
    }

    div[data-testid="stMetric"] {
        border-top: 2px solid rgba(34,211,238,.72) !important;
    }
    div[data-testid="stMetric"]:nth-child(2) { border-top-color: rgba(167,139,250,.78) !important; }
    div[data-testid="stMetric"]:nth-child(3) { border-top-color: rgba(52,211,153,.78) !important; }
    div[data-testid="stMetric"]:nth-child(4) { border-top-color: rgba(251,191,36,.82) !important; }

    .ui-section-title { text-shadow: 0 0 20px rgba(34,211,238,.06); }
    .ui-section-title .fi { filter: drop-shadow(0 0 9px currentColor); }

    .clase-card { border-left: 3px solid rgba(34,211,238,.72) !important; }
    .clase-card:hover {
        border-left-color: rgba(167,139,250,.95) !important;
        box-shadow: 0 20px 42px rgba(0,0,0,.48), 0 0 22px rgba(167,139,250,.07), inset 0 1px 0 rgba(255,255,255,.07) !important;
    }

    div[data-testid="stDataFrame"] {
        border-color: rgba(255,255,255,.10) !important;
        box-shadow: 0 16px 34px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.05) !important;
    }

    /* BARRA DE PROGRESO DINÁMICA */
    .wow-progress-wrap {
        margin: 13px 0 18px 0;
        padding: 14px 16px 13px;
        border-radius: 17px;
        border: 1px solid rgba(255,255,255,.08);
        background: linear-gradient(145deg, rgba(255,255,255,.045), rgba(255,255,255,.012));
        box-shadow: 0 12px 28px rgba(0,0,0,.28), inset 0 1px 0 rgba(255,255,255,.055);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
    }
    .wow-progress-head { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:9px; }
    .wow-progress-label { color:#a7a7a7; font-size:12px; font-weight:800; letter-spacing:.7px; text-transform:uppercase; }
    .wow-progress-value { color:#fff; font-size:15px; font-weight:900; text-shadow:0 0 14px rgba(34,211,238,.18); }
    .wow-progress-track {
        position:relative; width:100%; height:13px; overflow:hidden; border-radius:999px;
        background:#090b0f; border:1px solid rgba(255,255,255,.07);
        box-shadow: inset 0 3px 7px rgba(0,0,0,.65), 0 1px 0 rgba(255,255,255,.025);
    }
    .wow-progress-fill {
        position:relative; height:100%; width:var(--progress-width); border-radius:999px;
        background:linear-gradient(90deg, var(--progress-start), var(--progress-mid), var(--progress-end));
        box-shadow:0 0 12px var(--progress-glow), 0 0 25px var(--progress-glow);
        animation: wowProgressIn 1.15s cubic-bezier(.2,.8,.2,1) both;
    }
    .wow-progress-fill::before {
        content:""; position:absolute; inset:0;
        background:linear-gradient(105deg, transparent 0%, rgba(255,255,255,.06) 38%, rgba(255,255,255,.68) 50%, rgba(255,255,255,.06) 62%, transparent 100%);
        transform:translateX(-120%); animation: wowProgressShine 2.8s ease-in-out 1.05s infinite;
    }
    .wow-progress-fill::after {
        content:""; position:absolute; inset:1px 0 auto 0; height:35%; border-radius:999px;
        background:linear-gradient(180deg, rgba(255,255,255,.32), transparent); opacity:.65;
    }
    .wow-progress-scale { display:flex; justify-content:space-between; margin-top:7px; color:#686868; font-size:10px; font-weight:700; }
    @keyframes wowProgressIn { from { width:0; opacity:.35; filter:brightness(.7); } to { width:var(--progress-width); opacity:1; filter:brightness(1); } }
    @keyframes wowProgressShine { 0%,35% { transform:translateX(-120%); } 70%,100% { transform:translateX(120%); } }
    @media (prefers-reduced-motion: reduce) { .wow-progress-fill, .wow-progress-fill::before { animation:none !important; } }

</style>
    """,
    unsafe_allow_html=True,
)

# UIcons de Flaticon: familia consistente para la interfaz.
st.markdown(
    "<link rel=\"stylesheet\" href=\"https://cdn-uicons.flaticon.com/2.6.0/uicons-regular-rounded/css/uicons-regular-rounded.css\">",
    unsafe_allow_html=True,
)

# ============================================================
# INTERFAZ PREMIUM FITNESS 2.0
# Capa exclusivamente visual: no modifica la lógica de negocio.
# ============================================================
st.markdown(
    """
    <style>

    /* ---------- GLASSMORPHISM PREMIUM 2.0 ---------- */
    .main .block-container {
        position: relative;
    }

    /* Cristal profundo para formularios y paneles */
    div[data-testid="stForm"],
    div[data-testid="stExpander"],
    div[data-testid="stMetric"],
    div[data-testid="stDataFrame"] {
        position: relative;
        overflow: hidden;
        backdrop-filter: blur(18px) saturate(120%);
        -webkit-backdrop-filter: blur(18px) saturate(120%);
    }

    div[data-testid="stForm"]::before,
    div[data-testid="stExpander"]::before,
    div[data-testid="stMetric"]::before,
    .clase-card::before,
    .ui-module-header::before {
        content: "";
        position: absolute;
        left: 0;
        right: 0;
        top: 0;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(255,255,255,0.32), transparent);
        opacity: 0.72;
        pointer-events: none;
    }

    /* Reflejo diagonal muy sutil, como vidrio real */
    div[data-testid="stMetric"]::after,
    div[data-testid="stForm"]::after,
    .clase-card::after {
        content: "";
        position: absolute;
        width: 55%;
        height: 180%;
        top: -55%;
        left: -28%;
        transform: rotate(24deg);
        background: linear-gradient(90deg, transparent, rgba(255,255,255,0.035), transparent);
        pointer-events: none;
    }

    /* Sombras multicapa para profundidad */
    div[data-testid="stMetric"] {
        box-shadow:
            0 2px 4px rgba(0,0,0,0.50),
            0 10px 24px rgba(0,0,0,0.38),
            0 24px 48px rgba(0,0,0,0.24),
            inset 0 1px 0 rgba(255,255,255,0.075),
            inset 0 -1px 0 rgba(0,0,0,0.65);
    }

    div[data-testid="stForm"] {
        box-shadow:
            0 3px 7px rgba(0,0,0,0.48),
            0 16px 34px rgba(0,0,0,0.40),
            0 30px 65px rgba(0,0,0,0.22),
            inset 0 1px 0 rgba(255,255,255,0.065),
            inset 0 -1px 0 rgba(0,0,0,0.70);
    }

    /* Inputs con sensación de cristal hundido */
    div[data-baseweb="input"] > div,
    div[data-baseweb="textarea"] > div,
    div[data-baseweb="select"] > div {
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        box-shadow:
            inset 0 2px 8px rgba(0,0,0,0.48),
            inset 0 1px 0 rgba(255,255,255,0.035),
            0 2px 8px rgba(0,0,0,0.22) !important;
    }

    /* Botones con volumen y sombra de objeto */
    div.stButton > button,
    div.stFormSubmitButton > button,
    div.stDownloadButton > button {
        position: relative;
        overflow: hidden;
        box-shadow:
            0 2px 4px rgba(0,0,0,0.55),
            0 8px 18px rgba(0,0,0,0.42),
            inset 0 1px 0 rgba(255,255,255,0.09),
            inset 0 -2px 0 rgba(0,0,0,0.45) !important;
    }

    div.stButton > button::before,
    div.stFormSubmitButton > button::before,
    div.stDownloadButton > button::before {
        content: "";
        position: absolute;
        top: 0;
        left: 10%;
        right: 10%;
        height: 1px;
        background: rgba(255,255,255,0.22);
        pointer-events: none;
    }

    div.stButton > button:hover,
    div.stFormSubmitButton > button:hover,
    div.stDownloadButton > button:hover {
        box-shadow:
            0 3px 5px rgba(0,0,0,0.60),
            0 14px 30px rgba(0,0,0,0.50),
            inset 0 1px 0 rgba(255,255,255,0.13),
            inset 0 -2px 0 rgba(0,0,0,0.38) !important;
    }

    /* Sidebar tipo panel de vidrio oscuro */
    section[data-testid="stSidebar"] {
        backdrop-filter: blur(20px) saturate(120%);
        -webkit-backdrop-filter: blur(20px) saturate(120%);
        box-shadow: 10px 0 35px rgba(0,0,0,0.30);
    }

    /* Encabezados de módulos con cristal */
    .ui-module-header {
        position: relative;
        overflow: hidden;
        backdrop-filter: blur(16px) saturate(120%);
        -webkit-backdrop-filter: blur(16px) saturate(120%);
        box-shadow:
            0 4px 8px rgba(0,0,0,0.42),
            0 16px 32px rgba(0,0,0,0.28),
            inset 0 1px 0 rgba(255,255,255,0.07);
    }

    .ui-module-icon {
        box-shadow:
            0 5px 14px rgba(0,0,0,0.42),
            inset 0 1px 0 rgba(255,255,255,0.07);
    }

    /* Tarjetas de clases más profundas */
    .clase-card {
        position: relative;
        overflow: hidden;
        backdrop-filter: blur(14px) saturate(115%);
        -webkit-backdrop-filter: blur(14px) saturate(115%);
        box-shadow:
            0 3px 6px rgba(0,0,0,0.52),
            0 14px 30px rgba(0,0,0,0.38),
            inset 0 1px 0 rgba(255,255,255,0.06),
            inset 0 -1px 0 rgba(0,0,0,0.62) !important;
    }

    .clase-card:hover {
        box-shadow:
            0 5px 9px rgba(0,0,0,0.55),
            0 20px 38px rgba(0,0,0,0.45),
            inset 0 1px 0 rgba(255,255,255,0.08) !important;
    }

    /* ---------- Fondo y profundidad general ---------- */
    .stApp {
        background:
            radial-gradient(circle at 12% 8%, rgba(255,255,255,0.055), transparent 24%),
            radial-gradient(circle at 88% 18%, rgba(120,120,120,0.045), transparent 22%),
            linear-gradient(135deg, #030303 0%, #080808 48%, #020202 100%) !important;
    }

    .main .block-container {
        max-width: 1450px;
        padding-top: 1.4rem;
        padding-bottom: 3rem;
    }

    /* ---------- Títulos ---------- */
    h1 {
        font-weight: 800 !important;
        letter-spacing: 1.2px !important;
        text-shadow: 0 3px 18px rgba(255,255,255,0.10);
    }

    h2, h3, h4 {
        letter-spacing: 0.35px;
    }

    /* ---------- Botones premium ---------- */
    div.stButton > button,
    div.stFormSubmitButton > button,
    div.stDownloadButton > button {
        border: 1px solid #353535 !important;
        border-radius: 14px !important;
        min-height: 46px !important;
        padding: 0.55rem 1.1rem !important;
        background: linear-gradient(145deg, #202020 0%, #0d0d0d 100%) !important;
        color: #f5f5f5 !important;
        font-weight: 700 !important;
        letter-spacing: 0.25px !important;
        box-shadow: 0 7px 18px rgba(0,0,0,0.38), inset 0 1px 0 rgba(255,255,255,0.06) !important;
        transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease, background 0.18s ease !important;
    }

    div.stButton > button:hover,
    div.stFormSubmitButton > button:hover,
    div.stDownloadButton > button:hover {
        transform: translateY(-2px) !important;
        border-color: #666666 !important;
        background: linear-gradient(145deg, #2b2b2b 0%, #111111 100%) !important;
        box-shadow: 0 12px 25px rgba(0,0,0,0.52), inset 0 1px 0 rgba(255,255,255,0.09) !important;
    }

    div.stButton > button:active,
    div.stFormSubmitButton > button:active,
    div.stDownloadButton > button:active {
        transform: translateY(1px) scale(0.99) !important;
    }

    /* ---------- Inputs ---------- */
    div[data-baseweb="input"] > div,
    div[data-baseweb="textarea"] > div,
    div[data-baseweb="select"] > div {
        background: linear-gradient(145deg, #151515, #0b0b0b) !important;
        border: 1px solid #303030 !important;
        border-radius: 12px !important;
        box-shadow: inset 0 1px 7px rgba(0,0,0,0.35) !important;
        transition: border-color 0.18s ease, box-shadow 0.18s ease !important;
    }

    div[data-baseweb="input"] > div:focus-within,
    div[data-baseweb="textarea"] > div:focus-within,
    div[data-baseweb="select"] > div:focus-within {
        border-color: #666666 !important;
        box-shadow: 0 0 0 1px #555555, 0 0 18px rgba(255,255,255,0.06) !important;
    }

    input, textarea {
        color: #f2f2f2 !important;
    }

    /* ---------- Métricas ---------- */
    div[data-testid="stMetric"] {
        background: linear-gradient(145deg, rgba(28,28,28,0.96), rgba(8,8,8,0.96));
        border: 1px solid #292929;
        border-radius: 18px;
        padding: 18px 18px 14px 18px;
        box-shadow: 0 10px 28px rgba(0,0,0,0.34), inset 0 1px 0 rgba(255,255,255,0.045);
        transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
    }

    div[data-testid="stMetric"]:hover {
        transform: translateY(-3px);
        border-color: #454545;
        box-shadow: 0 16px 34px rgba(0,0,0,0.48), inset 0 1px 0 rgba(255,255,255,0.07);
    }

    div[data-testid="stMetricLabel"] {
        color: #9f9f9f !important;
        font-weight: 600 !important;
    }

    div[data-testid="stMetricValue"] {
        color: #ffffff !important;
        font-weight: 800 !important;
    }

    /* ---------- Formularios / contenedores ---------- */
    div[data-testid="stForm"] {
        background: linear-gradient(145deg, rgba(18,18,18,0.92), rgba(7,7,7,0.92));
        border: 1px solid #262626;
        border-radius: 20px;
        padding: 18px;
        box-shadow: 0 14px 34px rgba(0,0,0,0.34), inset 0 1px 0 rgba(255,255,255,0.035);
    }

    /* ---------- Sidebar ---------- */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #080808 0%, #030303 100%) !important;
        border-right: 1px solid #242424;
    }

    section[data-testid="stSidebar"] div[data-testid="stButton"] button {
        border-radius: 12px !important;
    }

    section[data-testid="stSidebar"] label {
        transition: background 0.18s ease, transform 0.18s ease;
        border-radius: 10px;
        padding: 4px 6px;
    }

    section[data-testid="stSidebar"] label:hover {
        background: rgba(255,255,255,0.045);
        transform: translateX(2px);
    }

    /* ---------- Tarjetas personalizadas existentes ---------- */
    .clase-card {
        background: linear-gradient(145deg, #171717, #080808) !important;
        border: 1px solid #292929 !important;
        border-radius: 18px !important;
        box-shadow: 0 12px 28px rgba(0,0,0,0.38), inset 0 1px 0 rgba(255,255,255,0.04) !important;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }

    .clase-card:hover {
        transform: translateY(-2px);
        border-color: #444444 !important;
    }

    /* ---------- Separadores ---------- */
    hr {
        border-color: #252525 !important;
    }

    /* ---------- Expander ---------- */
    div[data-testid="stExpander"] {
        border: 1px solid #282828 !important;
        border-radius: 16px !important;
        background: rgba(10,10,10,0.72) !important;
        box-shadow: 0 9px 25px rgba(0,0,0,0.25);
    }

    /* ---------- Dataframes ---------- */
    div[data-testid="stDataFrame"] {
        border: 1px solid #292929;
        border-radius: 14px;
        overflow: hidden;
        box-shadow: 0 10px 25px rgba(0,0,0,0.28);
    }

    /* ---------- Logo ---------- */
    .logo-premium {
        filter: drop-shadow(0 10px 22px rgba(255,255,255,0.08));
    }

    /* ---------- Mobile ---------- */
    @media (max-width: 768px) {
        .main .block-container {
            padding-left: 0.8rem;
            padding-right: 0.8rem;
        }

        .ui-module-header {
            padding: 10px 12px;
        }

        .ui-module-icon {
            width: 48px;
            height: 48px;
        }
    }

\n\n    /* ========================================================\n       GLASS VIVO / MICROANIMACIONES PREMIUM\n       Solo visual: no altera la lógica de Streamlit.\n       ======================================================== */\n\n    .stApp {\n        background:\n            radial-gradient(circle at 12% 18%, rgba(255,255,255,0.075), transparent 20%),\n            radial-gradient(circle at 86% 12%, rgba(130,130,130,0.065), transparent 22%),\n            radial-gradient(circle at 50% 88%, rgba(255,255,255,0.035), transparent 25%),\n            linear-gradient(135deg, #020202 0%, #090909 48%, #020202 100%) !important;\n        background-size: 140% 140%;\n        animation: glassAmbient 18s ease-in-out infinite alternate;\n    }\n\n    @keyframes glassAmbient {\n        0% { background-position: 0% 0%; }\n        50% { background-position: 100% 35%; }\n        100% { background-position: 35% 100%; }\n    }\n\n    /* Luz ambiental muy suave que recorre el cristal */\n    div[data-testid="stMetric"]::after,\n    div[data-testid="stForm"]::after,\n    div[data-testid="stExpander"]::after,\n    .clase-card::after,\n    .ui-module-header::after {\n        animation: glassShimmer 7s ease-in-out infinite;\n    }\n\n    @keyframes glassShimmer {\n        0%, 100% { opacity: 0.18; transform: translateX(-35%) rotate(24deg); }\n        50% { opacity: 0.52; transform: translateX(115%) rotate(24deg); }\n    }\n\n    /* Tarjetas con una pequeña sensación de objeto flotante */\n    div[data-testid="stMetric"] {\n        animation: cardFloat 6s ease-in-out infinite;\n    }\n\n    div[data-testid="stMetric"]:nth-child(2) { animation-delay: -1.2s; }\n    div[data-testid="stMetric"]:nth-child(3) { animation-delay: -2.4s; }\n    div[data-testid="stMetric"]:nth-child(4) { animation-delay: -3.6s; }\n\n    @keyframes cardFloat {\n        0%, 100% { transform: translateY(0px); }\n        50% { transform: translateY(-3px); }\n    }\n\n    div[data-testid="stMetric"]:hover {\n        animation-play-state: paused;\n        transform: translateY(-7px) scale(1.012) !important;\n        border-color: #5a5a5a !important;\n        box-shadow:\n            0 5px 10px rgba(0,0,0,0.58),\n            0 20px 42px rgba(0,0,0,0.52),\n            0 0 28px rgba(255,255,255,0.035),\n            inset 0 1px 0 rgba(255,255,255,0.12) !important;\n    }\n\n    /* Botones con respuesta más viva */\n    div.stButton > button,\n    div.stFormSubmitButton > button,\n    div.stDownloadButton > button {\n        transition: transform 0.2s cubic-bezier(.2,.8,.2,1),\n                    box-shadow 0.2s ease,\n                    border-color 0.2s ease,\n                    background 0.2s ease !important;\n    }\n\n    div.stButton > button:hover,\n    div.stFormSubmitButton > button:hover,\n    div.stDownloadButton > button:hover {\n        transform: translateY(-3px) scale(1.015) !important;\n        border-color: #777777 !important;\n        box-shadow:\n            0 4px 8px rgba(0,0,0,0.62),\n            0 16px 32px rgba(0,0,0,0.52),\n            0 0 20px rgba(255,255,255,0.035),\n            inset 0 1px 0 rgba(255,255,255,0.14) !important;\n    }\n\n    /* Iconos: pequeño pulso elegante al pasar el mouse */\n    .ui-module-icon,\n    .ui-module-header i,\n    .ui-section-title i {\n        transition: transform 0.25s ease, filter 0.25s ease;\n    }\n\n    .ui-module-header:hover .ui-module-icon,\n    .ui-module-header:hover i {\n        transform: translateY(-2px) scale(1.06);\n        filter: drop-shadow(0 5px 10px rgba(255,255,255,0.12));\n    }\n\n    /* Inputs más vivos sin perder el aspecto de cristal */\n    div[data-baseweb="input"] > div:hover,\n    div[data-baseweb="textarea"] > div:hover,\n    div[data-baseweb="select"] > div:hover {\n        border-color: #4b4b4b !important;\n        box-shadow:\n            inset 0 2px 8px rgba(0,0,0,0.48),\n            0 0 16px rgba(255,255,255,0.025) !important;\n    }\n\n    /* Aparición suave de bloques al cargar */\n    .main .block-container > div {\n        animation: softReveal 0.55s ease both;\n    }\n\n    @keyframes softReveal {\n        from { opacity: 0; transform: translateY(7px); }\n        to { opacity: 1; transform: translateY(0); }\n    }\n\n    /* Respeta usuarios que prefieren menos movimiento */\n    @media (prefers-reduced-motion: reduce) {\n        *, *::before, *::after {\n            animation-duration: 0.01ms !important;\n            animation-iteration-count: 1 !important;\n            transition-duration: 0.01ms !important;\n        }\n    }\n    

    /* ==========================================================
       DASHBOARD WOW - GLASS INTERACTIVO
       ========================================================== */
    .dashboard-hero {
        position: relative;
        overflow: hidden;
        margin: 8px 0 24px 0;
        padding: 30px 34px;
        border-radius: 26px;
        border: 1px solid rgba(255,255,255,0.14);
        background:
            radial-gradient(circle at 85% 20%, rgba(255,255,255,0.12), transparent 22%),
            linear-gradient(135deg, rgba(255,255,255,0.075), rgba(255,255,255,0.018));
        backdrop-filter: blur(22px) saturate(125%);
        -webkit-backdrop-filter: blur(22px) saturate(125%);
        box-shadow: 0 24px 55px rgba(0,0,0,0.52), inset 0 1px 0 rgba(255,255,255,0.13);
        transform-style: preserve-3d;
        animation: heroFloat 7s ease-in-out infinite;
    }
    .dashboard-hero::before {
        content: "";
        position: absolute;
        width: 280px;
        height: 280px;
        right: -90px;
        top: -150px;
        border-radius: 50%;
        background: rgba(255,255,255,0.08);
        filter: blur(45px);
        animation: orbMove 9s ease-in-out infinite alternate;
    }
    .dashboard-kicker { color:#aaa; font-size:11px; letter-spacing:3px; font-weight:800; position:relative; z-index:1; }
    .dashboard-title { color:#fff; font-size:34px; font-weight:900; margin-top:5px; position:relative; z-index:1; text-shadow:0 5px 25px rgba(255,255,255,0.12); }
    .dashboard-subtitle { color:#9b9b9b; margin-top:6px; font-size:14px; position:relative; z-index:1; }
    .dashboard-section-title { margin:26px 0 12px; color:#fff; font-size:18px; font-weight:800; letter-spacing:.3px; }
    .glass-panel-title { color:#d7d7d7; font-weight:700; margin:4px 0 8px; }
    .dashboard-card {
        position:relative; overflow:hidden; min-height:145px; padding:20px; border-radius:22px;
        border:1px solid rgba(255,255,255,0.11);
        background:linear-gradient(145deg, rgba(35,35,35,.72), rgba(7,7,7,.74));
        backdrop-filter:blur(18px); -webkit-backdrop-filter:blur(18px);
        box-shadow:0 18px 38px rgba(0,0,0,.48), inset 0 1px 0 rgba(255,255,255,.08);
        transition:transform .28s ease, border-color .28s ease, box-shadow .28s ease;
    }
    .dashboard-card::after {
        content:""; position:absolute; inset:-60% -30%;
        background:linear-gradient(110deg, transparent 40%, rgba(255,255,255,.08) 50%, transparent 60%);
        transform:translateX(-65%) rotate(8deg); transition:transform .7s ease; pointer-events:none;
    }
    .dashboard-card:hover { transform:translateY(-8px) perspective(800px) rotateX(2deg) rotateY(-2deg); border-color:rgba(255,255,255,.24); box-shadow:0 28px 55px rgba(0,0,0,.62), inset 0 1px 0 rgba(255,255,255,.12); }
    .dashboard-card:hover::after { transform:translateX(65%) rotate(8deg); }
    .dash-icon { font-size:25px; margin-bottom:12px; filter:drop-shadow(0 5px 10px rgba(255,255,255,.12)); }
    .dash-label { color:#9c9c9c; font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:1px; }
    .dash-value { color:#fff; font-size:30px; font-weight:900; margin-top:4px; }
    .dash-note { color:#777; font-size:11px; margin-top:5px; }
    @keyframes heroFloat { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-3px)} }
    @keyframes orbMove { from{transform:translate(-15px,8px) scale(.9)} to{transform:translate(18px,28px) scale(1.15)} }
    @media (prefers-reduced-motion: reduce) { .dashboard-hero,.dashboard-hero::before { animation:none !important; } .dashboard-card { transition:none !important; } }


    /* ========================================================
       PALETA PREMIUM AZUL PETRÓLEO + VERDE OLIVA
       Capa visual: no modifica lógica ni datos.
       ======================================================== */
    .stApp {
        background:
            radial-gradient(circle at 8% 10%, rgba(43, 177, 224, .16), transparent 25%),
            radial-gradient(circle at 88% 14%, rgba(126, 145, 76, .14), transparent 27%),
            radial-gradient(circle at 72% 88%, rgba(49, 155, 119, .09), transparent 24%),
            linear-gradient(135deg, #06121b 0%, #0a222b 48%, #18281f 100%) !important;
        background-size: 150% 150%;
        animation: premiumAmbient 22s ease-in-out infinite alternate;
    }

    @keyframes premiumAmbient {
        0% { background-position: 0% 0%; }
        50% { background-position: 100% 35%; }
        100% { background-position: 35% 100%; }
    }

    /* Glass más luminoso, pero sobrio */
    .dashboard-card,
    div[data-testid="stMetric"],
    .clase-card,
    div[data-testid="stForm"],
    div[data-testid="stExpander"] {
        background:
            linear-gradient(145deg, rgba(255,255,255,.065), rgba(255,255,255,.018)) !important;
        border-color: rgba(185, 224, 218, .12) !important;
        box-shadow:
            0 20px 48px rgba(0,0,0,.30),
            inset 0 1px 0 rgba(255,255,255,.07) !important;
    }

    .dashboard-card:hover,
    div[data-testid="stMetric"]:hover,
    .clase-card:hover {
        border-color: rgba(76, 205, 224, .30) !important;
        box-shadow:
            0 25px 58px rgba(0,0,0,.38),
            0 0 28px rgba(54,185,232,.07),
            inset 0 1px 0 rgba(255,255,255,.10) !important;
    }

    /* Cabeceras de módulos */
    .ui-module-header {
        border-color: rgba(255,255,255,.11) !important;
        background:
            linear-gradient(135deg, rgba(54,185,232,.075), rgba(127,143,82,.065) 55%, rgba(255,255,255,.018)) !important;
        box-shadow:
            0 14px 32px rgba(0,0,0,.25),
            inset 0 1px 0 rgba(255,255,255,.07) !important;
    }

    /* Acentos de iconos por contexto */
    .ui-module-icon { filter: drop-shadow(0 0 10px currentColor); }
    .ui-module-header .fi-rr-users,
    .ui-module-header .fi-rr-user { color:#4fc3e8 !important; }
    .ui-module-header .fi-rr-dumbbell,
    .ui-module-header .fi-rr-chart-histogram { color:#9b8cff !important; }
    .ui-module-header .fi-rr-calendar,
    .ui-module-header .fi-rr-check { color:#55d5aa !important; }
    .ui-module-header .fi-rr-money,
    .ui-module-header .fi-rr-credit-card { color:#e5bd67 !important; }

    /* Botones: color premium, no arcoíris */
    div.stButton > button,
    div.stFormSubmitButton > button,
    div.stDownloadButton > button,
    a[data-testid="stLinkButton"] {
        background: linear-gradient(135deg, rgba(42,164,207,.20), rgba(91,119,68,.18)) !important;
        border-color: rgba(108,203,215,.22) !important;
        box-shadow:
            0 9px 25px rgba(0,0,0,.24),
            inset 0 1px 0 rgba(255,255,255,.08) !important;
    }

    div.stButton > button:hover,
    div.stFormSubmitButton > button:hover,
    div.stDownloadButton > button:hover,
    a[data-testid="stLinkButton"]:hover {
        background: linear-gradient(135deg, rgba(54,185,232,.30), rgba(127,143,82,.25)) !important;
        border-color: rgba(112,218,226,.48) !important;
        box-shadow:
            0 15px 34px rgba(0,0,0,.30),
            0 0 24px rgba(54,185,232,.10) !important;
    }

    /* Barra de progreso: azul -> violeta -> oliva/verde según avance */
    .wow-progress-wrap {
        background: linear-gradient(145deg, rgba(255,255,255,.065), rgba(255,255,255,.018)) !important;
        border: 1px solid rgba(177,218,207,.13) !important;
        box-shadow:
            0 20px 46px rgba(0,0,0,.30),
            inset 0 1px 0 rgba(255,255,255,.07) !important;
        backdrop-filter: blur(18px);
    }

    .wow-progress-track {
        background: rgba(2,12,17,.62) !important;
        border: 1px solid rgba(255,255,255,.07);
        box-shadow: inset 0 2px 7px rgba(0,0,0,.42) !important;
    }

    .wow-progress-fill {
        background: linear-gradient(90deg, var(--progress-start), var(--progress-mid), var(--progress-end)) !important;
        box-shadow:
            0 0 14px var(--progress-glow),
            0 0 30px var(--progress-glow) !important;
    }

    .wow-progress-fill::after {
        background: linear-gradient(90deg, transparent, rgba(255,255,255,.72), transparent) !important;
        animation: wowProgressShine 2.4s ease-in-out infinite !important;
    }

    @keyframes wowProgressShine {
        0% { transform: translateX(-140%); opacity:0; }
        18% { opacity:1; }
        52% { opacity:.9; }
        100% { transform: translateX(520%); opacity:0; }
    }

    /* Tabla más limpia */
    div[data-testid="stDataFrame"] {
        border: 1px solid rgba(176,218,211,.11) !important;
        box-shadow: 0 18px 40px rgba(0,0,0,.25) !important;
        border-radius: 16px !important;
    }

    /* Sidebar: azul petróleo con oliva casi imperceptible */
    section[data-testid="stSidebar"] {
        background:
            radial-gradient(circle at 15% 8%, rgba(54,185,232,.09), transparent 28%),
            linear-gradient(180deg, rgba(4,15,22,.98), rgba(14,25,22,.98)) !important;
        border-right: 1px solid rgba(103,194,203,.10) !important;
    }

    section[data-testid="stSidebar"] .stRadio label:hover {
        background: linear-gradient(90deg, rgba(54,185,232,.10), rgba(127,143,82,.07)) !important;
    }
</style>
    """,
    unsafe_allow_html=True,
)


def icono_ui(clase, tamano=28):
    """Icono UI con color contextual por módulo; solo cambia presentación."""
    colores = {
        "fi-rr-user": "#22d3ee",
        "fi-rr-users": "#22d3ee",
        "fi-rr-file-user": "#22d3ee",
        "fi-rr-dashboard": "#38bdf8",
        "fi-rr-apps": "#38bdf8",
        "fi-rr-dumbbell": "#a78bfa",
        "fi-rr-ruler-horizontal": "#a78bfa",
        "fi-rr-clipboard": "#34d399",
        "fi-rr-wallet": "#34d399",
        "fi-rr-credit-card": "#34d399",
        "fi-rr-calendar": "#fbbf24",
        "fi-rr-bell": "#fbbf24",
        "fi-rr-document": "#fb7185",
    }
    color = colores.get(clase, "#e5e7eb")
    return (
        f'<i class="fi {clase}" style="font-size:{tamano}px; color:{color}; '
        'vertical-align:middle; margin-right:10px;"></i>'
    )

def titulo_ui(texto, clase_icono="fi-rr-apps", nivel=2, tamano=30):
    tag = f"h{nivel}"
    st.markdown(
        f'<{tag} class=\"ui-section-title\">{icono_ui(clase_icono, tamano)}{texto}</{tag}>',
        unsafe_allow_html=True,
    )


# ============================================================
# FUNCIÓN FORMATEAR FECHA
# ============================================================

def parsear_fecha(valor_fecha):
    """Convierte fechas de Google Sheets/ISO/DD-MM-YYYY a Timestamp."""
    if valor_fecha is None:
        return pd.NaT

    if isinstance(valor_fecha, (datetime, date)):
        try:
            return pd.Timestamp(valor_fecha)
        except Exception:
            return pd.NaT

    texto = str(valor_fecha).strip()

    if not texto:
        return pd.NaT

    # Formato principal de la aplicación: DD-MM-YYYY
    dt = pd.to_datetime(
        texto,
        format="%d-%m-%Y",
        errors="coerce"
    )

    if not pd.isna(dt):
        return dt

    # ISO generado por Google Apps Script
    dt = pd.to_datetime(
        texto,
        errors="coerce",
        dayfirst=False
    )

    return dt


def formatear_fecha(valor_fecha):
    dt = parsear_fecha(valor_fecha)

    if pd.isna(dt):
        texto = str(valor_fecha).strip() if valor_fecha is not None else ""
        return "" if texto.lower() in ("nan", "nat", "none") else texto

    return dt.strftime("%d-%m-%Y")


# ============================================================
# MOSTRAR LOGO
# ============================================================

if icono_pestana is not None:
    col_l1, col_l2, col_l3 = st.columns(3)

    with col_l2:
        st.image(
            icono_pestana,
            width="stretch"
        )


# ============================================================
# ALIMENTACIÓN RECOMENDADA SEGÚN OBJETIVO
# Utiliza UIcons de Flaticon ya cargados por la aplicación.
# ============================================================

def calcular_recomendacion_alimentaria(row):
    """Calcula una guía orientativa desde la última evaluación disponible."""
    def numero(campos, predeterminado=0.0):
        for campo in campos:
            try:
                valor = float(row.get(campo, 0) or 0)
                if valor > 0:
                    return valor
            except (TypeError, ValueError):
                continue
        return float(predeterminado)

    peso = numero(["peso_kg", "peso"], 70.0)
    calorias = numero(["calorias_objetivo"], 0.0)
    meta = str(row.get("meta", row.get("objetivo", "Mantenimiento"))).strip().lower()

    if "recompos" in meta:
        objetivo, factor_proteina, grasa_pct, color = "Recomposición corporal", 2.0, 0.28, "#b69cff"
        enfoque = (
            "Busca reducir gradualmente el porcentaje de grasa mientras conservas o desarrollas músculo. "
            "Se usa como referencia el mantenimiento energético, proteína suficiente y entrenamiento de fuerza."
        )
    elif "ganar" in meta or "músc" in meta or "mus" in meta:
        objetivo, factor_proteina, grasa_pct, color = "Ganar músculo", 1.8, 0.27, "#35d0ba"
        enfoque = "Prioriza proteína suficiente y energía para apoyar el entrenamiento y el desarrollo muscular."
    elif "perder" in meta or "grasa" in meta or "peso" in meta or "déficit" in meta or "deficit" in meta:
        objetivo, factor_proteina, grasa_pct, color = "Perder peso / Déficit calórico", 1.8, 0.28, "#ff7185"
        enfoque = (
            "Déficit calórico moderado como punto de partida, con proteína suficiente, verduras y fibra "
            "para favorecer la pérdida gradual de grasa y ayudar a conservar músculo."
        )
    else:
        objetivo, factor_proteina, grasa_pct, color = "Mantenimiento", 1.6, 0.30, "#69aefc"
        enfoque = "Busca una alimentación equilibrada que ayude a mantener tu peso, energía y rendimiento."

    if calorias <= 0:
        calorias = max(1200.0, peso * 30.0)

    proteina = round(peso * factor_proteina)
    grasa = round((calorias * grasa_pct) / 9)
    carbohidratos = max(50, round((calorias - proteina * 4 - grasa * 9) / 4))

    distribucion = [
        {"nombre": "Desayuno", "icono": "fi-rr-sun", "kcal": 0.25, "p": 0.25, "c": 0.25, "g": 0.22,
         "alimentos": "Huevos o yogur griego, avena o pan integral y una fruta."},
        {"nombre": "Almuerzo", "icono": "fi-rr-utensils", "kcal": 0.32, "p": 0.30, "c": 0.35, "g": 0.32,
         "alimentos": "Pollo, pescado, huevos o legumbres; arroz, papa o pasta; verduras y una porción de grasa saludable."},
        {"nombre": "Merienda / entrenamiento", "icono": "fi-rr-dumbbell", "kcal": 0.15, "p": 0.18, "c": 0.17, "g": 0.16,
         "alimentos": "Yogur alto en proteína o una alternativa equivalente, fruta y avena o pan integral según preferencia."},
        {"nombre": "Cena", "icono": "fi-rr-moon", "kcal": 0.28, "p": 0.27, "c": 0.23, "g": 0.30,
         "alimentos": "Pescado, pollo, huevos, tofu o legumbres; una porción de papa, arroz u otro cereal y verduras."},
    ]
    comidas = []
    for item in distribucion:
        comidas.append({
            **item,
            "kcal_total": round(calorias * item["kcal"]),
            "proteina": round(proteina * item["p"]),
            "carbohidratos": round(carbohidratos * item["c"]),
            "grasa": round(grasa * item["g"]),
        })

    return {
        "objetivo": objetivo, "color": color, "enfoque": enfoque,
        "calorias": round(calorias), "proteina": proteina,
        "carbohidratos": carbohidratos, "grasa": grasa, "comidas": comidas,
    }


def mostrar_alimentacion_recomendada(row, nombre_cliente="Cliente"):
    """Muestra macros y ejemplos de comidas del cliente seleccionado."""
    if row is None or not hasattr(row, "index") or len(row.index) == 0:
        st.info("Todavía no hay una evaluación disponible para generar la guía alimentaria.")
        return

    plan = calcular_recomendacion_alimentaria(row)
    color = plan["color"]
    st.markdown("---")
    titulo_ui("Alimentación recomendada", "fi-rr-restaurant", 3, 26)
    st.caption(
        "Guía orientativa calculada con el peso, el objetivo y las calorías de la última evaluación. "
        "No sustituye una valoración individual de nutrición."
    )

    st.markdown(
        f"""<div style="background:linear-gradient(135deg,rgba(255,255,255,.085),rgba(255,255,255,.025));
        border:1px solid {color}77;border-radius:20px;padding:20px;margin:8px 0 16px;
        box-shadow:0 10px 32px rgba(0,0,0,.20);">
        <div style="font-size:13px;opacity:.78;">PLAN ORIENTATIVO · {nombre_cliente}</div>
        <div style="font-size:26px;font-weight:800;color:{color};margin:6px 0;">{plan['objetivo']}</div>
        <div style="font-size:14px;opacity:.9;">{plan['enfoque']}</div></div>""",
        unsafe_allow_html=True,
    )

    columnas = st.columns(4)
    tarjetas = [
        ("fi-rr-bolt", "Energía", f"{plan['calorias']:,} kcal/día", "#f6c85f"),
        ("fi-rr-egg", "Proteína", f"{plan['proteina']} g/día", "#35d0ba"),
        ("fi-rr-wheat", "Carbohidratos", f"{plan['carbohidratos']} g/día", "#69aefc"),
        ("fi-rr-apple-whole", "Grasas", f"{plan['grasa']} g/día", "#c49bff"),
    ]
    for col, (icono, etiqueta, valor, tono) in zip(columnas, tarjetas):
        with col:
            st.markdown(
                f"""<div style="height:100%;min-height:112px;padding:15px 12px;border-radius:16px;
                border:1px solid {tono}66;background:rgba(255,255,255,.045);text-align:center;">
                <div style="font-size:22px;color:{tono};"><i class="fi {icono}"></i></div>
                <div style="font-size:12px;opacity:.8;margin-top:5px;">{etiqueta}</div>
                <div style="font-size:19px;font-weight:800;color:{tono};margin-top:4px;">{valor}</div></div>""",
                unsafe_allow_html=True,
            )

    st.markdown("#### Distribución sugerida por comida")
    for comida in plan["comidas"]:
        st.markdown(
            f"""<div style="background:linear-gradient(145deg,rgba(255,255,255,.07),rgba(255,255,255,.025));
            border:1px solid rgba(255,255,255,.11);border-radius:17px;padding:17px;margin:10px 0;">
            <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;">
            <div style="font-size:19px;font-weight:800;"><i class="fi {comida['icono']}" style="color:{color};"></i>
            &nbsp;{comida['nombre']}</div><div style="font-weight:800;color:{color};">≈ {comida['kcal_total']} kcal</div></div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:13px;">
            <span style="padding:7px 10px;border-radius:9px;background:rgba(53,208,186,.12);">Proteína: <b>{comida['proteina']} g</b></span>
            <span style="padding:7px 10px;border-radius:9px;background:rgba(105,174,252,.12);">Carbohidratos: <b>{comida['carbohidratos']} g</b></span>
            <span style="padding:7px 10px;border-radius:9px;background:rgba(196,155,255,.12);">Grasas: <b>{comida['grasa']} g</b></span></div>
            <div style="margin-top:12px;font-size:14px;opacity:.9;"><b>Ideas de alimentos:</b> {comida['alimentos']}</div></div>""",
            unsafe_allow_html=True,
        )

    st.info(
        "Las cantidades de macronutrientes por comida son aproximadas y no equivalen a gramos de cada alimento. "
        "Las porciones reales deben ajustarse a preferencias, alergias, salud y entrenamiento; consulta a un profesional "
        "si necesitas una dieta individualizada."
    )


# ============================================================
# EVOLUCIÓN INTELIGENTE: TRES INFOGRAFÍAS DINÁMICAS
# Las imágenes se dibujan con PIL usando los datos reales guardados.
# No se envían datos personales a servicios externos ni se inventan
# cantidades nutricionales. Los macros por comida son estimaciones.
# ============================================================

def _valor_fila(row, claves, defecto=0.0):
    for clave in claves:
        try:
            valor = row.get(clave, None)
            if valor is not None and str(valor).strip() not in ("", "nan", "None"):
                return float(valor)
        except (TypeError, ValueError):
            pass
    return float(defecto)


def _texto_fila(row, claves, defecto=""):
    for clave in claves:
        try:
            valor = row.get(clave, None)
            if valor is not None and str(valor).strip() not in ("", "nan", "None"):
                return str(valor).strip()
        except Exception:
            pass
    return defecto


def _fuente_imagen(tamano, negrita=False):
    rutas = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if negrita else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if negrita else "C:/Windows/Fonts/arial.ttf",
        "DejaVuSans-Bold.ttf" if negrita else "DejaVuSans.ttf",
    ]
    for ruta in rutas:
        try:
            return ImageFont.truetype(ruta, tamano)
        except Exception:
            continue
    return ImageFont.load_default()


def _crear_lienzo(titulo, subtitulo, acento):
    ancho, alto = 900, 1200
    imagen = Image.new("RGB", (ancho, alto), (7, 13, 25))
    px = imagen.load()
    for y in range(alto):
        t = y / max(1, alto - 1)
        color = (int(8 + 5*t), int(17 + 12*t), int(31 + 20*t))
        for x in range(ancho):
            px[x, y] = color
    d = ImageDraw.Draw(imagen)
    d.rounded_rectangle((28, 28, ancho-28, alto-28), radius=34, outline=(48, 75, 100), width=3)
    d.rounded_rectangle((55, 55, ancho-55, 205), radius=26, fill=(14, 29, 47), outline=acento, width=2)
    d.text((82, 82), "PERSONAL TRAINING", font=_fuente_imagen(29, True), fill=(139, 220, 229))
    d.text((82, 120), titulo, font=_fuente_imagen(48, True), fill=(248, 250, 252))
    d.text((84, 174), subtitulo[:55], font=_fuente_imagen(23), fill=(183, 199, 216))
    return imagen, d


def _tarjeta(d, caja, titulo, valor, detalle="", acento=(48, 190, 190)):
    x1, y1, x2, y2 = caja
    d.rounded_rectangle(caja, radius=22, fill=(17, 34, 53), outline=acento, width=2)
    d.text((x1+22, y1+18), titulo.upper(), font=_fuente_imagen(17, True), fill=(170, 190, 210))
    d.text((x1+22, y1+54), str(valor), font=_fuente_imagen(35, True), fill=(245, 250, 255))
    if detalle:
        d.text((x1+22, y2-39), str(detalle)[:36], font=_fuente_imagen(15), fill=acento)


def _texto_ajustado(d, xy, texto, fuente, color, max_ancho, max_lineas=2, separacion=5):
    x, y = xy
    palabras = str(texto).split()
    lineas, actual = [], ""
    for palabra in palabras:
        prueba = (actual + " " + palabra).strip()
        if d.textbbox((0, 0), prueba, font=fuente)[2] <= max_ancho:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    for linea in lineas[:max_lineas]:
        d.text((x, y), linea, font=fuente, fill=color)
        y += fuente.size + separacion
    return y


def _dibujar_figura_humana_3d(imagen, centro_x=450, arriba=245, acento=(70, 190, 205)):
    """Silueta anatómica ilustrada con volumen, degradados, luz y sombra (sin datos externos)."""
    escala = 3
    w, h = imagen.size
    mascara = Image.new("L", (w * escala, h * escala), 0)
    md = ImageDraw.Draw(mascara)
    def poligono(puntos, fill=255):
        md.polygon([(int(x*escala), int((t + (y-t)*0.83)*escala)) for x, y in puntos], fill=fill)
    def elipse(caja, fill=255):
        x1, y1, x2, y2 = caja
        md.ellipse((int(x1*escala), int((t+(y1-t)*0.83)*escala),
                    int(x2*escala), int((t+(y2-t)*0.83)*escala)), fill=fill)
    cx, t = centro_x, arriba
    # Cabeza y cuello
    elipse((cx-43, t, cx+43, t+91))
    poligono([(cx-19,t+76),(cx+19,t+76),(cx+25,t+119),(cx-25,t+119)])
    # Tronco: hombros, pecho, cintura y cadera con contorno anatómico suave
    poligono([(cx-27,t+105),(cx-72,t+112),(cx-105,t+143),(cx-94,t+205),
              (cx-76,t+265),(cx-70,t+330),(cx-91,t+374),(cx-72,t+405),
              (cx-44,t+418),(cx+44,t+418),(cx+72,t+405),(cx+91,t+374),
              (cx+70,t+330),(cx+76,t+265),(cx+94,t+205),(cx+105,t+143),
              (cx+72,t+112),(cx+27,t+105)])
    # Brazos superiores, antebrazos y manos
    poligono([(cx-82,t+125),(cx-111,t+137),(cx-151,t+218),(cx-184,t+296),
              (cx-170,t+315),(cx-151,t+306),(cx-119,t+244),(cx-83,t+184)])
    poligono([(cx+82,t+125),(cx+111,t+137),(cx+151,t+218),(cx+184,t+296),
              (cx+170,t+315),(cx+151,t+306),(cx+119,t+244),(cx+83,t+184)])
    elipse((cx-187,t+286,cx-153,t+340)); elipse((cx+153,t+286,cx+187,t+340))
    # Piernas: muslos, rodillas y pantorrillas con separación natural
    poligono([(cx-76,t+390),(cx-18,t+399),(cx-26,t+510),(cx-39,t+565),
              (cx-48,t+610),(cx-91,t+610),(cx-88,t+560),(cx-91,t+505)])
    poligono([(cx+76,t+390),(cx+18,t+399),(cx+26,t+510),(cx+39,t+565),
              (cx+48,t+610),(cx+91,t+610),(cx+88,t+560),(cx+91,t+505)])
    # Pies
    elipse((cx-100,t+590,cx-35,t+632)); elipse((cx+35,t+590,cx+100,t+632))
    mascara = mascara.resize((w, h), Image.Resampling.LANCZOS)
    # Sombra proyectada para separar el cuerpo del fondo
    sombra = Image.new("RGBA", (w, h), (0,0,0,0))
    sombra_alpha = mascara.filter(ImageFilter.GaussianBlur(17))
    sombra_layer = Image.new("RGBA", (w, h), (0,0,0,0))
    sombra_layer.putalpha(sombra_alpha.point(lambda a: int(a*0.42)))
    sombra.alpha_composite(sombra_layer, (9, 13))
    imagen_rgba = imagen.convert("RGBA")
    imagen_rgba.alpha_composite(sombra)
    # Degradado horizontal/vertical: lado izquierdo iluminado, lateral derecho en sombra.
    grad = Image.new("RGBA", (w, h), (0,0,0,0))
    gd = ImageDraw.Draw(grad)
    base = (48, 125, 158)
    for x in range(cx-205, cx+206):
        rel = (x-(cx-205))/410
        luz = max(0.0, 1.0-abs(rel-0.28)*1.65)
        shade = max(0.0, (rel-0.60)/0.40)
        r = int(base[0] + 42*luz - 23*shade)
        g = int(base[1] + 65*luz - 42*shade)
        b = int(base[2] + 62*luz - 34*shade)
        gd.line((x, t-5, x, min(h-1,t+650)), fill=(max(0,r),max(0,g),max(0,b),255))
    grad.putalpha(mascara)
    imagen_rgba.alpha_composite(grad)
    # Detalles anatómicos discretos: clavículas, pectorales, abdomen y grupos musculares.
    detalle = Image.new("RGBA", (w, h), (0,0,0,0))
    dd = ImageDraw.Draw(detalle)
    yy = lambda v: int(t + (v-t)*0.83)
    tono_luz = (190, 235, 240, 75)
    tono_sombra = (8, 48, 76, 85)
    dd.arc((cx-78,yy(t+128),cx+78,yy(t+198)), 195, 345, fill=tono_luz, width=4)
    dd.arc((cx-78,yy(t+150),cx+78,yy(t+235)), 18, 162, fill=tono_sombra, width=4)
    dd.line((cx-27,yy(t+225),cx,yy(t+235),cx+27,yy(t+225)), fill=tono_luz, width=3)
    for dy in (255, 286, 317):
        dd.arc((cx-38,yy(t+dy-16),cx+38,yy(t+dy+17)), 8, 172, fill=tono_sombra, width=3)
    dd.arc((cx-65,yy(t+365),cx-8,yy(t+430)), 205, 340, fill=tono_luz, width=3)
    dd.arc((cx+8,yy(t+365),cx+65,yy(t+430)), 200, 335, fill=tono_luz, width=3)
    dd.arc((cx-87,yy(t+475),cx-28,yy(t+550)), 205, 330, fill=tono_sombra, width=3)
    dd.arc((cx+28,yy(t+475),cx+87,yy(t+550)), 210, 335, fill=tono_sombra, width=3)
    detalle.putalpha(ImageChops.multiply(detalle.getchannel("A"), mascara))
    imagen_rgba.alpha_composite(detalle)
    # Brillo suave en hombro, pecho y muslos para dar volumen 3D.
    brillo = Image.new("RGBA", (w,h), (0,0,0,0))
    bd = ImageDraw.Draw(brillo)
    bd.ellipse((cx-88,t+125,cx-8,t+290), fill=(160,225,235,55))
    bd.ellipse((cx-68,t+405,cx-30,t+565), fill=(155,220,235,42))
    bd.ellipse((cx+27,t+405,cx+65,t+565), fill=(155,220,235,28))
    brillo = brillo.filter(ImageFilter.GaussianBlur(24))
    brillo.putalpha(ImageChops.multiply(brillo.getchannel("A"), mascara))
    imagen_rgba.alpha_composite(brillo)
    # Contorno fino de luz en el borde exterior.
    borde = mascara.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.GaussianBlur(1.2))
    borde_layer = Image.new("RGBA", (w,h), (acento[0],acento[1],acento[2],0))
    borde_layer.putalpha(borde.point(lambda a: min(150, int(a*0.75))))
    imagen_rgba.alpha_composite(borde_layer)
    return imagen_rgba.convert("RGB")


def generar_imagenes_evolucion(row, anterior=None, nombre_cliente="Cliente"):
    """Retorna tres PNG basados en la evaluación actual y, si existe, la anterior."""
    plan = calcular_recomendacion_alimentaria(row)
    peso = _valor_fila(row, ["peso_kg", "peso"])
    estatura = _valor_fila(row, ["estatura_cm", "estatura"])
    imc = _valor_fila(row, ["imc"])
    grasa = _valor_fila(row, ["porcentaje_grasa", "grasa"])
    edad_meta = _valor_fila(row, ["edad_metabolica"])
    edad = _valor_fila(row, ["edad"])
    cintura = _valor_fila(row, ["cintura_cm", "cintura"])
    pecho = _valor_fila(row, ["pecho_cm", "pecho"])
    cadera = _valor_fila(row, ["cadera_cm", "cadera"])
    meta = _texto_fila(row, ["meta", "objetivo"], plan["objetivo"])
    sexo = _texto_fila(row, ["sexo"], "")
    fecha = _texto_fila(row, ["fecha_evaluacion"], datetime.today().strftime("%d-%m-%Y"))
    acento = (48, 205, 190) if "ganar" in meta.lower() or "recompos" in meta.lower() else (92, 166, 255)

    # 1. Evolución física
    img1, d1 = _crear_lienzo("EVOLUCIÓN FÍSICA", f"{nombre_cliente} · {fecha}", acento)
    # Figura humana anatómica ilustrada con volumen 3D, luz lateral y sombra suave.
    img1 = _dibujar_figura_humana_3d(img1, centro_x=450, arriba=245, acento=acento)
    d1 = ImageDraw.Draw(img1)
    d1.text((78, 815), "INDICADORES ACTUALES", font=_fuente_imagen(27, True), fill=(150, 215, 225))
    vals = [
        ("Peso", f"{peso:.1f} kg" if peso else "Sin dato"),
        ("IMC", f"{imc:.2f}" if imc else "Sin dato"),
        ("Grasa estimada", f"{grasa:.1f}%" if grasa else "Sin dato"),
        ("Cintura", f"{cintura:.1f} cm" if cintura else "Sin dato"),
        ("Pecho", f"{pecho:.1f} cm" if pecho else "Sin dato"),
        ("Edad metabólica", f"{edad_meta:.0f} años" if edad_meta else "Sin dato"),
    ]
    for i, (lab, val) in enumerate(vals):
        col, fila = i % 2, i // 2
        x = 75 + col*385
        y = 865 + fila*91
        d1.rounded_rectangle((x, y, x+350, y+76), radius=15, fill=(17, 35, 54), outline=(53, 91, 116), width=2)
        d1.text((x+16, y+8), lab, font=_fuente_imagen(19, True), fill=(165, 188, 207))
        d1.text((x+16, y+37), val, font=_fuente_imagen(27, True), fill=(245, 250, 255))
    if anterior is not None:
        p0 = _valor_fila(anterior, ["peso_kg", "peso"])
        g0 = _valor_fila(anterior, ["porcentaje_grasa", "grasa"])
        d1.text((78, 1150), f"Comparación anterior: peso {p0:.1f} kg · grasa {g0:.1f}%", font=_fuente_imagen(17), fill=(160, 205, 215))
    else:
        d1.text((78, 1150), "Esta es tu primera evaluación registrada.", font=_fuente_imagen(17), fill=(160, 205, 215))

    # 2. Nutrición
    img2, d2 = _crear_lienzo("PLAN NUTRICIONAL", f"{nombre_cliente} · {plan['objetivo']}", (95, 190, 150))
    d2.text((75, 245), f"{plan['calorias']:,} kcal / día".replace(",", "."), font=_fuente_imagen(42, True), fill=(125, 225, 175))
    d2.text((78, 305), "DISTRIBUCIÓN DIARIA DE MACRONUTRIENTES", font=_fuente_imagen(21, True), fill=(180, 200, 215))
    macros = [("PROTEÍNA", plan["proteina"], (72, 205, 170)), ("CARBOHIDRATOS", plan["carbohidratos"], (105, 170, 255)), ("GRASAS", plan["grasa"], (195, 155, 255))]
    for i, (lab, val, col) in enumerate(macros):
        y = 350 + i*105
        d2.rounded_rectangle((75, y, 825, y+76), radius=17, fill=(17, 35, 54), outline=col, width=2)
        d2.text((98, y+13), lab, font=_fuente_imagen(21, True), fill=(180, 200, 215))
        d2.text((660, y+12), f"{val} g", font=_fuente_imagen(35, True), fill=col)
    d2.text((78, 690), "REPARTO APROXIMADO POR COMIDA", font=_fuente_imagen(19, True), fill=(150, 215, 225))
    y = 735
    for comida in plan["comidas"]:
        d2.rounded_rectangle((75, y, 825, y+82), radius=15, fill=(17, 35, 54), outline=(54, 86, 110), width=1)
        d2.text((96, y+10), comida["nombre"], font=_fuente_imagen(19, True), fill=(245, 250, 255))
        detalle = f"{comida['kcal_total']} kcal · P {comida['proteina']} g · C {comida['carbohidratos']} g · G {comida['grasa']} g"
        d2.text((96, y+43), detalle, font=_fuente_imagen(18), fill=(145, 210, 190))
        y += 91
    _texto_ajustado(d2, (78, 1105), "Alimentos sugeridos: proteína magra, cereales o tubérculos, frutas y verduras. Las cifras por comida son macros estimados, no gramos exactos de cada alimento.", _fuente_imagen(14), (185, 202, 215), 740, 3, 3)

    # 3. Resumen integral
    img3, d3 = _crear_lienzo("PLAN INTEGRAL", f"{nombre_cliente} · {fecha}", (145, 165, 255))
    d3.text((78, 250), "TU OBJETIVO", font=_fuente_imagen(20, True), fill=(155, 190, 255))
    _texto_ajustado(d3, (78, 292), plan["objetivo"], _fuente_imagen(36, True), (248, 250, 255), 735, 2, 6)
    d3.rounded_rectangle((75, 405, 825, 600), radius=24, fill=(17, 35, 54), outline=(90, 120, 180), width=2)
    d3.text((105, 435), "ENERGÍA DIARIA", font=_fuente_imagen(18, True), fill=(175, 195, 220))
    d3.text((105, 475), f"{plan['calorias']:,} kcal".replace(",", "."), font=_fuente_imagen(48, True), fill=(145, 190, 255))
    _texto_ajustado(
        d3, (105, 540),
        f"Proteína {plan['proteina']} g · Carbohidratos {plan['carbohidratos']} g · Grasas {plan['grasa']} g",
        _fuente_imagen(16), (190, 205, 220), 680, 2, 2,
    )
    d3.text((78, 650), "PUNTOS DE SEGUIMIENTO", font=_fuente_imagen(20, True), fill=(155, 190, 255))
    puntos = [
        f"Peso actual: {peso:.1f} kg" if peso else "Registrar peso corporal",
        f"Grasa estimada: {grasa:.1f}%" if grasa else "Completar medidas corporales",
        f"Cintura: {cintura:.1f} cm" if cintura else "Registrar cintura",
        f"Estatura: {estatura:.0f} cm · Edad: {edad:.0f}" if estatura and edad else "Revisar datos del perfil",
    ]
    for i, punto in enumerate(puntos):
        yy = 705 + i*76
        d3.ellipse((85, yy+6, 112, yy+33), fill=(105, 205, 185))
        d3.text((135, yy), punto, font=_fuente_imagen(24), fill=(235, 242, 250))
    _texto_ajustado(d3, (78, 1045), plan["enfoque"], _fuente_imagen(17), (180, 205, 225), 740, 4, 5)
    d3.text((78, 1155), "Guía orientativa: ajustar con el entrenador y un profesional de nutrición.", font=_fuente_imagen(16), fill=(155, 175, 195))

    resultados = {}
    for nombre, imagen in [("01_Evolucion_Fisica.png", img1), ("02_Plan_Nutricional.png", img2), ("03_Plan_Integral.png", img3)]:
        buffer = io.BytesIO()
        imagen.save(buffer, format="PNG", optimize=True)
        resultados[nombre] = buffer.getvalue()
    return resultados


def mostrar_evolucion_inteligente(row, nombre_cliente="Cliente", anterior=None, clave="evolucion"):
    """Muestra tres imágenes del mismo tamaño en una fila y permite descargarlas."""
    if row is None or not hasattr(row, "get"):
        st.info("Registra una evaluación para generar las imágenes de evolución.")
        return
    try:
        imagenes = generar_imagenes_evolucion(row, anterior, nombre_cliente)
        st.markdown("---")
        titulo_ui("Evolución Inteligente", "fi-rr-gallery", 3, 25)
        st.caption("Imágenes generadas automáticamente con los resultados de la evaluación seleccionada.")
        columnas = st.columns(3, gap="small")
        etiquetas = ["Evolución física", "Plan nutricional", "Plan integral"]
        for i, ((archivo, datos), col, etiqueta) in enumerate(zip(imagenes.items(), columnas, etiquetas)):
            with col:
                st.image(datos, use_container_width=True)
                st.download_button(
                    f"⬇️ {etiqueta}", data=datos, file_name=archivo,
                    mime="image/png", use_container_width=True,
                    key=f"{clave}_png_{i}",
                )
        paquete = io.BytesIO()
        with zipfile.ZipFile(paquete, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for archivo, datos in imagenes.items():
                zf.writestr(archivo, datos)
        st.download_button(
            "📦 Descargar las 3 imágenes", data=paquete.getvalue(),
            file_name="Evolucion_Inteligente_Imagenes.zip",
            mime="application/zip", use_container_width=True,
            key=f"{clave}_zip",
        )
    except Exception as e:
        st.error(f"No fue posible generar las imágenes de evolución: {e}")


# ============================================================
# CALCULAR MÉTRICAS (CORREGIDO Y AJUSTADO MATEMÁTICAMENTE)
# ============================================================

def calcular_metricas(
    peso,
    estatura_cm,
    edad,
    sexo,
    cuello,
    cintura,
    cadera,
    meta,
):
    """Calcula IMC, % de grasa, calorías objetivo y edad metabólica estimada.

    La ecuación de densidad tipo US Navy utilizada aquí aplica sus
    coeficientes sobre medidas en centímetros. La fórmula se mantiene
    consistente con los resultados históricos esperados por la aplicación.

    La edad metabólica es solamente una estimación orientativa; no es
    una medida clínica universal.
    """
    peso = float(peso)
    estatura_cm = float(estatura_cm)
    edad = int(edad)
    cuello = float(cuello)
    cintura = float(cintura)
    cadera = float(cadera)

    if peso <= 0:
        raise ValueError("El peso debe ser mayor que cero.")
    if estatura_cm <= 0:
        raise ValueError("La estatura debe ser mayor que cero.")
    if edad <= 0:
        raise ValueError("La edad debe ser mayor que cero.")
    if cuello <= 0 or cintura <= 0 or cadera <= 0:
        raise ValueError("Cuello, cintura y cadera deben ser mayores que cero.")

    # ============================================================
    # IMC
    # ============================================================
    estatura_m = estatura_cm / 100.0
    imc = peso / (estatura_m ** 2)

    # ============================================================
    # % GRASA - ECUACIÓN TIPO US NAVY
    #
    # Estos coeficientes de densidad se aplican directamente a
    # centímetros. No convertir a pulgadas aquí.
    # ============================================================
    if sexo == "Masculino":
        circunferencia = cintura - cuello

        if circunferencia <= 0:
            raise ValueError("La cintura debe ser mayor que el cuello.")

        densidad = (
            1.0324
            - 0.19077 * math.log10(circunferencia)
            + 0.15456 * math.log10(estatura_cm)
        )

    else:
        circunferencia = cintura + cadera - cuello

        if circunferencia <= 0:
            raise ValueError(
                "La combinación cintura + cadera - cuello no es válida."
            )

        densidad = (
            1.29579
            - 0.35004 * math.log10(circunferencia)
            + 0.22100 * math.log10(estatura_cm)
        )

    pct_grasa = (495.0 / densidad) - 450.0
    pct_grasa = max(3.0, min(pct_grasa, 60.0))

    # ============================================================
    # TMB - MIFFLIN-ST JEOR
    # ============================================================
    if sexo == "Masculino":
        tmb = (
            10 * peso
            + 6.25 * estatura_cm
            - 5 * edad
            + 5
        )
    else:
        tmb = (
            10 * peso
            + 6.25 * estatura_cm
            - 5 * edad
            - 161
        )

    # ============================================================
    # MANTENIMIENTO Y CALORÍAS OBJETIVO
    # ============================================================
    mantenimiento = tmb * 1.375

    meta_normalizada = str(meta).strip().lower()
    if (
        "perder" in meta_normalizada
        or "grasa" in meta_normalizada
        or "peso" in meta_normalizada
        or "déficit" in meta_normalizada
        or "deficit" in meta_normalizada
    ):
        # Déficit moderado de referencia. Se conserva la lógica histórica
        # para los registros antiguos guardados como "Perder Grasa".
        calorias = mantenimiento - 400
    elif "ganar" in meta_normalizada or "músc" in meta_normalizada or "mus" in meta_normalizada:
        calorias = mantenimiento + 350
    else:
        # Mantenimiento y recomposición corporal.
        calorias = mantenimiento

    calorias = max(800, calorias)

    # ============================================================
    # EDAD METABÓLICA - ESTIMACIÓN ORIENTATIVA
    #
    # Se utiliza la composición corporal para obtener una TMB por
    # Katch-McArdle y luego se calcula una edad equivalente con
    # Mifflin-St Jeor. Para evitar que la diferencia entre ambas
    # ecuaciones produzca valores exagerados, el resultado se acerca
    # de forma conservadora a la edad real del cliente.
    #
    # IMPORTANTE: es un indicador orientativo, no una medición clínica.
    # ============================================================
    masa_magra = peso * (1.0 - pct_grasa / 100.0)
    tmb_composicion = 370.0 + (21.6 * masa_magra)

    if sexo == "Masculino":
        constante_sexo = 5.0
    else:
        constante_sexo = -161.0

    edad_equivalente = (
        10 * peso
        + 6.25 * estatura_cm
        + constante_sexo
        - tmb_composicion
    ) / 5.0

    # Suavizado conservador: solo el 35 % de la diferencia se refleja
    # en la edad metabólica para reducir el efecto de error acumulado
    # entre las ecuaciones de composición corporal y TMB.
    diferencia_edad = edad_equivalente - edad
    diferencia_edad = max(-10.0, min(diferencia_edad, 10.0))
    edad_metabolica = edad + (diferencia_edad * 0.35)

    edad_metabolica = int(round(edad_metabolica))
    edad_metabolica = max(18, min(edad_metabolica, 80))

    return (
        round(imc, 2),
        round(pct_grasa, 2),
        int(round(calorias)),
        edad_metabolica,
    )


# ============================================================
# WHATSAPP
# ============================================================

def link_whatsapp(
    num_celular,
    nombre_cliente,
    mensaje=""
):
    num_limpio = (
        str(num_celular)
        .strip()
        .replace(" ", "")
        .replace("-", "")
        .replace(".", "")
    )

    if not num_limpio.startswith("57"):
        num_limpio = "57" + num_limpio

    if not mensaje:
        mensaje = (
            f"💪 ¡Hola {nombre_cliente}! "
            "Te saludamos de tu plan de "
            "Entrenamiento Personalizado. "
            "¡Queremos revisar cómo van "
            "tus avances!"
        )

    return (
        "https://wa.me/"
        f"{num_limpio}"
        "?text="
        + urllib.parse.quote(mensaje)
    )


# ============================================================
# NORMALIZAR CÉDULA
# ============================================================

def normalizar_cedula(valor):
    if pd.isna(valor):
        return ""
    return str(valor).replace(".0", "").strip()


# ============================================================
# CONVERTIR RESPUESTAS DE GOOGLE SHEETS A DATAFRAME
# ============================================================

def construir_dataframe(raw, columnas_default):
    """
    Acepta respuestas de Apps Script en cualquiera de estos formatos:
    1) Matriz: [headers, fila1, fila2, ...]
    2) Lista de diccionarios: [{...}, {...}]
    3) Diccionario con data/rows/values
    """
    if raw is None:
        return pd.DataFrame(columns=columnas_default)

    # Si Apps Script devuelve un objeto, buscar el contenedor de filas.
    if isinstance(raw, dict):
        for clave in ("data", "rows", "values", "items", "result"):
            if clave in raw and isinstance(raw[clave], (list, tuple)):
                raw = raw[clave]
                break
        else:
            # Un único registro como diccionario.
            raw = [raw]

    if not isinstance(raw, (list, tuple)) or len(raw) == 0:
        return pd.DataFrame(columns=columnas_default)

    # Lista de diccionarios.
    if isinstance(raw[0], dict):
        df = pd.DataFrame(list(raw))
        df.columns = [str(c).strip().lower() for c in df.columns]
        return df

    # Matriz de Google Sheets: primera fila = encabezados.
    if isinstance(raw[0], (list, tuple)):
        headers = [str(c).strip().lower() for c in raw[0]]
        rows = list(raw[1:])
        if not headers:
            return pd.DataFrame(columns=columnas_default)

        # Evita errores si alguna fila tiene menos/más columnas.
        ancho = len(headers)
        filas_limpias = []
        for row in rows:
            row = list(row) if isinstance(row, (list, tuple)) else [row]
            if len(row) < ancho:
                row += [""] * (ancho - len(row))
            elif len(row) > ancho:
                row = row[:ancho]
            filas_limpias.append(row)

        df = pd.DataFrame(filas_limpias, columns=headers)
        df = df.loc[:, ~df.columns.duplicated()]
        return df

    return pd.DataFrame(columns=columnas_default)


# ============================================================
# CARGAR SOLO USUARIOS PARA LOGIN / REGISTRO
# ============================================================

@st.cache_data(ttl=5)
def cargar_usuarios_login():
    """
    Consulta únicamente la hoja Usuarios mediante el endpoint
    action=usuarios. Esto evita descargar Historial, Pagos y Clases
    cada vez que alguien intenta iniciar sesión.

    Retorna: (df_usuarios, error)
    error = None si la consulta fue exitosa.
    """
    try:
        respuesta = api_get(
            URL_API,
            params={"action": "usuarios"},
            timeout=15,
        )
        respuesta.raise_for_status()
        res = respuesta.json()

        if not isinstance(res, dict):
            return pd.DataFrame(), "La API no devolvió una respuesta válida."

        if str(res.get("status", "success")).lower() == "error":
            return pd.DataFrame(), str(
                res.get("message", "Error desconocido de Google Apps Script.")
            )

        usuarios_raw = res.get("usuarios", [])
        df_u = construir_dataframe(
            usuarios_raw,
            [
                "cedula",
                "nombre_completo",
                "whatsapp",
                "eps",
                "condiciones_medicas",
                "rol",
                "password",
                "fecha_registro",
            ],
        )

        if not df_u.empty and "cedula" in df_u.columns:
            df_u["cedula"] = df_u["cedula"].apply(normalizar_cedula)

        return df_u, None

    except requests.exceptions.Timeout:
        return (
            pd.DataFrame(),
            "Google Apps Script tardó demasiado en responder. Intenta nuevamente en unos segundos.",
        )
    except requests.exceptions.RequestException as e:
        return pd.DataFrame(), f"No fue posible conectar con Google Apps Script: {e}"
    except ValueError:
        return pd.DataFrame(), "Google Apps Script devolvió una respuesta que no es JSON válido."
    except Exception as e:
        return pd.DataFrame(), f"Error procesando usuarios: {e}"


# ============================================================
# CARGAR BASE DE DATOS COMPLETA
# ============================================================

@st.cache_data(ttl=20)
def cargar_bd():
    try:
        respuesta = api_get(
            URL_API,
            timeout=30
        )
        respuesta.raise_for_status()
        res = respuesta.json()

        # ====================================================
        # USUARIOS
        # ====================================================
        usuarios_raw = res.get("usuarios", [])
        df_u = construir_dataframe(
            usuarios_raw,
            [
                "cedula",
                "nombre_completo",
                "whatsapp",
                "eps",
                "condiciones_medicas",
                "rol",
                "password",
                "fecha_registro",
            ],
        )

        # ====================================================
        # HISTORIAL DE MEDIDAS
        # ====================================================
        historial_raw = res.get("historial", [])
        df_m = construir_dataframe(
            historial_raw,
            ['id_registro', 'fecha_evaluacion', 'cedula', 'edad', 'sexo', 'meta', 'peso_kg', 'estatura_cm', 'cuello_cm', 'hombros_cm', 'bicep_der_cm', 'bicep_izq_cm', 'pecho_cm', 'cintura_cm', 'cadera_cm', 'pierna_der_cm', 'pierna_izq_cm', 'gemelo_der_cm', 'gemelo_izq_cm', 'imc', 'porcentaje_grasa', 'calorias_objetivo', 'edad_metabolica'],
        )

        # ====================================================
        # PAGOS
        # ====================================================
        pagos_raw = res.get("pagos", [])
        df_p = construir_dataframe(
            pagos_raw,
            ['id_pago', 'cedula', 'fecha_pago', 'valor', 'concepto', 'valor_mensualidad'],
        )

        # ====================================================
        # PLANES
        # Se aprovecha la misma respuesta completa de la API para
        # evitar una segunda petición HTTP exclusiva para Planes.
        # ====================================================
        planes_raw = res.get("planes", [])
        df_planes = construir_dataframe(
            planes_raw,
            [
                "cedula",
                "nombre_completo",
                "tipo_plan",
                "fecha_inicio",
                "fecha_fin",
                "estado",
                "observaciones",
                "clases_incluidas",
                "id_plan",
            ],
        )

        # ====================================================
        # CLASES
        # ====================================================
        clases_raw = res.get("clases", [])
        df_c = construir_dataframe(
            clases_raw,
            ['id_clase', 'cedula', 'nombre_completo', 'fecha_clase', 'tipo_plan', 'periodo', 'estado', 'id_plan'],
        )

        # ====================================================
        # LIMPIAR CÉDULAS
        # ====================================================
        for dataframe in (df_u, df_m, df_p, df_planes, df_c):
            if not dataframe.empty and "cedula" in dataframe.columns:
                dataframe["cedula"] = dataframe["cedula"].apply(normalizar_cedula)

        # ====================================================
        # NUMÉRICOS DE MEDIDAS
        # ====================================================
        columnas_numericas_medidas = [
            "edad",
            "peso_kg",
            "estatura_cm",
            "cuello_cm",
            "hombros_cm",
            "bicep_der_cm",
            "bicep_izq_cm",
            "pecho_cm",
            "cintura_cm",
            "cadera_cm",
            "pierna_der_cm",
            "pierna_izq_cm",
            "gemelo_der_cm",
            "gemelo_izq_cm",
            "imc",
            "porcentaje_grasa",
            "calorias_objetivo",
            "edad_metabolica",
        ]

        for columna in columnas_numericas_medidas:
            if columna in df_m.columns:
                df_m[columna] = pd.to_numeric(df_m[columna], errors="coerce")

        # ====================================================
        # NUMÉRICOS DE PAGOS
        # ====================================================
        for columna in ["valor", "valor_mensualidad"]:
            if columna in df_p.columns:
                df_p[columna] = pd.to_numeric(df_p[columna], errors="coerce")

        # ====================================================
        # NUMÉRICOS DE PLANES Y CLASES
        # ====================================================
        if not df_planes.empty and "clases_incluidas" in df_planes.columns:
            df_planes["clases_incluidas"] = pd.to_numeric(
                df_planes["clases_incluidas"], errors="coerce"
            ).fillna(0)

        if not df_c.empty and "periodo" in df_c.columns:
            df_c["periodo"] = pd.to_numeric(df_c["periodo"], errors="coerce")

        # ====================================================
        # FECHAS
        # ====================================================
        if not df_u.empty and "fecha_registro" in df_u.columns:
            df_u["fecha_registro"] = df_u["fecha_registro"].apply(formatear_fecha)

        if not df_m.empty and "fecha_evaluacion" in df_m.columns:
            df_m["fecha_evaluacion"] = df_m["fecha_evaluacion"].apply(formatear_fecha)

        if not df_p.empty and "fecha_pago" in df_p.columns:
            df_p["fecha_pago"] = df_p["fecha_pago"].apply(formatear_fecha)

        if not df_planes.empty and "fecha_inicio" in df_planes.columns:
            df_planes["_fecha_inicio_dt"] = df_planes["fecha_inicio"].apply(parsear_fecha)
        else:
            df_planes["_fecha_inicio_dt"] = pd.NaT

        if not df_c.empty and "fecha_clase" in df_c.columns:
            df_c["fecha_clase"] = df_c["fecha_clase"].apply(formatear_fecha)

        if not df_c.empty and "fecha_registro" in df_c.columns:
            df_c["fecha_registro"] = df_c["fecha_registro"].apply(formatear_fecha)

        return (
            df_u,
            df_m,
            df_p,
            df_c,
            df_planes,
        )

    except Exception as e:
        st.error(f"Error procesando base de datos: {e}")
        return (
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame()
        )


# ============================================================
# GRÁFICOS
# ============================================================

def mostrar_resumen_metricas_evolucion(df_filtrado):
    """Muestra de forma persistente los resultados de la última evaluación."""
    if df_filtrado is None or df_filtrado.empty:
        return

    datos = df_filtrado.copy()
    if "fecha_evaluacion" in datos.columns:
        datos["_fecha_evolucion"] = datos["fecha_evaluacion"].apply(parsear_fecha)
        datos = datos.sort_values("_fecha_evolucion", na_position="first")
    actual = datos.iloc[-1]

    def numero(columnas, default=0.0):
        for columna in columnas:
            if columna in actual.index:
                try:
                    valor = float(actual[columna])
                    if pd.notna(valor):
                        return valor
                except (TypeError, ValueError):
                    continue
        return float(default)

    imc = numero(["imc"])
    grasa = numero(["porcentaje_grasa", "grasa"])
    calorias = numero(["calorias_objetivo"])
    edad_metabolica = numero(["edad_metabolica"])

    titulo_ui("Resultados de tu última evaluación", "fi-rr-chart-line-up", 3, 24)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("IMC", f"{imc:.2f}")
    c2.metric("% Grasa Estimada", f"{grasa:.2f}%")
    c3.metric("Calorías Recomendadas", f"{calorias:,.0f} kcal".replace(",", "."))
    c4.metric("Edad Metabólica", f"{edad_metabolica:.0f} años")


def mostrar_resumen_evolucion_actual(row):
    """Muestra permanentemente los resultados de la última evaluación física."""
    def numero(keys, default=0.0):
        for key in keys:
            if key in row.index:
                try:
                    valor = float(row[key])
                    if pd.notna(valor):
                        return valor
                except (TypeError, ValueError):
                    pass
        return default

    imc = numero(["imc"], 0.0)
    grasa = numero(["porcentaje_grasa", "grasa"], 0.0)
    calorias = numero(["calorias_objetivo"], 0.0)
    edad_metabolica = numero(["edad_metabolica"], 0.0)

    st.markdown("### 📊 Resultados de tu última evaluación")
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("IMC", f"{imc:.2f}")
    r2.metric("% Grasa Estimada", f"{grasa:.2f}%")
    r3.metric("Calorías Recomendadas", f"{calorias:,.0f} kcal".replace(",", "."))
    r4.metric("Edad Metabólica", f"{edad_metabolica:.0f} años")

def mostrar_graficos_evolucion(df_filtrado):
    if df_filtrado.empty:
        return

    # Las 4 métricas principales quedan visibles permanentemente en
    # cualquier pantalla que utilice el módulo de Evolución Física.
    mostrar_resumen_metricas_evolucion(df_filtrado)

    df_graficos = df_filtrado.copy()

    columnas_num = [
        "peso_kg", "porcentaje_grasa", "cintura_cm", "pecho_cm", "cadera_cm",
        "bicep_der_cm", "bicep_izq_cm", "pierna_der_cm", "pierna_izq_cm",
        "gemelo_der_cm", "gemelo_izq_cm",
    ]

    for col in columnas_num:
        if col in df_graficos.columns:
            df_graficos[col] = pd.to_numeric(df_graficos[col], errors="coerce")

    df_graficos["fecha_dt"] = pd.to_datetime(
        df_graficos["fecha_evaluacion"], format="%d-%m-%Y", errors="coerce"
    )
    if df_graficos["fecha_dt"].isna().any():
        df_graficos["fecha_dt"] = pd.to_datetime(
            df_graficos["fecha_evaluacion"], errors="coerce"
        )

    df_graficos = (
        df_graficos.dropna(subset=["fecha_dt"]).sort_values(by="fecha_dt")
    )
    if df_graficos.empty:
        st.info("No hay fechas válidas para construir las gráficas.")
        return

    df_graficos["Fecha"] = df_graficos["fecha_dt"].dt.strftime("%d-%m-%Y")

    titulo_ui("Gráficas de Evolución Temporal", "fi-rr-chart-line-up", 3, 24)

    tab1, tab2, tab3, tab4 = st.tabs([
        "Peso y Composición",
        "Perímetros Principales",
        "Extremidades Superiores",
        "Piernas y Glúteos",
    ])

    with tab1:
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.markdown("<p style='text-align:center;'>Evolución del Peso Corporal (kg)</p>", unsafe_allow_html=True)
            if "peso_kg" in df_graficos.columns:
                st.line_chart(
                    df_graficos.set_index("Fecha")[["peso_kg"]].rename(columns={"peso_kg": "Peso (kg)"})
                )
        with col_g2:
            st.markdown("<p style='text-align:center;'>Evolución del % de Grasa Corporal</p>", unsafe_allow_html=True)
            if "porcentaje_grasa" in df_graficos.columns:
                st.line_chart(
                    df_graficos.set_index("Fecha")[["porcentaje_grasa"]].rename(columns={"porcentaje_grasa": "% Grasa"})
                )

    with tab2:
        st.markdown("<p style='text-align:center;'>Evolución de Torso y Cintura (cm)</p>", unsafe_allow_html=True)
        cols, names = [], {}
        for col, name in [("cintura_cm", "Cintura"), ("pecho_cm", "Pecho"), ("cadera_cm", "Cadera / Glúteos")]:
            if col in df_graficos.columns:
                cols.append(col); names[col] = name
        if cols:
            st.line_chart(df_graficos.set_index("Fecha")[cols].rename(columns=names))
        else:
            st.info("No hay perímetros registrados.")

    with tab3:
        st.markdown("<p style='text-align:center;'>Evolución de Brazos (cm)</p>", unsafe_allow_html=True)
        cols, names = [], {}
        for col, name in [("bicep_der_cm", "Bícep Derecho"), ("bicep_izq_cm", "Bícep Izquierdo")]:
            if col in df_graficos.columns:
                cols.append(col); names[col] = name
        if cols:
            st.line_chart(df_graficos.set_index("Fecha")[cols].rename(columns=names))
        else:
            st.info("No hay medidas de brazos registradas.")

    with tab4:
        st.markdown("<p style='text-align:center;'>Comparativa de Piernas (cm)</p>", unsafe_allow_html=True)
        cols, names = [], {}
        for col, name in [("pierna_der_cm", "Pierna Derecha"), ("pierna_izq_cm", "Pierna Izquierda")]:
            if col in df_graficos.columns:
                cols.append(col); names[col] = name
        if cols:
            st.line_chart(df_graficos.set_index("Fecha")[cols].rename(columns=names))
        else:
            st.info("No hay medidas de piernas registradas.")

        st.markdown("<p style='text-align:center;'>Comparativa de Glúteos y Gemelos (cm)</p>", unsafe_allow_html=True)
        cols, names = [], {}
        for col, name in [
            ("cadera_cm", "Glúteos / Cadera"),
            ("gemelo_der_cm", "Gemelo Derecho"),
            ("gemelo_izq_cm", "Gemelo Izquierdo"),
        ]:
            if col in df_graficos.columns:
                cols.append(col); names[col] = name
        if cols:
            st.line_chart(df_graficos.set_index("Fecha")[cols].rename(columns=names))
        else:
            st.info("No hay medidas de glúteos/cadera o gemelos registradas.")



# ============================================================
# INFORME DE EVOLUCIÓN EN PDF
# ============================================================

def _numero_seguro(valor):
    try:
        if pd.isna(valor):
            return None
        return float(valor)
    except Exception:
        return None


def generar_informe_evolucion_pdf(df_historial_cliente, nombre_cliente, cedula_cliente, logo_path=None, incluir_alimentacion=False):
    """Genera un informe PDF de evolución y, opcionalmente, una guía alimentaria basada en la última evaluación."""
    try:
        from io import BytesIO
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate,
            Paragraph,
            Spacer,
            Table,
            TableStyle,
            Image as RLImage,
            PageBreak,
            KeepTogether,
        )
    except ImportError:
        raise RuntimeError(
            "Para generar el PDF debes agregar 'reportlab' a requirements.txt "
            "y volver a desplegar la aplicación."
        )

    if df_historial_cliente is None or df_historial_cliente.empty:
        raise ValueError("El cliente no tiene evaluaciones registradas para generar el informe.")

    df = df_historial_cliente.copy()
    df["_fecha_dt"] = df["fecha_evaluacion"].apply(parsear_fecha)
    df = df.sort_values("_fecha_dt", ascending=True, na_position="last").reset_index(drop=True)

    # Si hay fechas no válidas, igual conservar los registros y mostrar su texto original.
    if df.empty:
        raise ValueError("No fue posible preparar las evaluaciones del cliente.")

    inicial = df.iloc[0]
    actual = df.iloc[-1]

    def valor_fila(row, columna):
        return _numero_seguro(row[columna]) if columna in row.index else None

    def fmt_num(v, dec=1):
        if v is None:
            return "—"
        return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def fmt_cambio(v, dec=1, sufijo=""):
        if v is None:
            return "—"
        signo = "+" if v > 0 else ""
        return f"{signo}{fmt_num(v, dec)}{sufijo}"

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.35 * cm,
        leftMargin=1.35 * cm,
        topMargin=1.25 * cm,
        bottomMargin=1.25 * cm,
        title=f"Informe de Evolución - {nombre_cliente}",
        author="Julian Avila - Personal Training & Evolution Tracker",
    )

    styles = getSampleStyleSheet()
    titulo = ParagraphStyle(
        "TituloInforme", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=20, leading=23, alignment=TA_CENTER, textColor=colors.HexColor("#111111"),
        spaceAfter=5,
    )
    subtitulo = ParagraphStyle(
        "Subtitulo", parent=styles["Normal"], fontName="Helvetica",
        fontSize=10, leading=13, alignment=TA_CENTER, textColor=colors.HexColor("#555555"),
        spaceAfter=10,
    )
    h2 = ParagraphStyle(
        "H2Informe", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=13, leading=16, textColor=colors.HexColor("#111111"), spaceBefore=7, spaceAfter=7,
    )
    normal = ParagraphStyle(
        "NormalInforme", parent=styles["Normal"], fontName="Helvetica",
        fontSize=8.5, leading=11, textColor=colors.HexColor("#222222"),
    )
    small = ParagraphStyle(
        "SmallInforme", parent=normal, fontSize=7.5, leading=9.5,
    )
    # Estilo específico para encabezados de tablas.
    # Las tablas tienen fondo negro, por lo que el texto debe ser blanco.
    table_header = ParagraphStyle(
        "TableHeaderInforme", parent=small, fontName="Helvetica-Bold",
        textColor=colors.white, alignment=TA_CENTER,
    )
    note = ParagraphStyle(
        "NotaInforme", parent=normal, fontSize=7.5, leading=10,
        textColor=colors.HexColor("#555555"),
    )

    story = []

    # Logo
    if logo_path and os.path.isfile(logo_path):
        try:
            logo = RLImage(logo_path)
            max_w = 6.2 * cm
            max_h = 2.0 * cm
            ratio = min(max_w / logo.imageWidth, max_h / logo.imageHeight)
            logo.drawWidth = logo.imageWidth * ratio
            logo.drawHeight = logo.imageHeight * ratio
            logo.hAlign = "CENTER"
            story.append(logo)
            story.append(Spacer(1, 0.18 * cm))
        except Exception:
            pass

    story.append(Paragraph("INFORME DE EVOLUCIÓN FÍSICA", titulo))
    story.append(Paragraph("Personal Training & Evolution Tracker · Julian Avila", subtitulo))

    fecha_generacion = datetime.today().strftime("%d-%m-%Y %H:%M")
    info_data = [
        [Paragraph("<b>Cliente</b>", normal), Paragraph(str(nombre_cliente), normal),
         Paragraph("<b>Cédula / ID</b>", normal), Paragraph(str(cedula_cliente), normal)],
        [Paragraph("<b>Evaluación inicial</b>", normal), Paragraph(formatear_fecha(inicial.get("fecha_evaluacion", "")), normal),
         Paragraph("<b>Evaluación actual</b>", normal), Paragraph(formatear_fecha(actual.get("fecha_evaluacion", "")), normal)],
        [Paragraph("<b>Evaluaciones registradas</b>", normal), Paragraph(str(len(df)), normal),
         Paragraph("<b>Informe generado</b>", normal), Paragraph(fecha_generacion, normal)],
    ]
    info_table = Table(info_data, colWidths=[3.0*cm, 6.2*cm, 3.0*cm, 5.0*cm])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#F3F3F3")),
        ("BOX", (0,0), (-1,-1), 0.5, colors.HexColor("#BBBBBB")),
        ("INNERGRID", (0,0), (-1,-1), 0.3, colors.HexColor("#D5D5D5")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.28 * cm))

    # Resumen de indicadores principales
    story.append(Paragraph("1. Resumen de indicadores", h2))
    resumen_campos = [
        ("Peso", "peso_kg", "kg", 1),
        ("% Grasa corporal", "porcentaje_grasa", "%", 2),
        ("IMC", "imc", "", 2),
        ("Calorías objetivo", "calorias_objetivo", "kcal", 0),
        ("Edad metabólica estimada", "edad_metabolica", "años", 0),
    ]
    resumen_data = [[
        Paragraph("Indicador", table_header), Paragraph("Inicial", table_header),
        Paragraph("Actual", table_header), Paragraph("Cambio", table_header)
    ]]
    for etiqueta, campo, sufijo, dec in resumen_campos:
        vi = valor_fila(inicial, campo)
        va = valor_fila(actual, campo)
        cambio = (va - vi) if vi is not None and va is not None else None
        resumen_data.append([
            Paragraph(etiqueta, small),
            Paragraph((fmt_num(vi, dec) + (" " + sufijo if sufijo else "")), small),
            Paragraph((fmt_num(va, dec) + (" " + sufijo if sufijo else "")), small),
            Paragraph((fmt_cambio(cambio, dec, (" " + sufijo if sufijo else ""))), small),
        ])
    resumen_table = Table(resumen_data, colWidths=[6.0*cm, 3.4*cm, 3.4*cm, 4.4*cm], repeatRows=1)
    resumen_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#171717")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#CCCCCC")),
        ("BACKGROUND", (0,1), (-1,-1), colors.white),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F7F7F7")]),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(resumen_table)
    story.append(Spacer(1, 0.18 * cm))
    story.append(Paragraph(
        "Los cambios se muestran de forma descriptiva entre la primera y la última evaluación registrada. "
        "La interpretación debe considerar el objetivo individual y el contexto de cada evaluación.", note
    ))
    story.append(Paragraph(
        "La edad metabólica es un indicador estimado y orientativo calculado a partir de ecuaciones antropométricas y de metabolismo basal. "
        "No constituye una medición clínica ni debe interpretarse de forma aislada.", note
    ))

    # Tabla antropométrica completa
    story.append(Paragraph("2. Comparativa antropométrica completa", h2))
    antropometricos = [
        ("Cuello", "cuello_cm"),
        ("Hombros", "hombros_cm"),
        ("Pecho", "pecho_cm"),
        ("Cintura / Abdomen", "cintura_cm"),
        ("Cadera / Glúteos", "cadera_cm"),
        ("Bíceps Derecho", "bicep_der_cm"),
        ("Bíceps Izquierdo", "bicep_izq_cm"),
        ("Pierna Derecha", "pierna_der_cm"),
        ("Pierna Izquierda", "pierna_izq_cm"),
        ("Gemelo Derecho", "gemelo_der_cm"),
        ("Gemelo Izquierdo", "gemelo_izq_cm"),
    ]
    ant_data = [[
        Paragraph("Medida", table_header), Paragraph("Inicial (cm)", table_header),
        Paragraph("Actual (cm)", table_header), Paragraph("Cambio (cm)", table_header)
    ]]
    for etiqueta, campo in antropometricos:
        vi = valor_fila(inicial, campo)
        va = valor_fila(actual, campo)
        cambio = (va - vi) if vi is not None and va is not None else None
        ant_data.append([
            Paragraph(etiqueta, small),
            Paragraph(fmt_num(vi, 1), small),
            Paragraph(fmt_num(va, 1), small),
            Paragraph(fmt_cambio(cambio, 1), small),
        ])
    ant_table = Table(ant_data, colWidths=[7.0*cm, 3.1*cm, 3.1*cm, 4.0*cm], repeatRows=1)
    ant_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#171717")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#CCCCCC")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F7F7F7")]),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(ant_table)

    # Guía de alimentación opcional: toma automáticamente el objetivo y datos
    # de la última evaluación guardada; nunca solicita elegir perder grasa/ganar músculo.
    if incluir_alimentacion:
        try:
            plan_alimentario = calcular_recomendacion_alimentaria(actual)
            story.append(PageBreak())
            story.append(Paragraph("GUÍA DE ALIMENTACIÓN ORIENTATIVA", titulo))
            story.append(Paragraph(
                "Generada automáticamente con los datos y el objetivo registrados en la última evaluación.",
                subtitulo,
            ))
            story.append(Paragraph(f"Objetivo registrado: {plan_alimentario['objetivo']}", h2))
            story.append(Paragraph(plan_alimentario["enfoque"], normal))
            story.append(Spacer(1, 0.18 * cm))

            macros_data = [
                [Paragraph("Energía diaria", table_header), Paragraph("Proteína", table_header),
                 Paragraph("Carbohidratos", table_header), Paragraph("Grasas", table_header)],
                [Paragraph(f"{plan_alimentario['calorias']} kcal", normal),
                 Paragraph(f"{plan_alimentario['proteina']} g", normal),
                 Paragraph(f"{plan_alimentario['carbohidratos']} g", normal),
                 Paragraph(f"{plan_alimentario['grasa']} g", normal)],
            ]
            macros_table = Table(macros_data, colWidths=[4.1*cm, 4.1*cm, 4.1*cm, 4.1*cm])
            macros_table.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#171717")),
                ("BACKGROUND", (0,1), (-1,1), colors.HexColor("#F3F3F3")),
                ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#CCCCCC")),
                ("ALIGN", (0,0), (-1,-1), "CENTER"),
                ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                ("TOPPADDING", (0,0), (-1,-1), 8),
                ("BOTTOMPADDING", (0,0), (-1,-1), 8),
            ]))
            story.append(macros_table)
            story.append(Spacer(1, 0.35 * cm))
            story.append(Paragraph("Distribución sugerida por comida", h2))

            for comida in plan_alimentario["comidas"]:
                comida_data = [
                    [Paragraph(f"<b>{comida['nombre']}</b> · aproximadamente {comida['kcal_total']} kcal", normal)],
                    [Paragraph(
                        f"Proteína: {comida['proteina']} g · Carbohidratos: {comida['carbohidratos']} g · "
                        f"Grasas: {comida['grasa']} g", small)],
                    [Paragraph(f"<b>Ideas de alimentos:</b> {comida['alimentos']}", normal)],
                ]
                comida_table = Table(comida_data, colWidths=[16.4*cm])
                comida_table.setStyle(TableStyle([
                    ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#F7F7F7")),
                    ("BOX", (0,0), (-1,-1), 0.5, colors.HexColor("#D5D5D5")),
                    ("LINEBELOW", (0,0), (-1,0), 0.4, colors.HexColor("#B8B8B8")),
                    ("LEFTPADDING", (0,0), (-1,-1), 8),
                    ("RIGHTPADDING", (0,0), (-1,-1), 8),
                    ("TOPPADDING", (0,0), (-1,-1), 5),
                    ("BOTTOMPADDING", (0,0), (-1,-1), 5),
                ]))
                story.append(KeepTogether([comida_table, Spacer(1, 0.18*cm)]))

            story.append(Spacer(1, 0.15*cm))
            story.append(Paragraph(
                "Importante: esta guía es orientativa. Los macronutrientes por comida son aproximados y no equivalen "
                "a gramos de cada alimento. Ajusta las porciones a preferencias, alergias y necesidades personales; "
                "no sustituye una valoración individual de nutrición.", note
            ))
        except Exception as exc:
            raise ValueError(f"No se pudo generar la guía alimentaria con los datos guardados: {exc}")

    # Historial completo de evaluaciones
    story.append(PageBreak())
    story.append(Paragraph("3. Historial de evaluaciones", h2))
    historia_campos = [
        ("Fecha", "fecha_evaluacion"),
        ("Peso (kg)", "peso_kg"),
        ("% Grasa", "porcentaje_grasa"),
        ("IMC", "imc"),
        ("Cintura (cm)", "cintura_cm"),
        ("Cadera (cm)", "cadera_cm"),
        ("Pierna D (cm)", "pierna_der_cm"),
        ("Pierna I (cm)", "pierna_izq_cm"),
        ("Gemelo D (cm)", "gemelo_der_cm"),
        ("Gemelo I (cm)", "gemelo_izq_cm"),
    ]
    hist_data = [[Paragraph(x[0], table_header) for x in historia_campos]]
    for _, row in df.iterrows():
        fila = []
        for etiqueta, campo in historia_campos:
            if campo == "fecha_evaluacion":
                valor = formatear_fecha(row.get(campo, ""))
            else:
                n = valor_fila(row, campo)
                valor = fmt_num(n, 1) if n is not None else "—"
            fila.append(Paragraph(str(valor), small))
        hist_data.append(fila)
    hist_widths = [2.2*cm, 1.7*cm, 1.7*cm, 1.6*cm, 1.8*cm, 1.8*cm, 1.8*cm, 1.8*cm, 1.8*cm, 1.8*cm]
    hist_table = Table(hist_data, colWidths=hist_widths, repeatRows=1)
    hist_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#171717")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), 0.3, colors.HexColor("#CCCCCC")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F7F7F7")]),
        ("ALIGN", (1,1), (-1,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 3),
        ("RIGHTPADDING", (0,0), (-1,-1), 3),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(hist_table)

    # Datos complementarios de las evaluaciones
    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph("4. Datos complementarios", h2))
    comp_data = [[
        Paragraph("Fecha", table_header), Paragraph("Edad", table_header), Paragraph("Sexo", table_header),
        Paragraph("Meta", table_header), Paragraph("Calorías", table_header), Paragraph("Edad metabólica", table_header)
    ]]
    for _, row in df.iterrows():
        comp_data.append([
            Paragraph(formatear_fecha(row.get("fecha_evaluacion", "")), small),
            Paragraph(fmt_num(valor_fila(row, "edad"), 0), small),
            Paragraph(str(row.get("sexo", "—")), small),
            Paragraph(str(row.get("meta", "—")), small),
            Paragraph(fmt_num(valor_fila(row, "calorias_objetivo"), 0), small),
            Paragraph(fmt_num(valor_fila(row, "edad_metabolica"), 0), small),
        ])
    comp_table = Table(comp_data, colWidths=[2.3*cm, 1.6*cm, 2.4*cm, 4.0*cm, 2.3*cm, 3.2*cm], repeatRows=1)
    comp_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#171717")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), 0.3, colors.HexColor("#CCCCCC")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F7F7F7")]),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(comp_table)

    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(
        "Nota: IMC, porcentaje de grasa, calorías objetivo y edad metabólica son cálculos/estimaciones "
        "generados por la aplicación a partir de los datos registrados. Este informe es de seguimiento "
        "deportivo y no sustituye una valoración médica o clínica.", note
    ))

    def pie_pagina(canvas, doc_obj):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#DDDDDD"))
        canvas.line(1.35*cm, 0.9*cm, A4[0]-1.35*cm, 0.9*cm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(1.35*cm, 0.55*cm, "Julian Avila · Personal Training & Evolution Tracker")
        canvas.drawRightString(A4[0]-1.35*cm, 0.55*cm, f"Página {doc_obj.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=pie_pagina, onLaterPages=pie_pagina)
    buffer.seek(0)
    return buffer.getvalue()


def cargar_solo_planes():
    """
    Reutiliza la hoja Planes que ya viene en la respuesta completa de la API.
    Evita una petición HTTP adicional y comparte la misma caché de cargar_bd.
    """
    try:
        datos = cargar_bd()
        if isinstance(datos, (tuple, list)) and len(datos) >= 5:
            return datos[4]
        return pd.DataFrame()
    except Exception:
        # El resumen de clases no debe tumbar toda la aplicación si Planes
        # no responde temporalmente.
        return pd.DataFrame()


def obtener_resumen_clases(df_clases, cedula):
    """
    Obtiene el último plan activo del cliente y cuenta sus clases.

    Compatible con la estructura actual de Google Sheets:
    Planes: 8 columnas, sin id_plan.
    Clases: 7 columnas, sin id_plan.

    Si existe id_plan en una versión futura de la hoja, también lo utiliza.
    """
    resultado = {
        "plan": "Sin plan registrado",
        "id_plan": "",
        "fecha_inicio": pd.NaT,
        "clases_contratadas": 0,
        "clases_tomadas": 0,
        "clases_restantes": 0,
        "porcentaje": 0.0,
        "registros": pd.DataFrame(),
    }

    cedula_str = normalizar_cedula(cedula)
    if not cedula_str:
        return resultado

    # ------------------------------------------------------------
    # 1. Obtener el último plan ACTIVO del cliente
    # ------------------------------------------------------------
    df_planes = cargar_solo_planes()

    if not df_planes.empty and "cedula" in df_planes.columns:
        planes = df_planes.copy()
        planes["_cedula_norm"] = planes["cedula"].apply(normalizar_cedula)

        if "estado" not in planes.columns:
            planes["estado"] = "Activo"

        activos = planes[
            (planes["_cedula_norm"] == cedula_str)
            & (
                planes["estado"]
                .astype(str)
                .str.strip()
                .str.lower()
                .isin(["activo", "activa"])
            )
        ].copy()

        if not activos.empty:
            if "_fecha_inicio_dt" not in activos.columns:
                activos["_fecha_inicio_dt"] = activos["fecha_inicio"].apply(parsear_fecha)

            activos = activos.sort_values(
                by="_fecha_inicio_dt",
                ascending=True,
                na_position="first",
            )
            plan_activo = activos.iloc[-1]

            resultado["plan"] = str(plan_activo.get("tipo_plan", "")).strip()
            resultado["id_plan"] = str(plan_activo.get("id_plan", "")).strip()
            resultado["fecha_inicio"] = parsear_fecha(plan_activo.get("fecha_inicio"))

            try:
                resultado["clases_contratadas"] = int(
                    float(
                        pd.to_numeric(
                            plan_activo.get("clases_incluidas", 0),
                            errors="coerce",
                        )
                    )
                )
            except Exception:
                resultado["clases_contratadas"] = 0

    # ------------------------------------------------------------
    # 2. Filtrar clases del cliente
    # ------------------------------------------------------------
    if df_clases is not None and not df_clases.empty and "cedula" in df_clases.columns:
        clases = df_clases.copy()
        clases["_cedula_norm"] = clases["cedula"].apply(normalizar_cedula)

        if "estado" not in clases.columns:
            clases["estado"] = "Tomada"

        registros = clases[
            (clases["_cedula_norm"] == cedula_str)
            & (
                clases["estado"]
                .astype(str)
                .str.strip()
                .str.lower()
                == "tomada"
            )
        ].copy()

        # --------------------------------------------------------
        # 3. Asociar las clases al ciclo actual.
        #    - Si hay id_plan en ambas tablas, usarlo.
        #    - Si no existe (estructura actual), usar fecha_inicio.
        # --------------------------------------------------------
        id_plan_actual = resultado["id_plan"]

        ids_clase = (
            registros["id_plan"].fillna("").astype(str).str.strip()
            if "id_plan" in registros.columns else pd.Series(dtype=str)
        )
        hay_ids_plan_en_clases = bool((ids_clase != "").any())
        if id_plan_actual and hay_ids_plan_en_clases:
            registros["_id_plan_norm"] = ids_clase
            registros = registros[registros["_id_plan_norm"] == id_plan_actual].copy()
            registros = registros.drop(columns=["_id_plan_norm"], errors="ignore")

        elif not pd.isna(resultado["fecha_inicio"]) and "fecha_clase" in registros.columns:
            registros["_fecha_clase_dt"] = registros["fecha_clase"].apply(parsear_fecha)
            registros = registros[
                registros["_fecha_clase_dt"].notna()
                & (registros["_fecha_clase_dt"] >= resultado["fecha_inicio"])
            ].copy()
            registros = registros.drop(columns=["_fecha_clase_dt"], errors="ignore")

        elif id_plan_actual:
            # Hay ID de plan, pero las clases no lo traen: no mezclar históricos.
            registros = registros.iloc[0:0].copy()

        resultado["clases_tomadas"] = len(registros)
        resultado["registros"] = registros.drop(
            columns=["_cedula_norm"],
            errors="ignore",
        )

    # ------------------------------------------------------------
    # 4. Totales
    # ------------------------------------------------------------
    resultado["clases_restantes"] = max(
        resultado["clases_contratadas"] - resultado["clases_tomadas"],
        0,
    )

    if resultado["clases_contratadas"] > 0:
        resultado["porcentaje"] = min(
            (
                resultado["clases_tomadas"]
                / resultado["clases_contratadas"]
            )
            * 100,
            100,
        )

    return resultado


# ============================================================
# MOSTRAR RESUMEN DE CLASES
# ============================================================

def mostrar_resumen_clases(
    df_clases,
    cedula,
    titulo="Clases Personalizadas"
):
    resumen = obtener_resumen_clases(df_clases, cedula)

    titulo_ui(titulo, "fi-rr-dumbbell", 3, 24)

    if resumen["clases_contratadas"] <= 0:
        st.info("Este cliente todavía no tiene un plan de clases configurado.")
        return

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Plan", resumen["plan"])
    c2.metric("Clases contratadas", resumen["clases_contratadas"])
    c3.metric("Clases tomadas", resumen["clases_tomadas"])
    c4.metric("Clases restantes", resumen["clases_restantes"])

    porcentaje = float(resumen["porcentaje"])
    if porcentaje < 50:
        p_start, p_mid, p_end, p_glow = "#38bdf8", "#22d3ee", "#34d399", "#22d3ee"
    elif porcentaje < 80:
        p_start, p_mid, p_end, p_glow = "#22d3ee", "#a78bfa", "#fbbf24", "#a78bfa"
    else:
        p_start, p_mid, p_end, p_glow = "#fbbf24", "#fb7185", "#ef4444", "#fb7185"

    porcentaje_seguro = max(0.0, min(porcentaje, 100.0))
    st.markdown(
        f"""
        <div class="wow-progress-wrap">
            <div class="wow-progress-head">
                <span class="wow-progress-label">Progreso del plan · {resumen['clases_tomadas']} de {resumen['clases_contratadas']} clases</span>
                <span class="wow-progress-value">{porcentaje:.1f}%</span>
            </div>
            <div class="wow-progress-track" role="progressbar" aria-valuenow="{porcentaje_seguro:.1f}" aria-valuemin="0" aria-valuemax="100">
                <div class="wow-progress-fill" style="--progress-width:{porcentaje_seguro:.2f}%; --progress-start:{p_start}; --progress-mid:{p_mid}; --progress-end:{p_end}; --progress-glow:{p_glow};"></div>
            </div>
            <div class="wow-progress-scale"><span>0 clases</span><span>{resumen['clases_restantes']} restantes</span><span>Plan completo</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# ESTADO DE SESIÓN
# ============================================================

# ============================================================
# DASHBOARD ADMINISTRADOR - CAPA VISUAL
# ============================================================
def mostrar_dashboard_admin(df_usuarios, df_historial, df_pagos, df_clases):
    clientes = df_usuarios.copy() if not df_usuarios.empty else pd.DataFrame()
    if not clientes.empty and "rol" in clientes.columns:
        clientes = clientes[clientes["rol"].astype(str).str.lower() == "cliente"].copy()

    total_clientes = len(clientes)
    total_clases = len(df_clases) if not df_clases.empty else 0
    clases_tomadas = 0
    if not df_clases.empty and "estado" in df_clases.columns:
        clases_tomadas = int((df_clases["estado"].astype(str).str.lower() == "tomada").sum())

    total_ingresos = 0.0
    if not df_pagos.empty and "valor" in df_pagos.columns:
        total_ingresos = pd.to_numeric(df_pagos["valor"], errors="coerce").fillna(0).sum()

    ultima_evaluacion = "Sin registros"
    if not df_historial.empty and "fecha_evaluacion" in df_historial.columns:
        fechas = pd.to_datetime(df_historial["fecha_evaluacion"], errors="coerce")
        if fechas.notna().any():
            ultima_evaluacion = fechas.max().strftime("%d-%m-%Y")

    st.markdown(
        '<div class="dashboard-hero">'
        '<div class="dashboard-glow"></div>'
        '<div class="dashboard-kicker">PERSONAL TRAINING · CONTROL CENTER</div>'
        '<div class="dashboard-title">Dashboard General</div>'
        '<div class="dashboard-subtitle">Visión rápida de clientes, clases, ingresos y evolución.</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Clientes", f"{total_clientes:,}")
    c2.metric("Clases tomadas", f"{clases_tomadas:,}")
    c3.metric("Ingresos registrados", f"${total_ingresos:,.0f}")
    c4.metric("Última evaluación", ultima_evaluacion)

    st.markdown('<div class="dashboard-section-title">Actividad de la plataforma</div>', unsafe_allow_html=True)
    left, right = st.columns([1.15, 0.85])

    with left:
        if not df_clases.empty and "fecha_clase" in df_clases.columns:
            actividad = df_clases.copy()
            actividad["fecha"] = pd.to_datetime(actividad["fecha_clase"], errors="coerce")
            actividad = actividad.dropna(subset=["fecha"])
            if not actividad.empty:
                actividad = actividad.groupby(actividad["fecha"].dt.strftime("%d-%m"), sort=False).size().tail(14)
                st.markdown('<div class="glass-panel-title">Clases por día</div>', unsafe_allow_html=True)
                st.line_chart(actividad, use_container_width=True)
            else:
                st.info("Aún no hay fechas de clases para mostrar.")
        else:
            st.info("Aún no hay clases registradas.")

    with right:
        if not df_pagos.empty and "valor" in df_pagos.columns:
            pagos = df_pagos.copy()
            pagos["valor_num"] = pd.to_numeric(pagos["valor"], errors="coerce").fillna(0)
            if "fecha_pago" in pagos.columns:
                pagos["fecha"] = pd.to_datetime(pagos["fecha_pago"], errors="coerce")
                pagos = pagos.dropna(subset=["fecha"])
                if not pagos.empty:
                    resumen = pagos.groupby(pagos["fecha"].dt.strftime("%b")).agg(Ingresos=("valor_num", "sum"))
                    st.markdown('<div class="glass-panel-title">Ingresos registrados</div>', unsafe_allow_html=True)
                    st.bar_chart(resumen, use_container_width=True)
                else:
                    st.metric("Total histórico", f"${total_ingresos:,.0f}")
            else:
                st.metric("Total histórico", f"${total_ingresos:,.0f}")
        else:
            st.info("Aún no hay pagos registrados.")

    st.markdown('<div class="dashboard-section-title">Resumen operativo</div>', unsafe_allow_html=True)
    r1, r2, r3 = st.columns(3)

    with r1:
        st.markdown(
            f'<div class="dashboard-card"><div class="dash-icon">👥</div>'
            f'<div class="dash-label">Clientes registrados</div><div class="dash-value">{total_clientes}</div>'
            f'<div class="dash-note">Usuarios con rol Cliente</div></div>',
            unsafe_allow_html=True,
        )
    with r2:
        st.markdown(
            f'<div class="dashboard-card"><div class="dash-icon">🏋️</div>'
            f'<div class="dash-label">Clases registradas</div><div class="dash-value">{total_clases}</div>'
            f'<div class="dash-note">Incluye historial de clases</div></div>',
            unsafe_allow_html=True,
        )
    with r3:
        st.markdown(
            f'<div class="dashboard-card"><div class="dash-icon">💳</div>'
            f'<div class="dash-label">Movimientos de pago</div><div class="dash-value">{len(df_pagos) if not df_pagos.empty else 0}</div>'
            f'<div class="dash-note">Ingresos registrados en sistema</div></div>',
            unsafe_allow_html=True,
        )


if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
    st.session_state["rol"] = None
    st.session_state["cedula"] = None
    st.session_state["nombre"] = None


# ============================================================
# TARIFARIO DEL ADMINISTRADOR
# ============================================================

ARCHIVO_TARIFARIO = os.path.join(BASE_DIR, "tarifario_personal_training.json")

TARIFAS_INICIALES = [
    {"Modalidad": "Individual", "Plan": "1 clase", "Sesiones": 1, "Precio COP": 33000, "Frecuencia semanal": "Variable", "Estado": "Activo", "Observaciones": "Sesión individual"},
    {"Modalidad": "Individual", "Plan": "Paquete 4 clases", "Sesiones": 4, "Precio COP": 130000, "Frecuencia semanal": "Variable", "Estado": "Activo", "Observaciones": "Paquete de 4 sesiones"},
    {"Modalidad": "Individual", "Plan": "Paquete 8 clases", "Sesiones": 8, "Precio COP": 260000, "Frecuencia semanal": "Variable", "Estado": "Activo", "Observaciones": "Paquete de 8 sesiones"},
    {"Modalidad": "Individual", "Plan": "Paquete 12 clases", "Sesiones": 12, "Precio COP": 400000, "Frecuencia semanal": "Variable", "Estado": "Activo", "Observaciones": "Paquete de 12 sesiones"},
    {"Modalidad": "Individual", "Plan": "Paquete 20 clases", "Sesiones": 20, "Precio COP": 520000, "Frecuencia semanal": "Variable", "Estado": "Activo", "Observaciones": "Paquete de 20 sesiones"},
    {"Modalidad": "Individual", "Plan": "Paquete 30 clases", "Sesiones": 30, "Precio COP": 750000, "Frecuencia semanal": "Variable", "Estado": "Activo", "Observaciones": "Paquete de 30 sesiones"},
    {"Modalidad": "Pareja", "Plan": "Pareja 12 clases", "Sesiones": 12, "Precio COP": 650000, "Frecuencia semanal": "Variable", "Estado": "Activo", "Observaciones": "Precio total por pareja"},
    {"Modalidad": "Pareja", "Plan": "Pareja 20 clases", "Sesiones": 20, "Precio COP": 1000000, "Frecuencia semanal": "Variable", "Estado": "Activo", "Observaciones": "Precio total por pareja"},
    {"Modalidad": "Individual", "Plan": "Mensualidad personalizada", "Sesiones": 0, "Precio COP": 0, "Frecuencia semanal": "Variable", "Estado": "Por definir", "Observaciones": "Precio y sesiones mensuales por definir"},
    {"Modalidad": "Pareja", "Plan": "Mensualidad para pareja", "Sesiones": 0, "Precio COP": 0, "Frecuencia semanal": "Variable", "Estado": "Por definir", "Observaciones": "Precio y sesiones mensuales por definir"},
]


def cargar_tarifario_local():
    """Lee las tarifas del archivo de configuración; si no existe, usa la tabla inicial."""
    try:
        if os.path.isfile(ARCHIVO_TARIFARIO):
            with open(ARCHIVO_TARIFARIO, "r", encoding="utf-8") as archivo:
                datos = json.load(archivo)
            if isinstance(datos, list) and datos:
                return pd.DataFrame(datos)
    except Exception:
        pass
    return pd.DataFrame(TARIFAS_INICIALES)


def guardar_tarifario_local(df_tarifas):
    """Guarda la tabla de tarifas en JSON sin tocar planes ni pagos de clientes."""
    columnas = ["Modalidad", "Plan", "Sesiones", "Precio COP", "Frecuencia semanal", "Estado", "Observaciones"]
    datos = df_tarifas.copy()
    for columna in columnas:
        if columna not in datos.columns:
            datos[columna] = ""
    datos = datos[columnas].fillna("")
    datos["Sesiones"] = pd.to_numeric(datos["Sesiones"], errors="coerce").fillna(0).astype(int)
    datos["Precio COP"] = pd.to_numeric(datos["Precio COP"], errors="coerce").fillna(0).clip(lower=0).round(0).astype(int)
    with open(ARCHIVO_TARIFARIO, "w", encoding="utf-8") as archivo:
        json.dump(datos.to_dict(orient="records"), archivo, ensure_ascii=False, indent=2)


def mostrar_modulo_tarifario():
    st.markdown("## 💰 Tarifario y planes")
    st.caption("Módulo privado del administrador. Edita los planes y sus precios sin modificar los pagos ni las contrataciones ya registradas.")
    df_tarifas = cargar_tarifario_local()

    # Garantiza que nuevas columnas existan si el archivo fue creado con una versión anterior.
    columnas = ["Modalidad", "Plan", "Sesiones", "Precio COP", "Frecuencia semanal", "Estado", "Observaciones"]
    for columna in columnas:
        if columna not in df_tarifas.columns:
            df_tarifas[columna] = ""
    df_tarifas = df_tarifas[columnas]

    if "Precio COP" in df_tarifas:
        total_activos = int((df_tarifas["Estado"].astype(str).str.lower() == "activo").sum())
        precios_definidos = pd.to_numeric(df_tarifas["Precio COP"], errors="coerce").fillna(0)
        c1, c2, c3 = st.columns(3)
        c1.metric("Planes configurados", len(df_tarifas))
        c2.metric("Planes activos", total_activos)
        c3.metric("Tarifas con precio", int((precios_definidos > 0).sum()))

    st.info("Las mensualidades individual y de pareja quedan creadas como 'Por definir'. Puedes completarlas cuando decidas el precio y las sesiones incluidas.")
    editado = st.data_editor(
        df_tarifas,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "Modalidad": st.column_config.SelectboxColumn("Modalidad", options=["Individual", "Pareja", "Grupo"], required=True),
            "Plan": st.column_config.TextColumn("Nombre del plan", required=True),
            "Sesiones": st.column_config.NumberColumn("Sesiones incluidas", min_value=0, step=1, format="%d"),
            "Precio COP": st.column_config.NumberColumn("Precio total (COP)", min_value=0, step=1000, format="$ %d"),
            "Frecuencia semanal": st.column_config.SelectboxColumn("Frecuencia semanal", options=["Variable", "1 día/semana", "2 días/semana", "3 días/semana", "4 días/semana", "5 días/semana"], required=True),
            "Estado": st.column_config.SelectboxColumn("Estado", options=["Activo", "Inactivo", "Por definir"], required=True),
            "Observaciones": st.column_config.TextColumn("Condiciones / observaciones"),
        },
        key="editor_tarifario_admin",
    )

    vista = editado.copy()
    vista["Sesiones"] = pd.to_numeric(vista["Sesiones"], errors="coerce").fillna(0)
    vista["Precio COP"] = pd.to_numeric(vista["Precio COP"], errors="coerce").fillna(0)
    vista["Valor por sesión (COP)"] = vista.apply(
        lambda fila: round(float(fila["Precio COP"]) / float(fila["Sesiones"])) if float(fila["Sesiones"]) > 0 else 0,
        axis=1,
    )
    st.markdown("### Vista previa para cotizar")
    vista_activa = vista[vista["Estado"].astype(str).str.lower() == "activo"].copy()
    if not vista_activa.empty:
        vista_activa["Precio total"] = vista_activa["Precio COP"].map(lambda v: "$" + f"{int(v):,}".replace(",", "."))
        vista_activa["Valor por sesión"] = vista_activa["Valor por sesión (COP)"].map(lambda v: "$" + f"{int(v):,}".replace(",", ".") if v else "Por definir")
        st.dataframe(vista_activa[["Modalidad", "Plan", "Sesiones", "Precio total", "Valor por sesión", "Frecuencia semanal"]], use_container_width=True, hide_index=True)
    else:
        st.warning("No hay planes activos para mostrar en la vista de cotización.")

    col_guardar, col_descargar = st.columns(2)
    with col_guardar:
        if st.button("💾 Guardar cambios del tarifario", type="primary", use_container_width=True):
            try:
                if (editado["Plan"].astype(str).str.strip() == "").any():
                    st.error("Todos los planes deben tener un nombre.")
                elif (pd.to_numeric(editado["Precio COP"], errors="coerce").fillna(0) < 0).any():
                    st.error("Los precios no pueden ser negativos.")
                else:
                    guardar_tarifario_local(editado)
                    st.success("Tarifario guardado correctamente.")
                    st.rerun()
            except Exception as exc:
                st.error(f"No fue posible guardar el tarifario: {exc}")
    with col_descargar:
        csv = editado.to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇️ Descargar tarifario CSV", data=csv, file_name="tarifario_entrenamiento.csv", mime="text/csv", use_container_width=True)

    st.caption("Nota técnica: esta versión guarda los cambios en un archivo JSON junto a la aplicación. En Streamlit Cloud, el archivo local puede reiniciarse al volver a desplegar o reiniciar el servicio; para persistencia garantizada conviene conectar el tarifario a Google Sheets mediante una acción específica del Apps Script.")


# ============================================================
# TÍTULO
# ============================================================

st.title("PERSONAL TRAINING & EVOLUTION TRACKER")


# ============================================================
# LOGIN / REGISTRO
# ============================================================

if not st.session_state["autenticado"]:
    col1, col2 = st.columns(2)

    # LOGIN
    with col1:
        titulo_ui("Iniciar Sesión", "fi-rr-lock", 2, 28)

        cedula_ingreso = st.text_input(
            "Número de Cédula / ID:"
        ).strip()

        pass_ingreso = st.text_input(
            "Contraseña:",
            type="password"
        ).strip()

        if st.button("Ingresar", use_container_width=True):
            if cedula_ingreso == "admin" and pass_ingreso == "admin123456":
                st.session_state["autenticado"] = True
                st.session_state["rol"] = "Admin"
                st.session_state["cedula"] = "ADMIN"
                st.session_state["nombre"] = "JULIAN AVILA"
                st.rerun()
            else:
                # Para iniciar sesión consultamos únicamente Usuarios.
                # No descargamos Historial, Pagos ni Clases hasta que
                # la autenticación haya sido confirmada.
                df_usuarios, error_usuarios = cargar_usuarios_login()

                if error_usuarios:
                    st.error(f"⚠️ {error_usuarios}")
                elif df_usuarios.empty or "cedula" not in df_usuarios.columns:
                    st.error("❌ No fue posible verificar los usuarios en este momento. Intenta nuevamente.")
                elif normalizar_cedula(cedula_ingreso) in df_usuarios["cedula"].values:
                    u = df_usuarios[df_usuarios["cedula"] == normalizar_cedula(cedula_ingreso)].iloc[0]

                    if str(u["password"]).strip() == pass_ingreso:
                        st.session_state["autenticado"] = True
                        st.session_state["rol"] = u.get("rol", "Cliente")
                        st.session_state["cedula"] = str(u["cedula"])
                        st.session_state["nombre"] = u["nombre_completo"]
                        st.rerun()
                    else:
                        st.error("❌ Contraseña incorrecta.")
                else:
                    st.error("❌ Cédula no registrada.")

    # REGISTRO
    with col2:
        titulo_ui("Crear Cuenta Nueva", "fi-rr-user-add", 2, 28)

        with st.form("form_registro"):
            reg_cedula = st.text_input("Número de Cédula / ID:").strip()
            reg_nombre = st.text_input("Nombre Completo:").strip()
            reg_whatsapp = st.text_input(
                "Número de Whatsapp (10 dígitos):",
                placeholder="310......."
            ).strip()
            reg_eps = st.text_input("EPS :").strip()
            reg_condiciones = st.text_area(
                "Condiciones Médicas / Lesiones / Cirugías:"
            ).strip()
            reg_pass = st.text_input("Crea tu Contraseña:", type="password").strip()

            if st.form_submit_button("Crear Perfil"):
                # Para validar duplicados consultamos únicamente Usuarios.
                df_usuarios, error_usuarios = cargar_usuarios_login()

                if error_usuarios:
                    st.error(f"⚠️ {error_usuarios}")
                elif not reg_cedula or not reg_nombre or not reg_pass:
                    st.error("⚠️ Cédula, Nombre y Contraseña son obligatorios.")
                elif not df_usuarios.empty and normalizar_cedula(reg_cedula) in df_usuarios["cedula"].values:
                    st.error("❌ Esta cédula ya está registrada.")
                else:
                    datos_usuario = {
                        "action": "registrar_usuario",
                        "cedula": str(reg_cedula).strip(),
                        "nombre_completo": str(reg_nombre).strip(),
                        "whatsapp": str(reg_whatsapp).strip(),
                        "eps": reg_eps if reg_eps else "NINGUNA",
                        "condiciones_medicas": (
                            reg_condiciones
                            if reg_condiciones
                            else "NINGUNA"
                        ),
                        "rol": "Cliente",
                        "password": str(reg_pass),
                        "fecha_registro": datetime.today().strftime("%d-%m-%Y"),
                    }

                    try:
                        respuesta_registro = api_post(
                            URL_API,
                            json=datos_usuario,
                            timeout=30,
                        )
                        respuesta_registro.raise_for_status()

                        try:
                            resultado_registro = respuesta_registro.json()
                        except Exception:
                            resultado_registro = {}

                        if str(resultado_registro.get("status", "")).lower() == "error":
                            st.error(
                                "❌ Google Apps Script reportó un error: "
                                + str(
                                    resultado_registro.get(
                                        "message",
                                        "No fue posible registrar el usuario.",
                                    )
                                )
                            )
                        else:
                            invalidar_cache_datos()
                            st.success(
                                "✅ Perfil creado correctamente. "
                                "Ya puedes iniciar sesión con tu cédula y contraseña."
                            )

                    except Exception as e:
                        st.error(f"❌ Error al guardar usuario: {e}")


# ============================================================
# APLICACIÓN AUTENTICADA
# ============================================================

else:
    st.sidebar.markdown(f"### {icono_ui('fi-rr-user', 22)}{st.session_state['nombre']}", unsafe_allow_html=True)
    st.sidebar.markdown(f"Rol: {st.session_state['rol']}")

    if st.sidebar.button("Cerrar Sesión"):
        st.session_state["autenticado"] = False
        st.session_state["rol"] = None
        st.session_state["cedula"] = None
        st.session_state["nombre"] = None
        st.rerun()

    df_usuarios, df_historial, df_pagos, df_clases, df_planes_bd = cargar_bd()

    # ========================================================
    # CLIENTE
    # ========================================================
    if st.session_state["rol"] == "Cliente":
        st.sidebar.markdown(
            f"{icono_ui('fi-rr-apps', 20)}<b>MENÚ CLIENTE</b>",
            unsafe_allow_html=True,
        )
        opcion = st.sidebar.radio(
            "",
            [
                "Registrar Medidas Hoy",
                "Ver Mi Progreso",
                "Mis Clases",
            ],
        )

        # REGISTRAR MEDIDAS
        if opcion == "Registrar Medidas Hoy":
            st.subheader("Registro de Evaluación Antropométrica")

            with st.form("form_medidas_cliente"):
                c1, c2, c3 = st.columns(3)

                peso = c1.number_input("Peso (kg):", 30.0, 200.0, 70.0, 0.5)
                estatura = c2.number_input("Estatura (cm):", 100.0, 220.0, 170.0, 1.0)
                edad = c3.number_input("Edad (años):", 10, 90, 25)

                sexo = c1.selectbox("Sexo Fisiológico:", ["Masculino", "Femenino"])
                meta = c2.selectbox(
                    "Objetivo Principal:",
                    [
                        "Perder peso / Déficit calórico",
                        "Recomposición corporal",
                        "Ganar Músculo",
                        "Mantenimiento",
                    ],
                    help=(
                        "El déficit calórico usa una reducción moderada de referencia de 400 kcal/día; "
                        "la recomposición toma como referencia las calorías de mantenimiento."
                    ),
                )

                st.markdown("---")
                titulo_ui("Medidas Corporales (cm) — Ordenado de Cabeza a Pies", "fi-rr-ruler-horizontal", 3, 24)

                col_izq, col_der = st.columns(2)

                with col_izq:
                    titulo_ui("Tren Superior y Torso", "fi-rr-body", 4, 21)
                    cuello = st.number_input("1. Cuello:", 20.0, 60.0, 38.0)
                    hombros = st.number_input("2. Hombros:", 50.0, 180.0, 110.0)
                    pecho = st.number_input("3. Pecho:", 50.0, 180.0, 95.0)
                    cintura = st.number_input("4. Cintura / Abdomen:", 40.0, 180.0, 80.0)
                    cadera = st.number_input("5. Glúteos / Cadera:", 40.0, 180.0, 95.0)

                with col_der:
                    titulo_ui("Extremidades (Brazos y Piernas)", "fi-rr-dumbbell", 4, 21)
                    bicep_der = st.number_input("6. Bícep Derecho:", 15.0, 60.0, 32.0)
                    bicep_izq = st.number_input("7. Bícep Izquierdo:", 15.0, 60.0, 32.0)
                    pierna_der = st.number_input("8. Pierna Derecha:", 20.0, 90.0, 55.0)
                    pierna_izq = st.number_input("9. Pierna Izquierda:", 20.0, 90.0, 55.0)
                    gemelo_der = st.number_input("10. Gemelo Derecho:", 15.0, 60.0, 35.0)
                    gemelo_izq = st.number_input("11. Gemelo Izquierdo:", 15.0, 60.0, 35.0)

                if st.form_submit_button("Guardar Evaluación"):
                    try:
                        imc, grasa, cals, edad_bio = calcular_metricas(
                            peso, estatura, edad, sexo, cuello, cintura, cadera, meta
                        )

                        if imc < 10 or imc > 60:
                            st.error(
                                f"⚠️ El IMC calculado ({imc}) está fuera de un rango razonable. Revisa peso y estatura."
                            )
                            st.stop()

                        id_reg = f"{st.session_state['cedula']}_{datetime.today().strftime('%Y%m%d%H%M')}"
                        fecha_hoy = datetime.today().strftime("%d-%m-%Y")

                        fila_medidas = [
                            str(id_reg),
                            str(fecha_hoy),
                            str(st.session_state["cedula"]),
                            int(edad),
                            str(sexo),
                            str(meta),
                            float(peso),
                            float(estatura),
                            float(cuello),
                            float(hombros),
                            float(bicep_der),
                            float(bicep_izq),
                            float(pecho),
                            float(cintura),
                            float(cadera),
                            float(pierna_der),
                            float(pierna_izq),
                            float(gemelo_der),
                            float(gemelo_izq),
                            float(imc),
                            float(grasa),
                            int(cals),
                            int(edad_bio),
                        ]

                        # Apps Script espera los campos directamente, no dentro de "row".
                        # Enviar la cédula explícitamente evita el error:
                        # "La cédula es obligatoria."
                        datos_medidas = {
                            "action": "guardar_medidas",
                            "id_registro": str(id_reg),
                            "fecha_evaluacion": str(fecha_hoy),
                            "cedula": str(st.session_state["cedula"]).strip(),
                            "edad": int(edad),
                            "sexo": str(sexo),
                            "meta": str(meta),
                            "peso_kg": float(peso),
                            "estatura_cm": float(estatura),
                            "cuello_cm": float(cuello),
                            "hombros_cm": float(hombros),
                            "bicep_der_cm": float(bicep_der),
                            "bicep_izq_cm": float(bicep_izq),
                            "pecho_cm": float(pecho),
                            "cintura_cm": float(cintura),
                            "cadera_cm": float(cadera),
                            "pierna_der_cm": float(pierna_der),
                            "pierna_izq_cm": float(pierna_izq),
                            "gemelo_der_cm": float(gemelo_der),
                            "gemelo_izq_cm": float(gemelo_izq),
                            "imc": float(imc),
                            "porcentaje_grasa": float(grasa),
                            "calorias_objetivo": int(cals),
                            "edad_metabolica": int(edad_bio),
                        }

                        respuesta_medidas = api_post(
                            URL_API,
                            json=datos_medidas,
                            timeout=30,
                        )
                        respuesta_medidas.raise_for_status()

                        try:
                            resultado_api = respuesta_medidas.json()
                        except Exception:
                            resultado_api = {}

                        if resultado_api.get("status") == "error":
                            st.error(
                                "❌ Google Apps Script reportó un error: "
                                + str(resultado_api.get("message", "Error desconocido"))
                            )
                            st.stop()

                        invalidar_cache_datos()
                        st.success("¡Medidas guardadas con éxito!")

                        r1, r2, r3, r4 = st.columns(4)
                        r1.metric("IMC", f"{imc:.2f}")
                        r2.metric("% Grasa Estimada", f"{grasa:.2f}%")
                        r3.metric("Calorías Recomendadas", f"{cals} kcal")
                        r4.metric("Edad Metabólica", f"{edad_bio} años")

                        # Generar las tres imágenes inmediatamente después de guardar.
                        fila_imagenes = dict(datos_medidas)
                        mostrar_evolucion_inteligente(
                            fila_imagenes,
                            st.session_state.get("nombre", "Cliente"),
                            anterior=None,
                            clave=f"registro_{id_reg}",
                        )

                    except Exception as e:
                        st.error(f"❌ Error calculando o guardando las medidas: {e}")

        # VER PROGRESO
        elif opcion == "Ver Mi Progreso":
            titulo_ui("Comparativa de Evolución", "fi-rr-chart-line-up", 2, 28)

            user_id = str(st.session_state["cedula"]).strip()
            mis_registros = (
                df_historial[df_historial["cedula"] == user_id]
                if not df_historial.empty
                else pd.DataFrame()
            )

            if not mis_registros.empty:
                mis_registros = mis_registros.copy()
                mis_registros["_fecha_dt"] = pd.to_datetime(
                    mis_registros["fecha_evaluacion"],
                    format="%d-%m-%Y",
                    errors="coerce",
                )
                mis_registros = mis_registros.sort_values(by="_fecha_dt").drop(columns=["_fecha_dt"])

                mostrar_graficos_evolucion(mis_registros)

                mostrar_alimentacion_recomendada(
                    mis_registros.iloc[-1],
                    st.session_state.get("nombre", "Cliente"),
                )
                evaluacion_anterior = mis_registros.iloc[-2] if len(mis_registros) > 1 else None
                mostrar_evolucion_inteligente(
                    mis_registros.iloc[-1],
                    st.session_state.get("nombre", "Cliente"),
                    anterior=evaluacion_anterior,
                    clave=f"cliente_{user_id}",
                )

                st.markdown("---")
                titulo_ui("Informe de Evolución", "fi-rr-file-user", 3, 24)
                st.caption("Genera un informe PDF con logo, resumen, comparativa completa y todo el historial antropométrico.")
                incluir_alimentacion_cliente = st.checkbox(
                    "Incluir guía de alimentación en el PDF",
                    value=False,
                    key="incluir_alimentacion_pdf_cliente",
                    help="La guía usa automáticamente el objetivo y los datos de la última evaluación del perfil.",
                )
                if st.button("Generar Informe de Evolución en PDF", use_container_width=True, key="btn_pdf_cliente"):
                    try:
                        pdf_bytes = generar_informe_evolucion_pdf(
                            mis_registros,
                            st.session_state.get("nombre", "Cliente"),
                            user_id,
                            ruta_logo,
                            incluir_alimentacion=incluir_alimentacion_cliente,
                        )
                        nombre_pdf = "Informe_Evolucion_" + "".join(ch for ch in st.session_state.get("nombre", "Cliente") if ch.isalnum() or ch in " _-").strip().replace(" ", "_") + ".pdf"
                        st.download_button(
                            "⬇️ Descargar Informe PDF",
                            data=pdf_bytes,
                            file_name=nombre_pdf,
                            mime="application/pdf",
                            use_container_width=True,
                            key="download_pdf_cliente",
                        )
                    except Exception as e:
                        st.error(f"❌ No fue posible generar el informe PDF: {e}")

                titulo_ui("Historial de Registros Completos", "fi-rr-clipboard", 4, 21)
                st.dataframe(mis_registros.astype(str), use_container_width=True)
            else:
                st.info("Aún no has registrado ninguna evaluación física.")

        # MIS CLASES
        elif opcion == "Mis Clases":
            titulo_ui("Mi Plan de Clases Personalizadas", "fi-rr-dumbbell", 2, 28)
            mostrar_resumen_clases(df_clases, st.session_state["cedula"])

            resumen_clases = obtener_resumen_clases(df_clases, st.session_state["cedula"])
            registros_clases = resumen_clases["registros"]

            if not registros_clases.empty:
                titulo_ui("Clases tomadas", "fi-rr-calendar", 4, 21)
                tabla = registros_clases.copy()

                columnas_tabla = [
                    columna
                    for columna in ["fecha_clase", "tipo_plan", "periodo", "estado"]
                    if columna in tabla.columns
                ]
                tabla = tabla[columnas_tabla]
                tabla = tabla.rename(
                    columns={
                        "fecha_clase": "Fecha de Clase",
                        "tipo_plan": "Plan",
                        "periodo": "Periodo",
                        "estado": "Estado",
                    }
                )

                if "Fecha de Clase" in tabla.columns:
                    tabla["_fecha"] = tabla["Fecha de Clase"].apply(parsear_fecha)
                    tabla = tabla.sort_values("_fecha", ascending=False).drop(columns=["_fecha"])

                st.dataframe(tabla.astype(str), use_container_width=True, hide_index=True)
            else:
                st.info("Todavía no tienes clases registradas.")

    # ========================================================
    # ADMINISTRADOR
    # ========================================================
    elif st.session_state["rol"] == "Admin":
        st.subheader("Panel de Control General")

        if not df_usuarios.empty:
            clientes = df_usuarios[df_usuarios["rol"].astype(str).str.lower() == "cliente"]
            st.markdown(f"Total de Clientes Registrados: {len(clientes)}")

            if not clientes.empty:
                st.sidebar.markdown(
                    f"{icono_ui('fi-rr-dashboard', 20)}<b>MENÚ ADMINISTRADOR</b>",
                    unsafe_allow_html=True,
                )
                opcion_admin = st.sidebar.radio(
                    "",
                    [
                        "Dashboard General",
                        "Gestión de Clientes",
                        "Control de Clases",
                        "Tarifario y Planes",
                    ],
                )

                # TARIFARIO PRIVADO DEL ADMINISTRADOR
                if opcion_admin == "Tarifario y Planes":
                    mostrar_modulo_tarifario()

                # DASHBOARD GENERAL
                elif opcion_admin == "Dashboard General":
                    mostrar_dashboard_admin(df_usuarios, df_historial, df_pagos, df_clases)

                # GESTIÓN DE CLIENTES
                elif opcion_admin == "Gestión de Clientes":
                    cedula_sel = st.selectbox(
                        "Buscar Cliente por Nombre/Cédula:",
                        clientes["cedula"].astype(str) + " - " + clientes["nombre_completo"].astype(str),
                    )

                    if cedula_sel:
                        id_cliente = str(cedula_sel.split(" - ")[0]).strip()
                        cliente_encontrado = clientes[clientes["cedula"] == id_cliente]

                        if not cliente_encontrado.empty:
                            u_info = cliente_encontrado.iloc[0]

                            st.markdown("---")
                            titulo_ui(f"Información de: {u_info['nombre_completo']}", "fi-rr-file-user", 3, 24)

                            info_col1, info_col2, info_col3 = st.columns(3)
                            info_col1.markdown(f"WhatsApp: {u_info.get('whatsapp', 'No registra')}")
                            info_col2.markdown(f"EPS: {str(u_info.get('eps', 'No registra')).upper()}")
                            info_col3.markdown(f"Fecha Registro: {u_info.get('fecha_registro', 'No registra')}")

                            st.markdown(f"Condiciones Médicas / Lesiones: {u_info.get('condiciones_medicas', 'Ninguna')}")

                            ws_url = link_whatsapp(u_info.get("whatsapp", ""), u_info["nombre_completo"])
                            st.markdown(f"[Enviar Mensaje de Seguimiento por WhatsApp]({ws_url})")

                            # RESUMEN DE CLASES EN PERFIL
                            st.markdown("---")
                            mostrar_resumen_clases(df_clases, id_cliente, "Resumen de Clases")

                            # PAGOS Y MEMBRESÍAS: compromisos por contratación/renovación, no por cambio de mes
                            st.markdown("---")
                            titulo_ui("Pagos y Membresías", "fi-rr-credit-card", 4, 21)

                            pagos_cliente = pd.DataFrame()
                            if not df_pagos.empty and "cedula" in df_pagos.columns:
                                pagos_cliente = df_pagos[df_pagos["cedula"].apply(normalizar_cedula) == normalizar_cedula(id_cliente)].copy()

                            obligaciones_cliente = construir_estado_cuenta(df_pagos, df_planes_bd, id_cliente)
                            total_comprometido = sum(float(x["valor"]) for x in obligaciones_cliente)
                            total_abonado = sum(float(x["pagado"]) for x in obligaciones_cliente)
                            total_pendiente = sum(float(x["saldo"]) for x in obligaciones_cliente)
                            estado_cuenta = "🟢 AL DÍA" if total_pendiente <= 0.001 else ("🟡 CON ABONOS" if total_abonado > 0 else "🔴 PENDIENTE")

                            p1, p2, p3, p4 = st.columns(4)
                            p1.metric("Compromisos identificados", f"${total_comprometido:,.0f}")
                            p2.metric("Abonos registrados", f"${total_abonado:,.0f}")
                            p3.metric("Saldo pendiente", f"${total_pendiente:,.0f}")
                            p4.metric("Estado", estado_cuenta)
                            st.caption("Los paquetes de clases no se reinician por mes: el compromiso permanece abierto hasta completar el pago. Las renovaciones crean un compromiso independiente. Los registros antiguos sin referencia se concilian por mes cuando existe un movimiento guardado.")

                            if obligaciones_cliente:
                                filas_estado = []
                                for ob in obligaciones_cliente:
                                    filas_estado.append({
                                        "Concepto": ob["descripcion"],
                                        "Valor acordado": f"${ob['valor']:,.0f}",
                                        "Abonado": f"${ob['pagado']:,.0f}",
                                        "Pendiente": f"${ob['saldo']:,.0f}",
                                        "Estado": "PAGADO" if ob["saldo"] <= 0.001 else ("ABONO" if ob["pagado"] > 0 else "PENDIENTE"),
                                    })
                                st.dataframe(pd.DataFrame(filas_estado), use_container_width=True, hide_index=True)
                            else:
                                st.info("No hay compromisos pendientes detectables. Los planes nuevos se registrarán con su valor negociado y los abonos asociados.")

                            # REGISTRAR ABONO: se conserva el flujo manual, ahora aplicado a un compromiso concreto.
                            if obligaciones_cliente and any(x["saldo"] > 0.001 for x in obligaciones_cliente):
                                pendientes_pago = [x for x in obligaciones_cliente if x["saldo"] > 0.001]
                                etiquetas_ob = [f"{x['descripcion']} · Pendiente ${x['saldo']:,.0f}" for x in pendientes_pago]
                                with st.expander("➕ Registrar nuevo pago / abono", expanded=True):
                                    with st.form(f"form_pago_{id_cliente}"):
                                        idx_ob = st.selectbox("¿A qué compromiso corresponde el pago?", range(len(pendientes_pago)), format_func=lambda i: etiquetas_ob[i])
                                        obligacion_sel = pendientes_pago[idx_ob]
                                        valor_mensualidad = st.number_input(
                                            "Valor negociado del plan / compromiso ($):",
                                            min_value=1.0, value=float(obligacion_sel["valor"]), step=5000.0, format="%.0f",
                                        )
                                        saldo_para_nuevo_pago = max(float(valor_mensualidad) - float(obligacion_sel["pagado"]), 0.0)
                                        st.caption(f"Abonado a este compromiso: ${obligacion_sel['pagado']:,.0f} | Saldo disponible: ${saldo_para_nuevo_pago:,.0f}")
                                        valor_pago = st.number_input(
                                            "Valor del pago / abono ($):", min_value=1.0,
                                            value=float(saldo_para_nuevo_pago if saldo_para_nuevo_pago > 0 else 1.0),
                                            step=5000.0, format="%.0f",
                                        )
                                        concepto_base = st.text_input("Concepto:", value=f"Abono {obligacion_sel['descripcion']}").strip()
                                        guardar_pago = st.form_submit_button("Registrar Pago", use_container_width=True)
                                        if guardar_pago:
                                            try:
                                                if valor_mensualidad <= 0 or valor_pago <= 0:
                                                    st.error("El valor del compromiso y el abono deben ser mayores que cero.")
                                                    st.stop()
                                                if valor_pago > saldo_para_nuevo_pago + 0.001:
                                                    st.error(f"El abono supera el saldo pendiente. Disponible: ${saldo_para_nuevo_pago:,.0f}.")
                                                    st.stop()
                                                concepto_pago = concepto_base or "Abono de compromiso"
                                                if obligacion_sel.get("ref"):
                                                    concepto_pago += f" | REF={obligacion_sel['ref']}"
                                                enviar_pago_api(id_cliente, valor_pago, concepto_pago, valor_mensualidad)
                                                invalidar_cache_datos()
                                                st.success("✅ Pago registrado correctamente.")
                                                st.rerun()
                                            except Exception as e:
                                                st.error(f"❌ Error registrando el pago: {e}")
                            elif not obligaciones_cliente:
                                st.caption("Al registrar una nueva membresía o renovación podrás indicar el valor negociado y el abono inicial. No se crearán cobros automáticos por el cambio de mes.")

                            # HISTORIAL DE PAGOS
                            if not pagos_cliente.empty:
                                titulo_ui("Historial de Pagos", "fi-rr-receipt", 4, 21)
                                pagos_mostrar = pagos_cliente.copy()
                                if "_fecha_dt" not in pagos_mostrar.columns:
                                    pagos_mostrar["_fecha_dt"] = (
                                        pagos_mostrar["fecha_pago"].apply(parsear_fecha)
                                        if "fecha_pago" in pagos_mostrar.columns
                                        else pd.NaT
                                    )
                                pagos_mostrar = pagos_mostrar.sort_values(by="_fecha_dt", ascending=False).drop(
                                    columns=["_fecha_dt"], errors="ignore"
                                )

                                columnas_pago_mostrar = [
                                    c for c in ["fecha_pago", "valor", "concepto", "valor_mensualidad"]
                                    if c in pagos_mostrar.columns
                                ]
                                tabla_pagos = pagos_mostrar[columnas_pago_mostrar].copy()

                                if "valor" in tabla_pagos.columns:
                                    tabla_pagos["valor"] = pd.to_numeric(tabla_pagos["valor"], errors="coerce").fillna(0).map(lambda x: f"${x:,.0f}")
                                if "valor_mensualidad" in tabla_pagos.columns:
                                    tabla_pagos["valor_mensualidad"] = pd.to_numeric(tabla_pagos["valor_mensualidad"], errors="coerce").fillna(0).map(lambda x: f"${x:,.0f}")

                                tabla_pagos = tabla_pagos.rename(
                                    columns={
                                        "fecha_pago": "Fecha",
                                        "valor": "Pago",
                                        "concepto": "Concepto",
                                        "valor_mensualidad": "Mensualidad",
                                    }
                                )
                                st.dataframe(tabla_pagos, use_container_width=True, hide_index=True)
                            else:
                                st.info("Este cliente todavía no tiene pagos registrados.")

                            # HISTORIAL Y PROGRESO
                            st.markdown("---")
                            titulo_ui("Historial y Progreso del Cliente", "fi-rr-chart-line-up", 4, 21)

                            if not df_historial.empty:
                                h_cliente = df_historial[df_historial["cedula"] == id_cliente].copy()
                                if not h_cliente.empty:
                                    h_cliente["_fecha_nutricion_dt"] = pd.to_datetime(
                                        h_cliente["fecha_evaluacion"],
                                        format="%d-%m-%Y",
                                        errors="coerce",
                                    )
                                    h_cliente = h_cliente.sort_values("_fecha_nutricion_dt", na_position="first")
                                    mostrar_graficos_evolucion(h_cliente.drop(columns=["_fecha_nutricion_dt"], errors="ignore"))

                                    mostrar_alimentacion_recomendada(
                                        h_cliente.iloc[-1],
                                        u_info.get("nombre_completo", "Cliente"),
                                    )
                                    evaluacion_anterior_admin = h_cliente.iloc[-2] if len(h_cliente) > 1 else None
                                    mostrar_evolucion_inteligente(
                                        h_cliente.iloc[-1],
                                        u_info.get("nombre_completo", "Cliente"),
                                        anterior=evaluacion_anterior_admin,
                                        clave=f"admin_{id_cliente}",
                                    )
                                    h_cliente = h_cliente.drop(columns=["_fecha_nutricion_dt"], errors="ignore")

                                    titulo_ui("Informe de Evolución del Cliente", "fi-rr-file-user", 3, 24)
                                    st.caption("Incluye logo, indicadores, medidas de brazos, pecho, cintura, glúteos/cadera, piernas y gemelos, además del historial.")
                                    incluir_alimentacion_admin = st.checkbox(
                                        "Incluir guía de alimentación en el PDF",
                                        value=False,
                                        key=f"incluir_alimentacion_pdf_admin_{id_cliente}",
                                        help="La guía toma automáticamente el objetivo y los datos de la última evaluación del cliente.",
                                    )
                                    if st.button("Generar Informe PDF del Cliente", use_container_width=True, key=f"btn_pdf_admin_{id_cliente}"):
                                        try:
                                            pdf_bytes_admin = generar_informe_evolucion_pdf(
                                                h_cliente,
                                                u_info.get("nombre_completo", "Cliente"),
                                                id_cliente,
                                                ruta_logo,
                                                incluir_alimentacion=incluir_alimentacion_admin,
                                            )
                                            nombre_admin_pdf = "Informe_Evolucion_" + "".join(ch for ch in str(u_info.get("nombre_completo", "Cliente")) if ch.isalnum() or ch in " _-").strip().replace(" ", "_") + ".pdf"
                                            st.download_button(
                                                "⬇️ Descargar Informe PDF",
                                                data=pdf_bytes_admin,
                                                file_name=nombre_admin_pdf,
                                                mime="application/pdf",
                                                use_container_width=True,
                                                key=f"download_pdf_admin_{id_cliente}",
                                            )
                                        except Exception as e:
                                            st.error(f"❌ No fue posible generar el informe PDF: {e}")

                                    titulo_ui("Registros en Tabla", "fi-rr-table-list", 4, 21)
                                    h_cliente["_fecha_dt"] = pd.to_datetime(
                                        h_cliente["fecha_evaluacion"],
                                        format="%d-%m-%Y",
                                        errors="coerce",
                                    )
                                    h_cliente_ord = h_cliente.sort_values(by="_fecha_dt", ascending=False).drop(columns=["_fecha_dt"])
                                    st.dataframe(h_cliente_ord.astype(str), use_container_width=True)
                                else:
                                    st.info("Este cliente no se ha tomado medidas corporales todavía.")
                            else:
                                st.info("No hay registros en el historial general.")

                # CONTROL DE CLASES
                elif opcion_admin == "Control de Clases":
                    titulo_ui("Control de Clases Personalizadas", "fi-rr-dumbbell", 2, 28)
                    st.info("Aquí el ADMIN configura el plan y registra manualmente cada clase realmente tomada.")

                    cliente_clase_sel = st.selectbox(
                        "Seleccionar Cliente:",
                        clientes["cedula"].astype(str) + " - " + clientes["nombre_completo"].astype(str),
                        key="selector_cliente_clases",
                    )

                    id_cliente_clases = cliente_clase_sel.split(" - ")[0].strip()
                    nombre_cliente_clases = cliente_clase_sel.split(" - ", 1)[1]

                    titulo_ui(nombre_cliente_clases, "fi-rr-user", 3, 24)
                    mostrar_resumen_clases(df_clases, id_cliente_clases)

                    resumen_actual = obtener_resumen_clases(df_clases, id_cliente_clases)
                    plan_agotado = (
                        resumen_actual["clases_contratadas"] > 0
                        and resumen_actual["clases_tomadas"] >= resumen_actual["clases_contratadas"]
                    )

                    # ------------------------------------------------
                    # CONFIGURACIÓN DEL PLAN
                    # ------------------------------------------------
                    st.markdown("---")
                    titulo_ui("Renovar plan agotado" if plan_agotado else "Registrar un nuevo plan", "fi-rr-file-plus", 4, 21)

                    with st.form(f"form_config_clases_{id_cliente_clases}"):
                        col_plan1, col_plan2 = st.columns(2)

                        with col_plan1:
                            plan_cliente = st.text_input(
                                "Tipo / nombre del plan:",
                                value=(
                                    resumen_actual["plan"]
                                    if resumen_actual["plan"] != "Sin plan registrado"
                                    else ""
                                ),
                                placeholder="Ej: Premium, Básico, 3 días, Plan 12 clases...",
                            ).strip()

                        with col_plan2:
                            clases_contratadas = st.number_input(
                                "Número de clases contratadas:", min_value=1, max_value=500,
                                value=(resumen_actual["clases_contratadas"] if resumen_actual["clases_contratadas"] > 0 else 20), step=1,
                            )

                        col_valor_plan, col_abono_plan = st.columns(2)
                        with col_valor_plan:
                            valor_plan_negociado = st.number_input(
                                "Valor negociado de esta contratación ($):", min_value=1.0,
                                value=520000.0, step=5000.0, format="%.0f",
                                help="Puedes ingresar el precio acordado con este cliente, aunque sea diferente al tarifario.",
                            )
                        with col_abono_plan:
                            abono_inicial_plan = st.number_input(
                                "Abono recibido ahora ($):", min_value=0.0, value=0.0,
                                step=5000.0, format="%.0f",
                                help="Registra cero si todavía no ha abonado. El saldo quedará pendiente.",
                            )

                        st.caption(
                            "Cada contratación o renovación crea un nuevo ciclo de clases. El paquete no vence por cambio de mes: "
                            "las clases no utilizadas continúan disponibles hasta consumirse. El valor negociado y el abono quedan asociados a este plan."
                        )

                        guardar_config_plan = st.form_submit_button(
                            "Registrar renovación" if plan_agotado else "Registrar nuevo plan",
                            use_container_width=True,
                        )

                        if guardar_config_plan:
                            try:
                                if not plan_cliente:
                                    st.error("❌ Debes indicar el tipo o nombre del plan.")
                                    st.stop()

                                valor_plan_negociado = float(valor_plan_negociado)
                                abono_inicial_plan = float(abono_inicial_plan)
                                if valor_plan_negociado <= 0:
                                    st.error("❌ Ingresa el valor negociado de la contratación.")
                                    st.stop()
                                if abono_inicial_plan < 0 or abono_inicial_plan > valor_plan_negociado:
                                    st.error("❌ El abono inicial no puede ser superior al valor negociado.")
                                    st.stop()

                                fecha_hoy_str = datetime.today().strftime("%d-%m-%Y")
                                ref_contrato = f"CT{normalizar_cedula(id_cliente_clases)}{datetime.today().strftime('%Y%m%d%H%M%S%f')}"
                                id_plan_nuevo = f"PLAN_{ref_contrato}"
                                observaciones_plan = f"Nueva contratación | REF={ref_contrato} | VALOR={valor_plan_negociado:.0f}"

                                # Estructura ACTUAL de la hoja Planes:
                                # cedula, nombre_completo, tipo_plan, fecha_inicio,
                                # fecha_fin, estado, observaciones, clases_incluidas
                                fila_config = [
                                    str(id_cliente_clases),
                                    str(nombre_cliente_clases),
                                    str(plan_cliente),
                                    fecha_hoy_str,
                                    "",
                                    "Activo",
                                    observaciones_plan,
                                    int(clases_contratadas),
                                ]

                                respuesta_config = api_post(
                                    URL_API,
                                    json={
                                        "action": "guardar_plan",
                                        "cedula": str(id_cliente_clases).strip(),
                                        "nombre_completo": str(nombre_cliente_clases).strip(),
                                        "tipo_plan": str(plan_cliente).strip(),
                                        "fecha_inicio": str(fecha_hoy_str),
                                        "fecha_fin": "",
                                        "estado": "Activo",
                                        "observaciones": observaciones_plan,
                                        "clases_incluidas": int(clases_contratadas),
                                        "id_plan": id_plan_nuevo,
                                    },
                                    timeout=30,
                                )
                                respuesta_config.raise_for_status()
                                resultado_config = respuesta_config.json()

                                if resultado_config.get("status") == "error":
                                    st.error(
                                        "❌ Google Apps Script reportó un error: "
                                        + str(
                                            resultado_config.get(
                                                "message",
                                                "Error desconocido",
                                            )
                                        )
                                    )
                                    st.stop()

                                if abono_inicial_plan > 0:
                                    try:
                                        enviar_pago_api(
                                            id_cliente_clases,
                                            abono_inicial_plan,
                                            f"Abono inicial · {plan_cliente} · REF={ref_contrato}",
                                            valor_plan_negociado,
                                        )
                                    except Exception as e_pago:
                                        st.warning(
                                            "El plan quedó registrado, pero no se pudo guardar el abono inicial. "
                                            f"Regístralo desde Pagos y Membresías. Detalle: {e_pago}"
                                        )
                                invalidar_cache_datos()
                                saldo_nuevo_plan = max(valor_plan_negociado - abono_inicial_plan, 0.0)
                                st.success(
                                    f"✅ Nueva contratación registrada. Valor: ${valor_plan_negociado:,.0f} · "
                                    f"Abono: ${abono_inicial_plan:,.0f} · Saldo: ${saldo_nuevo_plan:,.0f}."
                                )
                                st.rerun()

                            except Exception as e:
                                st.error(f"❌ Error registrando el nuevo plan: {e}")

                    # ------------------------------------------------
                    # REGISTRAR CLASE TOMADA
                    # ------------------------------------------------
                    st.markdown("---")
                    titulo_ui("Registrar clase tomada", "fi-rr-calendar-plus", 4, 21)

                    if plan_agotado:
                        st.warning(
                            "⚠️ ¡Paquete agotado! El cliente consumió todas las clases contratadas. "
                            "Es momento de negociar y registrar la renovación. El aviso no depende del mes calendario."
                        )
                    elif resumen_actual["clases_contratadas"] > 0 and resumen_actual["clases_restantes"] <= 2:
                        st.info(f"🔔 Próxima renovación: quedan {resumen_actual['clases_restantes']} clases de este paquete.")

                    with st.form(f"form_registro_clase_{id_cliente_clases}"):
                        fecha_clase = st.date_input(
                            "Fecha de la clase tomada:",
                            value=date.today(),
                            max_value=date.today(),
                            format="DD-MM-YYYY",
                        )

                        registrar_clase = st.form_submit_button(
                            "Registrar Clase Tomada",
                            use_container_width=True,
                        )

                        if registrar_clase:
                            try:
                                if resumen_actual["clases_contratadas"] <= 0:
                                    st.error("❌ Primero debes configurar el plan y el número de clases contratadas.")
                                    st.stop()

                                if resumen_actual["clases_tomadas"] >= resumen_actual["clases_contratadas"]:
                                    st.error("❌ El cliente ya utilizó todas las clases de su plan.")
                                    st.stop()

                                fecha_clase_str = fecha_clase.strftime("%d-%m-%Y")
                                clases_cliente = resumen_actual["registros"]
                                id_plan_actual = str(
                                    resumen_actual.get("id_plan", "")
                                ).strip()

                                if not clases_cliente.empty and "fecha_clase" in clases_cliente.columns:
                                    fechas_existentes = (
                                        clases_cliente["fecha_clase"]
                                        .apply(formatear_fecha)
                                        .astype(str)
                                        .str.strip()
                                        .tolist()
                                    )
                                    if fecha_clase_str in fechas_existentes:
                                        st.error(f"❌ Ya existe una clase registrada para este cliente el {fecha_clase_str}.")
                                        st.stop()

                                id_clase = (
                                    f"{id_cliente_clases}CLASE"
                                    f"{fecha_clase.strftime('%Y%m%d')}_"
                                    f"{datetime.today().strftime('%H%M%S%f')}"
                                )

                                # Estructura ACTUAL de la hoja Clases:
                                # id_clase, cedula, nombre_completo, fecha_clase,
                                # tipo_plan, periodo, estado
                                fila_clase = [
                                    str(id_clase),
                                    str(id_cliente_clases),
                                    str(nombre_cliente_clases),
                                    str(fecha_clase_str),
                                    str(resumen_actual["plan"]),
                                    int(resumen_actual["clases_tomadas"]) + 1,
                                    "Tomada",
                                    str(id_plan_actual),
                                ]

                                respuesta_clase = api_post(
                                    URL_API,
                                    json={
                                        "action": "guardar_clase",
                                        "id_clase": str(id_clase),
                                        "cedula": str(id_cliente_clases).strip(),
                                        "nombre_completo": str(nombre_cliente_clases).strip(),
                                        "fecha_clase": str(fecha_clase_str),
                                        "tipo_plan": str(resumen_actual["plan"]).strip(),
                                        "periodo": int(resumen_actual["clases_tomadas"]) + 1,
                                        "estado": "Tomada",
                                        "id_plan": str(id_plan_actual),
                                    },
                                    timeout=30,
                                )
                                respuesta_clase.raise_for_status()
                                resultado_clase = respuesta_clase.json()

                                if resultado_clase.get("status") == "error":
                                    st.error(
                                        "❌ Google Apps Script reportó un error: "
                                        + str(resultado_clase.get("message", "Error desconocido"))
                                    )
                                    st.stop()

                                invalidar_cache_datos()
                                st.success("✅ Clase registrada correctamente.")
                                st.rerun()

                            except Exception as e:
                                st.error(f"❌ Error registrando la clase: {e}")

                    # ------------------------------------------------
                    # HISTORIAL DE CLASES
                    # ------------------------------------------------
                    st.markdown("---")
                    titulo_ui("Historial de clases tomadas", "fi-rr-clipboard", 4, 21)

                    resumen_historial = obtener_resumen_clases(df_clases, id_cliente_clases)
                    registros_historial = resumen_historial["registros"]

                    if not registros_historial.empty:
                        historial = registros_historial.copy()

                        if "fecha_clase" in historial.columns:
                            historial["_fecha_dt"] = historial["fecha_clase"].apply(parsear_fecha)
                            historial = historial.sort_values("_fecha_dt", ascending=False)

                        columnas_historial = [
                            c for c in ["fecha_clase", "tipo_plan", "periodo", "estado"]
                            if c in historial.columns
                        ]

                        historial = historial[columnas_historial].copy()
                        historial = historial.rename(
                            columns={
                                "fecha_clase": "Fecha Clase",
                                "tipo_plan": "Plan",
                                "periodo": "Periodo",
                                "estado": "Estado",
                            }
                        )

                        st.dataframe(historial.astype(str), use_container_width=True, hide_index=True)
                    else:
                        st.info("Este cliente todavía no tiene clases registradas.")
            else:
                st.info("No hay clientes registrados actualmente.")


# ============================================================
# ATRIBUCIÓN DE ICONOS
# ============================================================

st.markdown(
    """
    <div class="ui-attribution">
        Iconos de interfaz: <a href="https://www.flaticon.com/uicons" target="_blank">Uicons by Flaticon</a>
    </div>
    """,
    unsafe_allow_html=True,
)
