import streamlit as st
import pandas as pd
import datetime as dt
import math
import io
import plotly.express as px

# 1. Configuración de la página
st.set_page_config(page_title="DHL | Torre de Control Etiquetado", layout="wide", page_icon="🏭")

# Estilos visuales DHL
st.markdown("""
    <style>
    .stApp { background-color: #fcfcfc; }
    [data-testid="stMetricValue"] { color: #D40000; font-family: 'Arial Black'; }
    .stTabs [aria-selected="true"] { background-color: #D40000 !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

# --- MOTOR DE LÓGICA: PRIORIDAD LLENADO TOTAL ---
def procesar_logica(df, dias_excluidos):
    INICIO_H, FIN_H, SETUP_MIN = 8, 15, 5
    LINEAS_TOTALES = 12
    dias_semana_raw = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    traduccion_inv = {'Lunes': 'Monday', 'Martes': 'Tuesday', 'Miércoles': 'Wednesday', 'Jueves': 'Thursday', 'Viernes': 'Friday'}
    
    dias_reales = [d for d in dias_semana_raw if d not in [traduccion_inv[fer] for fer in dias_excluidos]]
    dias_semana = [dt.datetime(2026, 1, 12 + i, INICIO_H, 0) for i, d in enumerate(dias_semana_raw) if d in dias_reales]
    
    if not dias_semana: return pd.DataFrame()

    # Inicializar el reloj de cada línea en el primer día disponible
    lineas_reloj = {i: dias_semana[0] for i in range(1, LINEAS_TOTALES + 1)}
    plan = []
    
    # Ordenamos la demanda para procesar primero lo que requiere líneas automáticas si es posible
    for _, fila in df.iterrows():
        marca = str(fila['Marca']).upper()
        cajas_totales = int(fila['Unit Quantity'])
        p_auto, p_man = fila['Cajas por hora línea automatica'], fila['Cajas por hora línea manual']
        
        # Prioridad de línea según tipo de producto/velocidad
        es_choco = any(x in marca for x in ["MKA", "MILKA", "OREO"])
        opciones = [1, 2] if (es_choco or p_auto > p_man) else list(range(3, 13))
        
        cajas_pendientes = cajas_totales
        
        # EL OBJETIVO: Llenar la línea actual lo más posible antes de saltar a otra
        while cajas_pendientes > 0:
            # Seleccionar la línea disponible más prioritaria (la primera de la lista de opciones)
            # que aún tenga tiempo en la semana
            n_linea = None
            for l in opciones:
                if lineas_reloj[l] < dias_semana[-1].replace(hour=FIN_H):
                    n_linea = l
                    break
            
            if n_linea is None: break # No hay más capacidad en ninguna línea

            tiempo_actual = lineas_reloj[n_linea]
            
            # Si el reloj de la línea llegó al fin del día, saltar al inicio del siguiente día laboral
            if tiempo_actual.hour >= FIN_H:
                actual_idx = [i for i, d in enumerate(dias_semana) if d.date() == tiempo_actual.date()]
                if actual_idx and actual_idx[0] + 1 < len(dias_semana):
                    lineas_reloj[n_linea] = dias_semana[actual_idx[0] + 1]
                    continue
                else: 
                    # Esta línea se llenó toda la semana, probar con la siguiente opción
                    opciones.pop(0)
                    if not opciones: break
                    continue

            fin_dia = tiempo_actual.replace(hour=FIN_H, minute=0)
            horas_disp = (fin_dia - tiempo_actual).total_seconds() / 3600
            
            prod_usada = p_auto if n_linea <= 2 else p_man
            procesar = min(cajas_pendientes, math.floor(horas_disp * prod_usada))
            
            if procesar <= 0: # Día agotado para esta línea
                lineas_reloj[n_linea] = tiempo_actual.replace(hour=FIN_H)
                continue

            tiempo_fin = tiempo_actual + dt.timedelta(hours=procesar/prod_usada)
            plan.append({
                'Línea': n_linea,
                'Icono': "🍫" if n_linea <= 2 else "📦",
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

# --- INTERFAZ ---
st.title("🏷️ Dashboard de Etiquetado DHL")

with st.sidebar:
    st.header("⚙️ Configuración")
    archivo = st.file_uploader("Subir Demanda (Excel)", type=["xlsx"])
    feriados = st.multiselect("Marcar Feriados:", ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"])
    modo_ranking = st.radio("Ranking por:", ["Cajas Totales 📦", "Horas de Uso ⏳"])

if archivo:
    df_raw = pd.read_excel(archivo)
    df_plan = procesar_logica(df_raw, feriados)
    
    if not df_plan.empty:
        # 1. KPIs SUPERIORES
        lineas_act = df_plan['Línea'].nunique()
        c1, c2, c3, c4 = st.columns(4)
        dias_lab = 5 - len(feriados)
        
        c1.metric("🏭 Líneas en Uso", f"{lineas_act} / 12")
        c2.metric("📦 Cajas Totales", f"{df_plan['Cajas'].sum():,}")
        c3.metric("👥 Personal Total", f"{lineas_act * 6}")
        c4.metric("⏱️ Tiempo Set-up", f"{len(df_plan)*5} min")

        tab1, tab2 = st.tabs(["📊 Dashboard de Ocupación", "📅 Secuencia por Línea"])

        with tab1:
            col_l, col_r = st.columns([1.2, 0.8])
            with col_l:
                st.subheader("📈 % Ocupación Semanal por Línea")
                df_occ = df_plan.groupby(['Línea', 'Icono'])['Duracion'].sum().reset_index()
                all_lines = pd.DataFrame({'Línea': range(1, 13)})
                df_occ = pd.merge(all_lines, df_occ, on='Línea', how='left').fillna(0)
                
                df_occ['%'] = ((df_occ['Duracion'] / (7 * dias_lab)) * 100).round(0).astype(int)
                df_occ['Etiqueta'] = df_occ.apply(lambda x: f"L{int(x['Línea'])} {x['Icono'] if x['Icono'] != 0 else '⚪'}", axis=1)
                
                # Gráfico horizontal para ver el "llenado"
                fig_occ = px.bar(df_occ, x='%', y='Etiqueta', orientation='h', text='%',
                                 color='%', color_continuous_scale='Reds', range_x=[0, 110])
                fig_occ.update_traces(texttemplate='%{text}%', textposition='outside')
                fig_occ.update_layout(yaxis={'categoryorder':'array', 'categoryarray': df_occ['Etiqueta'][::-1]})
                st.plotly_chart(fig_occ, use_container_width=True)

            with col_r:
                st.subheader("🏆 Ranking Marcas")
                met = 'Cajas' if "Cajas" in modo_ranking else 'Duracion'
                df_m = df_plan.groupby('Marca')[met].sum().reset_index().sort_values(met)
                st.plotly_chart(px.bar(df_m, x=met, y='Marca', orientation='h', color_discrete_sequence=['#FFCC00']), use_container_width=True)

        with tab2:
            st.subheader("🔍 Orden de Entrada a Proceso")
            l_sel = st.multiselect("Ver Líneas:", range(1, 13), default=range(1, 13))
            df_det = df_plan[df_plan['Línea'].isin(l_sel)].sort_values(['Línea', 'Día', 'Hora Inicio'])
            st.dataframe(df_det[['Línea', 'Día', 'Hora Inicio', 'Hora Fin', 'Marca', 'Producto', 'Cajas']], use_container_width=True, hide_index=True)