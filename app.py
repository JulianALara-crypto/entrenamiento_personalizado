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

URL_API = (
    "https://script.google.com/macros/s/AKfycbxOo4IBYU5XR9exMTEotOlkvqhWXLJWBEIWT5s0MK3FXi0dbkN6H7KQXaRuK4Vv_Ovs/exec"
)


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
# FUNCIÓN FORMATEAR FECHA Y CÉDULA
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


def normalizar_cedula(valor):
    if pd.isna(valor):
        return ""
    texto = str(valor).strip()
    if texto.endswith(".0"):
        texto = texto[:-2]
    return texto


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
# CALCULAR MÉTRICAS
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

    estatura_m = estatura_cm / 100.0
    imc = peso / (estatura_m ** 2)

    try:
        sexo_str = str(sexo).strip().capitalize()
        if sexo_str == "Femenino":
            valor_log = cintura + cadera - cuello
            if valor_log <= 1.0:
                valor_log = 1.0
            pct_grasa = (
                163.205 * math.log10(valor_log)
                - 97.684 * math.log10(estatura_cm)
                - 78.387
            )
        else:
            valor_log = cintura - cuello
            if valor_log <= 1.0:
                valor_log = 1.0
            pct_grasa = (
                86.010 * math.log10(valor_log)
                - 70.041 * math.log10(estatura_cm)
                + 36.760
            )

        pct_grasa = max(min(pct_grasa, 60.0), 3.0)

    except Exception:
        pct_grasa = 15.0 if str(sexo).strip().capitalize() == "Masculino" else 24.0

    masa_magra_kg = peso * (1.0 - (pct_grasa / 100.0))
    tmb_real = 370.0 + (21.6 * masa_magra_kg)
    mantenimiento = tmb_real * 1.375

    if meta == "Perder Grasa":
        calorias = mantenimiento - 400.0
    elif meta == "Ganar Músculo":
        calorias = mantenimiento + 350.0
    else:
        calorias = mantenimiento

    sexo_str = str(sexo).strip().capitalize()
    if sexo_str == "Femenino":
        tmb_esperada_edad = (10.0 * peso) + (6.25 * estatura_cm) - (5.0 * edad) - 161.0
    else:
        tmb_esperada_edad = (10.0 * peso) + (6.25 * estatura_cm) - (5.0 * edad) + 5.0

    diferencia_tmb = tmb_real - tmb_esperada_edad
    edad_metabolica_calc = edad - (diferencia_tmb / 20.0)
    edad_metabolica = int(round(max(18, min(80, edad_metabolica_calc))))

    imc = float(round(imc, 2))
    pct_grasa = float(round(pct_grasa, 2))
    calorias = int(round(calorias))

    return (
        imc,
        pct_grasa,
        calorias,
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
# CARGAR BASE DE DATOS
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

        def procesar_raw(nombre_hoja, columnas_defecto):
            raw = res.get(nombre_hoja, [])
            if len(raw) > 1:
                cols = [str(c).strip().lower() for c in raw[0]]
                df = pd.DataFrame(raw[1:], columns=cols)
                return df.loc[:, ~df.columns.duplicated()]
            return pd.DataFrame(columns=columnas_defecto)

        df_u = procesar_raw("usuarios", [
            "cedula", "nombre_completo", "whatsapp", "eps",
            "condiciones_medicas", "rol", "password", "fecha_registro"
        ])

        df_m = procesar_raw("historial", [
            "id_registro", "fecha_evaluacion", "cedula", "edad", "sexo", "meta",
            "peso_kg", "estatura_cm", "cuello_cm", "hombros_cm", "bicep_der_cm",
            "bicep_izq_cm", "pecho_cm", "cintura_cm", "cadera_cm", "pierna_der_cm",
            "pierna_izq_cm", "gemelo_der_cm", "gemelo_izq_cm", "imc",
            "porcentaje_grasa", "calorias_objetivo", "edad_metabolica"
        ])

        df_p = procesar_raw("pagos", [
            "id_pago", "cedula", "fecha_pago", "valor", "concepto", "valor_mensualidad"
        ])

        df_c = procesar_raw("clases", [
            "id_clase", "cedula", "nombre_completo", "fecha_clase",
            "tipo_plan", "periodo", "estado", "id_plan"
        ])

        df_planes = procesar_raw("planes", [
            "id_plan", "cedula", "nombre_completo", "tipo_plan",
            "fecha_inicio", "fecha_fin", "estado", "observaciones", "clases_incluidas"
        ])

        for df in (df_u, df_m, df_p, df_c, df_planes):
            if not df.empty and "cedula" in df.columns:
                df["cedula"] = df["cedula"].apply(normalizar_cedula)

        columnas_numericas_medidas = [
            "edad", "peso_kg", "estatura_cm", "cuello_cm", "hombros_cm",
            "bicep_der_cm", "bicep_izq_cm", "pecho_cm", "cintura_cm",
            "cadera_cm", "pierna_der_cm", "pierna_izq_cm", "gemelo_der_cm",
            "gemelo_izq_cm", "imc", "porcentaje_grasa", "calorias_objetivo", "edad_metabolica"
        ]

        for columna in columnas_numericas_medidas:
            if columna in df_m.columns:
                df_m[columna] = pd.to_numeric(df_m[columna], errors="coerce")

        for columna in ["valor", "valor_mensualidad"]:
            if columna in df_p.columns:
                df_p[columna] = pd.to_numeric(df_p[columna], errors="coerce")

        if not df_c.empty and "periodo" in df_c.columns:
            df_c["periodo"] = pd.to_numeric(df_c["periodo"], errors="coerce")

        if not df_u.empty and "fecha_registro" in df_u.columns:
            df_u["fecha_registro"] = df_u["fecha_registro"].apply(formatear_fecha)

        if not df_m.empty and "fecha_evaluacion" in df_m.columns:
            df_m["fecha_evaluacion"] = df_m["fecha_evaluacion"].apply(formatear_fecha)

        if not df_p.empty and "fecha_pago" in df_p.columns:
            df_p["fecha_pago"] = df_p["fecha_pago"].apply(formatear_fecha)

        if not df_c.empty and "fecha_clase" in df_c.columns:
            df_c["fecha_clase"] = df_c["fecha_clase"].apply(formatear_fecha)

        return df_u, df_m, df_p, df_c, df_planes

    except Exception as e:
        st.error(f"Error procesando base de datos: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()


# ============================================================
# GRÁFICOS
# ============================================================

def mostrar_graficos_evolucion(df_filtrado):
    if df_filtrado.empty:
        return

    df_graficos = df_filtrado.copy()

    columnas_num = [
        "peso_kg", "porcentaje_grasa", "cintura_cm", "pecho_cm",
        "cadera_cm", "bicep_der_cm", "bicep_izq_cm",
    ]

    for col in columnas_num:
        if col in df_graficos.columns:
            df_graficos[col] = pd.to_numeric(df_graficos[col], errors="coerce")

    df_graficos["fecha_dt"] = pd.to_datetime(
        df_graficos["fecha_evaluacion"],
        format="%d-%m-%Y",
        errors="coerce"
    )

    if df_graficos["fecha_dt"].isna().any():
        df_graficos["fecha_dt"] = pd.to_datetime(
            df_graficos["fecha_evaluacion"],
            errors="coerce"
        )

    df_graficos = (
        df_graficos
        .dropna(subset=["fecha_dt"])
        .sort_values(by="fecha_dt")
    )

    df_graficos["Fecha"] = df_graficos["fecha_dt"].dt.strftime("%d-%m-%Y")

    st.markdown("### 📈 Gráficas de Evolución Temporal")

    tab1, tab2, tab3 = st.tabs([
        "⚖️ Peso y Composición",
        "📏 Perímetros Principales",
        "💪 Extremidades",
    ])

    with tab1:
        col_g1, col_g2 = st.columns(2)

        with col_g1:
            st.markdown("<p style='text-align: center;'>Evolución del Peso Corporal (kg)</p>", unsafe_allow_html=True)
            df_peso = df_graficos.set_index("Fecha")[["peso_kg"]].rename(columns={"peso_kg": "Peso (kg)"})
            st.line_chart(df_peso)

        with col_g2:
            st.markdown("<p style='text-align: center;'>Evolución del % de Grasa Corporal</p>", unsafe_allow_html=True)
            df_grasa = df_graficos.set_index("Fecha")[["porcentaje_grasa"]].rename(columns={"porcentaje_grasa": "% Grasa"})
            st.line_chart(df_grasa)

    with tab2:
        st.markdown("<p style='text-align: center;'>Evolución de Torso y Cintura (cm)</p>", unsafe_allow_html=True)
        columnas_perimetros = []
        nombres_perimetros = {}

        if "cintura_cm" in df_graficos.columns:
            columnas_perimetros.append("cintura_cm")
            nombres_perimetros["cintura_cm"] = "Cintura"

        if "pecho_cm" in df_graficos.columns:
            columnas_perimetros.append("pecho_cm")
            nombres_perimetros["pecho_cm"] = "Pecho"

        if "cadera_cm" in df_graficos.columns:
            columnas_perimetros.append("cadera_cm")
            nombres_perimetros["cadera_cm"] = "Cadera/Glúteos"

        if columnas_perimetros:
            df_peri = df_graficos.set_index("Fecha")[columnas_perimetros].rename(columns=nombres_perimetros)
            st.line_chart(df_peri)

    with tab3:
        st.markdown("<p style='text-align: center;'>Evolución de Brazos (cm)</p>", unsafe_allow_html=True)
        columnas_brazos = []
        nombres_brazos = {}

        if "bicep_der_cm" in df_graficos.columns:
            columnas_brazos.append("bicep_der_cm")
            nombres_brazos["bicep_der_cm"] = "Bícep Derecho"

        if "bicep_izq_cm" in df_graficos.columns:
            columnas_brazos.append("bicep_izq_cm")
            nombres_brazos["bicep_izq_cm"] = "Bícep Izquierdo"

        if columnas_brazos:
            df_brz = df_graficos.set_index("Fecha")[columnas_brazos].rename(columns=nombres_brazos)
            st.line_chart(df_brz)


# ============================================================
# RESUMEN DE CLASES
# ============================================================

def obtener_resumen_clases(df_clases, df_planes, cedula):
    cedula_str = normalizar_cedula(cedula)

    resultado = {
        "plan": "Sin Plan",
        "clases_contratadas": 0,
        "clases_tomadas": 0,
        "clases_restantes": 0,
        "porcentaje": 0.0,
        "id_plan": None,
        "registros": pd.DataFrame()
    }

    # 1. Obtener plan ACTIVO
    if df_planes is not None and not df_planes.empty and "cedula" in df_planes.columns:
        planes_cliente = df_planes[
            (df_planes["cedula"].apply(normalizar_cedula) == cedula_str) &
            (df_planes["estado"].astype(str).str.strip().str.lower() == "activo")
        ]

        if not planes_cliente.empty:
            plan_activo = planes_cliente.iloc[-1]
            resultado["id_plan"] = str(plan_activo.get("id_plan", "")).strip()
            resultado["plan"] = str(plan_activo.get("tipo_plan", "Personalizado"))
            resultado["clases_contratadas"] = int(pd.to_numeric(plan_activo.get("clases_incluidas", 0), errors="coerce"))

    # 2. Obtener clases tomadas SOLO asociadas al id_plan ACTIVO
    if df_clases is not None and not df_clases.empty and "cedula" in df_clases.columns:
        df_clases_cliente = df_clases[df_clases["cedula"].apply(normalizar_cedula) == cedula_str]

        if resultado["id_plan"] and "id_plan" in df_clases_cliente.columns:
            registros = df_clases_cliente[
                (df_clases_cliente["id_plan"].astype(str).str.strip() == resultado["id_plan"]) &
                (df_clases_cliente["estado"].astype(str).str.strip().str.lower() == "tomada")
            ]
        else:
            registros = df_clases_cliente[
                df_clases_cliente["estado"].astype(str).str.strip().str.lower() == "tomada"
            ]

        resultado["registros"] = registros
        resultado["clases_tomadas"] = len(registros)

    resultado["clases_restantes"] = max(0, resultado["clases_contratadas"] - resultado["clases_tomadas"])

    if resultado["clases_contratadas"] > 0:
        pct = (resultado["clases_tomadas"] / resultado["clases_contratadas"]) * 100.0
        resultado["porcentaje"] = min(pct, 100.0)

    return resultado


def mostrar_resumen_clases(
    df_clases,
    df_planes,
    cedula,
    titulo="🏋️ Clases Personalizadas"
):
    resumen = obtener_resumen_clases(df_clases, df_planes, cedula)

    st.markdown(f"### {titulo}")

    if resumen["clases_contratadas"] <= 0:
        st.info("Este cliente todavía no tiene un plan de clases activo configurado.")
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

        cedula_ingreso = st.text_input("Número de Cédula / ID:").strip()
        pass_ingreso = st.text_input("Contraseña:", type="password").strip()

        if st.button("Ingresar", use_container_width=True):
            if cedula_ingreso == "admin" and pass_ingreso == "admin123456":
                st.session_state["autenticado"] = True
                st.session_state["rol"] = "Admin"
                st.session_state["cedula"] = "ADMIN"
                st.session_state["nombre"] = "JULIAN AVILA"
                st.rerun()
            else:
                df_usuarios, _, _, _, _ = cargar_bd()

                if not df_usuarios.empty and cedula_ingreso in df_usuarios["cedula"].values:
                    u = df_usuarios[df_usuarios["cedula"] == cedula_ingreso].iloc[0]

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
                df_usuarios, _, _, _, _ = cargar_bd()

                if not reg_cedula or not reg_nombre or not reg_pass:
                    st.error("⚠️ Cédula, Nombre y Contraseña son obligatorios.")
                elif not df_usuarios.empty and reg_cedula in df_usuarios["cedula"].values:
                    st.error("❌ Esta cédula ya está registrada.")
                else:
                    nueva_fila = [
                        reg_cedula,
                        reg_nombre,
                        reg_whatsapp,
                        reg_eps if reg_eps else "NINGUNA",
                        reg_condiciones if reg_condiciones else "NINGUNA",
                        "Cliente",
                        reg_pass,
                        datetime.today().strftime("%d-%m-%Y"),
                    ]

                    try:
                        respuesta_registro = requests.post(
                            URL_API,
                            json={
                                "action": "registrar_usuario",
                                "row": nueva_fila,
                            },
                            timeout=30,
                        )
                        respuesta_registro.raise_for_status()
                        st.cache_data.clear()
                        st.success("¡Perfil creado con éxito! Ya puedes iniciar sesión.")
                    except Exception as e:
                        st.error(f"Error al guardar usuario: {e}")

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

    df_usuarios, df_historial, df_pagos, df_clases, df_planes = cargar_bd()

    # ========================================================
    # CLIENTE
    # ========================================================
    if st.session_state["rol"] == "Cliente":
        opcion = st.sidebar.radio(
            "MENÚ",
            [
                "📏 Registrar Medidas Hoy",
                "📊 Ver Mi Progreso",
                "🏋️ Mis Clases",
            ],
        )

        # REGISTRAR MEDIDAS
        if opcion == "📏 Registrar Medidas Hoy":
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
                st.write("### 📏 Medidas Corporales (cm) — Ordenado de Cabeza a Pies")

                col_izq, col_der = st.columns(2)

                with col_izq:
                    st.markdown("💥 Tren Superior y Torso")
                    cuello = st.number_input("1. Cuello:", 20.0, 60.0, 38.0)
                    hombros = st.number_input("2. Hombros:", 50.0, 180.0, 110.0)
                    pecho = st.number_input("3. Pecho:", 50.0, 180.0, 95.0)
                    cintura = st.number_input("4. Cintura / Abdomen:", 40.0, 180.0, 80.0)
                    cadera = st.number_input("5. Glúteos / Cadera:", 40.0, 180.0, 95.0)

                with col_der:
                    st.markdown("💪 Extremidades (Brazos y Piernas)")
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
                                f"⚠️ El IMC calculated ({imc}) está fuera de un rango razonable. Revisa peso y estatura."
                            )
                            st.stop()

                        id_reg = f"{st.session_state['cedula']}_{datetime.today().strftime('%Y%m%d%H%M')}"
                        fecha_hoy = datetime.today().strftime("%d-%m-%Y")

                        fila_medidas = [
                            str(id_reg), str(fecha_hoy), str(st.session_state["cedula"]),
                            int(edad), str(sexo), str(meta), float(peso), float(estatura),
                            float(cuello), float(hombros), float(bicep_der), float(bicep_izq),
                            float(pecho), float(cintura), float(cadera), float(pierna_der),
                            float(pierna_izq), float(gemelo_der), float(gemelo_izq),
                            float(imc), float(grasa), int(cals), int(edad_bio),
                        ]

                        respuesta_medidas = requests.post(
                            URL_API,
                            json={"action": "guardar_medidas", "row": fila_medidas},
                            timeout=30,
                        )
                        respuesta_medidas.raise_for_status()

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
        elif opcion == "📊 Ver Mi Progreso":
            st.subheader("📉 Comparativa de Evolución")

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

                    st.info("📊 Resumen desde tu primer registro hasta hoy:")

                    c1, c2, c3 = st.columns(3)
                    c1.metric("Variación de Peso", f"{peso_a} kg", f"{peso_a - peso_i:.1f} kg")
                    c2.metric("Variación de Cintura", f"{cint_a} cm", f"{cint_a - cint_i:.1f} cm")
                    c3.metric("Variación % Grasa", f"{gras_a}%", f"{gras_a - gras_i:.1f}%")

                mostrar_graficos_evolucion(mis_registros)

                st.markdown("#### 📋 Historial de Registros Completos")
                st.dataframe(mis_registros.astype(str), use_container_width=True)
            else:
                st.info("Aún no has registrado ninguna evaluación física.")

        # MIS CLASES
        elif opcion == "🏋️ Mis Clases":
            st.subheader("🏋️ Mi Plan de Clases Personalizadas")
            mostrar_resumen_clases(df_clases, df_planes, st.session_state["cedula"])

            resumen_clases = obtener_resumen_clases(df_clases, df_planes, st.session_state["cedula"])
            registros_clases = resumen_clases["registros"]

            if not registros_clases.empty:
                st.markdown("#### 📅 Clases tomadas de mi plan activo")
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
                st.info("Todavía no tienes clases registradas en este plan.")

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
                        "🏋️ Control de Clases",
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
                            mostrar_resumen_clases(df_clases, df_planes, id_cliente, "🏋️ Resumen de Clases")

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

                                            id_pago = f"{id_cliente}_{datetime.today().strftime('%Y%m%d%H%M%S%f')}"
                                            fecha_pago = datetime.today().strftime("%d-%m-%Y")

                                            fila_pago = [
                                                str(id_pago), str(id_cliente), str(fecha_pago),
                                                float(valor_pago), str(concepto_pago), float(valor_mensualidad),
                                            ]

                                            respuesta_pago = requests.post(
                                                URL_API,
                                                json={"action": "guardar_pago", "row": fila_pago},
                                                timeout=30,
                                            )
                                            respuesta_pago.raise_for_status()

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
                                    pagos_mostrar["_fecha_dt"] = pagos_mostrar["fecha_pago"].apply(parsear_fecha)
                                pagos_mostrar = pagos_mostrar.sort_values(by="_fecha_dt", ascending=False).drop(columns=["_fecha_dt"], errors="ignore")

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
                elif opcion_admin == "🏋️ Control de Clases":
                    st.subheader("🏋️ Control de Clases Personalizadas")
                    st.info("Aquí el ADMIN configura el plan y registra manualmente cada clase realmente tomada.")

                    cliente_clase_sel = st.selectbox(
                        "👤 Seleccionar Cliente:",
                        clientes["cedula"].astype(str) + " - " + clientes["nombre_completo"].astype(str),
                        key="selector_cliente_clases",
                    )

                    id_cliente_clases = cliente_clase_sel.split(" - ")[0].strip()
                    nombre_cliente_clases = cliente_clase_sel.split(" - ", 1)[1]

                    st.markdown(f"### 👤 {nombre_cliente_clases}")
                    mostrar_resumen_clases(df_clases, df_planes, id_cliente_clases)

                    resumen_actual = obtener_resumen_clases(df_clases, df_planes, id_cliente_clases)

                    # ------------------------------------------------
                    # CONFIGURACIÓN DEL PLAN
                    # ------------------------------------------------
                    st.markdown("---")
                    st.markdown("#### ⚙️ Configuración del plan")

                    with st.form(f"form_config_clases_{id_cliente_clases}"):
                        col_plan1, col_plan2 = st.columns(2)

                        with col_plan1:
                            opciones_plan = ["Premium", "Personalizado", "Otro"]
                            plan_actual = resumen_actual["plan"]
                            plan_cliente = st.selectbox(
                                "Plan:",
                                opciones_plan,
                                index=(
                                    opciones_plan.index(plan_actual)
                                    if plan_actual in opciones_plan
                                    else 0
                                ),
                            )

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
                            "La configuración inicia un nuevo ciclo. Las clases anteriores dejan de contar para este nuevo plan."
                        )

                        guardar_config_plan = st.form_submit_button(
                            "💾 Guardar configuración del plan",
                            use_container_width=True,
                        )

                        if guardar_config_plan:
                            try:
                                fecha_hoy_str = datetime.today().strftime('%d-%m-%Y')
                                id_plan_nuevo = f"PLAN_{id_cliente_clases}_{datetime.today().strftime('%Y%m%d%H%M%S')}"

                                fila_config = [
                                    str(id_plan_nuevo),             # 0: ID Plan (NUEVO)
                                    str(id_cliente_clases),         # 1: Cédula
                                    str(nombre_cliente_clases),     # 2: Nombre
                                    str(plan_cliente),              # 3: Tipo de Plan
                                    fecha_hoy_str,                  # 4: Fecha Inicio
                                    "",                             # 5: Fecha Fin (vacío)
                                    "Activo",                       # 6: Estado
                                    "Configuración del plan",       # 7: Observaciones
                                    int(clases_contratadas),        # 8: Clases Incluidas
                                ]

                                respuesta_config = requests.post(
                                    URL_API,
                                    json={
                                        "action": "registrar_plan",
                                        "row": fila_config,
                                    },
                                    timeout=30,
                                )
                                respuesta_config.raise_for_status()

                                st.cache_data.clear()
                                st.success("✅ Configuración del plan guardada correctamente.")
                                st.rerun()

                            except Exception as e:
                                st.error(f"❌ Error guardando el plan: {e}")

                    # ------------------------------------------------
                    # REGISTRAR CLASE TOMADA
                    # ------------------------------------------------
                    st.markdown("---")
                    st.markdown("#### 📅 Registrar clase tomada")

                    if (
                        resumen_actual["clases_contratadas"] > 0
                        and resumen_actual["clases_tomadas"] >= resumen_actual["clases_contratadas"]
                    ):
                        st.warning("⚠️ Este cliente ya utilizó todas las clases contratadas de su plan activo. Por favor configura un nuevo plan.")

                    with st.form(f"form_registro_clase_{id_cliente_clases}"):
                        fecha_clase = st.date_input(
                            "📅 Fecha de la clase tomada:",
                            value=date.today(),
                            max_value=date.today(),
                            format="DD-MM-YYYY",
                        )

                        registrar_clase = st.form_submit_button(
                            "🏋️ Registrar Clase Tomada",
                            use_container_width=True,
                        )

                        if registrar_clase:
                            try:
                                if resumen_actual["clases_contratadas"] <= 0:
                                    st.error("❌ Primero debes configurar el plan y el número de clases contratadas.")
                                    st.stop()

                                if resumen_actual["clases_tomadas"] >= resumen_actual["clases_contratadas"]:
                                    st.error("❌ El cliente ya utilizó todas las clases de su plan activo.")
                                    st.stop()

                                fecha_clase_str = fecha_clase.strftime("%d-%m-%Y")
                                clases_cliente = resumen_actual["registros"]

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

                                fila_clase = [
                                    str(id_clase),
                                    str(id_cliente_clases),
                                    str(nombre_cliente_clases),
                                    str(fecha_clase_str),
                                    str(resumen_actual["plan"]),
                                    "",
                                    "Tomada",
                                    str(resumen_actual["id_plan"]) # ID del plan activo
                                ]

                                respuesta_clase = requests.post(
                                    URL_API,
                                    json={
                                        "action": "registrar_clase",
                                        "row": fila_clase,
                                    },
                                    timeout=30,
                                )
                                respuesta_clase.raise_for_status()

                                st.cache_data.clear()
                                st.success("✅ Clase registrada correctamente.")
                                st.rerun()

                            except Exception as e:
                                st.error(f"❌ Error registrando la clase: {e}")

                    # ------------------------------------------------
                    # HISTORIAL DE CLASES
                    # ------------------------------------------------
                    st.markdown("---")
                    st.markdown("#### 📋 Historial de clases tomadas del plan activo")

                    resumen_historial = obtener_resumen_clases(df_clases, df_planes, id_cliente_clases)
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
                        st.info("Este cliente todavía no tiene clases registradas en este plan.")
            else:
                st.info("No hay clientes registrados actualmente.")
