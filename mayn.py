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
    [data-testid="stMetricValue"] { color: #D40000; font-family: 'Arial Black'; font-size: 24px; }
    .stTabs [aria-selected="true"] { background-color: #D40000 !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

# --- MOTOR DE LÓGICA (RECUPERADO Y MEJORADO) ---
def procesar_logica(df, dias_excluidos):
    INICIO_H, FIN_H, SETUP_MIN = 8, 15, 5  # Capacidad 7h y Set-up 5 min
    LINEAS_TOTALES = 12
    dias_semana_raw = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    traduccion_inv = {'Lunes': 'Monday', 'Martes': 'Tuesday', 'Miércoles': 'Wednesday', 'Jueves': 'Thursday', 'Viernes': 'Friday'}
    
    dias_reales = [d for d in dias_semana_raw if d not in [traduccion_inv[fer] for fer in dias_excluidos]]
    # Semana del 12 de Enero 2026 como referencia
    dias_semana = [dt.datetime(2026, 1, 12 + i, INICIO_H, 0) for i, d in enumerate(dias_semana_raw) if d in dias_reales]
    
    if not dias_semana: return pd.DataFrame()

    lineas_reloj = {i: dias_semana[0] for i in range(1, LINEAS_TOTALES + 1)}
    plan = []
    
    for _, fila in df.iterrows():
        marca = str(fila['Marca']).upper()
        cajas_totales = int(fila['Unit Quantity'])
        p_auto = fila['Cajas por hora línea automatica']
        p_man = fila['Cajas por hora línea manual']
        
        # Lógica de asignación: L1 y L2 son Automáticas/Chocolates
        es_choco = any(x in marca for x in ["MKA", "MILKA", "OREO"])
        opciones = [1, 2] if (es_choco or p_auto > p_man) else list(range(3, 13))
        
        n_linea = opciones[0]
        # Buscar la línea con más tiempo libre dentro de sus opciones
        for l in opciones:
            if lineas_reloj[l] < lineas_reloj[n_linea]:
                n_linea = l

        cajas_pendientes = cajas_totales
        while cajas_pendientes > 0:
            tiempo_actual = lineas_reloj[n_linea]
            
            # Si se acaba el tiempo en esta línea, buscar en el siguiente día laboral
            if tiempo_actual.hour >= FIN_H:
                actual_idx = [i for i, d in enumerate(dias_semana) if d.date() == tiempo_actual.date()]
                if actual_idx and actual_idx[0] + 1 < len(dias_semana):
                    lineas_reloj[n_linea] = dias_semana[actual_idx[0] + 1]
                    tiempo_actual = lineas_reloj[n_linea]
                else:
                    break # No hay más días

            fin_dia = tiempo_actual.replace(hour=FIN_H, minute=0)
            horas_disp = (fin_dia - tiempo_actual).total_seconds() / 3600
            
            prod_usada = p_auto if n_linea <= 2 else p_man
            procesar = min(cajas_pendientes, math.floor(horas_disp * prod_usada))
            
            if procesar <= 0: # Si no cabe ni una caja, saltar al día siguiente
                actual_idx = [i for i, d in enumerate(dias_semana) if d.date() == tiempo_actual.date()]
                if actual_idx and actual_idx[0] + 1 < len(dias_semana):
                    lineas_reloj[n_linea] = dias_semana[actual_idx[0] + 1]
                    continue
                else: break

            tiempo_fin = tiempo_actual + dt.timedelta(hours=procesar/prod_usada)
            plan.append({
                'Línea': n_linea, 
                'Tipo': 'Automática 🍫' if n_linea <= 2 else 'Manual ✍️',
                'Día': tiempo_actual.strftime('%A'), 
                'Marca': marca,
                'Producto': fila['Descripcion'],
                'Hora Inicio': tiempo_actual.strftime('%H:%M'), 
                'Hora Fin': tiempo_fin.strftime('%H:%M'),
                'Duracion': (tiempo_fin - tiempo_actual).total_seconds() / 3600, 
                'Cajas': int(procesar)
            })
            cajas_pendientes -= procesar
            lineas_reloj[n_linea] = tiempo_fin + dt.timedelta(minutes=SETUP_MIN)

    res_df = pd.DataFrame(plan)
    traduccion = {'Monday':'Lunes','Tuesday':'Martes','Wednesday':'Miércoles','Thursday':'Jueves','Friday':'Viernes'}
    if not res_df.empty: res_df['Día'] = res_df['Día'].map(traduccion)
    return res_df

# --- INTERFAZ STREAMLIT ---
st.title("🏭 Dashboard de Etiquetado DHL")

with st.sidebar:
    st.header("⚙️ Configuración")
    archivo = st.file_uploader("Subir Excel de Demanda", type=["xlsx"])
    feriados = st.multiselect("Días Feriados:", ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"])
    modo_ranking = st.radio("Ranking de Marcas por:", ["Cajas 📦", "Horas ⏳"])

if archivo:
    df_raw = pd.read_excel(archivo)
    df_plan = procesar_logica(df_raw, feriados)
    
    if not df_plan.empty:
        # 1. KPIs SUPERIORES
        lineas_act = df_plan['Línea'].nunique()
        c1, c2, c3, c4 = st.columns(4)
        
        dias_lab = 5 - len(feriados)
        cap_total_h = 12 * 7 * dias_lab
        uso_total_h = df_plan['Duracion'].sum()
        util_global = (uso_total_h / cap_total_h) * 100 if cap_total_h > 0 else 0
        
        c1.metric("🏭 Uso Planta", f"{int(util_global)}%")
        c2.metric("📦 Total Cajas", f"{df_plan['Cajas'].sum():,}")
        c3.metric("👥 Pers. Total", f"{lineas_act * 6}")
        c4.metric("⏱️ Set-up Total", f"{len(df_plan) * 5} min")

        tab1, tab2 = st.tabs(["📊 Dashboard de Ocupación", "📅 Orden de Trabajo"])

        with tab1:
            col_left, col_right = st.columns([1.2, 0.8])
            
            with col_left:
                st.subheader("📈 Ocupación Real por Línea (Hacia abajo)")
                # Crear base de las 12 líneas para que siempre aparezcan
                df_occ = df_plan.groupby('Línea')['Duracion'].sum().reset_index()
                all_lines = pd.DataFrame({'Línea': range(1, 13)})
                df_occ = pd.merge(all_lines, df_occ, on='Línea', how='left').fillna(0)
                
                # Capacidad semanal por línea es 7h * dias_lab
                cap_linea = 7 * dias_lab
                df_occ['% Ocupación'] = ((df_occ['Duracion'] / cap_linea) * 100).round(0).astype(int)
                
                # Etiquetas con iconos
                df_occ['Nombre'] = df_occ['Línea'].apply(lambda x: f"L{x} 🍫" if x <= 2 else f"L{x} ✍️")
                
                fig_occ = px.bar(df_occ, x='% Ocupación', y='Nombre', orientation='h',
                                 text='% Ocupación', color='% Ocupación',
                                 color_continuous_scale=['#4CAF50', '#FFCC00', '#D40000'],
                                 range_x=[0, 110])
                fig_occ.update_traces(texttemplate='%{text}%', textposition='outside')
                fig_occ.update_layout(yaxis={'categoryorder':'total descending'}, height=500)
                st.plotly_chart(fig_occ, use_container_width=True)

            with col_right:
                st.subheader(f"🏆 Top Marcas ({modo_ranking})")
                m_col = 'Cajas' if "Cajas" in modo_ranking else 'Duracion'
                df_m = df_plan.groupby('Marca')[m_col].sum().reset_index().sort_values(m_col)
                fig_m = px.bar(df_m, x=m_col, y='Marca', orientation='h', color_discrete_sequence=['#FFCC00'])
                st.plotly_chart(fig_m, use_container_width=True)

        with tab2:
            st.subheader("🔍 Filtros y Secuencia")
            f1, f2 = st.columns(2)
            with f1: d_filter = st.multiselect("Día:", df_plan['Día'].unique(), default=df_plan['Día'].unique())
            with f2: l_filter = st.multiselect("Línea:", range(1, 13), default=range(1, 13))
            
            df_final = df_plan[(df_plan['Día'].isin(d_filter)) & (df_plan['Línea'].isin(l_filter))]
            df_final = df_final.sort_values(['Día', 'Línea', 'Hora Inicio'])
            
            st.dataframe(df_final[['Día', 'Línea', 'Tipo', 'Hora Inicio', 'Hora Fin', 'Marca', 'Producto', 'Cajas']], 
                         use_container_width=True, hide_index=True)

            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df_plan.to_excel(writer, index=False)
            st.download_button("📥 Descargar Plan Excel", buffer, "Plan_DHL_Final.xlsx")