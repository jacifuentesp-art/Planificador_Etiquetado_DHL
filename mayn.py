import streamlit as st
import pandas as pd
import datetime as dt
import math
import io
import plotly.express as px
import plotly.graph_objects as go

# 1. Configuración de la página
st.set_page_config(page_title="DHL | Planner Dashboard", layout="wide", page_icon="📦")

# Estilos visuales DHL
st.markdown("""
    <style>
    .stApp { background-color: #fcfcfc; }
    [data-testid="stMetricValue"] { color: #D40000; font-family: 'Arial Black'; }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [aria-selected="true"] { background-color: #D40000 !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

# --- MOTOR DE LÓGICA ---
def procesar_logica(df, dias_excluidos):
    INICIO_H, FIN_H, SETUP_MIN = 8, 15, 5  # ACTUALIZADO: Set-up a 5 minutos 
    LINEAS_TOTALES = 12
    dias_semana_raw = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    traduccion_inv = {'Lunes': 'Monday', 'Martes': 'Tuesday', 'Miércoles': 'Wednesday', 'Jueves': 'Thursday', 'Viernes': 'Friday'}
    
    dias_reales = [d for d in dias_semana_raw if d not in [traduccion_inv[fer] for fer in dias_excluidos]] [cite: 1]
    dias_semana = [dt.datetime(2026, 1, 12 + i, INICIO_H, 0) for i, d in enumerate(dias_semana_raw) if d in dias_reales] [cite: 1]
    
    if not dias_semana: return pd.DataFrame()

    lineas_reloj = {i: dias_semana[0] for i in range(1, LINEAS_TOTALES + 1)}
    plan = []
    
    for _, fila in df.iterrows():
        marca = str(fila['Marca']).upper()
        cajas_totales = int(fila['Unit Quantity'])
        p_auto, p_man = fila['Cajas por hora línea automatica'], fila['Cajas por hora línea manual']
        es_choco = any(x in marca for x in ["MKA", "MILKA"])
        
        opciones = [1, 2] if (es_choco or p_auto > p_man) else list(range(3, 13))
        n_linea = opciones[0]
        
        for l in opciones:
            if lineas_reloj[l] < dias_semana[-1].replace(hour=FIN_H):
                n_linea = l
                break

        cajas_pendientes = cajas_totales
        while cajas_pendientes > 0:
            tiempo_actual = lineas_reloj[n_linea]
            if tiempo_actual >= dias_semana[-1].replace(hour=FIN_H):
                prox = [o for o in opciones if o > n_linea]
                if prox: n_linea = prox[0]; continue
                else: break

            fin_dia = tiempo_actual.replace(hour=FIN_H, minute=0)
            horas_disp = (fin_dia - tiempo_actual).total_seconds() / 3600
            
            if horas_disp <= 0:
                actual_idx = [i for i, d in enumerate(dias_semana) if d.date() == tiempo_actual.date()]
                if actual_idx and actual_idx[0] + 1 < len(dias_semana):
                    lineas_reloj[n_linea] = dias_semana[actual_idx[0] + 1]
                    continue
                else: break

            prod_usada = p_auto if opciones == [1, 2] else p_man
            procesar = min(cajas_pendientes, math.floor(horas_disp * prod_usada))
            if procesar <= 0: break

            tiempo_fin = tiempo_actual + dt.timedelta(hours=procesar/prod_usada)
            plan.append({
                'Línea': n_linea, 'Día': tiempo_actual.strftime('%A'), 'Marca': marca,
                'Hora Inicio': tiempo_actual.strftime('%H:%M'), 'Hora Fin': tiempo_fin.strftime('%H:%M'),
                'Duracion': (tiempo_fin - tiempo_actual).total_seconds() / 3600, 'Cajas': int(procesar)
            })
            cajas_pendientes -= procesar
            lineas_reloj[n_linea] = tiempo_fin + dt.timedelta(minutes=SETUP_MIN) [cite: 1]

    res_df = pd.DataFrame(plan)
    traduccion = {'Monday':'Lunes','Tuesday':'Martes','Wednesday':'Miércoles','Thursday':'Jueves','Friday':'Viernes'}
    if not res_df.empty: res_df['Día'] = res_df['Día'].map(traduccion)
    return res_df

# --- INTERFAZ ---
st.title("🚀 Dashboard de Producción DHL")

with st.sidebar:
    st.header("Ajustes")
    archivo = st.file_uploader("Subir Excel", type=["xlsx"])
    feriados = st.multiselect("Días Feriados:", ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]) [cite: 1]
    modo_ranking = st.radio("Ver Ranking por:", ["Cajas Totales", "Horas de Uso"]) # DINAMISMO 

if archivo:
    df_raw = pd.read_excel(archivo) [cite: 1]
    df_plan = procesar_logica(df_raw, feriados) [cite: 1]
    
    if not df_plan.empty:
        # KPIs Superiores
        lineas_act = df_plan['Línea'].nunique()
        c1, c2, c3 = st.columns(3)
        c1.metric("Líneas en Uso", lineas_act)
        c2.metric("Cajas Totales", f"{df_plan['Cajas'].sum():,}")
        c3.metric("Personal Extra", max(0, (lineas_act - 5) * 6)) [cite: 1]

        tab1, tab2 = st.tabs(["📊 Gráficos Dinámicos", "📋 Detalle"])

        with tab1:
            col_a, col_b = st.columns(2)
            
            with col_a:
                st.subheader(f"🏆 Top Marcas por {modo_ranking}")
                metrica = 'Cajas' if modo_ranking == "Cajas Totales" else 'Duracion'
                df_m = df_plan.groupby('Marca')[metrica].sum().reset_index().sort_values(metrica)
                fig_m = px.bar(df_m, x=metrica, y='Marca', orientation='h', color_discrete_sequence=['#FFCC00'])
                st.plotly_chart(fig_m, use_container_width=True)

            with col_b:
                st.subheader("⏳ Carga por Línea (Max 7h)")
                df_l = df_plan.groupby(['Línea', 'Día'])['Duracion'].sum().reset_index()
                fig_l = px.bar(df_l, x='Línea', y='Duracion', color='Día', barmode='group')
                fig_l.add_hline(y=7, line_dash="dash", line_color="red")
                st.plotly_chart(fig_l, use_container_width=True)

        with tab2:
            st.dataframe(df_plan, use_container_width=True)