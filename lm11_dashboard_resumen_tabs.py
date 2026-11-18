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

st.set_page_config(
    page_title="FONASA LM - Resumen Tabs",
    page_icon="🏥",
    layout="wide",
)


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


def load_all_data():
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
    ]
    return {t: load_table(t) for t in tablas}


def main():
    missing = [v for v in ["SOURCE_HOST", "SOURCE_DB", "SOURCE_USER", "SOURCE_PASSWORD"]
               if not os.getenv(v)]
    if missing:
        st.error(f"Faltan variables de entorno para conexion a DATALAKE: {', '.join(missing)}")
        st.stop()

    st.title("FONASA LM - Resumen")

    with st.spinner("Cargando datos desde DATALAKE..."):
        data = load_all_data()

    # Sidebar filtros
    st.sidebar.title("Filtros")

    df_anio = data.get("lm_resumen_anio", pd.DataFrame())
    anios = sorted(df_anio["anio"].dropna().unique().tolist()) if not df_anio.empty else []
    anio_sel = st.sidebar.multiselect("Año(s)", options=anios, default=anios)

    df_mensual = data.get("lm_resumen_mensual", pd.DataFrame())
    periodos = sorted(df_mensual["periodo"].dropna().unique().tolist()) if not df_mensual.empty else []
    periodo_desde = st.sidebar.selectbox("Período desde", options=periodos, index=0) if periodos else None
    periodo_hasta = st.sidebar.selectbox("Período hasta", options=periodos, index=len(periodos) - 1) if periodos else None

    df_est_base = data.get("lm_resumen_estrato_anio", pd.DataFrame())
    estratos = sorted(df_est_base["estrato"].dropna().unique().tolist()) if not df_est_base.empty else []
    estrato_sel = st.sidebar.multiselect("Estrato(s)", options=estratos, default=estratos)

    tab1, tab2, tab3 = st.tabs(["Resumen", "Estadísticas", "Detalle Empleadores"])

    # --- Pestaña Resumen ---
    with tab1:
        df = df_anio.copy()
        if anio_sel:
            df = df[df["anio"].isin(anio_sel)]

        if not df.empty:
            st.subheader("Resumen por Año")
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Sin datos para los filtros seleccionados.")

        df_m = df_mensual.copy()
        if periodo_desde and periodo_hasta:
            df_m = df_m[
                (df_m["periodo"] >= periodo_desde) & (df_m["periodo"] <= periodo_hasta)
            ]
        if not df_m.empty:
            st.subheader("Resumen por Período")
            st.dataframe(df_m, use_container_width=True)

        df_ea = df_est_base.copy()
        if not df_ea.empty:
            if anio_sel:
                df_ea = df_ea[df_ea["anio"].isin(anio_sel)]
            if estrato_sel:
                df_ea = df_ea[df_ea["estrato"].isin(estrato_sel)]
            st.subheader("Resumen por Estrato y Año")
            st.dataframe(df_ea, use_container_width=True)

        df_em_mes = data.get("lm_resumen_estrato_mensual", pd.DataFrame()).copy()
        if not df_em_mes.empty:
            if periodo_desde and periodo_hasta:
                df_em_mes = df_em_mes[
                    (df_em_mes["periodo"] >= periodo_desde) & (df_em_mes["periodo"] <= periodo_hasta)
                ]
            if estrato_sel:
                df_em_mes = df_em_mes[df_em_mes["estrato"].isin(estrato_sel)]
            st.subheader("Resumen por Estrato y Período")
            st.dataframe(df_em_mes, use_container_width=True)

    # --- Pestaña Estadísticas ---
    with tab2:
        df_sea = data.get("lm_resumen_estadisticas_estrato_anio", pd.DataFrame()).copy()
        if not df_sea.empty:
            if anio_sel:
                df_sea = df_sea[df_sea["anio"].isin(anio_sel)]
            if estrato_sel:
                df_sea = df_sea[df_sea["estrato"].isin(estrato_sel)]
            st.subheader("Estadísticas por Estrato y Año")
            st.dataframe(df_sea, use_container_width=True)

        df_sem = data.get("lm_resumen_estadisticas_estrato_mensual", pd.DataFrame()).copy()
        if not df_sem.empty:
            if periodo_desde and periodo_hasta:
                df_sem = df_sem[
                    (df_sem["periodo"] >= periodo_desde) & (df_sem["periodo"] <= periodo_hasta)
                ]
            if estrato_sel:
                df_sem = df_sem[df_sem["estrato"].isin(estrato_sel)]
            st.subheader("Estadísticas por Estrato y Período")
            st.dataframe(df_sem, use_container_width=True)

        df_ga = data.get("lm_resumen_estadisticas_anio", pd.DataFrame()).copy()
        if not df_ga.empty:
            if anio_sel:
                df_ga = df_ga[df_ga["anio"].isin(anio_sel)]
            st.subheader("Estadísticas Globales por Año")
            st.dataframe(df_ga, use_container_width=True)

        df_gm = data.get("lm_resumen_estadisticas_mensual", pd.DataFrame()).copy()
        if not df_gm.empty:
            if periodo_desde and periodo_hasta:
                df_gm = df_gm[
                    (df_gm["periodo"] >= periodo_desde) & (df_gm["periodo"] <= periodo_hasta)
                ]
            st.subheader("Estadísticas Globales por Período")
            st.dataframe(df_gm, use_container_width=True)

    # --- Pestaña Detalle Empleadores ---
    with tab3:
        df_em = data.get("lm_empleador_mensual", pd.DataFrame()).copy()
        if not df_em.empty:
            if periodo_desde and periodo_hasta:
                df_em = df_em[
                    (df_em["periodo"] >= periodo_desde) & (df_em["periodo"] <= periodo_hasta)
                ]

            rut_buscar = st.text_input("Buscar RUT empleador")
            if rut_buscar:
                df_em = df_em[
                    df_em["rut_empleador"].astype(str).str.contains(rut_buscar, case=False)
                ]

            st.subheader(f"Empleador Mensual ({len(df_em):,} registros)")
            st.dataframe(df_em.head(1000), use_container_width=True)
            if len(df_em) > 1000:
                st.caption(f"Mostrando 1.000 de {len(df_em):,} registros.")
        else:
            st.info("No hay datos de empleador mensual.")


if __name__ == "__main__":
    main()
