import math
import os
import urllib.parse
from datetime import datetime, date

import pandas as pd
import requests
import streamlit as st
from PIL import Image


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

URL_API = ("https://script.google.com/macros/s/AKfycbwnEcgCX3HRKCY2d_H6nvNOpXmI7BptOesa4-jJhIp-ZCnVNGbHniYye6Qdj5Ev23Fm/exec")


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

    </style>
    """,
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

    if meta == "Perder Grasa":
        calorias = mantenimiento - 400
    elif meta == "Ganar Músculo":
        calorias = mantenimiento + 350
    else:
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
        respuesta = requests.get(
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

@st.cache_data(ttl=10)
def cargar_bd():
    try:
        respuesta = requests.get(
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
        for dataframe in (df_u, df_m, df_p, df_c):
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
        # NUMÉRICOS DE CLASES
        # ====================================================
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

        if not df_c.empty and "fecha_clase" in df_c.columns:
            df_c["fecha_clase"] = df_c["fecha_clase"].apply(formatear_fecha)

        if not df_c.empty and "fecha_registro" in df_c.columns:
            df_c["fecha_registro"] = df_c["fecha_registro"].apply(formatear_fecha)

        return (
            df_u,
            df_m,
            df_p,
            df_c
        )

    except Exception as e:
        st.error(f"Error procesando base de datos: {e}")
        return (
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame()
        )


# ============================================================
# GRÁFICOS
# ============================================================

def mostrar_graficos_evolucion(df_filtrado):
    if df_filtrado.empty:
        return

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

    st.markdown("### 📈 Gráficas de Evolución Temporal")

    tab1, tab2, tab3, tab4 = st.tabs([
        " Peso y Composición",
        " Perímetros Principales",
        " Extremidades Superiores",
        " Piernas y Glúteos",
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


def generar_informe_evolucion_pdf(df_historial_cliente, nombre_cliente, cedula_cliente, logo_path=None):
    """Genera un informe PDF profesional con la evolución completa del cliente."""
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


@st.cache_data(ttl=10)
def cargar_solo_planes():
    """Carga la hoja Planes de la API y la normaliza de forma segura."""
    try:
        respuesta = requests.get(
            URL_API,
            params={"action": "planes"},
            timeout=30,
        )
        respuesta.raise_for_status()
        datos = respuesta.json()

        # Algunas versiones del Apps Script devuelven {planes: [...]};
        # otras pueden devolver directamente una lista.
        if isinstance(datos, dict):
            planes_raw = datos.get("planes", [])
        elif isinstance(datos, list):
            planes_raw = datos
        else:
            planes_raw = []

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

        if df_planes.empty:
            return df_planes

        if "cedula" in df_planes.columns:
            df_planes["cedula"] = df_planes["cedula"].apply(normalizar_cedula)

        if "clases_incluidas" in df_planes.columns:
            df_planes["clases_incluidas"] = pd.to_numeric(
                df_planes["clases_incluidas"], errors="coerce"
            ).fillna(0)

        if "fecha_inicio" in df_planes.columns:
            df_planes["_fecha_inicio_dt"] = df_planes["fecha_inicio"].apply(parsear_fecha)
        else:
            df_planes["_fecha_inicio_dt"] = pd.NaT

        return df_planes

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

        if id_plan_actual and "id_plan" in registros.columns:
            registros["_id_plan_norm"] = (
                registros["id_plan"].fillna("").astype(str).str.strip()
            )
            registros = registros[
                registros["_id_plan_norm"] == id_plan_actual
            ].copy()
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
    titulo=" Clases Personalizadas"
):
    resumen = obtener_resumen_clases(df_clases, cedula)

    st.markdown(f"### {titulo}")

    if resumen["clases_contratadas"] <= 0:
        st.info("Este cliente todavía no tiene un plan de clases configurado.")
        return

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Plan", resumen["plan"])
    c2.metric("Clases contratadas", resumen["clases_contratadas"])
    c3.metric("Clases tomadas", resumen["clases_tomadas"])
    c4.metric("Clases restantes", resumen["clases_restantes"])

    st.progress(int(round(resumen["porcentaje"])))

    st.markdown(
        f"""
        <div style="
            text-align:center;
            font-size:18px;
            margin-top:-10px;
            margin-bottom:15px;
        ">
        <strong>
        {resumen['porcentaje']:.1f}% del plan utilizado
        </strong>
        </div>
        """,
        unsafe_allow_html=True
    )


# ============================================================
# ESTADO DE SESIÓN
# ============================================================

if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
    st.session_state["rol"] = None
    st.session_state["cedula"] = None
    st.session_state["nombre"] = None


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
        st.subheader("🔐 Iniciar Sesión")

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
        st.subheader("📝 Crear Cuenta Nueva")

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
                        respuesta_registro = requests.post(
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
                            st.cache_data.clear()
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
    st.sidebar.markdown(f"### 👤 {st.session_state['nombre']}")
    st.sidebar.markdown(f"Rol: {st.session_state['rol']}")

    if st.sidebar.button("Cerrar Sesión"):
        st.session_state["autenticado"] = False
        st.session_state["rol"] = None
        st.session_state["cedula"] = None
        st.session_state["nombre"] = None
        st.rerun()

    df_usuarios, df_historial, df_pagos, df_clases = cargar_bd()

    # ========================================================
    # CLIENTE
    # ========================================================
    if st.session_state["rol"] == "Cliente":
        opcion = st.sidebar.radio(
            "MENÚ",
            [
                " Registrar Medidas Hoy",
                " Ver Mi Progreso",
                " Mis Clases",
            ],
        )

        # REGISTRAR MEDIDAS
        if opcion == " Registrar Medidas Hoy":
            st.subheader("Registro de Evaluación Antropométrica")

            with st.form("form_medidas_cliente"):
                c1, c2, c3 = st.columns(3)

                peso = c1.number_input("Peso (kg):", 30.0, 200.0, 70.0, 0.5)
                estatura = c2.number_input("Estatura (cm):", 100.0, 220.0, 170.0, 1.0)
                edad = c3.number_input("Edad (años):", 10, 90, 25)

                sexo = c1.selectbox("Sexo Fisiológico:", ["Masculino", "Femenino"])
                meta = c2.selectbox(
                    "Objetivo Principal:",
                    ["Perder Grasa", "Ganar Músculo", "Mantenimiento"],
                )

                st.markdown("---")
                st.write("###  Medidas Corporales (cm) — Ordenado de Cabeza a Pies")

                col_izq, col_der = st.columns(2)

                with col_izq:
                    st.markdown(" Tren Superior y Torso")
                    cuello = st.number_input("1. Cuello:", 20.0, 60.0, 38.0)
                    hombros = st.number_input("2. Hombros:", 50.0, 180.0, 110.0)
                    pecho = st.number_input("3. Pecho:", 50.0, 180.0, 95.0)
                    cintura = st.number_input("4. Cintura / Abdomen:", 40.0, 180.0, 80.0)
                    cadera = st.number_input("5. Glúteos / Cadera:", 40.0, 180.0, 95.0)

                with col_der:
                    st.markdown(" Extremidades (Brazos y Piernas)")
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

                        respuesta_medidas = requests.post(
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

                        st.cache_data.clear()
                        st.success("¡Medidas guardadas con éxito!")

                        r1, r2, r3, r4 = st.columns(4)
                        r1.metric("IMC", f"{imc:.2f}")
                        r2.metric("% Grasa Estimada", f"{grasa:.2f}%")
                        r3.metric("Calorías Recomendadas", f"{cals} kcal")
                        r4.metric("Edad Metabólica", f"{edad_bio} años")

                    except Exception as e:
                        st.error(f"❌ Error calculando o guardando las medidas: {e}")

        # VER PROGRESO
        elif opcion == " Ver Mi Progreso":
            st.subheader(" Comparativa de Evolución")

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

                if len(mis_registros) >= 2:
                    inicial = mis_registros.iloc[0]
                    actual = mis_registros.iloc[-1]

                    def get_val(row, keys_posibles, default=0.0):
                        for k in keys_posibles:
                            if k in row.index:
                                try:
                                    return float(row[k])
                                except Exception:
                                    pass
                        return default

                    peso_i = get_val(inicial, ["peso_kg", "peso"], 70.0)
                    peso_a = get_val(actual, ["peso_kg", "peso"], 70.0)
                    cint_i = get_val(inicial, ["cintura_cm", "cintura"], 80.0)
                    cint_a = get_val(actual, ["cintura_cm", "cintura"], 80.0)
                    gras_i = get_val(inicial, ["porcentaje_grasa", "grasa"], 20.0)
                    gras_a = get_val(actual, ["porcentaje_grasa", "grasa"], 20.0)

                    diff_peso = peso_a - peso_i
                    diff_cintura = cint_a - cint_i
                    diff_grasa = gras_a - gras_i

                    st.info(" Resumen desde tu primer registro hasta hoy:")

                    c1, c2, c3 = st.columns(3)
                    c1.metric("Variación de Peso", f"{peso_a} kg", f"{diff_peso:.1f} kg")
                    c2.metric("Variación de Cintura", f"{cint_a} cm", f"{diff_cintura:.1f} cm")
                    c3.metric("Variación % Grasa", f"{gras_a}%", f"{diff_grasa:.1f}%")

                mostrar_graficos_evolucion(mis_registros)

                st.markdown("---")
                st.markdown("### 📄 Informe de Evolución")
                st.caption("Genera un informe PDF con logo, resumen, comparativa completa y todo el historial antropométrico.")
                if st.button("📄 Generar Informe de Evolución en PDF", use_container_width=True, key="btn_pdf_cliente"):
                    try:
                        pdf_bytes = generar_informe_evolucion_pdf(
                            mis_registros,
                            st.session_state.get("nombre", "Cliente"),
                            user_id,
                            ruta_logo,
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

                st.markdown("####  Historial de Registros Completos")
                st.dataframe(mis_registros.astype(str), use_container_width=True)
            else:
                st.info("Aún no has registrado ninguna evaluación física.")

        # MIS CLASES
        elif opcion == " Mis Clases":
            st.subheader(" Mi Plan de Clases Personalizadas")
            mostrar_resumen_clases(df_clases, st.session_state["cedula"])

            resumen_clases = obtener_resumen_clases(df_clases, st.session_state["cedula"])
            registros_clases = resumen_clases["registros"]

            if not registros_clases.empty:
                st.markdown("#### 📅 Clases tomadas")
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
                opcion_admin = st.sidebar.radio(
                    "MENÚ ADMINISTRADOR",
                    [
                        "👤 Gestión de Clientes",
                        "️ Control de Clases",
                    ],
                )

                # GESTIÓN DE CLIENTES
                if opcion_admin == "👤 Gestión de Clientes":
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
                            st.markdown(f"### 📋 Información de: {u_info['nombre_completo']}")

                            info_col1, info_col2, info_col3 = st.columns(3)
                            info_col1.markdown(f"WhatsApp: {u_info.get('whatsapp', 'No registra')}")
                            info_col2.markdown(f"EPS: {str(u_info.get('eps', 'No registra')).upper()}")
                            info_col3.markdown(f"Fecha Registro: {u_info.get('fecha_registro', 'No registra')}")

                            st.markdown(f"Condiciones Médicas / Lesiones: {u_info.get('condiciones_medicas', 'Ninguna')}")

                            ws_url = link_whatsapp(u_info.get("whatsapp", ""), u_info["nombre_completo"])
                            st.markdown(f"[💬 Enviar Mensaje de Seguimiento por WhatsApp]({ws_url})")

                            # RESUMEN DE CLASES EN PERFIL
                            st.markdown("---")
                            mostrar_resumen_clases(df_clases, id_cliente, " Resumen de Clases")

                            # PAGOS Y MENSUALIDAD
                            st.markdown("---")
                            st.markdown("#### 💳 Pagos y Mensualidad")

                            pagos_cliente = pd.DataFrame()
                            if not df_pagos.empty and "cedula" in df_pagos.columns:
                                pagos_cliente = df_pagos[df_pagos["cedula"] == id_cliente].copy()

                            hoy = pd.Timestamp.today().normalize()

                            if not pagos_cliente.empty:
                                pagos_cliente["_fecha_dt"] = (
                                    pagos_cliente["fecha_pago"].apply(parsear_fecha)
                                    if "fecha_pago" in pagos_cliente.columns
                                    else pd.NaT
                                )
                                pagos_mes_actual = pagos_cliente[
                                    pagos_cliente["_fecha_dt"].notna()
                                    & (pagos_cliente["_fecha_dt"].dt.year == hoy.year)
                                    & (pagos_cliente["_fecha_dt"].dt.month == hoy.month)
                                ].copy()
                            else:
                                pagos_mes_actual = pd.DataFrame()

                            valor_mensualidad_actual = 0.0
                            if not pagos_cliente.empty and "valor_mensualidad" in pagos_cliente.columns:
                                mensualidades_validas = pd.to_numeric(
                                    pagos_cliente["valor_mensualidad"], errors="coerce"
                                ).dropna()
                                if not mensualidades_validas.empty:
                                    valor_mensualidad_actual = float(mensualidades_validas.iloc[-1])

                            if valor_mensualidad_actual <= 0:
                                valor_mensualidad_actual = 250000.0

                            total_pagado = 0.0
                            if not pagos_mes_actual.empty and "valor" in pagos_mes_actual.columns:
                                total_pagado = float(
                                    pd.to_numeric(pagos_mes_actual["valor"], errors="coerce")
                                    .fillna(0)
                                    .sum()
                                )

                            saldo_actual = max(valor_mensualidad_actual - total_pagado, 0.0)

                            if saldo_actual <= 0.001:
                                estado_pago = "🟢 PAGADO"
                            elif total_pagado > 0:
                                estado_pago = "🟡 ABONO"
                            else:
                                estado_pago = "🔴 PENDIENTE"

                            nombre_mes = hoy.strftime("%B").capitalize()

                            p1, p2, p3, p4 = st.columns(4)
                            p1.metric("Mensualidad", f"${valor_mensualidad_actual:,.0f}")
                            p2.metric("Pagado este mes", f"${total_pagado:,.0f}")
                            p3.metric("Saldo Pendiente", f"${saldo_actual:,.0f}")
                            p4.metric("Estado", estado_pago)
                            st.caption(f"📅 Estado de pagos correspondiente a {nombre_mes} de {hoy.year}.")

                            # REGISTRAR PAGO
                            with st.expander("➕ Registrar nuevo pago / abono", expanded=saldo_actual > 0):
                                with st.form(f"form_pago_{id_cliente}"):
                                    valor_mensualidad = st.number_input(
                                        "Valor de la mensualidad ($):",
                                        min_value=1.0,
                                        value=float(valor_mensualidad_actual),
                                        step=5000.0,
                                        format="%.0f",
                                    )

                                    saldo_para_nuevo_pago = max(float(valor_mensualidad) - total_pagado, 0.0)

                                    if total_pagado > 0:
                                        st.caption(
                                            f"Pagado este mes: ${total_pagado:,.0f} | Saldo según esta mensualidad: ${saldo_para_nuevo_pago:,.0f}"
                                        )

                                    valor_pago_default = saldo_para_nuevo_pago if saldo_para_nuevo_pago > 0 else 1.0
                                    valor_pago = st.number_input(
                                        "Valor del pago / abono ($):",
                                        min_value=1.0,
                                        value=float(valor_pago_default),
                                        step=5000.0,
                                        format="%.0f",
                                    )

                                    concepto_pago = st.text_input(
                                        "Concepto:",
                                        value="Abono mensualidad"
                                    ).strip()

                                    guardar_pago = st.form_submit_button("💾 Registrar Pago", use_container_width=True)

                                    if guardar_pago:
                                        try:
                                            valor_mensualidad = float(valor_mensualidad)
                                            valor_pago = float(valor_pago)

                                            if valor_mensualidad <= 0:
                                                st.error("❌ La mensualidad debe ser mayor que cero.")
                                                st.stop()
                                            if valor_pago <= 0:
                                                st.error("❌ El valor del pago debe ser mayor que cero.")
                                                st.stop()
                                            if not concepto_pago:
                                                concepto_pago = "Abono mensualidad"

                                            nuevo_total = total_pagado + valor_pago
                                            if nuevo_total > valor_mensualidad + 0.001:
                                                st.error(
                                                    f"❌ El abono supera el saldo pendiente. Saldo disponible: ${saldo_para_nuevo_pago:,.0f}."
                                                )
                                                st.stop()

                                            id_pago = f"{id_cliente}_{datetime.today().strftime('%Y%m%d%H%M%S%f')}"
                                            fecha_pago = datetime.today().strftime("%d-%m-%Y")

                                            fila_pago = [
                                                str(id_pago),
                                                str(id_cliente),
                                                str(fecha_pago),
                                                float(valor_pago),
                                                str(concepto_pago),
                                                float(valor_mensualidad),
                                            ]

                                            respuesta_pago = requests.post(
                                                URL_API,
                                                json={"action": "guardar_pago", "row": fila_pago},
                                                timeout=30,
                                            )
                                            respuesta_pago.raise_for_status()

                                            try:
                                                resultado_pago = respuesta_pago.json()
                                            except Exception:
                                                resultado_pago = {}

                                            if resultado_pago.get("status") == "error":
                                                st.error(
                                                    "❌ Google Apps Script reportó un error: "
                                                    + str(resultado_pago.get("message", "Error desconocido"))
                                                )
                                                st.stop()

                                            st.cache_data.clear()
                                            st.success("✅ Pago registrado correctamente.")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"❌ Error registrando el pago: {e}")

                            # HISTORIAL DE PAGOS
                            if not pagos_cliente.empty:
                                st.markdown("#### 📜 Historial de Pagos")
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
                            st.markdown("#### 📈 Historial y Progreso del Cliente")

                            if not df_historial.empty:
                                h_cliente = df_historial[df_historial["cedula"] == id_cliente].copy()
                                if not h_cliente.empty:
                                    mostrar_graficos_evolucion(h_cliente)

                                    st.markdown("### 📄 Informe de Evolución del Cliente")
                                    st.caption("Incluye logo, indicadores, medidas de brazos, pecho, cintura, glúteos/cadera, piernas y gemelos, además del historial.")
                                    if st.button("📄 Generar Informe PDF del Cliente", use_container_width=True, key=f"btn_pdf_admin_{id_cliente}"):
                                        try:
                                            pdf_bytes_admin = generar_informe_evolucion_pdf(
                                                h_cliente,
                                                u_info.get("nombre_completo", "Cliente"),
                                                id_cliente,
                                                ruta_logo,
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

                                    st.markdown("#### 📋 Registros en Tabla")
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
                elif opcion_admin == "️ Control de Clases":
                    st.subheader("️ Control de Clases Personalizadas")
                    st.info("Aquí el ADMIN configura el plan y registra manualmente cada clase realmente tomada.")

                    cliente_clase_sel = st.selectbox(
                        "👤 Seleccionar Cliente:",
                        clientes["cedula"].astype(str) + " - " + clientes["nombre_completo"].astype(str),
                        key="selector_cliente_clases",
                    )

                    id_cliente_clases = cliente_clase_sel.split(" - ")[0].strip()
                    nombre_cliente_clases = cliente_clase_sel.split(" - ", 1)[1]

                    st.markdown(f"### 👤 {nombre_cliente_clases}")
                    mostrar_resumen_clases(df_clases, id_cliente_clases)

                    resumen_actual = obtener_resumen_clases(df_clases, id_cliente_clases)

                    # ------------------------------------------------
                    # CONFIGURACIÓN DEL PLAN
                    # ------------------------------------------------
                    st.markdown("---")
                    st.markdown("#### ⚙️ Registrar un nuevo plan")

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
                                "Número de clases contratadas:",
                                min_value=1,
                                max_value=500,
                                value=(
                                    resumen_actual["clases_contratadas"]
                                    if resumen_actual["clases_contratadas"] > 0
                                    else 20
                                ),
                                step=1,
                            )

                        st.caption(
                            "Cada vez que guardes un plan se crea una nueva contratación "
                            "con un ID único. El plan anterior queda en el historial y "
                            "las clases del nuevo plan comienzan desde cero."
                        )

                        guardar_config_plan = st.form_submit_button(
                            "💾 Registrar nuevo plan",
                            use_container_width=True,
                        )

                        if guardar_config_plan:
                            try:
                                if not plan_cliente:
                                    st.error("❌ Debes indicar el tipo o nombre del plan.")
                                    st.stop()

                                fecha_hoy_str = datetime.today().strftime("%d-%m-%Y")

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
                                    "Nueva contratación",
                                    int(clases_contratadas),
                                ]

                                respuesta_config = requests.post(
                                    URL_API,
                                    json={
                                        "action": "guardar_plan",
                                        "row": fila_config,
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

                                st.cache_data.clear()
                                st.success(
                                    "✅ Nuevo plan registrado correctamente."
                                )
                                st.rerun()

                            except Exception as e:
                                st.error(f"❌ Error registrando el nuevo plan: {e}")

                    # ------------------------------------------------
                    # REGISTRAR CLASE TOMADA
                    # ------------------------------------------------
                    st.markdown("---")
                    st.markdown("#### 📅 Registrar clase tomada")

                    if (
                        resumen_actual["clases_contratadas"] > 0
                        and resumen_actual["clases_tomadas"] >= resumen_actual["clases_contratadas"]
                    ):
                        st.warning("⚠️ Este cliente ya utilizó todas las clases contratadas.")

                    with st.form(f"form_registro_clase_{id_cliente_clases}"):
                        fecha_clase = st.date_input(
                            "📅 Fecha de la clase tomada:",
                            value=date.today(),
                            max_value=date.today(),
                            format="DD-MM-YYYY",
                        )

                        registrar_clase = st.form_submit_button(
                            " Registrar Clase Tomada",
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
                                ]

                                respuesta_clase = requests.post(
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

                                st.cache_data.clear()
                                st.success("✅ Clase registrada correctamente.")
                                st.rerun()

                            except Exception as e:
                                st.error(f"❌ Error registrando la clase: {e}")

                    # ------------------------------------------------
                    # HISTORIAL DE CLASES
                    # ------------------------------------------------
                    st.markdown("---")
                    st.markdown("#### 📋 Historial de clases tomadas")

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
