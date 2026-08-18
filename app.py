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
    "https://script.google.com/macros/s/AKfycbwDyMSmGUzHJcRfOgq_SaaQzdJ5uCnVIrVSwxcs8wPySYx2nsocp1_6lBp2cM4MZPoN/exec"
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

    estatura_cm = float(
        estatura_cm
    )

    edad = int(edad)

    cuello = float(cuello)

    cintura = float(cintura)

    cadera = float(cadera)


    if peso <= 0:

        raise ValueError(
            "El peso debe ser mayor que cero."
        )


    if estatura_cm <= 0:

        raise ValueError(
            "La estatura debe ser mayor que cero."
        )


    # --------------------------------------------------------
    # IMC
    # --------------------------------------------------------

    estatura_m = (
        estatura_cm / 100.0
    )

    imc = (
        peso /
        (estatura_m ** 2)
    )


    # --------------------------------------------------------
    # PORCENTAJE DE GRASA
    # --------------------------------------------------------

    try:

        if sexo == "Masculino":

            valor_log = (
                cintura - cuello
            )

            if valor_log <= 0:

                valor_log = 1.0

            densidad = (
                1.0324
                - 0.19077
                * math.log10(
                    valor_log
                )
                + 0.15456
                * math.log10(
                    estatura_cm
                )
            )

            pct_grasa = (
                495 / densidad
            ) - 450

        else:

            valor_log = (
                cintura
                + cadera
                - cuello
            )

            if valor_log <= 0:

                valor_log = 1.0

            densidad = (
                1.29579
                - 0.35004
                * math.log10(
                    valor_log
                )
                + 0.22100
                * math.log10(
                    estatura_cm
                )
            )

            pct_grasa = (
                495 / densidad
            ) - 450


        pct_grasa = max(
            min(
                pct_grasa,
                60.0
            ),
            3.0
        )


    except Exception:

        pct_grasa = (
            15.0
            if sexo == "Masculino"
            else 24.0
        )


    # --------------------------------------------------------
    # TASA METABÓLICA BASAL
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # MANTENIMIENTO
    # --------------------------------------------------------

    mantenimiento = (
        tmb * 1.375
    )


    # --------------------------------------------------------
    # OBJETIVO CALÓRICO
    # --------------------------------------------------------

    if meta == "Perder Grasa":

        calorias = (
            mantenimiento - 400
        )

    elif meta == "Ganar Músculo":

        calorias = (
            mantenimiento + 350
        )

    else:

        calorias = mantenimiento


    # --------------------------------------------------------
    # EDAD METABÓLICA
    # --------------------------------------------------------

    desvio_imc = max(
        0,
        imc - 22.0
    )

    desvio_grasa = max(
        0,
        pct_grasa
        - (
            15.0
            if sexo == "Masculino"
            else 22.0
        )
    )

    edad_metabolica = int(
        edad
        + (
            desvio_imc
            * 0.6
        )
        + (
            desvio_grasa
            * 0.4
        )
    )


    imc = float(
        round(imc, 2)
    )

    pct_grasa = float(
        round(pct_grasa, 2)
    )

    calorias = int(
        round(calorias)
    )

    edad_metabolica = int(
        edad_metabolica
    )


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
# NORMALIZAR CÉDULA
# ============================================================

def normalizar_cedula(valor):

    if pd.isna(valor):

        return ""

    return (
        str(valor)
        .replace(".0", "")
        .strip()
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


        # ====================================================
        # USUARIOS
        # ====================================================

        usuarios_raw = res.get(
            "usuarios",
            []
        )

        if len(usuarios_raw) > 1:

            columnas_u = [
                str(c)
                .strip()
                .lower()
                for c in usuarios_raw[0]
            ]

            df_u = pd.DataFrame(
                usuarios_raw[1:],
                columns=columnas_u
            )

            df_u = df_u.loc[
                :,
                ~df_u.columns.duplicated()
            ]

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


        # ====================================================
        # HISTORIAL DE MEDIDAS
        # ====================================================

        historial_raw = res.get(
            "historial",
            []
        )

        if len(historial_raw) > 1:

            columnas_h = [
                str(c)
                .strip()
                .lower()
                for c in historial_raw[0]
            ]

            df_m = pd.DataFrame(
                historial_raw[1:],
                columns=columnas_h
            )

            df_m = df_m.loc[
                :,
                ~df_m.columns.duplicated()
            ]

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


        # ====================================================
        # PAGOS
        # ====================================================

        pagos_raw = res.get(
            "pagos",
            []
        )

        if len(pagos_raw) > 1:

            columnas_p = [
                str(c)
                .strip()
                .lower()
                for c in pagos_raw[0]
            ]

            df_p = pd.DataFrame(
                pagos_raw[1:],
                columns=columnas_p
            )

            df_p = df_p.loc[
                :,
                ~df_p.columns.duplicated()
            ]

        else:

            df_p = pd.DataFrame(
                columns=[
                    "id_pago",
                    "cedula",
                    "fecha_pago",
                    "valor",
                    "concepto",
                    "valor_mensualidad",
                ]
            )


        # ====================================================
        # CLASES
        # ====================================================

        clases_raw = res.get(
            "clases",
            []
        )

        if len(clases_raw) > 1:

            columnas_c = [
                str(c)
                .strip()
                .lower()
                for c in clases_raw[0]
            ]

            df_c = pd.DataFrame(
                clases_raw[1:],
                columns=columnas_c
            )

            df_c = df_c.loc[
                :,
                ~df_c.columns.duplicated()
            ]

        else:

            df_c = pd.DataFrame(
                columns=[
                    "id_clase",
                    "cedula",
                    "fecha_clase",
                    "plan",
                    "clases_contratadas",
                    "observacion",
                    "fecha_registro",
                ]
            )


        # ====================================================
        # LIMPIAR CÉDULAS
        # ====================================================

        for dataframe in (
            df_u,
            df_m,
            df_p,
            df_c
        ):

            if (
                not dataframe.empty
                and "cedula" in dataframe.columns
            ):

                dataframe["cedula"] = (
                    dataframe["cedula"]
                    .apply(
                        normalizar_cedula
                    )
                )


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

                df_m[columna] = pd.to_numeric(
                    df_m[columna],
                    errors="coerce"
                )


        # ====================================================
        # NUMÉRICOS DE PAGOS
        # ====================================================

        for columna in [
            "valor",
            "valor_mensualidad",
        ]:

            if columna in df_p.columns:

                df_p[columna] = pd.to_numeric(
                    df_p[columna],
                    errors="coerce"
                )


        # ====================================================
        # NUMÉRICOS DE CLASES
        # ====================================================

        if (
            not df_c.empty
            and "clases_contratadas" in df_c.columns
        ):

            df_c[
                "clases_contratadas"
            ] = pd.to_numeric(
                df_c[
                    "clases_contratadas"
                ],
                errors="coerce"
            )


        # ====================================================
        # FECHAS
        # ====================================================

        if (
            not df_u.empty
            and "fecha_registro" in df_u.columns
        ):

            df_u[
                "fecha_registro"
            ] = (
                df_u[
                    "fecha_registro"
                ]
                .apply(formatear_fecha)
            )


        if (
            not df_m.empty
            and "fecha_evaluacion" in df_m.columns
        ):

            df_m[
                "fecha_evaluacion"
            ] = (
                df_m[
                    "fecha_evaluacion"
                ]
                .apply(formatear_fecha)
            )


        if (
            not df_p.empty
            and "fecha_pago" in df_p.columns
        ):

            df_p[
                "fecha_pago"
            ] = (
                df_p[
                    "fecha_pago"
                ]
                .apply(formatear_fecha)
            )


        if (
            not df_c.empty
            and "fecha_clase" in df_c.columns
        ):

            df_c[
                "fecha_clase"
            ] = (
                df_c[
                    "fecha_clase"
                ]
                .apply(formatear_fecha)
            )


        if (
            not df_c.empty
            and "fecha_registro" in df_c.columns
        ):

            df_c[
                "fecha_registro"
            ] = (
                df_c[
                    "fecha_registro"
                ]
                .apply(formatear_fecha)
            )


        return (
            df_u,
            df_m,
            df_p,
            df_c
        )


    except Exception as e:

        st.error(
            "Error procesando base de datos: "
            f"{e}"
        )

        return (
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame()
        )


# ============================================================
# GRÁFICOS
# ============================================================

def mostrar_graficos_evolucion(
    df_filtrado
):

    if df_filtrado.empty:

        return


    df_graficos = (
        df_filtrado.copy()
    )


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

            df_graficos[col] = (
                pd.to_numeric(
                    df_graficos[col],
                    errors="coerce"
                )
            )


    df_graficos[
        "fecha_dt"
    ] = pd.to_datetime(
        df_graficos[
            "fecha_evaluacion"
        ],
        format="%d-%m-%Y",
        errors="coerce"
    )


    if (
        df_graficos[
            "fecha_dt"
        ].isna().any()
    ):

        df_graficos[
            "fecha_dt"
        ] = pd.to_datetime(
            df_graficos[
                "fecha_evaluacion"
            ],
            errors="coerce"
        )


    df_graficos = (
        df_graficos
        .dropna(
            subset=[
                "fecha_dt"
            ]
        )
        .sort_values(
            by="fecha_dt"
        )
    )


    df_graficos[
        "Fecha"
    ] = (
        df_graficos[
            "fecha_dt"
        ]
        .dt.strftime(
            "%d-%m-%Y"
        )
    )


    st.markdown(
        "### 📈 Gráficas de Evolución Temporal"
    )


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
                "<p style='text-align: center;'>"
                "Evolución del Peso Corporal (kg)"
                "</p>",
                unsafe_allow_html=True,
            )

            df_peso = (
                df_graficos
                .set_index("Fecha")[
                    ["peso_kg"]
                ]
                .rename(
                    columns={
                        "peso_kg":
                        "Peso (kg)"
                    }
                )
            )

            st.line_chart(
                df_peso
            )


        with col_g2:

            st.markdown(
                "<p style='text-align: center;'>"
                "Evolución del % de Grasa Corporal"
                "</p>",
                unsafe_allow_html=True,
            )

            df_grasa = (
                df_graficos
                .set_index("Fecha")[
                    [
                        "porcentaje_grasa"
                    ]
                ]
                .rename(
                    columns={
                        "porcentaje_grasa":
                        "% Grasa"
                    }
                )
            )

            st.line_chart(
                df_grasa
            )


    with tab2:

        st.markdown(
            "<p style='text-align: center;'>"
            "Evolución de Torso y Cintura (cm)"
            "</p>",
            unsafe_allow_html=True,
        )

        columnas_perimetros = []

        nombres_perimetros = {}


        if (
            "cintura_cm"
            in df_graficos.columns
        ):

            columnas_perimetros.append(
                "cintura_cm"
            )

            nombres_perimetros[
                "cintura_cm"
            ] = "Cintura"


        if (
            "pecho_cm"
            in df_graficos.columns
        ):

            columnas_perimetros.append(
                "pecho_cm"
            )

            nombres_perimetros[
                "pecho_cm"
            ] = "Pecho"


        if (
            "cadera_cm"
            in df_graficos.columns
        ):

            columnas_perimetros.append(
                "cadera_cm"
            )

            nombres_perimetros[
                "cadera_cm"
            ] = "Cadera/Glúteos"


        if columnas_perimetros:

            df_peri = (
                df_graficos
                .set_index("Fecha")[
                    columnas_perimetros
                ]
                .rename(
                    columns=
                    nombres_perimetros
                )
            )

            st.line_chart(
                df_peri
            )


    with tab3:

        st.markdown(
            "<p style='text-align: center;'>"
            "Evolución de Brazos (cm)"
            "</p>",
            unsafe_allow_html=True,
        )

        columnas_brazos = []

        nombres_brazos = {}


        if (
            "bicep_der_cm"
            in df_graficos.columns
        ):

            columnas_brazos.append(
                "bicep_der_cm"
            )

            nombres_brazos[
                "bicep_der_cm"
            ] = "Bícep Derecho"


        if (
            "bicep_izq_cm"
            in df_graficos.columns
        ):

            columnas_brazos.append(
                "bicep_izq_cm"
            )

            nombres_brazos[
                "bicep_izq_cm"
            ] = "Bícep Izquierdo"


        if columnas_brazos:

            df_brz = (
                df_graficos
                .set_index("Fecha")[
                    columnas_brazos
                ]
                .rename(
                    columns=nombres_brazos
                )
            )

            st.line_chart(
                df_brz
            )


# ============================================================
# RESUMEN DE CLASES
# ============================================================

def obtener_resumen_clases(
    df_clases,
    cedula
):
    """
    Obtiene el estado del plan actual y las clases realmente tomadas.

    Regla importante:
    - Una fila con fecha_clase vacía = configuración de un nuevo plan.
    - Una fila con fecha_clase = clase realmente tomada.
    - Al configurar un nuevo plan, las clases anteriores dejan de contar
      para el nuevo ciclo.
    """

    resultado = {
        "plan": "Sin plan registrado",
        "clases_contratadas": 0,
        "clases_tomadas": 0,
        "clases_restantes": 0,
        "porcentaje": 0.0,
        "registros": pd.DataFrame(),
    }

    if (
        df_clases is None
        or df_clases.empty
        or "cedula" not in df_clases.columns
    ):
        return resultado

    cedula = normalizar_cedula(cedula)

    registros = df_clases[
        df_clases["cedula"].apply(normalizar_cedula) == cedula
    ].copy()

    if registros.empty:
        return resultado

    # Mantener el orden original de Google Sheets.
    registros["_orden"] = range(len(registros))

    if "fecha_clase" not in registros.columns:
        registros["fecha_clase"] = ""

    fechas_texto = (
        registros["fecha_clase"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    registros["_es_config"] = fechas_texto == ""

    # Buscar la última configuración de plan.
    configuraciones = registros[
        registros["_es_config"]
    ].copy()

    indice_config = None

    if not configuraciones.empty:
        indice_config = int(
            configuraciones["_orden"].iloc[-1]
        )

        config = configuraciones.iloc[-1]

        if "plan" in config.index:
            plan_config = str(
                config["plan"]
            ).strip()

            if plan_config:
                resultado["plan"] = plan_config

        if "clases_contratadas" in config.index:
            cantidad_config = pd.to_numeric(
                config["clases_contratadas"],
                errors="coerce"
            )

            if not pd.isna(cantidad_config):
                resultado["clases_contratadas"] = int(
                    cantidad_config
                )

    # Si nunca hubo configuración explícita, usar el último registro
    # con fecha como referencia histórica.
    if indice_config is None:
        registros_tomados = registros[
            ~registros["_es_config"]
        ].copy()

        if not registros_tomados.empty:
            ultimo = registros_tomados.iloc[-1]

            if "plan" in ultimo.index:
                plan_ultimo = str(
                    ultimo["plan"]
                ).strip()

                if plan_ultimo:
                    resultado["plan"] = plan_ultimo

            if "clases_contratadas" in ultimo.index:
                cantidad_ultimo = pd.to_numeric(
                    ultimo["clases_contratadas"],
                    errors="coerce"
                )

                if not pd.isna(cantidad_ultimo):
                    resultado["clases_contratadas"] = int(
                        cantidad_ultimo
                    )

    # Solo cuentan las clases posteriores a la última configuración.
    if indice_config is not None:
        registros_tomados = registros[
            (registros["_orden"] > indice_config)
            & (~registros["_es_config"])
        ].copy()
    else:
        registros_tomados = registros[
            ~registros["_es_config"]
        ].copy()

    resultado["clases_tomadas"] = len(
        registros_tomados
    )

    resultado["clases_restantes"] = max(
        resultado["clases_contratadas"]
        - resultado["clases_tomadas"],
        0
    )

    if resultado["clases_contratadas"] > 0:
        resultado["porcentaje"] = min(
            (
                resultado["clases_tomadas"]
                / resultado["clases_contratadas"]
            ) * 100,
            100
        )

    # Limpiar columnas internas antes de devolver.
    registros_tomados = registros_tomados.drop(
        columns=[
            "_orden",
            "_es_config"
        ],
        errors="ignore"
    )

    resultado["registros"] = registros_tomados

    return resultado


# ============================================================
# MOSTRAR RESUMEN DE CLASES
# ============================================================

def mostrar_resumen_clases(
    df_clases,
    cedula,
    titulo="🏋️ Clases Personalizadas"
):

    resumen = obtener_resumen_clases(
        df_clases,
        cedula
    )


    st.markdown(
        f"### {titulo}"
    )


    if (
        resumen[
            "clases_contratadas"
        ]
        <= 0
    ):

        st.info(
            "Este cliente todavía no tiene "
            "un plan de clases configurado."
        )

        return


    c1, c2, c3, c4 = st.columns(4)


    c1.metric(
        "Plan",
        resumen["plan"]
    )


    c2.metric(
        "Clases contratadas",
        resumen[
            "clases_contratadas"
        ]
    )


    c3.metric(
        "Clases tomadas",
        resumen[
            "clases_tomadas"
        ]
    )


    c4.metric(
        "Clases restantes",
        resumen[
            "clases_restantes"
        ]
    )


    st.progress(
        int(
            round(
                resumen[
                    "porcentaje"
                ]
            )
        )
    )


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

                df_usuarios, _, _, _ = (
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

                df_usuarios, _, _, _ = (
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

                        st.cache_data.clear()

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


    (
        df_usuarios,
        df_historial,
        df_pagos,
        df_clases
    ) = cargar_bd()


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
                "🏋️ Mis Clases",
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


                        fila_medidas = [

                            str(id_reg),

                            str(fecha_hoy),

                            str(
                                st.session_state[
                                    "cedula"
                                ]
                            ),

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


                        st.cache_data.clear()


                        st.success(
                            "¡Medidas guardadas con éxito!"
                        )


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


        # ====================================================
        # MIS CLASES
        # ====================================================

        elif (
            opcion
            == "🏋️ Mis Clases"
        ):

            st.subheader(
                "🏋️ Mi Plan de Clases Personalizadas"
            )


            mostrar_resumen_clases(
                df_clases,
                st.session_state[
                    "cedula"
                ]
            )


            resumen_clases = (
                obtener_resumen_clases(
                    df_clases,
                    st.session_state[
                        "cedula"
                    ]
                )
            )


            registros_clases = (
                resumen_clases[
                    "registros"
                ]
            )


            if not registros_clases.empty:

                st.markdown(
                    "#### 📅 Clases tomadas"
                )


                tabla = registros_clases.copy()


                columnas_tabla = [

                    columna

                    for columna in [

                        "fecha_clase",
                        "plan",
                        "clases_contratadas",
                        "observacion",

                    ]

                    if columna in tabla.columns

                ]


                tabla = tabla[
                    columnas_tabla
                ]


                tabla = tabla.rename(
                    columns={
                        "fecha_clase":
                            "Fecha de Clase",

                        "plan":
                            "Plan",

                        "clases_contratadas":
                            "Clases Contratadas",

                        "observacion":
                            "Observación",
                    }
                )


                if "Fecha de Clase" in tabla.columns:

                    tabla["_fecha"] = tabla[
                        "Fecha de Clase"
                    ].apply(parsear_fecha)

                    tabla = (
                        tabla
                        .sort_values(
                            "_fecha",
                            ascending=False
                        )
                        .drop(
                            columns=[
                                "_fecha"
                            ]
                        )
                    )


                st.dataframe(
                    tabla.astype(str),
                    use_container_width=True,
                    hide_index=True,
                )


            else:

                st.info(
                    "Todavía no tienes clases registradas."
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

                # ====================================================
                # MENÚ ADMINISTRADOR
                # ====================================================

                opcion_admin = st.sidebar.radio(
                    "MENÚ ADMINISTRADOR",
                    [
                        "👤 Gestión de Clientes",
                        "🏋️ Control de Clases",
                    ],
                )


                # ====================================================
                # GESTIÓN DE CLIENTES
                # ====================================================

                if (
                    opcion_admin
                    == "👤 Gestión de Clientes"
                ):

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
                            # RESUMEN DE CLASES EN PERFIL
                            # ====================================================

                            st.markdown(
                                "---"
                            )


                            mostrar_resumen_clases(
                                df_clases,
                                id_cliente,
                                "🏋️ Resumen de Clases"
                            )


                            # ====================================================
                            # PAGOS Y MENSUALIDAD
                            # ====================================================

                            st.markdown(
                                "---"
                            )

                            st.markdown(
                                "#### 💳 Pagos y Mensualidad"
                            )

                            pagos_cliente = pd.DataFrame()

                            if (
                                not df_pagos.empty
                                and "cedula" in df_pagos.columns
                            ):
                                pagos_cliente = df_pagos[
                                    df_pagos["cedula"]
                                    == id_cliente
                                ].copy()

                            # ------------------------------------------------
                            # MES ACTUAL
                            # ------------------------------------------------

                            hoy = pd.Timestamp.today().normalize()

                            if not pagos_cliente.empty:
                                pagos_cliente["_fecha_dt"] = (
                                    pagos_cliente["fecha_pago"]
                                    .apply(parsear_fecha)
                                    if "fecha_pago" in pagos_cliente.columns
                                    else pd.NaT
                                )

                                pagos_mes_actual = pagos_cliente[
                                    pagos_cliente["_fecha_dt"].notna()
                                    & (
                                        pagos_cliente["_fecha_dt"].dt.year
                                        == hoy.year
                                    )
                                    & (
                                        pagos_cliente["_fecha_dt"].dt.month
                                        == hoy.month
                                    )
                                ].copy()

                            else:
                                pagos_mes_actual = pd.DataFrame()

                            # ------------------------------------------------
                            # MENSUALIDAD ACTUAL
                            # ------------------------------------------------

                            valor_mensualidad_actual = 0.0

                            if (
                                not pagos_cliente.empty
                                and "valor_mensualidad"
                                in pagos_cliente.columns
                            ):
                                mensualidades_validas = (
                                    pd.to_numeric(
                                        pagos_cliente[
                                            "valor_mensualidad"
                                        ],
                                        errors="coerce"
                                    )
                                    .dropna()
                                )

                                if not mensualidades_validas.empty:
                                    valor_mensualidad_actual = float(
                                        mensualidades_validas.iloc[-1]
                                    )

                            if valor_mensualidad_actual <= 0:
                                valor_mensualidad_actual = 250000.0

                            # ------------------------------------------------
                            # TOTAL PAGADO DEL MES
                            # ------------------------------------------------

                            total_pagado = 0.0

                            if (
                                not pagos_mes_actual.empty
                                and "valor" in pagos_mes_actual.columns
                            ):
                                total_pagado = float(
                                    pd.to_numeric(
                                        pagos_mes_actual["valor"],
                                        errors="coerce"
                                    )
                                    .fillna(0)
                                    .sum()
                                )

                            saldo_actual = max(
                                valor_mensualidad_actual
                                - total_pagado,
                                0.0
                            )

                            if saldo_actual <= 0.001:
                                estado_pago = "🟢 PAGADO"
                            elif total_pagado > 0:
                                estado_pago = "🟡 ABONO"
                            else:
                                estado_pago = "🔴 PENDIENTE"

                            nombre_mes = hoy.strftime("%B").capitalize()

                            p1, p2, p3, p4 = st.columns(4)

                            p1.metric(
                                "Mensualidad",
                                f"${valor_mensualidad_actual:,.0f}"
                            )

                            p2.metric(
                                "Pagado este mes",
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

                            st.caption(
                                f"📅 Estado de pagos correspondiente a "
                                f"{nombre_mes} de {hoy.year}."
                            )

                            # ====================================================
                            # REGISTRAR PAGO
                            # ====================================================

                            with st.expander(
                                "➕ Registrar nuevo pago / abono",
                                expanded=saldo_actual > 0
                            ):

                                with st.form(
                                    f"form_pago_{id_cliente}"
                                ):

                                    mensualidad_default = (
                                        valor_mensualidad_actual
                                    )

                                    valor_mensualidad = st.number_input(
                                        "Valor de la mensualidad ($):",
                                        min_value=1.0,
                                        value=float(
                                            mensualidad_default
                                        ),
                                        step=5000.0,
                                        format="%.0f",
                                    )

                                    saldo_para_nuevo_pago = max(
                                        float(
                                            valor_mensualidad
                                        )
                                        - total_pagado,
                                        0.0
                                    )

                                    if total_pagado > 0:
                                        st.caption(
                                            "Pagado este mes: "
                                            f"${total_pagado:,.0f} | "
                                            "Saldo según esta mensualidad: "
                                            f"${saldo_para_nuevo_pago:,.0f}"
                                        )

                                    valor_pago_default = (
                                        saldo_para_nuevo_pago
                                        if saldo_para_nuevo_pago > 0
                                        else 1.0
                                    )

                                    valor_pago = st.number_input(
                                        "Valor del pago / abono ($):",
                                        min_value=1.0,
                                        value=float(
                                            valor_pago_default
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
                                                    "❌ La mensualidad debe "
                                                    "ser mayor que cero."
                                                )
                                                st.stop()

                                            if valor_pago <= 0:
                                                st.error(
                                                    "❌ El valor del pago "
                                                    "debe ser mayor que cero."
                                                )
                                                st.stop()

                                            if not concepto_pago:
                                                concepto_pago = (
                                                    "Abono mensualidad"
                                                )

                                            nuevo_total = (
                                                total_pagado
                                                + valor_pago
                                            )

                                            if (
                                                nuevo_total
                                                > valor_mensualidad
                                                + 0.001
                                            ):
                                                st.error(
                                                    "❌ El abono supera "
                                                    "el saldo pendiente. "
                                                    f"Saldo disponible: "
                                                    f"${saldo_para_nuevo_pago:,.0f}."
                                                )
                                                st.stop()

                                            id_pago = (
                                                f"{id_cliente}_"
                                                f"{datetime.today().strftime('%Y%m%d%H%M%S%f')}"
                                            )

                                            fecha_pago = (
                                                datetime.today()
                                                .strftime("%d-%m-%Y")
                                            )

                                            fila_pago = [
                                                str(id_pago),
                                                str(id_cliente),
                                                str(fecha_pago),
                                                float(valor_pago),
                                                str(concepto_pago),
                                                float(
                                                    valor_mensualidad
                                                ),
                                            ]

                                            respuesta_pago = requests.post(
                                                URL_API,
                                                json={
                                                    "action":
                                                    "guardar_pago",
                                                    "row":
                                                    fila_pago,
                                                },
                                                timeout=30,
                                            )

                                            respuesta_pago.raise_for_status()

                                            try:
                                                resultado_pago = (
                                                    respuesta_pago.json()
                                                )
                                            except Exception:
                                                resultado_pago = {}

                                            if (
                                                resultado_pago.get(
                                                    "status"
                                                )
                                                == "error"
                                            ):
                                                st.error(
                                                    "❌ Google Apps Script "
                                                    "reportó un error: "
                                                    + str(
                                                        resultado_pago.get(
                                                            "message",
                                                            "Error desconocido"
                                                        )
                                                    )
                                                )
                                                st.stop()

                                            st.cache_data.clear()

                                            nuevo_saldo = max(
                                                valor_mensualidad
                                                - nuevo_total,
                                                0.0
                                            )

                                            if nuevo_saldo <= 0.001:
                                                st.success(
                                                    "✅ Pago registrado. "
                                                    "La mensualidad de este "
                                                    "mes quedó completamente "
                                                    "pagada."
                                                )
                                            else:
                                                st.success(
                                                    "✅ Abono registrado "
                                                    "correctamente. "
                                                    f"Saldo pendiente: "
                                                    f"${nuevo_saldo:,.0f}."
                                                )

                                            st.rerun()

                                        except Exception as e:
                                            st.error(
                                                "❌ Error registrando "
                                                f"el pago: {e}"
                                            )

                            # ====================================================
                            # HISTORIAL DE PAGOS
                            # ====================================================

                            if not pagos_cliente.empty:

                                st.markdown(
                                    "#### 📜 Historial de Pagos"
                                )

                                pagos_mostrar = (
                                    pagos_cliente.copy()
                                )

                                if "_fecha_dt" not in pagos_mostrar.columns:
                                    pagos_mostrar["_fecha_dt"] = (
                                        pagos_mostrar["fecha_pago"]
                                        .apply(parsear_fecha)
                                        if "fecha_pago" in pagos_mostrar.columns
                                        else pd.NaT
                                    )

                                pagos_mostrar = (
                                    pagos_mostrar
                                    .sort_values(
                                        by="_fecha_dt",
                                        ascending=False
                                    )
                                    .drop(
                                        columns=[
                                            "_fecha_dt"
                                        ],
                                        errors="ignore"
                                    )
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
                                    tabla_pagos[
                                        "valor_mensualidad"
                                    ] = (
                                        pd.to_numeric(
                                            tabla_pagos[
                                                "valor_mensualidad"
                                            ],
                                            errors="coerce"
                                        )
                                        .fillna(0)
                                        .map(
                                            lambda x: f"${x:,.0f}"
                                        )
                                    )

                                tabla_pagos = (
                                    tabla_pagos.rename(
                                        columns={
                                            "fecha_pago": "Fecha",
                                            "valor": "Pago",
                                            "concepto": "Concepto",
                                            "valor_mensualidad":
                                                "Mensualidad",
                                        }
                                    )
                                )

                                st.dataframe(
                                    tabla_pagos,
                                    use_container_width=True,
                                    hide_index=True,
                                )

                            else:
                                st.info(
                                    "Este cliente todavía "
                                    "no tiene pagos registrados."
                                )

                            # ====================================================
                            # HISTORIAL DE CLASES DEL CLIENTE
                            # ====================================================

                            st.markdown(
                                "---"
                            )

                            mostrar_resumen_clases(
                                df_clases,
                                id_cliente,
                                "🏋️ Historial de Clases"
                            )


                            resumen_cliente_clases = (
                                obtener_resumen_clases(
                                    df_clases,
                                    id_cliente
                                )
                            )


                            if not resumen_cliente_clases[
                                "registros"
                            ].empty:

                                clases_mostrar = (
                                    resumen_cliente_clases[
                                        "registros"
                                    ].copy()
                                )


                                columnas_clases = [

                                    columna

                                    for columna in [

                                        "fecha_clase",
                                        "plan",
                                        "clases_contratadas",
                                        "observacion",

                                    ]

                                    if columna
                                    in clases_mostrar.columns

                                ]


                                tabla_clases = (
                                    clases_mostrar[
                                        columnas_clases
                                    ].copy()
                                )


                                tabla_clases = (
                                    tabla_clases.rename(
                                        columns={

                                            "fecha_clase":
                                                "Fecha Clase",

                                            "plan":
                                                "Plan",

                                            "clases_contratadas":
                                                "Clases Contratadas",

                                            "observacion":
                                                "Observación",

                                        }
                                    )
                                )


                                st.dataframe(
                                    tabla_clases.astype(str),
                                    use_container_width=True,
                                    hide_index=True,
                                )


                            # ====================================================
                            # HISTORIAL Y PROGRESO
                            # ====================================================

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


                # ====================================================
                # CONTROL DE CLASES
                # ====================================================

                elif (
                    opcion_admin
                    == "🏋️ Control de Clases"
                ):

                    st.subheader(
                        "🏋️ Control de Clases Personalizadas"
                    )


                    st.info(
                        "Aquí el ADMIN registra manualmente "
                        "cada clase realmente tomada. "
                        "No se generan clases automáticamente."
                    )


                    # ------------------------------------------------
                    # SELECCIÓN DEL CLIENTE
                    # ------------------------------------------------

                    cliente_clase_sel = st.selectbox(

                        "👤 Seleccionar Cliente:",

                        clientes[
                            "cedula"
                        ].astype(str)
                        + " - "
                        + clientes[
                            "nombre_completo"
                        ].astype(str),

                        key="selector_cliente_clases"

                    )


                    id_cliente_clases = (
                        cliente_clase_sel
                        .split(" - ")[0]
                        .strip()
                    )


                    nombre_cliente_clases = (
                        cliente_clase_sel
                        .split(" - ", 1)[1]
                    )


                    st.markdown(
                        f"### 👤 {nombre_cliente_clases}"
                    )


                    # ------------------------------------------------
                    # RESUMEN ACTUAL
                    # ------------------------------------------------

                    mostrar_resumen_clases(
                        df_clases,
                        id_cliente_clases
                    )


                    resumen_actual = (
                        obtener_resumen_clases(
                            df_clases,
                            id_cliente_clases
                        )
                    )


                    # ------------------------------------------------
                    # CONFIGURACIÓN DEL PLAN
                    # ------------------------------------------------

                    st.markdown(
                        "---"
                    )

                    st.markdown(
                        "#### ⚙️ Configuración del plan"
                    )


                    with st.form(
                        f"form_config_clases_{id_cliente_clases}"
                    ):

                        col_plan1, col_plan2 = st.columns(2)


                        with col_plan1:

                            plan_cliente = st.selectbox(
                                "Plan:",
                                [
                                    "Premium",
                                    "Personalizado",
                                    "Otro",
                                ],
                                index=(
                                    0
                                    if resumen_actual[
                                        "plan"
                                    ]
                                    == "Sin plan registrado"
                                    else
                                    [
                                        "Premium",
                                        "Personalizado",
                                        "Otro",
                                    ].index(
                                        resumen_actual[
                                            "plan"
                                        ]
                                    )
                                    if resumen_actual[
                                        "plan"
                                    ]
                                    in [
                                        "Premium",
                                        "Personalizado",
                                        "Otro",
                                    ]
                                    else 0
                                )
                            )


                        with col_plan2:

                            clases_contratadas = st.number_input(
                                "Número de clases contratadas:",
                                min_value=1,
                                max_value=500,
                                value=(
                                    resumen_actual[
                                        "clases_contratadas"
                                    ]
                                    if resumen_actual[
                                        "clases_contratadas"
                                    ] > 0
                                    else 20
                                ),
                                step=1,
                            )


                        st.caption(
                            "Ejemplo: el plan Premium puede "
                            "tener 20 clases disponibles. "
                            "Las clases solo se descuentan "
                            "cuando el ADMIN registra una fecha."
                        )


                        guardar_config_plan = st.form_submit_button(
                            "💾 Guardar configuración del plan",
                            use_container_width=True
                        )


                        if guardar_config_plan:

                            try:

                                # ------------------------------------------------
                                # Para configurar el plan sin crear una clase,
                                # usamos una fecha vacía.
                                # ------------------------------------------------

                                id_config = (
                                    f"{id_cliente_clases}_PLAN_"
                                    f"{datetime.today().strftime('%Y%m%d%H%M%S%f')}"
                                )


                                fila_config = [

                                    str(id_config),

                                    str(id_cliente_clases),

                                    "",

                                    str(plan_cliente),

                                    int(
                                        clases_contratadas
                                    ),

                                    "Configuración del plan",

                                    datetime.today().strftime(
                                        "%d-%m-%Y"
                                    ),

                                ]


                                respuesta_config = requests.post(

                                    URL_API,

                                    json={
                                        "action":
                                        "guardar_clase",

                                        "row":
                                        fila_config,
                                    },

                                    timeout=30,

                                )


                                respuesta_config.raise_for_status()


                                try:

                                    resultado_config = (
                                        respuesta_config.json()
                                    )

                                except Exception:

                                    resultado_config = {}


                                if (
                                    resultado_config.get(
                                        "status"
                                    )
                                    == "error"
                                ):

                                    st.error(
                                        "❌ Google Apps Script "
                                        "reportó un error: "
                                        + str(
                                            resultado_config.get(
                                                "message",
                                                "Error desconocido"
                                            )
                                        )
                                    )

                                    st.stop()


                                st.cache_data.clear()


                                st.success(
                                    "✅ Configuración del plan "
                                    "guardada correctamente."
                                )


                                st.rerun()


                            except Exception as e:

                                st.error(
                                    "❌ Error guardando "
                                    f"el plan: {e}"
                                )


                    # ------------------------------------------------
                    # REGISTRAR CLASE
                    # ------------------------------------------------

                    st.markdown(
                        "---"
                    )

                    st.markdown(
                        "#### 📅 Registrar clase tomada"
                    )


                    if (
                        resumen_actual[
                            "clases_contratadas"
                        ]
                        > 0
                        and
                        resumen_actual[
                            "clases_tomadas"
                        ]
                        >=
                        resumen_actual[
                            "clases_contratadas"
                        ]
                    ):

                        st.warning(
                            "⚠️ Este cliente ya utilizó "
                            "todas las clases contratadas."
                        )


                    with st.form(
                        f"form_registro_clase_{id_cliente_clases}"
                    ):

                        fecha_clase = st.date_input(
                            "📅 Fecha de la clase tomada:",
                            value=date.today(),
                            max_value=date.today(),
                            format="DD-MM-YYYY",
                        )


                        observacion_clase = st.text_input(
                            "Observación de la clase:",
                            placeholder=(
                                "Ej: Entrenamiento de pierna, "
                                "sesión personalizada, etc."
                            )
                        ).strip()


                        registrar_clase = st.form_submit_button(
                            "🏋️ Registrar Clase Tomada",
                            use_container_width=True
                        )


                        if registrar_clase:

                            try:

                                # ------------------------------------------------
                                # VALIDAR PLAN
                                # ------------------------------------------------

                                if (
                                    resumen_actual[
                                        "clases_contratadas"
                                    ]
                                    <= 0
                                ):

                                    st.error(
                                        "❌ Primero debes configurar "
                                        "el plan y el número de clases "
                                        "contratadas."
                                    )

                                    st.stop()


                                # ------------------------------------------------
                                # VALIDAR CUPO
                                # ------------------------------------------------

                                if (
                                    resumen_actual[
                                        "clases_tomadas"
                                    ]
                                    >=
                                    resumen_actual[
                                        "clases_contratadas"
                                    ]
                                ):

                                    st.error(
                                        "❌ El cliente ya utilizó "
                                        "todas las clases de su plan."
                                    )

                                    st.stop()


                                # ------------------------------------------------
                                # FECHA
                                # ------------------------------------------------

                                fecha_clase_str = (
                                    fecha_clase.strftime(
                                        "%d-%m-%Y"
                                    )
                                )


                                # ------------------------------------------------
                                # EVITAR DUPLICADOS
                                # ------------------------------------------------

                                clases_cliente = (
                                    resumen_actual[
                                        "registros"
                                    ]
                                )


                                if (
                                    not clases_cliente.empty
                                    and
                                    "fecha_clase"
                                    in clases_cliente.columns
                                ):

                                    fechas_existentes = (
                                        clases_cliente[
                                            "fecha_clase"
                                        ]
                                        .astype(str)
                                        .str.strip()
                                        .tolist()
                                    )


                                    if (
                                        fecha_clase_str
                                        in fechas_existentes
                                    ):

                                        st.error(
                                            "❌ Ya existe una clase "
                                            "registrada para este cliente "
                                            f"el {fecha_clase_str}."
                                        )

                                        st.stop()


                                # ------------------------------------------------
                                # GENERAR ID
                                # ------------------------------------------------

                                id_clase = (
                                    f"{id_cliente_clases}_"
                                    f"{fecha_clase.strftime('%Y%m%d')}_"
                                    f"{datetime.today().strftime('%H%M%S%f')}"
                                )


                                # ------------------------------------------------
                                # FILA
                                # ------------------------------------------------

                                fila_clase = [

                                    str(id_clase),

                                    str(id_cliente_clases),

                                    str(fecha_clase_str),

                                    str(
                                        resumen_actual[
                                            "plan"
                                        ]
                                    ),

                                    int(
                                        resumen_actual[
                                            "clases_contratadas"
                                        ]
                                    ),

                                    (
                                        observacion_clase
                                        if observacion_clase
                                        else
                                        "Clase personalizada"
                                    ),

                                    datetime.today().strftime(
                                        "%d-%m-%Y"
                                    ),

                                ]


                                # ------------------------------------------------
                                # ENVIAR A APPS SCRIPT
                                # ------------------------------------------------

                                respuesta_clase = requests.post(

                                    URL_API,

                                    json={
                                        "action":
                                        "guardar_clase",

                                        "row":
                                        fila_clase,
                                    },

                                    timeout=30,

                                )


                                respuesta_clase.raise_for_status()


                                try:

                                    resultado_clase = (
                                        respuesta_clase.json()
                                    )

                                except Exception:

                                    resultado_clase = {}


                                if (
                                    resultado_clase.get(
                                        "status"
                                    )
                                    == "error"
                                ):

                                    st.error(
                                        "❌ Google Apps Script "
                                        "reportó un error: "
                                        + str(
                                            resultado_clase.get(
                                                "message",
                                                "Error desconocido"
                                            )
                                        )
                                    )

                                    st.stop()


                                st.cache_data.clear()


                                clases_nuevas = (
                                    resumen_actual[
                                        "clases_tomadas"
                                    ]
                                    + 1
                                )


                                clases_restantes_nuevas = max(
                                    resumen_actual[
                                        "clases_contratadas"
                                    ]
                                    -
                                    clases_nuevas,
                                    0
                                )


                                porcentaje_nuevo = (
                                    clases_nuevas
                                    /
                                    resumen_actual[
                                        "clases_contratadas"
                                    ]
                                ) * 100


                                st.success(
                                    "✅ Clase registrada correctamente."
                                )


                                c1, c2, c3 = st.columns(3)


                                c1.metric(
                                    "Clases tomadas",
                                    clases_nuevas
                                )


                                c2.metric(
                                    "Clases restantes",
                                    clases_restantes_nuevas
                                )


                                c3.metric(
                                    "% utilizado",
                                    f"{min(porcentaje_nuevo, 100):.1f}%"
                                )


                                st.rerun()


                            except Exception as e:

                                st.error(
                                    "❌ Error registrando "
                                    f"la clase: {e}"
                                )


                    # ------------------------------------------------
                    # HISTORIAL DE CLASES
                    # ------------------------------------------------

                    st.markdown(
                        "---"
                    )

                    st.markdown(
                        "#### 📋 Historial de clases tomadas"
                    )


                    resumen_historial = (
                        obtener_resumen_clases(
                            df_clases,
                            id_cliente_clases
                        )
                    )


                    registros_historial = (
                        resumen_historial[
                            "registros"
                        ]
                    )


                    if not registros_historial.empty:

                        historial = (
                            registros_historial.copy()
                        )


                        if "fecha_clase" in historial.columns:

                            historial[
                                "_fecha_dt"
                            ] = historial[
                                "fecha_clase"
                            ].apply(parsear_fecha)


                            historial = (
                                historial
                                .sort_values(
                                    "_fecha_dt",
                                    ascending=False
                                )
                            )


                        columnas_historial = [

                            columna

                            for columna in [

                                "fecha_clase",
                                "plan",
                                "clases_contratadas",
                                "observacion",
                                "fecha_registro",

                            ]

                            if columna
                            in historial.columns

                        ]


                        historial = historial[
                            columnas_historial
                        ].copy()


                        historial = (
                            historial.rename(
                                columns={

                                    "fecha_clase":
                                        "Fecha Clase",

                                    "plan":
                                        "Plan",

                                    "clases_contratadas":
                                        "Clases Contratadas",

                                    "observacion":
                                        "Observación",

                                    "fecha_registro":
                                        "Registrado",

                                }
                            )
                        )


                        st.dataframe(
                            historial.astype(str),
                            use_container_width=True,
                            hide_index=True,
                        )


                    else:

                        st.info(
                            "Este cliente todavía "
                            "no tiene clases registradas."
                        )


            else:

                st.info(
                    "No hay clientes registrados "
                    "actualmente."
                )
