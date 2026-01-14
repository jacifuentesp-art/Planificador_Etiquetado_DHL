import streamlit as st
import pandas as pd
import datetime as dt
import math
import io

# 1. Configuración de la página (Debe ser lo primero)
st.set_page_config(page_title="DHL | Planner Dashboard", layout="wide")

# Estilos visuales
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: white; border: 1px solid #eee; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    h1, h2, h3 { color: #D40000; font-family: 'Arial'; }
    </style>
    """, unsafe_allow_html=True)

# --- MOTOR DE LÓGICA ---
def procesar_logica(df):
    INICIO_H, FIN_H, SETUP_MIN = 8, 15, 2
    LINEAS_TOTALES = 12
    # Semana de referencia 2026
    dias_semana = [dt.datetime(2026, 1, i, INICIO_H, 0) for i in range(12, 17)] 
    lineas_reloj = {i: dias_semana[0] for i in range(1, LINEAS_TOTALES + 1)}
    plan = []
    
    for _, fila in df.iterrows():
        marca = str(fila['Marca']).upper()
        cajas_totales = int(fila['Unit Quantity'])
        p_auto, p_man = fila['Cajas por hora línea automatica'], fila['Cajas por hora línea manual']
        es_choco = any(x in marca for x in ["MKA", "MILKA"])
        
        if es_choco or p_auto > p_man:
            modalidad, prod_usada, opciones = "Automatica", p_auto, [1, 2]
        else:
            modalidad, prod_usada, opciones = "Manual", p_man, list(range(3, 13))

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

            procesar = min(cajas_pendientes, math.floor(horas_disp * prod_usada))
            if procesar <= 0: break

            tiempo_fin = tiempo_actual + dt.timedelta(hours=procesar/prod_usada)
            plan.append({
                'Línea': n_linea, 'Día': tiempo_actual.strftime('%A'), 'Producto': fila['Descripcion'],
                'Marca': marca, 'Modalidad': modalidad, 'Hora Inicio': tiempo_actual.strftime('%H:%M'),
                'Hora Fin': tiempo_fin.strftime('%H:%M'), 'Cajas': int(procesar)
            })
            cajas_pendientes -= procesar
            lineas_reloj[n_linea] = tiempo_fin + dt.timedelta(minutes=SETUP_MIN)

    res_df = pd.DataFrame(plan)
    traduccion = {'Monday':'Lunes','Tuesday':'Martes','Wednesday':'Miércoles','Thursday':'Jueves','Friday':'Viernes'}
    if not res_df.empty: res_df['Día'] = res_df['Día'].map(traduccion)
    return res_df

# --- INTERFAZ ---
st.title("🚀 Sistema de Planificación DHL")
archivo = st.file_uploader("Cargar archivo de demanda (Excel)", type=["xlsx"])

if archivo:
    # IMPORTANTE: Aquí es donde se usa openpyxl internamente
    df_raw = pd.read_excel(archivo)
    df_plan = procesar_logica(df_raw)
    
    if not df_plan.empty:
        # CÁLCULOS PARA DASHBOARD
        l_total = df_plan['Línea'].nunique()
        
        # PESTAÑAS
        tab1, tab2 = st.tabs(["📊 Resumen Ejecutivo", "📅 Planificación Semanal Interactiva"])

        with tab1:
            st.write("### Indicadores de la Semana")
            c1, c2, c3 = st.columns(3)
            c1.metric("Líneas Activas", l_total)
            c2.metric("Headcount Total", l_total * 6)
            c3.metric("Externos Requeridos", max(0, (l_total * 6) - 30))

            st.write("#### Carga horaria por día")
            df_plan['H_I'] = pd.to_datetime(df_plan['Hora Inicio'], format='%H:%M')
            df_plan['H_F'] = pd.to_datetime(df_plan['Hora Fin'], format='%H:%M')
            df_plan['Horas'] = (df_plan['H_F'] - df_plan['H_I']).dt.total_seconds() / 3600
            carga_h = df_plan.groupby('Día')['Horas'].sum().reindex(["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"])
            st.bar_chart(carga_h)

        with tab2:
            st.write("### 🔍 Filtros Dinámicos")
            f1, f2, f3 = st.columns(3)
            with f1:
                sel_dia = st.multiselect("Filtrar Día:", df_plan['Día'].unique(), default=df_plan['Día'].unique())
            with f2:
                sel_linea = st.multiselect("Filtrar Línea:", sorted(df_plan['Línea'].unique()), default=sorted(df_plan['Línea'].unique()))
            with f3:
                sel_marca = st.multiselect("Filtrar Marca:", df_plan['Marca'].unique(), default=df_plan['Marca'].unique())

            # Aplicar filtros a la vista
            df_view = df_plan[
                (df_plan['Día'].isin(sel_dia)) & 
                (df_plan['Línea'].isin(sel_linea)) & 
                (df_plan['Marca'].isin(sel_marca))
            ]

            st.dataframe(df_view[['Línea', 'Día', 'Producto', 'Marca', 'Modalidad', 'Hora Inicio', 'Hora Fin', 'Cajas']], use_container_width=True, hide_index=True)

        # BOTÓN DE DESCARGA (Siempre disponible al final)
        st.divider()
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df_plan.to_excel(writer, index=False)
        
        st.download_button("📥 Descargar Planificación Completa", buffer, "Plan_DHL_Final.xlsx", "application/vnd.ms-excel")