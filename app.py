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
    "https://script.google.com/macros/s/AKfycbxE3iwforn3OwglccONjbkJ_H8JtLgmmLcQ9SLGrFq-m10CyHs30WkzS4jq8pPf6BHx/exec"
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


       
