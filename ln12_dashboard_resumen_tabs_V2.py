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
    page_title="FONASA LM v2 - Dashboard",
    page_icon="🏥",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Conexión y carga
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


TABLAS = [
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


@st.cache_data(ttl=600)
def load_all_data() -> dict:
    return {t: load_table(t) for t in TABLAS}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def fmt_n(v):
    if pd.isna(v):
        return "-"
    return f"{int(v):,}"


def fmt_m(v):
    if pd.isna(v):
        return "-"
    return f"${v:,.0f}"


def apply_filtros_periodo(df, col, desde, hasta):
    if desde is not None and hasta is not None and col in df.columns:
        return df[(df[col] >= desde) & (df[col] <= hasta)]
    return df


def apply_filtros_lista(df, col, lista):
    if lista and col in df.columns:
        return df[df[col].isin(lista)]
    return df


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
def render_sidebar(data):
    st.sidebar.title("🔎 Filtros")

    df_anio = data.get("lm_resumen_anio", pd.DataFrame())
    anios = sorted(df_anio["anio"].dropna().unique().tolist()) if not df_anio.empty else []
    anio_sel = st.sidebar.multiselect("Año(s)", options=anios, default=anios)

    df_mensual = data.get("lm_resumen_mensual", pd.DataFrame())
    periodos = sorted(df_mensual["periodo"].dropna().unique().tolist()) if not df_mensual.empty else []
    idx_fin = len(periodos) - 1 if periodos else 0
    periodo_desde = st.sidebar.selectbox("Período desde", options=periodos, index=0) if periodos else None
    periodo_hasta = st.sidebar.selectbox("Período hasta", options=periodos, index=idx_fin) if periodos else None

    df_est_base = data.get("lm_resumen_estrato_anio", pd.DataFrame())
    estratos = sorted(df_est_base["estrato"].dropna().unique().tolist()) if not df_est_base.empty else []
    estrato_sel = st.sidebar.multiselect("Estrato(s)", options=estratos, default=estratos)

    # Separador visual
    st.sidebar.markdown("---")
    st.sidebar.caption(f"Schema: {SOURCE_SCHEMA}")
    st.sidebar.caption(f"Host: {SOURCE_HOST}")

    return {
        "anios": anio_sel,
        "estratos": estrato_sel,
        "periodo_desde": periodo_desde,
        "periodo_hasta": periodo_hasta,
    }


# ---------------------------------------------------------------------------
# Pestaña Resumen
# ---------------------------------------------------------------------------
def tab_resumen(data, f):
    st.header("Resumen General")

    df = apply_filtros_lista(data.get("lm_resumen_anio", pd.DataFrame()).copy(), "anio", f["anios"])

    if not df.empty:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Empleadores", fmt_n(df["cantidad_empleadores"].sum()))
        c2.metric("Cotizantes", fmt_n(df["cantidad_cotizantes"].sum()))
        c3.metric("Días Autorizados", fmt_n(df["dias_autorizados"].sum()))
        c4.metric("Días Otorgados", fmt_n(df["sum_dias_otorgados"].sum()))
        c5.metric("Monto Cotización", fmt_m(df["sum_mto_coti"].sum()))

        st.markdown("---")
        st.subheader("Por Año")
        st.dataframe(df, use_container_width=True)

    df_m = apply_filtros_periodo(
        data.get("lm_resumen_mensual", pd.DataFrame()).copy(),
        "periodo", f["periodo_desde"], f["periodo_hasta"]
    )
    if not df_m.empty:
        st.subheader("Por Período")
        st.dataframe(df_m, use_container_width=True)

    df_ea = apply_filtros_lista(
        apply_filtros_lista(
            data.get("lm_resumen_estrato_anio", pd.DataFrame()).copy(),
            "anio", f["anios"]
        ), "estrato", f["estratos"]
    )
    if not df_ea.empty:
        st.subheader("Por Estrato y Año")
        st.dataframe(df_ea, use_container_width=True)

    df_ems = apply_filtros_lista(
        apply_filtros_periodo(
            data.get("lm_resumen_estrato_mensual", pd.DataFrame()).copy(),
            "periodo", f["periodo_desde"], f["periodo_hasta"]
        ), "estrato", f["estratos"]
    )
    if not df_ems.empty:
        st.subheader("Por Estrato y Período")
        st.dataframe(df_ems, use_container_width=True)


# ---------------------------------------------------------------------------
# Pestaña Estadísticas
# ---------------------------------------------------------------------------
def tab_estadisticas(data, f):
    st.header("Estadísticas")

    df_sea = apply_filtros_lista(
        apply_filtros_lista(
            data.get("lm_resumen_estadisticas_estrato_anio", pd.DataFrame()).copy(),
            "anio", f["anios"]
        ), "estrato", f["estratos"]
    )
    if not df_sea.empty:
        st.subheader("Estadísticas Estrato × Año")
        st.dataframe(df_sea, use_container_width=True)
    else:
        st.info("Sin datos de estadísticas estrato × año.")

    df_sem = apply_filtros_lista(
        apply_filtros_periodo(
            data.get("lm_resumen_estadisticas_estrato_mensual", pd.DataFrame()).copy(),
            "periodo", f["periodo_desde"], f["periodo_hasta"]
        ), "estrato", f["estratos"]
    )
    if not df_sem.empty:
        st.subheader("Estadísticas Estrato × Período")
        st.dataframe(df_sem, use_container_width=True)

    df_ga = apply_filtros_lista(
        data.get("lm_resumen_estadisticas_anio", pd.DataFrame()).copy(),
        "anio", f["anios"]
    )
    if not df_ga.empty:
        st.subheader("Estadísticas Globales por Año")
        st.dataframe(df_ga, use_container_width=True)

    df_gm = apply_filtros_periodo(
        data.get("lm_resumen_estadisticas_mensual", pd.DataFrame()).copy(),
        "periodo", f["periodo_desde"], f["periodo_hasta"]
    )
    if not df_gm.empty:
        st.subheader("Estadísticas Globales por Período")
        st.dataframe(df_gm, use_container_width=True)


# ---------------------------------------------------------------------------
# Pestaña Detalle Empleadores
# ---------------------------------------------------------------------------
def tab_detalle(data, f):
    st.header("Detalle Empleadores")

    df_emp = apply_filtros_periodo(
        data.get("lm_empleador_mensual", pd.DataFrame()).copy(),
        "periodo", f["periodo_desde"], f["periodo_hasta"]
    )

    if not df_emp.empty:
        col_buscar, col_info = st.columns([3, 1])
        rut_buscar = col_buscar.text_input("🔍 Buscar por RUT empleador")
        if rut_buscar:
            df_emp = df_emp[
                df_emp["rut_empleador"].astype(str).str.contains(rut_buscar, case=False)
            ]

        if "estrato" in df_emp.columns and f["estratos"]:
            df_emp = df_emp[df_emp["estrato"].isin(f["estratos"])]

        col_info.metric("Registros", fmt_n(len(df_emp)))

        st.subheader("Empleador Mensual")
        st.dataframe(df_emp.head(1000), use_container_width=True)
        if len(df_emp) > 1000:
            st.caption(f"Mostrando primeros 1.000 de {len(df_emp):,} registros.")
    else:
        st.info("Sin datos de empleador mensual con los filtros seleccionados.")

    df_cot = apply_filtros_lista(
        data.get("lm_cotizante_anio", pd.DataFrame()).copy(),
        "anio", f["anios"]
    )
    if not df_cot.empty:
        st.subheader(f"Cotizante Año — {len(df_cot):,} registros")
        st.dataframe(df_cot.head(500), use_container_width=True)
        if len(df_cot) > 500:
            st.caption(f"Mostrando 500 de {len(df_cot):,} registros.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    missing = [v for v in ["SOURCE_HOST", "SOURCE_DB", "SOURCE_USER", "SOURCE_PASSWORD"]
               if not os.getenv(v)]
    if missing:
        st.error(f"Faltan variables de entorno para conexion a DATALAKE: {', '.join(missing)}")
        st.stop()

    with st.spinner("Cargando datos desde DATALAKE..."):
        data = load_all_data()

    filtros = render_sidebar(data)

    tab1, tab2, tab3 = st.tabs(["📊 Resumen", "📈 Estadísticas", "🏢 Detalle Empleadores"])

    with tab1:
        tab_resumen(data, filtros)

    with tab2:
        tab_estadisticas(data, filtros)

    with tab3:
        tab_detalle(data, filtros)


if __name__ == "__main__":
    main()
