import os
import sys
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config import ConfigLoader
from src.data_loader import ExcelLoader
from src.logger import setup_logging
from src.services import KPIEngine, ReportProcessor
from src.template_engine import TemplateFiller


setup_logging()
config = ConfigLoader()
loader = ExcelLoader(config)
processor = ReportProcessor(config)
filler = TemplateFiller()


HOME_MODES = [
    {
        "key": "emisiones",
        "label": "Emisiones",
        "report_key": "emision_mensual",
        "icon": "📤",
        "description": "Convierte el archivo masivo de emisiones y cancelaciones al formato operativo.",
    },
    {
        "key": "renovaciones",
        "label": "Renovaciones",
        "report_key": "renovaciones",
        "icon": "🔁",
        "description": "Genera el control de renovaciones listo para seguimiento y actualización.",
    },
    {
        "key": "vencimientos",
        "label": "Vencimientos",
        "report_key": "vencimientos",
        "icon": "📅",
        "description": "Estandariza el listado de pólizas por vencer para revisión comercial.",
    },
    {
        "key": "cotizaciones",
        "label": "Cotizaciones",
        "report_key": "cotizaciones",
        "icon": "📄",
        "description": "Agrupa los PDF de cotización y extrae agente, unidad, vigencia y prima.",
    },
    {
        "key": "conjunto",
        "label": "Conjunto",
        "report_key": None,
        "icon": "🧩",
        "description": "Procesa emisiones, vencimientos y cotizaciones en una sola corrida.",
    },
]

MODE_MAP = {mode["key"]: mode for mode in HOME_MODES}


def current_mode():
    return MODE_MAP[st.session_state.active_mode]


def current_report_key():
    return current_mode()["report_key"]


def current_report_config():
    report_key = current_report_key()
    return config.get_report_config(report_key) if report_key else None


def reset_single_results():
    st.session_state.processed_df = None
    st.session_state.raw_df = None
    st.session_state.errors = []
    st.session_state.kpis = {}
    st.session_state.file_details = []
    st.session_state.generated_excel = None
    st.session_state.generated_excel_name = ""
    st.session_state.generated_csv = None
    st.session_state.generated_csv_name = ""
    st.session_state.step = 1


def reset_bundle_results():
    st.session_state.bundle_results = {}
    st.session_state.bundle_errors = []
    st.session_state.bundle_excel = None
    st.session_state.bundle_excel_name = ""


def reset_all_results():
    reset_single_results()
    reset_bundle_results()


def activate_mode(mode_key: str):
    if st.session_state.active_mode != mode_key:
        st.session_state.active_mode = mode_key
        reset_all_results()


def initialize_state():
    defaults = {
        "authenticated": False,
        "username": "",
        "active_mode": "emisiones",
        "processed_df": None,
        "raw_df": None,
        "errors": [],
        "step": 1,
        "kpis": {},
        "file_details": [],
        "generated_excel": None,
        "generated_excel_name": "",
        "generated_csv": None,
        "generated_csv_name": "",
        "bundle_results": {},
        "bundle_errors": [],
        "bundle_excel": None,
        "bundle_excel_name": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def check_credentials(username: str, password: str) -> bool:
    try:
        passwords = st.secrets.get("passwords", {})
        if username in passwords and passwords[username] == password:
            return True
    except Exception:
        pass
    fallback = {"montse": "montse2026", "admin": "admin2026"}
    return fallback.get(username) == password


def render_login():
    st.markdown(
        """
        <style>
        .login-title {
            text-align:center;
            font-size:2rem;
            font-weight:700;
            color:#12355b;
            margin-top:4rem;
        }
        .login-subtitle {
            text-align:center;
            color:#6b7280;
            margin-bottom:1.5rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="login-title">Reporteador Enterprise</div>', unsafe_allow_html=True)
    st.markdown('<div class="login-subtitle">Ingrese sus credenciales para continuar</div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        with st.form("login_form"):
            username = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            submitted = st.form_submit_button("Iniciar Sesión", use_container_width=True, type="primary")
            if submitted:
                if check_credentials(username, password):
                    st.session_state.authenticated = True
                    st.session_state.username = username
                    st.rerun()
                st.error("Usuario o contraseña incorrectos.")


def format_bytes(size):
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def calculate_quality_score(df, report_type):
    if df.empty:
        return 0

    report_config = config.get_report_config(report_type)
    if not report_config:
        return 0

    required_cols = [c["name"] for c in report_config.get("columns", []) if c.get("required")]
    total_checks = 0
    passed_checks = 0

    for col in required_cols:
        total_checks += 1
        if col in df.columns:
            passed_checks += 1

    for col in required_cols:
        if col in df.columns:
            total_checks += 1
            null_pct = df[col].isnull().mean()
            if null_pct < 0.05:
                passed_checks += 1
            elif null_pct < 0.2:
                passed_checks += 0.5

    total_checks += 1
    dup_pct = df.duplicated().mean()
    if dup_pct < 0.01:
        passed_checks += 1
    elif dup_pct < 0.1:
        passed_checks += 0.5

    return round((passed_checks / total_checks) * 100) if total_checks > 0 else 0


def render_step_indicator(current):
    labels = [("1", "Cargar"), ("2", "Analizar"), ("3", "Exportar")]
    html = ['<div style="display:flex;gap:.6rem;justify-content:center;margin:1rem 0 2rem 0;">']
    for num, label in labels:
        step_num = int(num)
        if step_num < current:
            bg, fg, icon = "#d1fae5", "#065f46", "OK"
        elif step_num == current:
            bg, fg, icon = "#12355b", "#ffffff", "ACT"
        else:
            bg, fg, icon = "#e5e7eb", "#6b7280", "..."
        html.append(
            f'<div style="padding:.55rem 1rem;border-radius:999px;background:{bg};color:{fg};font-size:.85rem;font-weight:600;">'
            f"{icon} {label}</div>"
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def render_kpi_cards(kpis):
    cols = st.columns(len(kpis))
    for col, (label, value) in zip(cols, kpis.items()):
        if isinstance(value, float):
            display = f"{value:,.2f}"
        elif isinstance(value, int):
            display = f"{value:,}"
        else:
            display = str(value)
        col.metric(label, display)


def render_quality_score(score):
    if score >= 80:
        color, label = "#16a34a", "Excelente"
    elif score >= 50:
        color, label = "#d97706", "Aceptable"
    else:
        color, label = "#dc2626", "Revisar"

    st.markdown(
        f"""
        <div style="background:white;padding:1rem 1.2rem;border-radius:14px;box-shadow:0 2px 12px rgba(0,0,0,.06);margin:1rem 0;">
            <div style="display:flex;justify-content:space-between;font-weight:600;margin-bottom:.5rem;">
                <span>Calidad de Datos</span>
                <span style="color:{color};">{score}% · {label}</span>
            </div>
            <div style="height:12px;background:#e5e7eb;border-radius:999px;overflow:hidden;">
                <div style="width:{score}%;height:100%;background:{color};"></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_mode_buttons():
    st.markdown("### Home")
    cols = st.columns(len(HOME_MODES))
    for col, mode in zip(cols, HOME_MODES):
        with col:
            st.markdown(
                f"""
                <div style="background:white;border:1px solid #dbe4ee;border-radius:16px;padding:1rem;min-height:148px;
                            box-shadow:0 8px 24px rgba(18,53,91,.06);margin-bottom:.5rem;">
                    <div style="font-size:1.8rem;">{mode['icon']}</div>
                    <div style="font-weight:700;color:#12355b;margin:.4rem 0;">{mode['label']}</div>
                    <div style="font-size:.84rem;color:#5b6470;">{mode['description']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(mode["label"], key=f"mode_{mode['key']}", use_container_width=True):
                activate_mode(mode["key"])
                st.rerun()


def render_file_cards(files):
    st.markdown(f"**{len(files)} archivo(s) cargado(s)**")
    for file_obj in files:
        st.markdown(
            f"""
            <div style="background:white;border:1px solid #e5e7eb;border-radius:12px;padding:.9rem 1rem;margin-bottom:.5rem;
                        display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <div style="font-weight:600;">{file_obj.name}</div>
                    <div style="font-size:.82rem;color:#6b7280;">{format_bytes(file_obj.size)}</div>
                </div>
                <div style="color:#16a34a;font-weight:700;">Listo</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_dataset_preview(df, key_prefix):
    if df is None or df.empty:
        return

    tabs = st.tabs(["Distribución", "Composición", "Datos"])
    text_cols = df.select_dtypes(include=["object"]).columns.tolist()
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()

    with tabs[0]:
        if text_cols:
            bar_col = st.selectbox("Agrupar por", text_cols, key=f"{key_prefix}_bar_col")
            counts = df[bar_col].replace("", "Sin dato").value_counts().reset_index()
            counts.columns = [bar_col, "Cantidad"]
            fig = px.bar(counts.head(15), x=bar_col, y="Cantidad", color="Cantidad", color_continuous_scale="Blues")
            fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No hay columnas de texto para esta visualización.")

    with tabs[1]:
        if text_cols:
            pie_col = st.selectbox("Agrupar por", text_cols, key=f"{key_prefix}_pie_col")
            if numeric_cols:
                pie_value = st.selectbox("Valor", numeric_cols, key=f"{key_prefix}_pie_val")
                fig = px.pie(df, names=pie_col, values=pie_value, color_discrete_sequence=px.colors.sequential.Blues_r)
            else:
                counts = df[pie_col].replace("", "Sin dato").value_counts().reset_index()
                counts.columns = [pie_col, "Cantidad"]
                fig = px.pie(counts, names=pie_col, values="Cantidad", color_discrete_sequence=px.colors.sequential.Blues_r)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No hay datos para la composición.")

    with tabs[2]:
        search = st.text_input("Buscar", key=f"{key_prefix}_search", placeholder="Filtrar registros...")
        display_df = df
        if search:
            mask = df.apply(lambda row: row.astype(str).str.contains(search, case=False, na=False).any(), axis=1)
            display_df = df[mask]
            st.caption(f"Mostrando {len(display_df)} de {len(df)} registros")
        st.dataframe(display_df, use_container_width=True, height=420)


def render_single_export(report_key, label):
    report_cfg = config.get_report_config(report_key)
    processed_df = st.session_state.processed_df
    if processed_df is None or processed_df.empty or not report_cfg:
        return

    st.divider()
    st.markdown("### Exportación")

    if st.button("Preparar Excel", key=f"prepare_excel_{report_key}", type="primary", use_container_width=True):
        output = filler.fill_template(processed_df, report_cfg)
        st.session_state.generated_excel = output.getvalue()
        st.session_state.generated_excel_name = f"{label}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        st.session_state.generated_csv = processed_df.to_csv(index=False).encode("utf-8")
        st.session_state.generated_csv_name = f"{label}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        st.session_state.step = 3

    if st.session_state.generated_excel:
        st.download_button(
            "Descargar Excel",
            data=st.session_state.generated_excel,
            file_name=st.session_state.generated_excel_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    if st.session_state.generated_csv:
        st.download_button(
            "Descargar CSV",
            data=st.session_state.generated_csv,
            file_name=st.session_state.generated_csv_name,
            mime="text/csv",
            use_container_width=True,
        )


def process_single_flow(files, mode_def):
    report_key = mode_def["report_key"]
    reset_single_results()
    df, errors = loader.load_and_validate(files, report_key)
    st.session_state.errors = errors

    if df.empty:
        return

    processed_df = processor.process_data(df, report_key)
    st.session_state.raw_df = df
    st.session_state.processed_df = processed_df
    st.session_state.kpis = KPIEngine.calculate(processed_df, report_key)
    st.session_state.file_details = [{"name": f.name, "size": f.size, "rows": "—"} for f in files]
    st.session_state.step = 2


def render_single_flow():
    mode_def = current_mode()
    report_key = mode_def["report_key"]
    report_cfg = current_report_config()
    allowed_extensions = [ext.lstrip(".") for ext in report_cfg.get("input_extensions", [".xlsx", ".xls"])]
    uploader_help = (
        "Puede subir múltiples archivos PDF. El sistema agrupará las cotizaciones automáticamente."
        if allowed_extensions == ["pdf"]
        else "Puede subir múltiples archivos Excel del mismo tipo."
    )

    st.markdown(f"### {mode_def['icon']} {mode_def['label']}")
    st.caption(mode_def["description"])

    files = st.file_uploader(
        f"Seleccione archivos para {mode_def['label']}",
        type=allowed_extensions,
        accept_multiple_files=True,
        key=f"uploader_{mode_def['key']}",
        help=uploader_help,
    )

    if files:
        render_file_cards(files)
        if st.button(f"Procesar {mode_def['label']}", key=f"process_{mode_def['key']}", type="primary", use_container_width=True):
            with st.spinner("Procesando información..."):
                process_single_flow(files, mode_def)
            st.rerun()

    if st.session_state.errors:
        st.warning("Se detectaron observaciones durante el procesamiento.")
        for error in st.session_state.errors:
            st.warning(error)

    if st.session_state.processed_df is not None and not st.session_state.processed_df.empty:
        processed_df = st.session_state.processed_df
        st.divider()
        st.markdown("### Dashboard")
        render_quality_score(calculate_quality_score(processed_df, report_key))
        if st.session_state.kpis:
            render_kpi_cards(st.session_state.kpis)
        render_dataset_preview(processed_df, mode_def["key"])
        render_single_export(report_key, mode_def["label"])


def process_bundle(emision_files, vencimiento_files, cotizacion_files):
    reset_bundle_results()

    results = {}
    errors = []

    if emision_files:
        df, issue_list = loader.load_and_validate(emision_files, "emision_mensual")
        errors.extend([f"Emisiones: {item}" for item in issue_list])
        if not df.empty:
            results["emision_mensual"] = processor.process_data(df, "emision_mensual")

    if vencimiento_files:
        df, issue_list = loader.load_and_validate(vencimiento_files, "vencimientos")
        errors.extend([f"Vencimientos: {item}" for item in issue_list])
        if not df.empty:
            results["vencimientos"] = processor.process_data(df, "vencimientos")
            results["renovaciones"] = processor.process_data(df, "renovaciones")

    if cotizacion_files:
        df, issue_list = loader.load_and_validate(cotizacion_files, "cotizaciones")
        errors.extend([f"Cotizaciones: {item}" for item in issue_list])
        if not df.empty:
            results["cotizaciones"] = processor.process_data(df, "cotizaciones")

    st.session_state.bundle_results = results
    st.session_state.bundle_errors = errors
    st.session_state.step = 2 if results else 1


def render_bundle_summary():
    bundle = st.session_state.bundle_results
    if not bundle:
        return

    st.divider()
    st.markdown("### Resumen Conjunto")

    cols = st.columns(len(bundle))
    for col, (report_key, df) in zip(cols, bundle.items()):
        label = config.get_report_config(report_key)["name"]
        col.metric(label, f"{len(df):,}")

    tabs = st.tabs([config.get_report_config(report_key)["name"] for report_key in bundle.keys()])
    for tab, (report_key, df) in zip(tabs, bundle.items()):
        with tab:
            render_dataset_preview(df, f"bundle_{report_key}")


def render_bundle_export():
    bundle = st.session_state.bundle_results
    if not bundle:
        return

    st.divider()
    st.markdown("### Exportación Conjunta")

    if st.button("Preparar Workbook Conjunto", key="prepare_bundle", type="primary", use_container_width=True):
        output = filler.fill_combined_report(bundle, config)
        st.session_state.bundle_excel = output.getvalue()
        st.session_state.bundle_excel_name = f"Reporte_Conjunto_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        st.session_state.step = 3

    if st.session_state.bundle_excel:
        st.download_button(
            "Descargar Workbook Conjunto",
            data=st.session_state.bundle_excel,
            file_name=st.session_state.bundle_excel_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )


def render_combined_flow():
    st.markdown("### 🧩 Flujo Conjunto")
    st.caption("Cargue cada fuente una sola vez. El sistema generará vencimientos, renovaciones, emisiones y cotizaciones dentro del mismo workbook.")

    col1, col2, col3 = st.columns(3)
    with col1:
        emision_files = st.file_uploader(
            "Emisiones",
            type=["xlsx", "xls"],
            accept_multiple_files=True,
            key="bundle_emisiones",
        )
        if emision_files:
            render_file_cards(emision_files)

    with col2:
        vencimiento_files = st.file_uploader(
            "Vencimientos / Renovaciones",
            type=["xlsx", "xls"],
            accept_multiple_files=True,
            key="bundle_vencimientos",
        )
        if vencimiento_files:
            render_file_cards(vencimiento_files)

    with col3:
        cotizacion_files = st.file_uploader(
            "Cotizaciones PDF",
            type=["pdf"],
            accept_multiple_files=True,
            key="bundle_cotizaciones",
        )
        if cotizacion_files:
            render_file_cards(cotizacion_files)

    if st.button("Procesar Todo", key="process_bundle", type="primary", use_container_width=True):
        with st.spinner("Procesando flujo conjunto..."):
            process_bundle(emision_files or [], vencimiento_files or [], cotizacion_files or [])
        st.rerun()

    if st.session_state.bundle_errors:
        st.warning("Se detectaron observaciones en el flujo conjunto.")
        for error in st.session_state.bundle_errors:
            st.warning(error)

    render_bundle_summary()
    render_bundle_export()


def render_sidebar():
    mode_def = current_mode()
    report_cfg = current_report_config()

    with st.sidebar:
        st.markdown(
            """
            <div style="text-align:center;padding:1rem 0;border-bottom:1px solid #e5e7eb;margin-bottom:1rem;">
                <div style="font-size:2.3rem;">📊</div>
                <div style="font-size:1.1rem;font-weight:700;color:#12355b;">Reporteador Enterprise</div>
                <div style="font-size:.75rem;color:#6b7280;">v1.1.0</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        user_col, logout_col = st.columns([3, 1])
        with user_col:
            st.markdown(f"**{st.session_state.username}**")
        with logout_col:
            if st.button("Salir", key="logout_btn"):
                st.session_state.authenticated = False
                st.session_state.username = ""
                st.rerun()

        st.markdown(
            f"""
            <div style="background:#e8f1fb;border-left:4px solid #12355b;padding:.8rem;border-radius:10px;margin:.75rem 0 1rem 0;">
                <div style="font-size:.82rem;color:#12355b;font-weight:700;">Modo activo</div>
                <div style="font-size:.95rem;color:#0f172a;">{mode_def['label']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if mode_def["key"] == "conjunto":
            for report_key in ["emision_mensual", "renovaciones", "vencimientos", "cotizaciones"]:
                cfg = config.get_report_config(report_key)
                with st.expander(cfg["name"]):
                    for col_def in cfg.get("columns", []):
                        req = "Req." if col_def.get("required") else "Opc."
                        st.markdown(f"- `{col_def['name']}` · `{col_def['type']}` · {req}")
        elif report_cfg:
            with st.expander("Columnas esperadas", expanded=False):
                for col_def in report_cfg.get("columns", []):
                    req = "Req." if col_def.get("required") else "Opc."
                    st.markdown(f"- `{col_def['name']}` · `{col_def['type']}` · {req}")

        with st.expander("Diagnóstico"):
            if os.path.exists("logs/app.log"):
                try:
                    with open("logs/app.log", "r", encoding="utf-8", errors="ignore") as file_obj:
                        lines = file_obj.readlines()[-15:]
                    st.code("".join(lines), language="text")
                except Exception:
                    st.info("Sin logs disponibles.")
            else:
                st.info("Sin logs aún.")


st.set_page_config(
    page_title="Reporteador Comercial Enterprise",
    layout="wide",
    page_icon="📊",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    * { font-family: 'Inter', sans-serif; }
    .stApp { background: linear-gradient(180deg, #f4f8fc 0%, #eef4f8 100%); }
    </style>
    """,
    unsafe_allow_html=True,
)

initialize_state()

if not st.session_state.authenticated:
    render_login()
    st.stop()

render_sidebar()

st.markdown(
    '<div style="text-align:center;font-size:2.4rem;font-weight:800;color:#12355b;">Reporteador Comercial Enterprise</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div style="text-align:center;color:#5b6470;font-size:1rem;margin-bottom:1rem;">Botones directos en home para emisiones, renovaciones, vencimientos, cotizaciones y flujo conjunto.</div>',
    unsafe_allow_html=True,
)

render_mode_buttons()
render_step_indicator(st.session_state.step)

if current_mode()["key"] == "conjunto":
    render_combined_flow()
else:
    render_single_flow()

if current_mode()["key"] != "conjunto" and st.session_state.processed_df is None:
    st.markdown(
        """
        <div style="text-align:center;background:white;border-radius:18px;padding:2.5rem;margin-top:1.5rem;
                    box-shadow:0 10px 30px rgba(18,53,91,.08);">
            <div style="font-size:3rem;">📂</div>
            <div style="font-size:1.2rem;font-weight:700;color:#12355b;margin:.5rem 0;">Seleccione un flujo y cargue sus archivos</div>
            <div style="max-width:520px;margin:0 auto;color:#6b7280;">
                Cada botón de la home prepara un reporte distinto. El modo conjunto permite procesar varias fuentes en la misma corrida.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
