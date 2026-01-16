import streamlit as st
import pandas as pd
import datetime as dt
import math
import io
import plotly.express as px
import plotly.graph_objects as go

# 1. Configuración de la página
st.set_page_config(page_title="DHL | Dashboard de Etiquetado", layout="wide", page_icon="🏷️")

# Estilos visuales DHL
st.markdown("""
    <style>
    .stApp { background-color: #fcfcfc; }
    [data-testid="stMetricValue"] { color: #D40000; font-family: 'Arial Black'; }
    .stTabs [aria-selected="true"] { background-color: #D40000 !important; color: white !important; }
    h1, h2, h3 { font-family: 'Arial'; }
    </style>
    """, unsafe_allow_html=True)

# --- MOTOR DE LÓGICA ---
def procesar_logica(df, dias_excluidos):
    INICIO_H, FIN_H, SETUP_MIN = 8, 15, 5  # Capacidad 7h y Set-up 5 min
    LINEAS_TOTALES = 12
    dias_semana_raw = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    traduccion_inv = {'Lunes': 'Monday', 'Martes': 'Tuesday', 'Miércoles': 'Wednesday', 'Jueves': 'Thursday', 'Viernes': 'Friday'}
    
    dias_reales = [d for d in dias_semana_raw if d not in [traduccion_inv[fer] for fer in dias_excluidos]]
    dias_semana = [dt.datetime(2026, 1, 12 + i, INICIO_H, 0) for i, d in enumerate(dias_semana_raw) if d in dias_reales]
    
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
                'Producto': fila['Descripcion'],
                'Hora Inicio': tiempo_actual.strftime('%H:%M'), 'Hora Fin': tiempo_fin.strftime('%H:%M'),
                'Duracion': (tiempo_fin - tiempo_actual).total_seconds() / 3600, 'Cajas': int(procesar)
            })
            cajas_pendientes -= procesar
            lineas_reloj[n_linea] = tiempo_fin + dt.timedelta(minutes=SETUP_MIN)

    res_df = pd.DataFrame(plan)
    traduccion = {'Monday':'Lunes','Tuesday':'Martes','Wednesday':'Miércoles','Thursday':'Jueves','Friday':'Viernes'}
    if not res_df.empty: res_df['Día'] = res_df['Día'].map(traduccion)
    return res_df

# --- INTERFAZ ---
st.title("🏭 Dashboard de Etiquetado DHL")

with st.sidebar:
    st.header("⚙️ Configuración")
    archivo = st.file_uploader("Subir Demanda", type=["xlsx"])
    feriados = st.multiselect("Marcar Feriados:", ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"])
    modo_ranking = st.radio("Ver Ranking por:", ["Cajas Totales 📦", "Horas de Uso ⏳"])

if archivo:
    df_raw = pd.read_excel(archivo)
    df_plan = procesar_logica(df_raw, feriados)
    
    if not df_plan.empty:
        # KPIs Superiores con iconos
        lineas_act = df_plan['Línea'].nunique()
        c1, c2, c3 = st.columns(3)
        c1.metric("🏭 Líneas en Uso", lineas_act)
        c2.metric("📦 Cajas Totales", f"{df_plan['Cajas'].sum():,}")
        c3.metric("👥 Personal Extra", f"{(max(0, lineas_act - 5) * 6)}")

        tab1, tab2 = st.tabs(["📊 Gráficos Dinámicos", "📅 Detalle y Orden de Líneas"])

        with tab1:
            col_a, col_b = st.columns(2)
            
            with col_a:
                st.subheader("🏆 Top de Marcas")
                metrica = 'Cajas' if "Cajas" in modo_ranking else 'Duracion'
                df_m = df_plan.groupby('Marca')[metrica].sum().reset_index().sort_values(metrica)
                fig_m = px.bar(df_m, x=metrica, y='Marca', orientation='h', color_discrete_sequence=['#FFCC00'])
                st.plotly_chart(fig_m, use_container_width=True)

            with col_b:
                st.subheader("📈 % Ocupación por Línea (Semanal)")
                # Capacidad total semanal = 35h (7h * 5 días)
                df_occ = df_plan.groupby('Línea')['Duracion'].sum().reset_index()
                df_occ['% Ocupación'] = (df_occ['Duracion'] / 35) * 100
                fig_occ = px.bar(df_occ, x='Línea', y='% Ocupación', 
                                 range_y=[0, 110], color='% Ocupación',
                                 color_continuous_scale='Reds')
                fig_occ.add_hline(y=100, line_dash="dash", line_color="black")
                st.plotly_chart(fig_occ, use_container_width=True)

        with tab2:
            st.subheader("🔍 Filtros de Visualización")
            f1, f2 = st.columns(2)
            with f1:
                sel_dia = st.multiselect("Filtrar por Día:", df_plan['Día'].unique(), default=df_plan['Día'].unique())
            with f2:
                sel_linea = st.multiselect("Filtrar por Línea:", sorted(df_plan['Línea'].unique()), default=sorted(df_plan['Línea'].unique()))
            
            # Filtrar el dataframe
            df_view = df_plan[(df_plan['Día'].isin(sel_dia)) & (df_plan['Línea'].isin(sel_linea))]
            # Ordenar para ver el flujo de entrada
            df_view = df_view.sort_values(['Día', 'Línea', 'Hora Inicio'])
            
            st.dataframe(df_view[['Día', 'Línea', 'Hora Inicio', 'Hora Fin', 'Producto', 'Marca', 'Cajas']], 
                         use_container_width=True, hide_index=True)

            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df_plan.to_excel(writer, index=False)
            st.download_button("📥 Descargar Planificación Completa", buffer, "Plan_Etiquetado_DHL.xlsx")