import streamlit as st
import pandas as pd
import datetime as dt
import math
import io
import plotly.express as px

# 1. Configuración de la página
st.set_page_config(page_title="DHL | Torre de Control", layout="wide", page_icon="🏷️")

# Estilos visuales DHL
st.markdown("""
    <style>
    .stApp { background-color: #fcfcfc; }
    [data-testid="stMetricValue"] { color: #D40000; font-family: 'Arial Black'; }
    .stTabs [aria-selected="true"] { background-color: #D40000 !important; color: white !important; }
    .metric-container { background-color: #ffffff; padding: 10px; border-radius: 10px; border: 1px solid #f0f0f0; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNCIÓN PARA ICONOS DE MARCA ---
def obtener_icono_marca(marca):
    m = str(marca).upper()
    if any(x in m for x in ["MILKA", "MKA", "CHOCO"]): return "🍫"
    if "OREO" in m: return "🍪"
    if any(x in m for x in ["TRIDENT", "CHICLE", "CLORETS"]): return "🍬"
    return "📦"

# --- MOTOR DE LÓGICA ---
def procesar_logica(df, dias_excluidos):
    INICIO_H, FIN_H, SETUP_MIN = 8, 15, 5
    LINEAS_TOTALES = 12
    dias_semana_raw = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    traduccion_inv = {'Lunes': 'Monday', 'Martes': 'Tuesday', 'Miércoles': 'Wednesday', 'Jueves': 'Thursday', 'Viernes': 'Friday'}
    
    dias_reales = [d for d in dias_semana_raw if d not in [traduccion_inv.get(fer, "") for fer in dias_excluidos]]
    dias_semana = [dt.datetime(2026, 1, 12 + i, INICIO_H, 0) for i, d in enumerate(dias_semana_raw) if d in dias_reales]
    
    if not dias_semana: return pd.DataFrame()

    lineas_reloj = {i: dias_semana[0] for i in range(1, LINEAS_TOTALES + 1)}
    plan = []
    
    for _, fila in df.iterrows():
        marca_raw = str(fila['Marca'])
        marca_up = marca_raw.upper()
        cajas_totales = int(fila['Unit Quantity'])
        p_auto, p_man = fila['Cajas por hora línea automatica'], fila['Cajas por hora línea manual']
        
        es_prioritario = any(x in marca_up for x in ["MILKA", "MKA", "OREO", "CHOCO"])
        opciones = [1, 2] if (es_prioritario or p_auto > p_man) else list(range(3, 13))
        
        cajas_pendientes = cajas_totales
        while cajas_pendientes > 0:
            n_linea = None
            for l in opciones:
                if lineas_reloj[l] < dias_semana[-1].replace(hour=FIN_H):
                    n_linea = l
                    break
            if n_linea is None: break

            tiempo_actual = lineas_reloj[n_linea]
            if tiempo_actual.hour >= FIN_H:
                idx = [i for i, d in enumerate(dias_semana) if d.date() == tiempo_actual.date()]
                if idx and idx[0] + 1 < len(dias_semana):
                    lineas_reloj[n_linea] = dias_semana[idx[0] + 1]
                    continue
                else: break

            fin_dia = tiempo_actual.replace(hour=FIN_H, minute=0)
            horas_disp = (fin_dia - tiempo_actual).total_seconds() / 3600
            prod = p_auto if n_linea <= 2 else p_man
            procesar = min(cajas_pendientes, math.floor(horas_disp * prod))
            
            if procesar <= 0:
                lineas_reloj[n_linea] = tiempo_actual.replace(hour=FIN_H)
                continue

            tiempo_fin = tiempo_actual + dt.timedelta(hours=procesar/prod)
            plan.append({
                'Línea': n_linea,
                'Tipo': "Automática ⚡" if n_linea <= 2 else "Manual ✍️",
                'Día': tiempo_actual.strftime('%A'),
                'Marca': marca_raw,
                'Icono': obtener_icono_marca(marca_raw),
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
st.title("🏭 Dashboard de Etiquetado DHL")

with st.sidebar:
    st.header("⚙️ Configuración")
    archivo = st.file_uploader("Subir Demanda (Excel)", type=["xlsx"])
    feriados = st.multiselect("Marcar Feriados:", ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"])

if archivo:
    df_raw = pd.read_excel(archivo)
    df_plan = procesar_logica(df_raw, feriados)
    
    if not df_plan.empty:
        # 1. KPIs SUPERIORES
        lineas_act = df_plan['Línea'].nunique()
        cajas_totales = df_plan['Cajas'].sum()
        horas_totales = df_plan['Duracion'].sum()
        dias_laborados = 5 - len(feriados)
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🏷️ Líneas en Uso", f"{lineas_act} / 12")
        c2.metric("📦 Cajas Totales", f"{cajas_totales:,}")
        c3.metric("👥 Pers. DHL", f"{min(lineas_act, 5) * 6}")
        extra = max(0, (lineas_act - 5) * 6)
        c4.metric("➕ Personal Extra", f"{extra} pers.")

        tab1, tab2 = st.tabs(["📊 Dashboard Visual", "📅 Secuencia Detallada"])

        with tab1:
            col_l, col_r = st.columns([1.1, 0.9])
            with col_l:
                st.subheader("📈 % Ocupación por Línea")
                df_occ = df_plan.groupby(['Línea', 'Tipo'])['Duracion'].sum().reset_index()
                all_l = pd.DataFrame({'Línea': range(1, 13)})
                df_occ = pd.merge(all_l, df_occ, on='Línea', how='left').fillna(0)
                df_occ['%'] = ((df_occ['Duracion'] / (7 * dias_laborados)) * 100).round(0).astype(int)
                df_occ['Label'] = df_occ.apply(lambda x: f"L{int(x['Línea'])} {'⚡' if x['Línea'] <= 2 else '✍️'}", axis=1)
                
                fig = px.bar(df_occ, x='%', y='Label', orientation='h', text='%',
                             color='%', color_continuous_scale='Reds', range_x=[0, 115])
                fig.update_layout(yaxis={'categoryorder':'array', 'categoryarray': df_occ['Label'][::-1]})
                st.plotly_chart(fig, use_container_width=True)

            with col_r:
                st.subheader("📋 Resumen Cajas por Marca")
                resumen_m = df_plan.groupby(['Icono', 'Marca'])['Cajas'].sum().reset_index()
                resumen_m = resumen_m.sort_values('Cajas', ascending=False)
                resumen_m.columns = ['Tipo', 'Marca', 'Total Cajas']
                st.dataframe(resumen_m, use_container_width=True, hide_index=True)

            # --- NUEVA SECCIÓN DE EFICIENCIA (ABAJO) ---
            st.markdown("---")
            st.subheader("🎯 Métricas de Eficiencia y Rendimiento")
            e1, e2, e3, e4 = st.columns(4)
            
            # Cálculos de Eficiencia
            cajas_hora = cajas_totales / horas_totales if horas_totales > 0 else 0
            cajas_dia = cajas_totales / dias_laborados if dias_laborados > 0 else 0
            setup_total = len(df_plan) * 5 # 5 min por cada tarea en el plan
            tiempo_por_caja = (horas_totales * 3600) / cajas_totales if cajas_totales > 0 else 0
            
            e1.metric("⏱️ Cajas por Hora", f"{int(cajas_hora)} u/h")
            e2.metric("📅 Cajas por Día", f"{int(cajas_dia):,} u/d")
            e3.metric("🛠️ Tiempo Set-up", f"{setup_total} min")
            e4.metric("⚙️ Segundos por Caja", f"{tiempo_por_caja:.2f} s")

        with tab2:
            st.subheader("🔍 Filtros de Secuencia")
            f1, f2 = st.columns(2)
            with f1: d_sel = st.multiselect("Días:", df_plan['Día'].unique(), default=df_plan['Día'].unique())
            with f2: l_sel = st.multiselect("Líneas:", range(1, 13), default=range(1, 13))
            
            df_det = df_plan[(df_plan['Día'].isin(d_sel)) & (df_plan['Línea'].isin(l_sel))]
            df_det = df_det.sort_values(['Día', 'Línea', 'Hora Inicio'])
            
            st.dataframe(df_det[['Día', 'Línea', 'Tipo', 'Hora Inicio', 'Hora Fin', 'Marca', 'Producto', 'Cajas']], 
                         use_container_width=True, hide_index=True)
            
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df_plan.to_excel(writer, index=False)
            st.download_button("📥 Descargar Excel", buffer, "Plan_DHL_Final.xlsx")