import os
import streamlit as st
import pandas as pd
import requests
import math
import urllib.parse
from datetime import datetime
from PIL import Image

# 🔗 TU URL DE GOOGLE APPS SCRIPT
URL_API = "https://google.com"

ruta_logo = "logo.png"
icono_pestana = Image.open(ruta_logo) if os.path.exists(ruta_logo) else "🏋️‍♂️"

st.set_page_config(page_title="Power Training - Personalizado", page_icon=icono_pestana, layout="wide")

# Estilos visuales en modo oscuro
st.markdown("""
    <style>
        .stApp { background-color: #111111; }
        h1, h2, h3, h4 { color: #ffffff !important; text-align: center; }
        p, label, .stMarkdown { color: #dddddd !important; }
        div[data-testid="stDecoration"] { display: none; }
    </style>
""", unsafe_allow_html=True)

# --- MOSTRAR LOGO CENTRADO EN LA CABECERA ---
if os.path.exists(ruta_logo):
    col_l1, col_l2, col_l3 = st.columns()
    with col_l2:
        st.image(Image.open(ruta_logo), width=180)

# --- FUNCIONES DE CÁLCULO FÍSICO Y SALUD ---
def calcular_metricas(peso, estatura_cm, edad, sexo, cuello, cintura, cadera, meta):
    estatura_m = estatura_cm / 100.0
    imc = peso / (estatura_m ** 2)
    
    try:
        if sexo == "Masculino":
            pct_grasa = 86.010 * math.log10(cintura - cuello) - 70.041 * math.log10(estatura_cm) + 36.76
        else:
            pct_grasa = 163.205 * math.log10(cintura + cadera - cuello) - 97.684 * math.log10(estatura_cm) - 78.387
        pct_grasa = max(pct_grasa, 4.0)
    except:
        pct_grasa = 20.0

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

# --- FUNCIÓN PARA LIMPIAR Y GENERAR WHATSAPP (COLOMBIA) ---
def link_whatsapp(num_celular, nombre_cliente, mensaje=""):
    num_limpio = str(num_celular).strip().replace(" ", "").replace("-", "").replace(".", "")
    if not num_limpio.startswith("57"):
        num_limpio = "57" + num_limpio
        
    if not mensaje:
        mensaje = f"💪 ¡Hola {nombre_cliente}! Te saludamos de tu plan de Entrenamiento Personalizado. ¡Queremos revisar cómo van tus avances!"
        
    return f"https://wa.me{num_limpio}?text={urllib.parse.quote(mensaje)}"

# --- CARGAR DATOS DESDE GOOGLE SHEETS ---
@st.cache_data(ttl=2)
def cargar_bd():
    try:
        res = requests.get(URL_API).json()
        
        usuarios_raw = res.get("usuarios", [])
        if len(usuarios_raw) > 1:
            columnas_u = [str(c).strip().lower() for c in usuarios_raw[0]]
            df_u = pd.DataFrame(usuarios_raw[1:], columns=columnas_u)
        else:
            df_u = pd.DataFrame(columns=["cedula", "nombre_completo", "whatsapp", "eps", "condiciones_medicas", "rol", "password", "fecha_registro"])

        historial_raw = res.get("historial", [])
        if len(historial_raw) > 1:
            columnas_h = [str(c).strip().lower() for c in historial_raw[0]]
            df_m = pd.DataFrame(historial_raw[1:], columns=columnas_h)
        else:
            df_m = pd.DataFrame(columns=["id_registro", "fecha_evaluacion", "cedula", "edad", "sexo", "meta", "peso_kg", "estatura_cm", "cuello_cm", "hombros_cm", "bicep_der_cm", "bicep_izq_cm", "pecho_cm", "cintura_cm", "cadera_cm", "pierna_der_cm", "pierna_izq_cm", "gemelo_der_cm", "gemelo_izq_cm", "imc", "porcentaje_grasa", "calorias_objetivo", "edad_metabolica"])

        if "cedula" in df_u.columns:
            df_u["cedula"] = df_u["cedula"].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        if not df_m.empty and "cedula" in df_m.columns:
            df_m["cedula"] = df_m["cedula"].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

        return df_u, df_m
    except Exception as e:
        return pd.DataFrame(), pd.DataFrame()

# --- AUTENTICACIÓN / SESIÓN ---
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
    st.session_state["rol"] = None
    st.session_state["cedula"] = None
    st.session_state["nombre"] = None

st.title("🏋️‍♂️ PERSONAL TRAINING & EVOLUTION TRACKER")
# --- LOGIN / REGISTRO ---
if not st.session_state["autenticado"]:
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🔐 Iniciar Sesión")
        cedula_ingreso = st.text_input("Número de Cédula / ID:").strip()
        pass_ingreso = st.text_input("Contraseña:", type="password").strip()
        
        if st.button("Ingresar", use_container_width=True):
            if cedula_ingreso == "admin" and pass_ingreso == "admin123":
                st.session_state["autenticado"] = True
                st.session_state["rol"] = "Admin"
                st.session_state["cedula"] = "ADMIN"
                st.session_state["nombre"] = "Administrador"
                st.rerun()
            else:
                df_usuarios, _ = cargar_bd()
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

    with col2:
        st.subheader("📝 Crear Cuenta Nueva")
        with st.form("form_registro"):
            reg_cedula = st.text_input("Número de Cédula / ID:").strip()
            reg_nombre = st.text_input("Nombre Completo:").strip()
            reg_whatsapp = st.text_input("Número de Celular (10 dígitos Colombia):", placeholder="3101234567").strip()
            reg_eps = st.text_input("EPS / Seguro de Salud:").strip()
            reg_condiciones = st.text_area("Condiciones Médicas / Lesiones / Cirugías:").strip()
            reg_pass = st.text_input("Crea tu Contraseña:", type="password").strip()
            
            if st.form_submit_button("Crear Perfil"):
                df_usuarios, _ = cargar_bd()
                if not reg_cedula or not reg_nombre or not reg_pass:
                    st.error("⚠️ Cédula, Nombre y Contraseña son obligatorios.")
                elif not df_usuarios.empty and reg_cedula in df_usuarios["cedula"].values:
                    st.error("❌ Esta cédula ya está registrada.")
                else:
                    nueva_fila = [reg_cedula, reg_nombre, reg_whatsapp, reg_eps if reg_eps else "NINGUNA", reg_condiciones if reg_condiciones else "NINGUNA", "Cliente", reg_pass, datetime.today().strftime('%Y-%m-%d')]
                    try:
                        requests.post(URL_API, json={"action": "registrar_usuario", "row": nueva_fila})
                        st.cache_data.clear()
                        st.success("🎉 ¡Perfil creado con éxito! Ya puedes iniciar sesión.")
                    except Exception as e:
                        st.error(f"Error al guardar usuario: {e}")

# --- PANELES UNA VEZ AUTENTICADO ---
else:
    st.sidebar.markdown(f"### 👤 {st.session_state['nombre']}")
    st.sidebar.markdown(f"**Rol:** {st.session_state['rol']}")
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state["autenticado"] = False
        st.session_state["rol"] = None
        st.session_state["cedula"] = None
        st.session_state["nombre"] = None
        st.rerun()

    df_usuarios, df_historial = cargar_bd()

    if st.session_state["rol"] == "Cliente":
        opcion = st.sidebar.radio("MENÚ", ["📏 Registrar Medidas Hoy", "📊 Ver Mi Progreso"])
        
        if opcion == "📏 Registrar Medidas Hoy":
            st.subheader("Registro de Evaluación Antropométrica")
            with st.form("form_medidas_cliente"):
                c1, c2, c3 = st.columns(3)
                peso = c1.number_input("Peso (kg):", 30.0, 200.0, 70.0, 0.5)
                estatura = c2.number_input("Estatura (cm):", 100.0, 220.0, 170.0, 1.0)
                edad = c3.number_input("Edad (años):", 10, 90, 25)
                sexo = c1.selectbox("Sexo Fisiológico:", ["Masculino", "Femenino"])
                meta = c2.selectbox("Objetivo Principal:", ["Perder Grasa", "Ganar Músculo", "Mantenimiento"])
                
                st.markdown("---")
                st.write("**Medidas Corporales (cm)**")
                m1, m2, m3, m4 = st.columns(4)
                cuello = m1.number_input("Cuello:", 20.0, 60.0, 38.0)
                hombros = m2.number_input("Hombros:", 50.0, 180.0, 110.0)
                pecho = m3.number_input("Pecho:", 50.0, 180.0, 95.0)
                cintura = m4.number_input("Cintura / Abdomen:", 40.0, 180.0, 80.0)
                
                bicep_der = m1.number_input("Bícep Der:", 15.0, 60.0, 32.0)
                bicep_izq = m2.number_input("Bícep Izq:", 15.0, 60.0, 32.0)
                cadera = m3.number_input("Glúteos / Cadera:", 40.0, 180.0, 95.0)
                pierna_der = m4.number_input("Pierna Der:", 20.0, 90.0, 55.0)
                
                pierna_izq = m1.number_input("Pierna Izq:", 20.0, 90.0, 55.0)
                gemelo_der = m2.number_input("Gemelo Der:", 15.0, 60.0, 35.0)
                gemelo_izq = m3.number_input("Gemelo Izq:", 15.0, 60.0, 35.0)
                
                if st.form_submit_button("Guardar Evaluación"):
                    imc, grasa, cals, edad_bio = calcular_metricas(peso, estatura, edad, sexo, cuello, cintura, cadera, meta)
                    id_reg = f"{st.session_state['cedula']}_{datetime.today().strftime('%Y%m%d%H%M')}"
                    fecha_hoy = datetime.today().strftime('%Y-%m-%d')
                    fila_medidas = [id_reg, fecha_hoy, st.session_state['cedula'], edad, sexo, meta, peso, estatura, cuello, hombros, bicep_der, bicep_izq, pecho, cintura, cadera, pierna_der, pierna_izq, gemelo_der, gemelo_izq, imc, grasa, cals, edad_bio]
                    
                    try:
                        requests.post(URL_API, json={"action": "guardar_medidas", "row": fila_medidas})
                        st.cache_data.clear()
                        st.success("🎉 ¡Medidas guardadas con éxito!")
                        r1, r2, r3, r4 = st.columns(4)
                        r1.metric("IMC", f"{imc}")
                        r2.metric("% Grasa Estimada", f"{grasa}%")
                        r3.metric("Calorías Recomendadas", f"{cals} kcal")
                        r4.metric("Edad Aparentada (Salud)", f"{edad_bio} años")
                    except Exception as e:
                        st.error(f"Error al enviar datos: {e}")

        elif opcion == "📊 Ver Mi Progreso":
            st.subheader("📉 Comparativa de Evolución")
            user_id = str(st.session_state['cedula']).strip()
            mis_registros = df_historial[df_historial["cedula"] == user_id] if not df_historial.empty else pd.DataFrame()
            
            if len(mis_registros) >= 2:
                mis_registros = mis_registros.sort_values(by="fecha_evaluacion")
                inicial = mis_registros.iloc[0]
                actual = mis_registros.iloc[-1]
                
                def get_val(row, keys_posibles, default=0.0):
                    for k in keys_posibles:
                        if k in row.index:
                            try: return float(row[k])
                            except: pass
                    return default
                
                peso_i = get_val(inicial, ["peso_kg", "peso", "peso(kg)"], 70.0)
                peso_a = get_val(actual, ["peso_kg", "peso", "peso(kg)"], 70.0)
                cint_i = get_val(inicial, ["cintura_cm", "cintura", "cintura / abdomen"], 80.0)
                cint_a = get_val(actual, ["cintura_cm", "cintura", "cintura / abdomen"], 80.0)
                gras_i = get_val(inicial, ["porcentaje_grasa", "grasa", "% grasa"], 20.0)
                gras_a = get_val(actual, ["porcentaje_grasa", "grasa", "% grasa"], 20.0)
                
                diff_peso = peso_a - peso_i
                diff_cintura = cint_a - cint_i
                diff_grasa = gras_a - gras_i
                
                st.info(f"📊 **Resumen desde tu primer registro ({inicial.get('fecha_evaluacion', 'Inicial')}) hasta hoy ({actual.get('fecha_evaluacion', 'Actual')}):**")
                c1, c2, c3 = st.columns(3)
                c1.metric("Variación de Peso", f"{peso_a} kg", f"{diff_peso:.1f} kg")
                c2.metric("Variación de Cintura", f"{cint_a} cm", f"{diff_cintura:.1f} cm")
                c3.metric("Variación % Grasa", f"{gras_a}%", f"{diff_grasa:.1f}%")
                
                st.table(mis_registros.astype(str))
            elif len(mis_registros) == 1:
                st.warning("⚠️ Tienes 1 registro guardado con éxito. Guarda una nueva evaluación para poder calcular la comparativa.")
                st.table(mis_registros.astype(str))
            else:
                st.info("Aún no has registrado ninguna evaluación física.")

    elif st.session_state["rol"] == "Admin":
        st.subheader("👑 Panel de Control General")
        if not df_usuarios.empty:
            clientes = df_usuarios[df_usuarios["rol"].str.lower() == "cliente"]
            st.markdown(f"**Total de Clientes Registrados:** {len(clientes)}")
            cedula_sel = st.selectbox("Buscar Cliente por Nombre/Cédula:", clientes["cedula"].astype(str) + " - " + clientes["nombre_completo"])
            
            if cedula_sel:
                id_cliente = cedula_sel.split(" - ")[0].strip()
                u_info = clientes[clientes["cedula"] == id_cliente].iloc[0]
                
                st.markdown("---")
                col_u1, col_u2 = st.columns(2)
                with col_u1:
                    st.markdown(f"""
                    * **Nombre:** {u_info['nombre_completo']}
                id_cliente = str(cedula_sel.split(" - ")[0]).strip()
                u_info = clientes[clientes["cedula"] == id_cliente].iloc[0]
                
                st.markdown("---")
                col_u1, col_u2 = st.columns(2)
                with col_u1:
                    st.markdown(f"""
                    * **Nombre:** {u_info['nombre_completo']}
                    * **Cédula:** {u_info['cedula']}
                    * **EPS:** {u_info['eps']}
                    * **Condiciones Físicas:** {u_info['condiciones_medicas']}
                    """)
                with col_u2:
                    ws_url = link_whatsapp(u_info['whatsapp'], u_info['nombre_completo'])
                    st.link_button("💬 Enviar WhatsApp", ws_url, use_container_width=True)
                    
                st.markdown("---")
                st.subheader("📈 Historial de Avances del Cliente")
                h_cliente = df_historial[df_historial["cedula"] == id_cliente] if not df_historial.empty else pd.DataFrame()
                if not h_cliente.empty:
                    st.table(h_cliente.astype(str))
                else:
                    st.warning("Este cliente aún no ha ingresado registros de medidas.")
