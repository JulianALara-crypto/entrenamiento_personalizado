import math
import os
import urllib.parse
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
from PIL import Image


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

URL_API = ("https://script.google.com/macros/s/AKfycbwS9DJyiUYu0pzdgQJZ1oQKmi-5xNpc1AnVIzCshixZDiGZiefKTypNBhWgz8jGt5OW/exec")


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

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# FUNCIÓN FORMATEAR FECHA
# ============================================================

def formatear_fecha(valor_fecha):

    if (
        pd.isna(valor_fecha)
        or not valor_fecha
        or str(valor_fecha).strip() == ""
    ):
        return ""

    try:

        dt = pd.to_datetime(
            valor_fecha,
            errors="coerce",
            utc=True
        )

        if pd.isna(dt):

            return str(valor_fecha)

        return dt.strftime(
            "%d-%m-%Y"
        )

    except Exception:

        return str(valor_fecha)


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
    """Calcula IMC, grasa corporal, calorías y una edad metabólica estimada.

    IMPORTANTE: la fórmula de grasa corporal tipo US Navy utiliza
    pulgadas (no centímetros). La versión anterior aplicaba log10
    directamente a centímetros, lo que producía porcentajes incorrectos.

    La edad metabólica no es una medida clínica universal. Aquí se estima
    de forma consistente comparando el BMR calculado con masa magra contra
    la edad implícita en Mifflin-St Jeor. Es una estimación orientativa,
    no un diagnóstico médico.
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

    estatura_m = estatura_cm / 100.0
    imc = peso / (estatura_m ** 2)

    # US Navy: las medidas deben estar en pulgadas.
    cm_a_pulg = 1.0 / 2.54
    altura_in = estatura_cm * cm_a_pulg
    cuello_in = cuello * cm_a_pulg
    cintura_in = cintura * cm_a_pulg
    cadera_in = cadera * cm_a_pulg

    if sexo == "Masculino":
        circunferencia = cintura_in - cuello_in
        if circunferencia <= 0:
            raise ValueError("La cintura debe ser mayor que el cuello.")

        densidad = (
            1.0324
            - 0.19077 * math.log10(circunferencia)
            + 0.15456 * math.log10(altura_in)
        )
    else:
        circunferencia = cintura_in + cadera_in - cuello_in
        if circunferencia <= 0:
            raise ValueError("La combinación cintura + cadera - cuello no es válida.")

        densidad = (
            1.29579
            - 0.35004 * math.log10(circunferencia)
            + 0.22100 * math.log10(altura_in)
        )

    pct_grasa = (495.0 / densidad) - 450.0
    pct_grasa = max(3.0, min(pct_grasa, 60.0))

    # Mifflin-St Jeor para BMR.
    if sexo == "Masculino":
        tmb = 10 * peso + 6.25 * estatura_cm - 5 * edad + 5
    else:
        tmb = 10 * peso + 6.25 * estatura_cm - 5 * edad - 161

    mantenimiento = tmb * 1.375

    if meta == "Perder Grasa":
        calorias = mantenimiento - 400
    elif meta == "Ganar Músculo":
        calorias = mantenimiento + 350
    else:
        calorias = mantenimiento

    # Estimación de edad metabólica a partir de masa magra.
    # Katch-McArdle estima el BMR a partir de masa libre de grasa.
    masa_magra = peso * (1.0 - pct_grasa / 100.0)
    tmb_masa_magra = 370.0 + (21.6 * masa_magra)

    # Edad que produciría aproximadamente ese BMR según Mifflin-St Jeor.
    if sexo == "Masculino":
        edad_metabolica = (
            10 * peso + 6.25 * estatura_cm + 5 - tmb_masa_magra
        ) / 5.0
    else:
        edad_metabolica = (
            10 * peso + 6.25 * estatura_cm - 161 - tmb_masa_magra
        ) / 5.0

    edad_metabolica = int(round(edad_metabolica))
    edad_metabolica = max(15, min(edad_metabolica, 90))

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

        num_limpio = (
            "57"
            + num_limpio
        )

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
        + urllib.parse.quote(
            mensaje
        )
    )


# ============================================================
# CARGAR BASE DE DATOS
# ============================================================

@st.cache_data(ttl=60)
def cargar_bd():
    """Carga usuarios, historial y pagos desde Apps Script.

    El Apps Script actual devuelve listas de diccionarios (objetos JSON),
    no una matriz donde la primera fila sean encabezados. Esta función
    admite ambos formatos para evitar perder registros.
    """
    columnas_usuarios = [
        "cedula", "nombre_completo", "whatsapp", "eps",
        "condiciones_medicas", "rol", "password", "fecha_registro"
    ]
    columnas_historial = [
        "id_registro", "fecha_evaluacion", "cedula", "edad",
        "sexo", "meta", "peso_kg", "estatura_cm",
        "cuello_cm", "hombros_cm", "bicep_der_cm",
        "bicep_izq_cm", "pecho_cm", "cintura_cm",
        "cadera_cm", "pierna_der_cm", "pierna_izq_cm",
        "gemelo_der_cm", "gemelo_izq_cm", "imc",
        "porcentaje_grasa", "calorias_objetivo", "edad_metabolica"
    ]
    columnas_pagos = [
        "id_pago", "cedula", "fecha_pago", "valor",
        "concepto", "valor_mensualidad"
    ]

    def convertir_dataframe(datos, columnas_vacias):
        if not isinstance(datos, list) or not datos:
            return pd.DataFrame(columns=columnas_vacias)

        # Formato actual de Apps Script: [{...}, {...}, ...]
        if isinstance(datos[0], dict):
            df = pd.DataFrame(datos)
        # Compatibilidad con un API que devuelva [encabezados, fila, fila...]
        elif isinstance(datos[0], (list, tuple)):
            encabezados = [str(c).strip().lower() for c in datos[0]]
            df = pd.DataFrame(datos[1:], columns=encabezados)
        else:
            return pd.DataFrame(columns=columnas_vacias)

        df.columns = [str(c).strip().lower() for c in df.columns]
        df = df.loc[:, ~df.columns.duplicated()]
        return df

    try:
        respuesta = requests.get(URL_API, timeout=30)
        respuesta.raise_for_status()
        res = respuesta.json()

        if not isinstance(res, dict):
            raise ValueError("La API no devolvió un objeto JSON válido.")

        if str(res.get("status", "success")).lower() == "error":
            raise ValueError(
                str(res.get("message", "Error desconocido de Google Apps Script."))
            )

        df_u = convertir_dataframe(res.get("usuarios", []), columnas_usuarios)
        df_m = convertir_dataframe(res.get("historial", []), columnas_historial)
        df_p = convertir_dataframe(res.get("pagos", []), columnas_pagos)

        # Normalizar cédulas sin eliminar filas.
        for dataframe in (df_u, df_m, df_p):
            if "cedula" in dataframe.columns:
                dataframe["cedula"] = (
                    dataframe["cedula"]
                    .astype(str)
                    .str.replace(r"\.0$", "", regex=True)
                    .str.strip()
                )

        # Columnas numéricas de medidas.
        columnas_numericas_medidas = [
            "edad", "peso_kg", "estatura_cm", "cuello_cm",
            "hombros_cm", "bicep_der_cm", "bicep_izq_cm",
            "pecho_cm", "cintura_cm", "cadera_cm",
            "pierna_der_cm", "pierna_izq_cm", "gemelo_der_cm",
            "gemelo_izq_cm", "imc", "porcentaje_grasa",
            "calorias_objetivo", "edad_metabolica"
        ]
        for columna in columnas_numericas_medidas:
            if columna in df_m.columns:
                df_m[columna] = pd.to_numeric(df_m[columna], errors="coerce")

        # Columnas numéricas de pagos.
        for columna in ("valor", "valor_mensualidad"):
            if columna in df_p.columns:
                df_p[columna] = pd.to_numeric(df_p[columna], errors="coerce")

        # Fechas para mostrar siempre en formato dd-mm-YYYY.
        if "fecha_registro" in df_u.columns:
            df_u["fecha_registro"] = df_u["fecha_registro"].apply(formatear_fecha)

        if "fecha_evaluacion" in df_m.columns:
            df_m["fecha_evaluacion"] = df_m["fecha_evaluacion"].apply(formatear_fecha)

        if "fecha_pago" in df_p.columns:
            df_p["fecha_pago"] = df_p["fecha_pago"].apply(formatear_fecha)

        return df_u, df_m, df_p

    except Exception as e:
        st.error(f"Error procesando base de datos: {e}")
        return (
            pd.DataFrame(columns=columnas_usuarios),
            pd.DataFrame(columns=columnas_historial),
            pd.DataFrame(columns=columnas_pagos),
        )


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
        "pierna_der_cm", "pierna_izq_cm",
        "gemelo_der_cm", "gemelo_izq_cm",
    ]

    for col in columnas_num:
        if col in df_graficos.columns:
            df_graficos[col] = pd.to_numeric(
                df_graficos[col], errors="coerce"
            )

    if "fecha_evaluacion" not in df_graficos.columns:
        return

    df_graficos["fecha_dt"] = pd.to_datetime(
        df_graficos["fecha_evaluacion"],
        format="%d-%m-%Y",
        errors="coerce",
    )

    faltantes = df_graficos["fecha_dt"].isna()
    if faltantes.any():
        df_graficos.loc[faltantes, "fecha_dt"] = pd.to_datetime(
            df_graficos.loc[faltantes, "fecha_evaluacion"],
            errors="coerce",
        )

    df_graficos = (
        df_graficos
        .dropna(subset=["fecha_dt"])
        .sort_values("fecha_dt")
    )

    if df_graficos.empty:
        return

    df_graficos["Fecha"] = df_graficos["fecha_dt"].dt.strftime("%d-%m-%Y")

    st.markdown("### 📈 Gráficas de Evolución Temporal")

    tab1, tab2, tab3, tab4 = st.tabs([
        "⚖️ Peso y Composición",
        "📏 Perímetros Principales",
        "💪 Brazos",
        "🦵 Piernas y Glúteos",
    ])

    with tab1:
        col_g1, col_g2 = st.columns(2)

        with col_g1:
            st.markdown("**Evolución del Peso Corporal (kg)**")
            if "peso_kg" in df_graficos.columns:
                df_peso = (
                    df_graficos.set_index("Fecha")[["peso_kg"]]
                    .rename(columns={"peso_kg": "Peso (kg)"})
                    .dropna(how="all")
                )
                if not df_peso.empty:
                    st.line_chart(df_peso, use_container_width=True)

        with col_g2:
            st.markdown("**Evolución del % de Grasa Corporal**")
            if "porcentaje_grasa" in df_graficos.columns:
                df_grasa = (
                    df_graficos.set_index("Fecha")[["porcentaje_grasa"]]
                    .rename(columns={"porcentaje_grasa": "% Grasa"})
                    .dropna(how="all")
                )
                if not df_grasa.empty:
                    st.line_chart(df_grasa, use_container_width=True)

    with tab2:
        st.markdown("**Evolución de Torso y Cintura (cm)**")
        columnas = [
            ("cintura_cm", "Cintura"),
            ("pecho_cm", "Pecho"),
            ("cadera_cm", "Cadera/Glúteos"),
        ]
        disponibles = [x for x, _ in columnas if x in df_graficos.columns]
        nombres = {x: n for x, n in columnas if x in disponibles}
        if disponibles:
            df_peri = (
                df_graficos.set_index("Fecha")[disponibles]
                .rename(columns=nombres)
                .dropna(how="all")
            )
            if not df_peri.empty:
                st.line_chart(df_peri, use_container_width=True)

    with tab3:
        st.markdown("**Evolución de Brazos (cm)**")
        columnas = [
            ("bicep_der_cm", "Bíceps Derecho"),
            ("bicep_izq_cm", "Bíceps Izquierdo"),
        ]
        disponibles = [x for x, _ in columnas if x in df_graficos.columns]
        nombres = {x: n for x, n in columnas if x in disponibles}
        if disponibles:
            df_brazos = (
                df_graficos.set_index("Fecha")[disponibles]
                .rename(columns=nombres)
                .dropna(how="all")
            )
            if not df_brazos.empty:
                st.line_chart(df_brazos, use_container_width=True)

    with tab4:
        st.markdown("**Evolución de Piernas, Glúteos y Gemelos (cm)**")
        columnas = [
            ("pierna_der_cm", "Pierna Derecha"),
            ("pierna_izq_cm", "Pierna Izquierda"),
            ("cadera_cm", "Glúteos/Cadera"),
            ("gemelo_der_cm", "Gemelo Derecho"),
            ("gemelo_izq_cm", "Gemelo Izquierdo"),
        ]
        disponibles = [x for x, _ in columnas if x in df_graficos.columns]
        nombres = {x: n for x, n in columnas if x in disponibles}
        if disponibles:
            df_piernas = (
                df_graficos.set_index("Fecha")[disponibles]
                .rename(columns=nombres)
                .dropna(how="all")
            )
            if not df_piernas.empty:
                st.line_chart(df_piernas, use_container_width=True)
            else:
                st.info("Aún no hay medidas de piernas, glúteos o gemelos registradas.")
        else:
            st.info("Aún no hay columnas de piernas/glúteos disponibles en el historial.")

# ============================================================
# ESTADO DE SESIÓN
# ============================================================

if "autenticado" not in st.session_state:

    st.session_state[
        "autenticado"
    ] = False

    st.session_state[
        "rol"
    ] = None

    st.session_state[
        "cedula"
    ] = None

    st.session_state[
        "nombre"
    ] = None


# ============================================================
# TÍTULO
# ============================================================

st.title(
    "PERSONAL TRAINING & EVOLUTION TRACKER"
)


# ============================================================
# LOGIN / REGISTRO
# ============================================================

if not st.session_state[
    "autenticado"
]:

    col1, col2 = st.columns(2)


    # ========================================================
    # LOGIN
    # ========================================================

    with col1:

        st.subheader(
            "🔐 Iniciar Sesión"
        )

        cedula_ingreso = st.text_input(
            "Número de Cédula / ID:"
        ).strip()

        pass_ingreso = st.text_input(
            "Contraseña:",
            type="password"
        ).strip()


        if st.button(
            "Ingresar",
            use_container_width=True
        ):

            if (
                cedula_ingreso
                == "admin"
                and pass_ingreso
                == "admin123456"
            ):

                st.session_state[
                    "autenticado"
                ] = True

                st.session_state[
                    "rol"
                ] = "Admin"

                st.session_state[
                    "cedula"
                ] = "ADMIN"

                st.session_state[
                    "nombre"
                ] = "JULIAN AVILA"

                st.rerun()


            else:

                df_usuarios, _, _ = (
                    cargar_bd()
                )


                if (
                    not df_usuarios.empty
                    and cedula_ingreso
                    in df_usuarios[
                        "cedula"
                    ].values
                ):

                    u = (
                        df_usuarios[
                            df_usuarios[
                                "cedula"
                            ]
                            == cedula_ingreso
                        ]
                        .iloc[0]
                    )


                    if (
                        str(
                            u["password"]
                        ).strip()
                        == pass_ingreso
                    ):

                        st.session_state[
                            "autenticado"
                        ] = True

                        st.session_state[
                            "rol"
                        ] = u.get(
                            "rol",
                            "Cliente"
                        )

                        st.session_state[
                            "cedula"
                        ] = str(
                            u["cedula"]
                        )

                        st.session_state[
                            "nombre"
                        ] = u[
                            "nombre_completo"
                        ]

                        st.rerun()


                    else:

                        st.error(
                            "❌ Contraseña incorrecta."
                        )


                else:

                    st.error(
                        "❌ Cédula no registrada."
                    )


    # ========================================================
    # REGISTRO
    # ========================================================

    with col2:

        st.subheader(
            "📝 Crear Cuenta Nueva"
        )


        with st.form(
            "form_registro"
        ):

            reg_cedula = st.text_input(
                "Número de Cédula / ID:"
            ).strip()

            reg_nombre = st.text_input(
                "Nombre Completo:"
            ).strip()

            reg_whatsapp = st.text_input(
                "Número de Whatsapp (10 dígitos):",
                placeholder="310......."
            ).strip()

            reg_eps = st.text_input(
                "EPS :"
            ).strip()

            reg_condiciones = st.text_area(
                "Condiciones Médicas / Lesiones / Cirugías:"
            ).strip()

            reg_pass = st.text_input(
                "Crea tu Contraseña:",
                type="password"
            ).strip()


            if st.form_submit_button(
                "Crear Perfil"
            ):

                df_usuarios, _, _ = (
                    cargar_bd()
                )


                if (
                    not reg_cedula
                    or not reg_nombre
                    or not reg_pass
                ):

                    st.error(
                        "⚠️ Cédula, Nombre y Contraseña "
                        "son obligatorios."
                    )


                elif (
                    not df_usuarios.empty
                    and reg_cedula
                    in df_usuarios[
                        "cedula"
                    ].values
                ):

                    st.error(
                        "❌ Esta cédula ya está registrada."
                    )


                else:

                    nueva_fila = [

                        reg_cedula,

                        reg_nombre,

                        reg_whatsapp,

                        (
                            reg_eps
                            if reg_eps
                            else "NINGUNA"
                        ),

                        (
                            reg_condiciones
                            if reg_condiciones
                            else "NINGUNA"
                        ),

                        "Cliente",

                        reg_pass,

                        datetime.today()
                        .strftime(
                            "%d-%m-%Y"
                        ),

                    ]


                    try:

                        respuesta_registro = (
                            requests.post(
                                URL_API,
                                json={
                                    "action":
                                    "registrar_usuario",
                                    "row":
                                    nueva_fila,
                                },
                                timeout=30,
                            )
                        )

                        respuesta_registro.raise_for_status()

                        cargar_bd.clear()

                        st.success(
                            "¡Perfil creado con éxito! "
                            "Ya puedes iniciar sesión."
                        )


                    except Exception as e:

                        st.error(
                            f"Error al guardar usuario: {e}"
                        )


# ============================================================
# APLICACIÓN AUTENTICADA
# ============================================================

else:

    st.sidebar.markdown(
        f"### 👤 "
        f"{st.session_state['nombre']}"
    )

    st.sidebar.markdown(
        f"Rol: "
        f"{st.session_state['rol']}"
    )


    if st.sidebar.button(
        "Cerrar Sesión"
    ):

        st.session_state[
            "autenticado"
        ] = False

        st.session_state[
            "rol"
        ] = None

        st.session_state[
            "cedula"
        ] = None

        st.session_state[
            "nombre"
        ] = None

        st.rerun()


    df_usuarios, df_historial, df_pagos = (
        cargar_bd()
    )


    # ========================================================
    # CLIENTE
    # ========================================================

    if (
        st.session_state["rol"]
        == "Cliente"
    ):

        opcion = st.sidebar.radio(
            "MENÚ",
            [
                "📏 Registrar Medidas Hoy",
                "📊 Ver Mi Progreso",
            ],
        )


        # ====================================================
        # REGISTRAR MEDIDAS
        # ====================================================

        if (
            opcion
            == "📏 Registrar Medidas Hoy"
        ):

            st.subheader(
                "Registro de Evaluación Antropométrica"
            )


            with st.form(
                "form_medidas_cliente"
            ):

                c1, c2, c3 = st.columns(3)


                peso = c1.number_input(
                    "Peso (kg):",
                    30.0,
                    200.0,
                    70.0,
                    0.5,
                )


                estatura = c2.number_input(
                    "Estatura (cm):",
                    100.0,
                    220.0,
                    170.0,
                    1.0,
                )


                edad = c3.number_input(
                    "Edad (años):",
                    10,
                    90,
                    25,
                )


                sexo = c1.selectbox(
                    "Sexo Fisiológico:",
                    [
                        "Masculino",
                        "Femenino",
                    ],
                )


                meta = c2.selectbox(
                    "Objetivo Principal:",
                    [
                        "Perder Grasa",
                        "Ganar Músculo",
                        "Mantenimiento",
                    ],
                )


                st.markdown(
                    "---"
                )


                st.write(
                    "### 📏 Medidas Corporales (cm) — "
                    "Ordenado de Cabeza a Pies"
                )


                col_izq, col_der = st.columns(2)


                with col_izq:

                    st.markdown(
                        "💥 Tren Superior y Torso"
                    )


                    cuello = st.number_input(
                        "1. Cuello:",
                        20.0,
                        60.0,
                        38.0,
                    )


                    hombros = st.number_input(
                        "2. Hombros:",
                        50.0,
                        180.0,
                        110.0,
                    )


                    pecho = st.number_input(
                        "3. Pecho:",
                        50.0,
                        180.0,
                        95.0,
                    )


                    cintura = st.number_input(
                        "4. Cintura / Abdomen:",
                        40.0,
                        180.0,
                        80.0,
                    )


                    cadera = st.number_input(
                        "5. Glúteos / Cadera:",
                        40.0,
                        180.0,
                        95.0,
                    )


                with col_der:

                    st.markdown(
                        "💪 Extremidades "
                        "(Brazos y Piernas)"
                    )


                    bicep_der = st.number_input(
                        "6. Bícep Derecho:",
                        15.0,
                        60.0,
                        32.0,
                    )


                    bicep_izq = st.number_input(
                        "7. Bícep Izquierdo:",
                        15.0,
                        60.0,
                        32.0,
                    )


                    pierna_der = st.number_input(
                        "8. Pierna Derecha:",
                        20.0,
                        90.0,
                        55.0,
                    )


                    pierna_izq = st.number_input(
                        "9. Pierna Izquierda:",
                        20.0,
                        90.0,
                        55.0,
                    )


                    gemelo_der = st.number_input(
                        "10. Gemelo Derecho:",
                        15.0,
                        60.0,
                        35.0,
                    )


                    gemelo_izq = st.number_input(
                        "11. Gemelo Izquierdo:",
                        15.0,
                        60.0,
                        35.0,
                    )


                if st.form_submit_button(
                    "Guardar Evaluación"
                ):

                    try:

                        (
                            imc,
                            grasa,
                            cals,
                            edad_bio,
                        ) = calcular_metricas(

                            peso,

                            estatura,

                            edad,

                            sexo,

                            cuello,

                            cintura,

                            cadera,

                            meta,

                        )


                        # ==================================
                        # VALIDACIÓN DEL IMC
                        # ==================================

                        if (
                            imc < 10
                            or imc > 60
                        ):

                            st.error(
                                "⚠️ El IMC calculado "
                                f"({imc}) está fuera de "
                                "un rango razonable. "
                                "Revisa peso y estatura."
                            )

                            st.stop()


                        # ==================================
                        # ID Y FECHA
                        # ==================================

                        id_reg = (
                            f"{st.session_state['cedula']}_"
                            f"{datetime.today().strftime('%Y%m%d%H%M')}"
                        )


                        fecha_hoy = (
                            datetime.today()
                            .strftime(
                                "%d-%m-%Y"
                            )
                        )


                        # ==================================
                        # FILA FINAL
                        #
                        # MUY IMPORTANTE:
                        # IMC, GRASA, CALORÍAS Y EDAD
                        # SON CONVERTIDOS EXPLÍCITAMENTE
                        # A TIPOS NUMÉRICOS.
                        # ==================================

                        fila_medidas = [

                            str(
                                id_reg
                            ),

                            str(
                                fecha_hoy
                            ),

                            str(
                                st.session_state[
                                    "cedula"
                                ]
                            ),

                            int(
                                edad
                            ),

                            str(
                                sexo
                            ),

                            str(
                                meta
                            ),

                            float(
                                peso
                            ),

                            float(
                                estatura
                            ),

                            float(
                                cuello
                            ),

                            float(
                                hombros
                            ),

                            float(
                                bicep_der
                            ),

                            float(
                                bicep_izq
                            ),

                            float(
                                pecho
                            ),

                            float(
                                cintura
                            ),

                            float(
                                cadera
                            ),

                            float(
                                pierna_der
                            ),

                            float(
                                pierna_izq
                            ),

                            float(
                                gemelo_der
                            ),

                            float(
                                gemelo_izq
                            ),

                            float(
                                imc
                            ),

                            float(
                                grasa
                            ),

                            int(
                                cals
                            ),

                            int(
                                edad_bio
                            ),

                        ]


                        # ==================================
                        # ENVIAR A GOOGLE APPS SCRIPT
                        # ==================================

                        respuesta_medidas = (
                            requests.post(

                                URL_API,

                                json={
                                    "action":
                                    "guardar_medidas",

                                    "row":
                                    fila_medidas,
                                },

                                timeout=30,

                            )
                        )


                        respuesta_medidas.raise_for_status()


                        # Intentar leer respuesta del API

                        try:

                            resultado_api = (
                                respuesta_medidas.json()
                            )

                        except Exception:

                            resultado_api = {}


                        if (
                            resultado_api.get(
                                "status"
                            )
                            == "error"
                        ):

                            st.error(
                                "❌ Google Apps Script "
                                "reportó un error: "
                                + str(
                                    resultado_api.get(
                                        "message",
                                        "Error desconocido"
                                    )
                                )
                            )

                            st.stop()


                        cargar_bd.clear()


                        st.success(
                            "¡Medidas guardadas con éxito!"
                        )


                        # ==================================
                        # MOSTRAR RESULTADOS
                        # ==================================

                        r1, r2, r3, r4 = (
                            st.columns(4)
                        )


                        r1.metric(
                            "IMC",
                            f"{imc:.2f}"
                        )


                        r2.metric(
                            "% Grasa Estimada",
                            f"{grasa:.2f}%"
                        )


                        r3.metric(
                            "Calorías Recomendadas",
                            f"{cals} kcal"
                        )


                        r4.metric(
                            "Edad Metabólica",
                            f"{edad_bio} años"
                        )


                    except Exception as e:

                        st.error(
                            "❌ Error calculando o "
                            f"guardando las medidas: {e}"
                        )


        # ====================================================
        # VER PROGRESO
        # ====================================================

        elif (
            opcion
            == "📊 Ver Mi Progreso"
        ):

            st.subheader(
                "📉 Comparativa de Evolución"
            )


            user_id = str(
                st.session_state[
                    "cedula"
                ]
            ).strip()


            mis_registros = (

                df_historial[
                    df_historial[
                        "cedula"
                    ]
                    == user_id
                ]

                if not df_historial.empty

                else pd.DataFrame()

            )


            if not mis_registros.empty:

                mis_registros = (
                    mis_registros.copy()
                )


                mis_registros[
                    "_fecha_dt"
                ] = pd.to_datetime(

                    mis_registros[
                        "fecha_evaluacion"
                    ],

                    format="%d-%m-%Y",

                    errors="coerce",

                )


                mis_registros = (
                    mis_registros

                    .sort_values(
                        by="_fecha_dt"
                    )

                    .drop(
                        columns=[
                            "_fecha_dt"
                        ]
                    )
                )


                if len(
                    mis_registros
                ) >= 2:

                    inicial = (
                        mis_registros.iloc[0]
                    )

                    actual = (
                        mis_registros.iloc[-1]
                    )


                    def get_val(
                        row,
                        keys_posibles,
                        default=0.0,
                    ):

                        for k in keys_posibles:

                            if (
                                k
                                in row.index
                            ):

                                try:

                                    return float(
                                        row[k]
                                    )

                                except Exception:

                                    pass

                        return default


                    peso_i = get_val(
                        inicial,
                        [
                            "peso_kg",
                            "peso",
                        ],
                        70.0,
                    )


                    peso_a = get_val(
                        actual,
                        [
                            "peso_kg",
                            "peso",
                        ],
                        70.0,
                    )


                    cint_i = get_val(
                        inicial,
                        [
                            "cintura_cm",
                            "cintura",
                        ],
                        80.0,
                    )


                    cint_a = get_val(
                        actual,
                        [
                            "cintura_cm",
                            "cintura",
                        ],
                        80.0,
                    )


                    gras_i = get_val(
                        inicial,
                        [
                            "porcentaje_grasa",
                            "grasa",
                        ],
                        20.0,
                    )


                    gras_a = get_val(
                        actual,
                        [
                            "porcentaje_grasa",
                            "grasa",
                        ],
                        20.0,
                    )


                    diff_peso = (
                        peso_a
                        - peso_i
                    )


                    diff_cintura = (
                        cint_a
                        - cint_i
                    )


                    diff_grasa = (
                        gras_a
                        - gras_i
                    )


                    st.info(
                        "📊 Resumen desde tu primer "
                        "registro hasta hoy:"
                    )


                    c1, c2, c3 = (
                        st.columns(3)
                    )


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


                mostrar_graficos_evolucion(
                    mis_registros
                )


                st.markdown(
                    "#### 📋 Historial de "
                    "Registros Completos"
                )


                st.dataframe(
                    mis_registros.astype(
                        str
                    ),
                    use_container_width=True,
                )


            else:

                st.info(
                    "Aún no has registrado ninguna "
                    "evaluación física."
                )


    # ========================================================
    # ADMINISTRADOR
    # ========================================================

    elif (
        st.session_state["rol"]
        == "Admin"
    ):

        st.subheader(
            "Panel de Control General"
        )


        if not df_usuarios.empty:

            clientes = (
                df_usuarios[
                    df_usuarios[
                        "rol"
                    ]
                    .astype(str)
                    .str.lower()
                    == "cliente"
                ]
            )


            st.markdown(
                "Total de Clientes Registrados: "
                f"{len(clientes)}"
            )


            if not clientes.empty:

                cedula_sel = (
                    st.selectbox(
                        "Buscar Cliente "
                        "por Nombre/Cédula:",
                        clientes[
                            "cedula"
                        ].astype(str)
                        + " - "
                        + clientes[
                            "nombre_completo"
                        ].astype(str),
                    )
                )


                if cedula_sel:

                    id_cliente = (
                        str(
                            cedula_sel
                            .split(" - ")[0]
                        )
                        .strip()
                    )


                    cliente_encontrado = (
                        clientes[
                            clientes[
                                "cedula"
                            ]
                            == id_cliente
                        ]
                    )


                    if not cliente_encontrado.empty:

                        u_info = (
                            cliente_encontrado
                            .iloc[0]
                        )


                        st.markdown(
                            "---"
                        )


                        st.markdown(
                            f"### 📋 Información de: "
                            f"{u_info['nombre_completo']}"
                        )


                        info_col1, info_col2, info_col3 = (
                            st.columns(3)
                        )


                        info_col1.markdown(
                            "WhatsApp: "
                            f"{u_info.get('whatsapp', 'No registra')}"
                        )


                        info_col2.markdown(
                            "EPS: "
                            f"{str(u_info.get('eps', 'No registra')).upper()}"
                        )


                        info_col3.markdown(
                            "Fecha Registro: "
                            f"{u_info.get('fecha_registro', 'No registra')}"
                        )


                        st.markdown(
                            "Condiciones Médicas / "
                            "Lesiones: "
                            f"{u_info.get('condiciones_medicas', 'Ninguna')}"
                        )


                        ws_url = link_whatsapp(
                            u_info.get(
                                "whatsapp",
                                ""
                            ),
                            u_info[
                                "nombre_completo"
                            ],
                        )


                        st.markdown(
                            f"[💬 Enviar Mensaje de "
                            f"Seguimiento por WhatsApp]"
                            f"({ws_url})"
                        )


                        # ====================================================
                        # PAGOS Y MENSUALIDAD
                        # ====================================================

                        st.markdown("---")
                        st.markdown("#### 💳 Pagos y Mensualidad")

                        pagos_cliente = pd.DataFrame()

                        if (
                            not df_pagos.empty
                            and "cedula" in df_pagos.columns
                        ):
                            pagos_cliente = df_pagos[
                                df_pagos["cedula"] == id_cliente
                            ].copy()

                        total_pagado = 0.0
                        valor_mensualidad_actual = 0.0

                        if not pagos_cliente.empty:

                            if "valor" in pagos_cliente.columns:
                                total_pagado = pd.to_numeric(
                                    pagos_cliente["valor"],
                                    errors="coerce"
                                ).fillna(0).sum()

                            if "valor_mensualidad" in pagos_cliente.columns:
                                mensualidades_validas = pd.to_numeric(
                                    pagos_cliente["valor_mensualidad"],
                                    errors="coerce"
                                ).dropna()

                                if not mensualidades_validas.empty:
                                    valor_mensualidad_actual = float(
                                        mensualidades_validas.iloc[-1]
                                    )

                        saldo_actual = max(
                            valor_mensualidad_actual - total_pagado,
                            0.0
                        )

                        estado_pago = (
                            "🟢 PAGADO"
                            if valor_mensualidad_actual > 0
                            and saldo_actual <= 0
                            else "🟡 ABONO"
                            if total_pagado > 0
                            else "🔴 PENDIENTE"
                        )

                        p1, p2, p3, p4 = st.columns(4)

                        p1.metric(
                            "Mensualidad",
                            f"${valor_mensualidad_actual:,.0f}"
                        )

                        p2.metric(
                            "Total Pagado",
                            f"${total_pagado:,.0f}"
                        )

                        p3.metric(
                            "Saldo Pendiente",
                            f"${saldo_actual:,.0f}"
                        )

                        p4.metric(
                            "Estado",
                            estado_pago
                        )

                        # ----------------------------------------------------
                        # REGISTRAR NUEVO PAGO
                        # ----------------------------------------------------

                        with st.expander(
                            "➕ Registrar nuevo pago / abono",
                            expanded=pagos_cliente.empty
                        ):

                            with st.form(
                                f"form_pago_{id_cliente}"
                            ):

                                if valor_mensualidad_actual > 0:
                                    mensualidad_default = float(
                                        valor_mensualidad_actual
                                    )
                                else:
                                    mensualidad_default = 250000.0

                                valor_mensualidad = st.number_input(
                                    "Valor de la mensualidad ($):",
                                    min_value=1.0,
                                    value=mensualidad_default,
                                    step=5000.0,
                                    format="%.0f",
                                )

                                saldo_para_nuevo_pago = max(
                                    float(valor_mensualidad)
                                    - total_pagado,
                                    0.0
                                )

                                if total_pagado > 0:
                                    st.caption(
                                        "Pagado hasta ahora: "
                                        f"${total_pagado:,.0f} | "
                                        "Saldo según esta mensualidad: "
                                        f"${saldo_para_nuevo_pago:,.0f}"
                                    )

                                valor_pago = st.number_input(
                                    "Valor del pago / abono ($):",
                                    min_value=1.0,
                                    value=(
                                        saldo_para_nuevo_pago
                                        if saldo_para_nuevo_pago > 0
                                        else 1.0
                                    ),
                                    step=5000.0,
                                    format="%.0f",
                                )

                                concepto_pago = st.text_input(
                                    "Concepto:",
                                    value="Abono mensualidad"
                                ).strip()

                                guardar_pago = st.form_submit_button(
                                    "💾 Registrar Pago",
                                    use_container_width=True
                                )

                                if guardar_pago:

                                    try:

                                        valor_mensualidad = float(
                                            valor_mensualidad
                                        )

                                        valor_pago = float(
                                            valor_pago
                                        )

                                        if valor_mensualidad <= 0:
                                            st.error(
                                                "❌ La mensualidad debe ser mayor que cero."
                                            )
                                            st.stop()

                                        if valor_pago <= 0:
                                            st.error(
                                                "❌ El valor del pago debe ser mayor que cero."
                                            )
                                            st.stop()

                                        if not concepto_pago:
                                            concepto_pago = "Abono mensualidad"

                                        nuevo_total = (
                                            total_pagado
                                            + valor_pago
                                        )

                                        if nuevo_total > valor_mensualidad + 0.001:
                                            st.error(
                                                "❌ El abono supera el saldo pendiente. "
                                                f"Saldo disponible: ${saldo_para_nuevo_pago:,.0f}."
                                            )
                                            st.stop()

                                        id_pago = (
                                            f"{id_cliente}_"
                                            f"{datetime.today().strftime('%Y%m%d%H%M%S%f')}"
                                        )

                                        fecha_pago = datetime.today().strftime(
                                            "%d-%m-%Y"
                                        )

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
                                            json={
                                                "action": "guardar_pago",
                                                "row": fila_pago,
                                            },
                                            timeout=30,
                                        )

                                        respuesta_pago.raise_for_status()

                                        try:
                                            resultado_pago = respuesta_pago.json()
                                        except Exception:
                                            resultado_pago = {}

                                        if (
                                            resultado_pago.get("status")
                                            == "error"
                                        ):
                                            st.error(
                                                "❌ Google Apps Script reportó un error: "
                                                + str(
                                                    resultado_pago.get(
                                                        "message",
                                                        "Error desconocido"
                                                    )
                                                )
                                            )
                                            st.stop()

                                        cargar_bd.clear()

                                        nuevo_saldo = max(
                                            valor_mensualidad
                                            - nuevo_total,
                                            0.0
                                        )

                                        if nuevo_saldo <= 0.001:
                                            st.success(
                                                "✅ Pago registrado. "
                                                "La mensualidad quedó completamente pagada."
                                            )
                                        else:
                                            st.success(
                                                "✅ Abono registrado correctamente. "
                                                f"Saldo pendiente: ${nuevo_saldo:,.0f}."
                                            )

                                        st.rerun()

                                    except Exception as e:

                                        st.error(
                                            "❌ Error registrando el pago: "
                                            f"{e}"
                                        )

                        # ----------------------------------------------------
                        # HISTORIAL DE PAGOS
                        # ----------------------------------------------------

                        if not pagos_cliente.empty:

                            st.markdown("#### 📜 Historial de Pagos")

                            pagos_mostrar = pagos_cliente.copy()

                            if "fecha_pago" in pagos_mostrar.columns:
                                pagos_mostrar["_fecha_dt"] = pd.to_datetime(
                                    pagos_mostrar["fecha_pago"],
                                    format="%d-%m-%Y",
                                    errors="coerce"
                                )

                                pagos_mostrar = (
                                    pagos_mostrar
                                    .sort_values(
                                        by="_fecha_dt",
                                        ascending=False
                                    )
                                    .drop(columns=["_fecha_dt"])
                                )

                            columnas_pago_mostrar = [
                                columna
                                for columna in [
                                    "fecha_pago",
                                    "valor",
                                    "concepto",
                                    "valor_mensualidad",
                                ]
                                if columna in pagos_mostrar.columns
                            ]

                            tabla_pagos = pagos_mostrar[
                                columnas_pago_mostrar
                            ].copy()

                            if "valor" in tabla_pagos.columns:
                                tabla_pagos["valor"] = (
                                    pd.to_numeric(
                                        tabla_pagos["valor"],
                                        errors="coerce"
                                    )
                                    .fillna(0)
                                    .map(
                                        lambda x: f"${x:,.0f}"
                                    )
                                )

                            if "valor_mensualidad" in tabla_pagos.columns:
                                tabla_pagos["valor_mensualidad"] = (
                                    pd.to_numeric(
                                        tabla_pagos["valor_mensualidad"],
                                        errors="coerce"
                                    )
                                    .fillna(0)
                                    .map(
                                        lambda x: f"${x:,.0f}"
                                    )
                                )

                            tabla_pagos = tabla_pagos.rename(
                                columns={
                                    "fecha_pago": "Fecha",
                                    "valor": "Pago",
                                    "concepto": "Concepto",
                                    "valor_mensualidad": "Mensualidad",
                                }
                            )

                            st.dataframe(
                                tabla_pagos,
                                use_container_width=True,
                                hide_index=True,
                            )

                        else:

                            st.info(
                                "Este cliente todavía no tiene pagos registrados."
                            )


                        st.markdown(
                            "#### 📈 Historial y "
                            "Progreso del Cliente"
                        )


                        if not df_historial.empty:

                            h_cliente = (
                                df_historial[
                                    df_historial[
                                        "cedula"
                                    ]
                                    == id_cliente
                                ].copy()
                            )


                            if not h_cliente.empty:

                                mostrar_graficos_evolucion(
                                    h_cliente
                                )


                                st.markdown(
                                    "#### 📋 Registros "
                                    "en Tabla"
                                )


                                h_cliente[
                                    "_fecha_dt"
                                ] = pd.to_datetime(

                                    h_cliente[
                                        "fecha_evaluacion"
                                    ],

                                    format="%d-%m-%Y",

                                    errors="coerce",

                                )


                                h_cliente_ord = (
                                    h_cliente

                                    .sort_values(
                                        by="_fecha_dt",
                                        ascending=False,
                                    )

                                    .drop(
                                        columns=[
                                            "_fecha_dt"
                                        ]
                                    )
                                )


                                st.dataframe(
                                    h_cliente_ord.astype(
                                        str
                                    ),
                                    use_container_width=True,
                                )


                            else:

                                st.info(
                                    "Este cliente no se ha "
                                    "tomado medidas corporales "
                                    "todavía."
                                )


                        else:

                            st.info(
                                "No hay registros en el "
                                "historial general."
                            )


            else:

                st.info(
                    "No hay clientes registrados "
                    "actualmente."
                )
