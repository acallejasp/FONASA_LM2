import os
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from dotenv import load_dotenv


ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_PATH)

SOURCE_HOST = os.getenv("SOURCE_HOST")
SOURCE_PORT = os.getenv("SOURCE_PORT", "5439")
SOURCE_DB = os.getenv("SOURCE_DB")
SOURCE_USER = os.getenv("SOURCE_USER")
SOURCE_PASSWORD = os.getenv("SOURCE_PASSWORD")
SOURCE_SCHEMA = os.getenv("SOURCE_SCHEMA", "gold_proes")

# ---------------------------------------------------------------------------
# Configuración de página
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="FONASA LM - Resumen",
    page_icon="🏥",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Conexión
# ---------------------------------------------------------------------------
@st.cache_resource
def get_engine():
    conn_str = (
        f"postgresql+psycopg2://{SOURCE_USER}:{SOURCE_PASSWORD}"
        f"@{SOURCE_HOST}:{SOURCE_PORT}/{SOURCE_DB}"
    )
    return create_engine(conn_str, connect_args={"sslmode": "prefer"})


@st.cache_data(ttl=600)
def load_table(table_name: str) -> pd.DataFrame:
    engine = get_engine()
    query = f'SELECT * FROM "{SOURCE_SCHEMA}"."{table_name}"'
    try:
        with engine.connect() as conn:
            return pd.read_sql(text(query), conn)
    except Exception as e:
        st.error(f"Error al cargar {table_name}: {e}")
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Carga de datos
# ---------------------------------------------------------------------------
def load_all_data():
    data = {}
    tablas = [
        "lm_resumen_anio",
        "lm_resumen_mensual",
        "lm_resumen_estrato_anio",
        "lm_resumen_estrato_mensual",
        "lm_resumen_estadisticas_anio",
        "lm_resumen_estadisticas_mensual",
        "lm_resumen_estadisticas_estrato_anio",
        "lm_resumen_estadisticas_estrato_mensual",
        "lm_empleador_mensual",
        "lm_cotizante_anio",
    ]
    for t in tablas:
        data[t] = load_table(t)
    return data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def fmt_numero(valor):
    if pd.isna(valor):
        return "-"
    return f"{int(valor):,}"


def fmt_monto(valor):
    if pd.isna(valor):
        return "-"
    return f"${valor:,.0f}"


# ---------------------------------------------------------------------------
# Sidebar: filtros
# ---------------------------------------------------------------------------
def render_sidebar(data):
    st.sidebar.title("Filtros")

    df_anio = data.get("lm_resumen_anio", pd.DataFrame())
    anios = sorted(df_anio["anio"].dropna().unique().tolist()) if not df_anio.empty else []
    anio_sel = st.sidebar.multiselect("Año(s)", options=anios, default=anios)

    df_est = data.get("lm_resumen_estrato_anio", pd.DataFrame())
    estratos = sorted(df_est["estrato"].dropna().unique().tolist()) if not df_est.empty else []
    estrato_sel = st.sidebar.multiselect("Estrato(s)", options=estratos, default=estratos)

    df_mensual = data.get("lm_resumen_mensual", pd.DataFrame())
    periodos = sorted(df_mensual["periodo"].dropna().unique().tolist()) if not df_mensual.empty else []
    periodo_desde = st.sidebar.selectbox("Período desde", options=periodos, index=0) if periodos else None
    periodo_hasta = st.sidebar.selectbox("Período hasta", options=periodos, index=len(periodos) - 1) if periodos else None

    return {
        "anios": anio_sel,
        "estratos": estrato_sel,
        "periodo_desde": periodo_desde,
        "periodo_hasta": periodo_hasta,
    }


# ---------------------------------------------------------------------------
# Pestaña 1: Resumen
# ---------------------------------------------------------------------------
def tab_resumen(data, filtros):
    st.title("Resumen General")

    df_anio = data.get("lm_resumen_anio", pd.DataFrame())
    if not df_anio.empty and filtros["anios"]:
        df_anio = df_anio[df_anio["anio"].isin(filtros["anios"])]

    if df_anio.empty:
        st.info("Sin datos con los filtros seleccionados.")
        return

    # Métricas cabecera
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Empleadores", fmt_numero(df_anio["cantidad_empleadores"].sum()))
    col2.metric("Cotizantes", fmt_numero(df_anio["cantidad_cotizantes"].sum()))
    col3.metric("Días Autorizados", fmt_numero(df_anio["dias_autorizados"].sum()))
    col4.metric("Monto Cotización", fmt_monto(df_anio["sum_mto_coti"].sum()))

    st.markdown("---")

    st.subheader("Resumen por Año")
    st.dataframe(df_anio, use_container_width=True)

    # Resumen mensual
    df_mensual = data.get("lm_resumen_mensual", pd.DataFrame())
    if not df_mensual.empty:
        if filtros["periodo_desde"] and filtros["periodo_hasta"]:
            df_mensual = df_mensual[
                (df_mensual["periodo"] >= filtros["periodo_desde"])
                & (df_mensual["periodo"] <= filtros["periodo_hasta"])
            ]
        st.subheader("Resumen por Período")
        st.dataframe(df_mensual, use_container_width=True)

    # Resumen por estrato
    df_est_anio = data.get("lm_resumen_estrato_anio", pd.DataFrame())
    if not df_est_anio.empty:
        if filtros["anios"]:
            df_est_anio = df_est_anio[df_est_anio["anio"].isin(filtros["anios"])]
        if filtros["estratos"]:
            df_est_anio = df_est_anio[df_est_anio["estrato"].isin(filtros["estratos"])]
        st.subheader("Resumen por Estrato y Año")
        st.dataframe(df_est_anio, use_container_width=True)


# ---------------------------------------------------------------------------
# Pestaña 2: Estadísticas
# ---------------------------------------------------------------------------
def tab_estadisticas(data, filtros):
    st.title("Estadísticas")

    df_est_anio = data.get("lm_resumen_estadisticas_estrato_anio", pd.DataFrame())
    df_est_mensual = data.get("lm_resumen_estadisticas_estrato_mensual", pd.DataFrame())

    if not df_est_anio.empty:
        if filtros["anios"]:
            df_est_anio = df_est_anio[df_est_anio["anio"].isin(filtros["anios"])]
        if filtros["estratos"]:
            df_est_anio = df_est_anio[df_est_anio["estrato"].isin(filtros["estratos"])]
        st.subheader("Estadísticas por Estrato y Año")
        st.dataframe(df_est_anio, use_container_width=True)
    else:
        st.info("No hay datos de estadísticas por estrato y año.")

    if not df_est_mensual.empty:
        if filtros["periodo_desde"] and filtros["periodo_hasta"]:
            df_est_mensual = df_est_mensual[
                (df_est_mensual["periodo"] >= filtros["periodo_desde"])
                & (df_est_mensual["periodo"] <= filtros["periodo_hasta"])
            ]
        if filtros["estratos"]:
            df_est_mensual = df_est_mensual[df_est_mensual["estrato"].isin(filtros["estratos"])]
        st.subheader("Estadísticas por Estrato y Período")
        st.dataframe(df_est_mensual, use_container_width=True)
    else:
        st.info("No hay datos de estadísticas por estrato y período.")

    # Estadísticas globales
    df_global_anio = data.get("lm_resumen_estadisticas_anio", pd.DataFrame())
    if not df_global_anio.empty:
        if filtros["anios"]:
            df_global_anio = df_global_anio[df_global_anio["anio"].isin(filtros["anios"])]
        st.subheader("Estadísticas Globales por Año")
        st.dataframe(df_global_anio, use_container_width=True)


# ---------------------------------------------------------------------------
# Pestaña 3: Detalle empleadores
# ---------------------------------------------------------------------------
def tab_detalle_empleadores(data, filtros):
    st.title("Detalle Empleadores")

    df_emp_mensual = data.get("lm_empleador_mensual", pd.DataFrame())
    df_cot_anio = data.get("lm_cotizante_anio", pd.DataFrame())

    if not df_emp_mensual.empty:
        if filtros["periodo_desde"] and filtros["periodo_hasta"]:
            df_emp_mensual = df_emp_mensual[
                (df_emp_mensual["periodo"] >= filtros["periodo_desde"])
                & (df_emp_mensual["periodo"] <= filtros["periodo_hasta"])
            ]

        st.subheader("Empleadores por Período")
        st.write(f"Total registros: {len(df_emp_mensual):,}")

        # Búsqueda por RUT
        rut_buscar = st.text_input("Buscar por RUT empleador")
        if rut_buscar:
            df_emp_mensual = df_emp_mensual[
                df_emp_mensual["rut_empleador"].astype(str).str.contains(rut_buscar, case=False)
            ]

        st.dataframe(df_emp_mensual.head(1000), use_container_width=True)
        if len(df_emp_mensual) > 1000:
            st.caption(f"Mostrando primeros 1.000 de {len(df_emp_mensual):,} registros.")
    else:
        st.info("No hay datos de empleador mensual.")

    if not df_cot_anio.empty:
        st.subheader("Cotizantes por Año")
        if filtros["anios"]:
            df_cot_anio = df_cot_anio[df_cot_anio["anio"].isin(filtros["anios"])]
        st.write(f"Total registros: {len(df_cot_anio):,}")
        st.dataframe(df_cot_anio.head(500), use_container_width=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    # Verificar variables de entorno críticas
    missing = [v for v in ["SOURCE_HOST", "SOURCE_DB", "SOURCE_USER", "SOURCE_PASSWORD"]
               if not os.getenv(v)]
    if missing:
        st.error(f"Faltan variables de entorno para conexion a DATALAKE: {', '.join(missing)}")
        st.stop()

    with st.spinner("Cargando datos..."):
        data = load_all_data()

    filtros = render_sidebar(data)

    tab1, tab2, tab3 = st.tabs(["Resumen", "Estadísticas", "Detalle Empleadores"])

    with tab1:
        tab_resumen(data, filtros)

    with tab2:
        tab_estadisticas(data, filtros)

    with tab3:
        tab_detalle_empleadores(data, filtros)


if __name__ == "__main__":
    main()
