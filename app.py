import math
import os
import urllib.parse
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
from PIL import Image

# 🔗 TU URL DE GOOGLE APPS SCRIPT
URL_API = "https://script.google.com/macros/s/AKfycbzE2qSC4oR8zDa1pTyTjQfKFxsTHepWC3iW9JriiQ75laCFCQbs7iaceuH9sVP-XuDo/exec"

ruta_logo = "logo.png"
icono_pestana = Image.open(ruta_logo) if os.path.exists(ruta_logo) else ""

st.set_page_config(
    page_title="Personal Training y Evolution Tracker Julian Avila",
    page_icon=icono_pestana,
    layout="wide",
)

# Estilos visuales en modo oscuro (Corregido para negro puro #000000)
st.markdown("""
    <style>
        .stApp { background-color: #000000; }
        h1, h2, h3, h4 { color: #ffffff !important; text-align: center; }
        p, label, .stMarkdown { color: #dddddd !important; }
        div[data-testid="stDecoration"] { display: none; }
    </style>
""", unsafe_allow_html=True)


# --- FUNCIÓN AUXILIAR PARA PARSEAR Y FORMATAR FECHAS A DD-MM-YYYY ---
def formatear_fecha(valor_fecha):
    if pd.isna(valor_fecha) or not valor_fecha or str(valor_fecha).strip() == "":
        return ""
    try:
        # pd.to_datetime maneja ISO 8601 (2026-07-30T07:00:00.000Z), YYYY-MM-DD, etc.
        dt = pd.to_datetime(valor_fecha, errors="coerce", utc=True)
        if pd.isna(dt):
            return str(valor_fecha)
        return dt.strftime("%d-%m-%Y")
    except Exception:
        return str(valor_fecha)


# --- MOSTRAR LOGO CENTRADO EN LA CABECERA ---
if os.path.exists(ruta_logo):
    col_l1, col_l2, col_l3 = st.columns(3)
    with col_l2:
        st.image(Image.open(ruta_logo), use_column_width=True)


# --- FUNCIONES DE CÁLCULO FÍSICO Y SALUD ---
def calcular_metricas(
    peso, estatura_cm, edad, sexo, cuello, cintura, cadera, meta
):
    estatura_m = estatura_cm / 100.0
    imc = peso / (estatura_m**2)

    try:
        if sexo == "Masculino":
            valor_log = cintura - cuello
            if valor_log <= 0:
                valor_log = 1.0
            densidad = (
                1.0324
                - 0.19077 * math.log10(valor_log)
                + 0.15456 * math.log10(estatura_cm)
            )
            pct_grasa = (495 / densidad) - 450
        else:
            valor_log = cintura + cadera - cuello
            if valor_log <= 0:
                valor_log = 1.0
            densidad = (
                1.29579
                - 0.35004 * math.log10(valor_log)
                + 0.22100 * math.log10(estatura_cm)
            )
            pct_grasa = (495 / densidad) - 450
        pct_grasa = max(min(pct_grasa, 60.0), 3.0)
    except Exception:
        pct_grasa = 15.0 if sexo == "Masculino" else 24.0

    if sexo == "Masculino":
        tmb = (10 * peso) + (6.25 * estatura_cm) - (5 * edad) + 5
    else:
        tmb = (10 * peso) + (6.25 * estatura_cm) - (5 * edad) - 161

    mantenimiento = tmb * 1.375

    if meta == "Perder Grasa":
        calorias = mantenimiento - 400
    elif meta == "Ganar Músculo":
        calorias = mantenimiento + 350
    else:
        calorias = mantenimiento

    desvio_imc = max(0, imc - 22.0)
    desvio_grasa = max(0, pct_grasa - (15.0 if sexo == "Masculino" else 22.0))
    edad_metabolica = int(edad + (desvio_imc * 0.6) + (desvio_grasa * 0.4))

    return round(imc, 1), round(pct_grasa, 1), int(calorias), edad_metabolica


# --- FUNCIÓN PARA LIMPIAR Y GENERAR WHATSAPP ---
def link_whatsapp(num_celular, nombre_cliente, mensaje=""):
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
        mensaje = f"💪 ¡Hola {nombre_cliente}! Te saludamos de tu plan de Entrenamiento Personalizado. ¡Queremos revisar cómo van tus avances!"

    return f"https://wa.me/{num_limpio}?text={urllib.parse.quote(mensaje)}"


# --- CARGAR DATOS DESDE GOOGLE SHEETS ---
@st.cache_data(ttl=2)
def cargar_bd():
    try:
        res = requests.get(URL_API).json()

        # Usuarios
        usuarios_raw = res.get("usuarios", [])
        if len(usuarios_raw) > 1:
            columnas_u = [str(c).strip().lower() for c in usuarios_raw[0]]
            df_u = pd.DataFrame(usuarios_raw[1:], columns=columnas_u)
            df_u = df_u.loc[:, ~df_u.columns.duplicated()]
        else:
            df_u = pd.DataFrame(
                columns=[
                    "cedula",
                    "nombre_completo",
                    "whatsapp",
                    "eps",
                    "condiciones_medicas",
                    "rol",
                    "password",
                    "fecha_registro",
                ]
            )

        # Historial
        historial_raw = res.get("historial", [])
        if len(historial_raw) > 1:
            columnas_h = [str(c).strip().lower() for c in historial_raw[0]]
            df_m = pd.DataFrame(historial_raw[1:], columns=columnas_h)
            df_m = df_m.loc[:, ~df_m.columns.duplicated()]
        else:
            df_m = pd.DataFrame(
                columns=[
                    "id_registro",
                    "fecha_evaluacion",
                    "cedula",
                    "edad",
                    "sexo",
                    "meta",
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
            )

        # Limpiar formatos de cédula
        if "cedula" in df_u.columns:
            df_u["cedula"] = (
                df_u["cedula"]
                .astype(str)
                .str.replace(r"\.0$", "", regex=True)
                .str.strip()
            )
        if not df_m.empty and "cedula" in df_m.columns:
            df_m["cedula"] = (
                df_m["cedula"]
                .astype(str)
                .str.replace(r"\.0$", "", regex=True)
                .str.strip()
            )

        # --- FORMATEAR FECHAS A DD-MM-YYYY EN AMBOS DATAFRAMES ---
        if not df_u.empty and "fecha_registro" in df_u.columns:
            df_u["fecha_registro"] = df_u["fecha_registro"].apply(formatear_fecha)

        if not df_m.empty and "fecha_evaluacion" in df_m.columns:
            df_m["fecha_evaluacion"] = df_m["fecha_evaluacion"].apply(formatear_fecha)

        return df_u, df_m
    except Exception as e:
        st.error(f"Error procesando base de datos: {e}")
        return pd.DataFrame(), pd.DataFrame()


# --- FUNCIÓN PARA GENERAR GRÁFICOS INTERACTIVOS ---
def mostrar_graficos_evolucion(df_filtrado):
    if df_filtrado.empty:
        return

    df_graficos = df_filtrado.copy()
    columnas_num = [
        "peso_kg",
        "porcentaje_grasa",
        "cintura_cm",
        "pecho_cm",
        "cadera_cm",
        "bicep_der_cm",
        "bicep_izq_cm",
    ]
    for col in columnas_num:
        if col in df_graficos.columns:
            df_graficos[col] = pd.to_numeric(df_graficos[col], errors="coerce")

    # Convertir a datetime para ordenar correctamente en los gráficos
    df_graficos["fecha_dt"] = pd.to_datetime(
        df_graficos["fecha_evaluacion"], format="%d-%m-%Y", errors="coerce"
    )
    # Fallback por si venían con otro formato no parseado
    if df_graficos["fecha_dt"].isna().any():
        df_graficos["fecha_dt"] = pd.to_datetime(
            df_graficos["fecha_evaluacion"], errors="coerce"
        )

    df_graficos = df_graficos.dropna(subset=["fecha_dt"]).sort_values(
        by="fecha_dt"
    )
    df_graficos["Fecha"] = df_graficos["fecha_dt"].dt.strftime("%d-%m-%Y")

    st.markdown("### 📈 Gráficas de Evolución Temporal")
    tab1, tab2, tab3 = st.tabs(
        [
            "⚖️ Peso y Composición",
            "📏 Perímetros Principales",
            "💪 Extremidades",
        ]
    )

    with tab1:
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.markdown(
                "<p style='text-align: center;'>Evolución del Peso Corporal (kg)</p>",
                unsafe_allow_html=True,
            )
            df_peso = df_graficos.set_index("Fecha")[["peso_kg"]].rename(
                columns={"peso_kg": "Peso (kg)"}
            )
            st.line_chart(df_peso)
        with col_g2:
            st.markdown(
                "<p style='text-align: center;'>Evolución del % de Grasa Corporal</p>",
                unsafe_allow_html=True,
            )
            df_grasa = df_graficos.set_index("Fecha")[
                ["porcentaje_grasa"]
            ].rename(columns={"porcentaje_grasa": "% Grasa"})
            st.line_chart(df_grasa)

    with tab2:
        st.markdown(
            "<p style='text-align: center;'>Evolución de Torso y Cintura (cm)</p>",
            unsafe_allow_html=True,
        )
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
            df_peri = df_graficos.set_index("Fecha")[columnas_perimetros].rename(
                columns=nombres_perimetros
            )
            st.line_chart(df_peri)

    with tab3:
        st.markdown(
            "<p style='text-align: center;'>Evolución de Brazos (cm)</p>",
            unsafe_allow_html=True,
        )
        columnas_brazos = []
        nombres_brazos = {}
        if "bicep_der_cm" in df_graficos.columns:
            columnas_brazos.append("bicep_der_cm")
            nombres_brazos["bicep_der_cm"] = "Bícep Derecho"
        if "bicep_izq_cm" in df_graficos.columns:
            columnas_brazos.append("bicep_izq_cm")
            nombres_brazos["bicep_izq_cm"] = "Bícep Izquierdo"

        if columnas_brazos:
            df_brz = df_graficos.set_index("Fecha")[columnas_brazos].rename(
                columns=nombres_brazos
            )
            st.line_chart(df_brz)


# --- AUTENTICACIÓN Y ESTADO DE SESIÓN ---
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
    st.session_state["rol"] = None
    st.session_state["cedula"] = None
    st.session_state["nombre"] = None

st.title("PERSONAL TRAINING & EVOLUTION TRACKER")

if not st.session_state["autenticado"]:
    col1, col2 = st.columns(2)

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
                df_usuarios, _ = cargar_bd()
                if (
                    not df_usuarios.empty
                    and cedula_ingreso in df_usuarios["cedula"].values
                ):
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

    with col2:
        st.subheader("📝 Crear Cuenta Nueva")
        with st.form("form_registro"):
            reg_cedula = st.text_input("Número de Cédula / ID:").strip()
            reg_nombre = st.text_input("Nombre Completo:").strip()
            reg_whatsapp = st.text_input(
                "Número de Whatsapp (10 dígitos):", placeholder="310......."
            ).strip()
            reg_eps = st.text_input("EPS :").strip()
            reg_condiciones = st.text_area(
                "Condiciones Médicas / Lesiones / Cirugías:"
            ).strip()
            reg_pass = st.text_input("Crea tu Contraseña:", type="password").strip()

            if st.form_submit_button("Crear Perfil"):
                df_usuarios, _ = cargar_bd()
                if not reg_cedula or not reg_nombre or not reg_pass:
                    st.error("⚠️ Cédula, Nombre y Contraseña son obligatorios.")
                elif (
                    not df_usuarios.empty
                    and reg_cedula in df_usuarios["cedula"].values
                ):
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
                        requests.post(
                            URL_API,
                            json={
                                "action": "registrar_usuario",
                                "row": nueva_fila,
                            },
                        )
                        st.cache_data.clear()
                        st.success(
                            "¡Perfil creado con éxito! Ya puedes iniciar sesión."
                        )
                    except Exception as e:
                        st.error(f"Error al guardar usuario: {e}")

else:
    st.sidebar.markdown(f"### 👤 {st.session_state['nombre']}")
    st.sidebar.markdown(f"Rol: {st.session_state['rol']}")

    if st.sidebar.button("Cerrar Sesión"):
        st.session_state["autenticado"] = False
        st.session_state["rol"] = None
        st.session_state["cedula"] = None
        st.session_state["nombre"] = None
        st.rerun()

    df_usuarios, df_historial = cargar_bd()

    # --- CLIENTE ---
    if st.session_state["rol"] == "Cliente":
        opcion = st.sidebar.radio(
            "MENÚ", ["📏 Registrar Medidas Hoy", "📊 Ver Mi Progreso"]
        )

        if opcion == "📏 Registrar Medidas Hoy":
            st.subheader("Registro de Evaluación Antropométrica")
            with st.form("form_medidas_cliente"):
                c1, c2, c3 = st.columns(3)
                peso = c1.number_input("Peso (kg):", 30.0, 200.0, 70.0, 0.5)
                estatura = c2.number_input(
                    "Estatura (cm):", 100.0, 220.0, 170.0, 1.0
                )
                edad = c3.number_input("Edad (años):", 10, 90, 25)
                sexo = c1.selectbox(
                    "Sexo Fisiológico:", ["Masculino", "Femenino"]
                )
                meta = c2.selectbox(
                    "Objetivo Principal:",
                    ["Perder Grasa", "Ganar Músculo", "Mantenimiento"],
                )

                st.markdown("---")
                st.write(
                    "### 📏 Medidas Corporales (cm) — Ordenado de Cabeza a Pies"
                )

                col_izq, col_der = st.columns(2)
                with col_izq:
                    st.markdown("💥 Tren Superior y Torso")
                    cuello = st.number_input("1. Cuello:", 20.0, 60.0, 38.0)
                    hombros = st.number_input("2. Hombros:", 50.0, 180.0, 110.0)
                    pecho = st.number_input("3. Pecho:", 50.0, 180.0, 95.0)
                    cintura = st.number_input(
                        "4. Cintura / Abdomen:", 40.0, 180.0, 80.0
                    )
                    cadera = st.number_input(
                        "5. Glúteos / Cadera:", 40.0, 180.0, 95.0
                    )

                with col_der:
                    st.markdown("💪 Extremidades (Brazos y Piernas)")
                    bicep_der = st.number_input(
                        "6. Bícep Derecho:", 15.0, 60.0, 32.0
                    )
                    bicep_izq = st.number_input(
                        "7. Bícep Izquierdo:", 15.0, 60.0, 32.0
                    )
                    pierna_der = st.number_input(
                        "8. Pierna Derecha:", 20.0, 90.0, 55.0
                    )
                    pierna_izq = st.number_input(
                        "9. Pierna Izquierda:", 20.0, 90.0, 55.0
                    )
                    gemelo_der = st.number_input(
                        "10. Gemelo Derecho:", 15.0, 60.0, 35.0
                    )
                    gemelo_izq = st.number_input(
                        "11. Gemelo Izquierdo:", 15.0, 60.0, 35.0
                    )

                if st.form_submit_button("Guardar Evaluación"):
                    imc, grasa, cals, edad_bio = calcular_metricas(
                        peso,
                        estatura,
                        edad,
                        sexo,
                        cuello,
                        cintura,
                        cadera,
                        meta,
                    )
                    id_reg = f"{st.session_state['cedula']}_{datetime.today().strftime('%Y%m%d%H%M')}"
                    fecha_hoy = datetime.today().strftime("%d-%m-%Y")

                    fila_medidas = [
                        id_reg,
                        fecha_hoy,
                        st.session_state["cedula"],
                        edad,
                        sexo,
                        meta,
                        peso,
                        estatura,
                        cuello,
                        hombros,
                        bicep_der,
                        bicep_izq,
                        pecho,
                        cintura,
                        cadera,
                        pierna_der,
                        pierna_izq,
                        gemelo_der,
                        gemelo_izq,
                        imc,
                        grasa,
                        cals,
                        edad_bio,
                    ]

                    try:
                        requests.post(
                            URL_API,
                            json={
                                "action": "guardar_medidas",
                                "row": fila_medidas,
                            },
                        )
                        st.cache_data.clear()
                        st.success("¡Medidas guardadas con éxito!")

                        r1, r2, r3, r4 = st.columns(4)
                        r1.metric("IMC", f"{imc}")
                        r2.metric("% Grasa Estimada", f"{grasa}%")
                        r3.metric("Calorías Recomendadas", f"{cals} kcal")
                        r4.metric("Edad Aparentada (Salud)", f"{edad_bio} años")
                    except Exception as e:
                        st.error(f"Error al enviar datos: {e}")

        elif opcion == "📊 Ver Mi Progreso":
            st.subheader("📉 Comparativa de Evolución")
            user_id = str(st.session_state["cedula"]).strip()
            mis_registros = (
                df_historial[df_historial["cedula"] == user_id]
                if not df_historial.empty
                else pd.DataFrame()
            )

            if not mis_registros.empty:
                # Ordenar cronológicamente parseando las fechas DD-MM-YYYY
                mis_registros["_fecha_dt"] = pd.to_datetime(
                    mis_registros["fecha_evaluacion"],
                    format="%d-%m-%Y",
                    errors="coerce",
                )
                mis_registros = mis_registros.sort_values(
                    by="_fecha_dt"
                ).drop(columns=["_fecha_dt"])

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
                    gras_i = get_val(
                        inicial, ["porcentaje_grasa", "grasa"], 20.0
                    )
                    gras_a = get_val(
                        actual, ["porcentaje_grasa", "grasa"], 20.0
                    )

                    diff_peso = peso_a - peso_i
                    diff_cintura = cint_a - cint_i
                    diff_grasa = gras_a - gras_i

                    st.info(
                        "📊 Resumen desde tu primer registro hasta hoy:"
                    )
                    c1, c2, c3 = st.columns(3)
                    c1.metric(
                        "Variación de Peso",
                        f"{peso_a} kg",
                        f"{diff_peso:.1f} kg",
                    )
                    c2.metric(
                        "Variación de Cintura",
                        f"{cint_a} cm",
                        f"{diff_cintura:.1f} cm",
                    )
                    c3.metric(
                        "Variación % Grasa",
                        f"{gras_a}%",
                        f"{diff_grasa:.1f}%",
                    )

                mostrar_graficos_evolucion(mis_registros)
                st.markdown("#### 📋 Historial de Registros Completos")
                st.dataframe(mis_registros.astype(str), use_container_width=True)
            else:
                st.info("Aún no has registrado ninguna evaluación física.")

    # --- ADMINISTRADOR ---
    elif st.session_state["rol"] == "Admin":
        st.subheader("Panel de Control General")
        if not df_usuarios.empty:
            clientes = df_usuarios[df_usuarios["rol"].str.lower() == "cliente"]
            st.markdown(f"Total de Clientes Registrados: {len(clientes)}")

            cedula_sel = st.selectbox(
                "Buscar Cliente por Nombre/Cédula:",
                clientes["cedula"].astype(str)
                + " - "
                + clientes["nombre_completo"],
            )

            if cedula_sel:
                id_cliente = str(cedula_sel.split(" - ")[0]).strip()
                u_info = clientes[clientes["cedula"] == id_cliente].iloc[0]

                st.markdown("---")
                st.markdown(
                    f"### 📋 Información de: {u_info['nombre_completo']}"
                )
                info_col1, info_col2, info_col3 = st.columns(3)
                info_col1.markdown(
                    f"WhatsApp: {u_info.get('whatsapp', 'No registra')}"
                )
                info_col2.markdown(
                    f"EPS: {str(u_info.get('eps', 'No registra')).upper()}"
                )
                info_col3.markdown(
                    f"Fecha Registro: {u_info.get('fecha_registro', 'No registra')}"
                )
                st.markdown(
                    f"Condiciones Médicas / Lesiones: {u_info.get('condiciones_medicas', 'Ninguna')}"
                )

                ws_url = link_whatsapp(
                    u_info.get("whatsapp", ""), u_info["nombre_completo"]
                )
                st.markdown(
                    f"[💬 Enviar Mensaje de Seguimiento por WhatsApp]({ws_url})"
                )

                st.markdown("#### 📈 Historial y Progreso del Cliente")
                if not df_historial.empty:
                    h_cliente = df_historial[df_historial["cedula"] == id_cliente]
                    if not h_cliente.empty:
                        mostrar_graficos_evolucion(h_cliente)
                        st.markdown("#### 📋 Registros en Tabla")

                        # Ordenar de la más reciente a la más antigua
                        h_cliente["_fecha_dt"] = pd.to_datetime(
                            h_cliente["fecha_evaluacion"],
                            format="%d-%m-%Y",
                            errors="coerce",
                        )
                        h_cliente_ord = h_cliente.sort_values(
                            by="_fecha_dt", ascending=False
                        ).drop(columns=["_fecha_dt"])

                        st.dataframe(
                            h_cliente_ord.astype(str),
                            use_container_width=True,
                        )
                    else:
                        st.info(
                            "Este cliente no se ha tomado medidas corporales todavía."
                        )
                else:
                    st.info("No hay registros en el historial general.")
