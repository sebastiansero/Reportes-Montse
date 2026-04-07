import os
import sys
from datetime import datetime

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


MODES = [
    {"key": "emisiones", "label": "Emisiones", "report_key": "emision_mensual"},
    {"key": "renovaciones", "label": "Renovaciones", "report_key": "renovaciones"},
    {"key": "vencimientos", "label": "Vencimientos", "report_key": "vencimientos"},
    {"key": "cotizaciones", "label": "Cotizaciones", "report_key": "cotizaciones"},
    {"key": "conjunto", "label": "Conjunto", "report_key": None},
]
MODE_MAP = {mode["key"]: mode for mode in MODES}


def get_mode(mode_key=None):
    return MODE_MAP[mode_key or st.session_state.active_mode]


def get_report_config(mode_key=None):
    mode = get_mode(mode_key)
    return config.get_report_config(mode["report_key"]) if mode["report_key"] else None


def initialize_state():
    defaults = {
        "authenticated": False,
        "username": "",
        "active_mode": "emisiones",
        "processed_df": None,
        "messages": [],
        "kpis": {},
        "download_bytes": None,
        "download_name": "",
        "bundle_results": {},
        "bundle_messages": [],
        "bundle_download": None,
        "bundle_download_name": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_single():
    st.session_state.processed_df = None
    st.session_state.messages = []
    st.session_state.kpis = {}
    st.session_state.download_bytes = None
    st.session_state.download_name = ""


def reset_bundle():
    st.session_state.bundle_results = {}
    st.session_state.bundle_messages = []
    st.session_state.bundle_download = None
    st.session_state.bundle_download_name = ""


def activate_mode(mode_key):
    if st.session_state.active_mode != mode_key:
        st.session_state.active_mode = mode_key
        reset_single()
        reset_bundle()


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
        <div class="login-brand">
            <div class="login-kicker">Montse</div>
            <h1>Reportes</h1>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left, center, right = st.columns([1.3, 1, 1.3])
    with center:
        with st.form("login_form"):
            username = st.text_input("Usuario")
            password = st.text_input("Contrasena", type="password")
            submitted = st.form_submit_button("Entrar", use_container_width=True, type="primary")
            if submitted:
                if check_credentials(username, password):
                    st.session_state.authenticated = True
                    st.session_state.username = username
                    st.rerun()
                st.error("Credenciales invalidas.")


def render_header():
    left, right = st.columns([6, 1.35], gap="small")

    with left:
        st.markdown(
            """
            <div class="hero">
                <div class="hero-kicker">Montse</div>
                <h1>Reportes</h1>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with right:
        st.markdown(f"<div class='account-chip'>{st.session_state.username}</div>", unsafe_allow_html=True)
        if st.button("Salir", key="logout", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.username = ""
            reset_single()
            reset_bundle()
            st.rerun()


def render_mode_selector():
    cols = st.columns(len(MODES), gap="small")
    active_mode = st.session_state.active_mode

    for col, mode in zip(cols, MODES):
        with col:
            if st.button(
                mode["label"],
                key=f"nav_{mode['key']}",
                type="primary" if mode["key"] == active_mode else "secondary",
                use_container_width=True,
            ):
                activate_mode(mode["key"])
                st.rerun()


def format_bytes(size):
    value = float(size)
    for unit in ["B", "KB", "MB", "GB"]:
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def calculate_quality_score(df, report_type):
    if df.empty:
        return 0

    report_config = config.get_report_config(report_type)
    if not report_config:
        return 0

    required_cols = [column["name"] for column in report_config.get("columns", []) if column.get("required")]
    total_checks = 0
    passed_checks = 0

    for column in required_cols:
        total_checks += 1
        if column in df.columns:
            passed_checks += 1

    for column in required_cols:
        if column in df.columns:
            total_checks += 1
            null_ratio = df[column].isnull().mean()
            if null_ratio < 0.05:
                passed_checks += 1
            elif null_ratio < 0.2:
                passed_checks += 0.5

    total_checks += 1
    duplicate_ratio = df.duplicated().mean()
    if duplicate_ratio < 0.01:
        passed_checks += 1
    elif duplicate_ratio < 0.1:
        passed_checks += 0.5

    return round((passed_checks / total_checks) * 100) if total_checks else 0


def render_file_list(files):
    if not files:
        return

    rows = "".join(
        f"<div class='file-pill'><span>{file.name}</span><span>{format_bytes(file.size)}</span></div>" for file in files
    )
    st.markdown(f"<div class='file-list'>{rows}</div>", unsafe_allow_html=True)


def render_messages(messages):
    for message in messages:
        lowered = message.lower()
        if "plantilla de salida" in lowered:
            st.info(message)
        else:
            st.warning(message)


def render_metrics_block(df, report_key):
    metrics = {
        "Registros": len(df),
        "Columnas": len(df.columns),
        "Calidad": f"{calculate_quality_score(df, report_key)}%",
    }
    metrics.update(st.session_state.kpis)

    cols = st.columns(min(len(metrics), 4), gap="small")
    for col, (label, value) in zip(cols, metrics.items()):
        col.metric(label, f"{value:,.2f}" if isinstance(value, float) else str(value))


def render_preview(df, key_prefix):
    tabs = st.tabs(["Resumen", "Datos"])
    text_cols = df.select_dtypes(include=["object"]).columns.tolist()

    with tabs[0]:
        if text_cols:
            st.markdown("<div class='field-label'>Vista por</div>", unsafe_allow_html=True)
            chart_col = st.selectbox(
                "Vista por",
                text_cols,
                key=f"{key_prefix}_chart",
                label_visibility="collapsed",
            )
            counts = df[chart_col].replace("", "Sin dato").value_counts().reset_index()
            counts.columns = [chart_col, "Cantidad"]
            fig = px.bar(counts.head(12), x=chart_col, y="Cantidad")
            fig.update_traces(marker_color="#183650", marker_line_color="#183650")
            fig.update_layout(
                margin=dict(l=0, r=0, t=10, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                xaxis_title=None,
                yaxis_title=None,
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.caption("Sin vista disponible.")

    with tabs[1]:
        search = st.text_input(
            "Buscar",
            key=f"{key_prefix}_search",
            placeholder="Filtrar...",
            label_visibility="collapsed",
        )
        display_df = df
        if search:
            mask = df.apply(lambda row: row.astype(str).str.contains(search, case=False, na=False).any(), axis=1)
            display_df = df.loc[mask]
        st.dataframe(display_df, use_container_width=True, hide_index=True, height=420)


def build_report_file(df, report_key, label):
    output = filler.fill_template(df, config.get_report_config(report_key))
    st.session_state.download_bytes = output.getvalue()
    st.session_state.download_name = f"{label}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"


def process_single(files, mode):
    reset_single()
    report_key = mode["report_key"]
    raw_df, messages = loader.load_and_validate(files, report_key)
    st.session_state.messages = messages
    if raw_df.empty:
        return

    processed_df = processor.process_data(raw_df, report_key)
    st.session_state.processed_df = processed_df
    st.session_state.kpis = KPIEngine.calculate(processed_df, report_key)
    build_report_file(processed_df, report_key, mode["label"])


def render_single_flow():
    mode = get_mode()
    report_cfg = get_report_config()
    allowed_extensions = [ext.lstrip(".") for ext in report_cfg.get("input_extensions", [".xlsx", ".xls"])]

    st.markdown(f"<h2 class='section-title'>{mode['label']}</h2>", unsafe_allow_html=True)
    files = st.file_uploader(
        "Archivos",
        type=allowed_extensions,
        accept_multiple_files=True,
        key=f"uploader_{mode['key']}",
        label_visibility="collapsed",
    )
    render_file_list(files)

    if st.button("Generar reporte", key=f"generate_{mode['key']}", type="primary", use_container_width=True):
        if not files:
            reset_single()
            st.session_state.messages = ["Carga al menos un archivo."]
        else:
            with st.spinner("Generando..."):
                process_single(files, mode)

    if st.session_state.messages:
        render_messages(st.session_state.messages)

    if st.session_state.download_bytes:
        st.download_button(
            "Descargar reporte",
            data=st.session_state.download_bytes,
            file_name=st.session_state.download_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    if st.session_state.processed_df is not None and not st.session_state.processed_df.empty:
        render_metrics_block(st.session_state.processed_df, mode["report_key"])
        render_preview(st.session_state.processed_df, mode["key"])


def build_bundle_file(datasets):
    output = filler.fill_combined_report(datasets, config)
    st.session_state.bundle_download = output.getvalue()
    st.session_state.bundle_download_name = f"Reporte_Conjunto_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"


def process_bundle(emision_files, vencimiento_files, cotizacion_files):
    reset_bundle()
    results = {}
    messages = []

    if emision_files:
        raw_df, issues = loader.load_and_validate(emision_files, "emision_mensual")
        messages.extend([f"Emisiones: {item}" for item in issues])
        if not raw_df.empty:
            results["emision_mensual"] = processor.process_data(raw_df, "emision_mensual")

    if vencimiento_files:
        raw_df, issues = loader.load_and_validate(vencimiento_files, "vencimientos")
        messages.extend([f"Vencimientos: {item}" for item in issues])
        if not raw_df.empty:
            results["vencimientos"] = processor.process_data(raw_df, "vencimientos")
            results["renovaciones"] = processor.process_data(raw_df, "renovaciones")

    if cotizacion_files:
        raw_df, issues = loader.load_and_validate(cotizacion_files, "cotizaciones")
        messages.extend([f"Cotizaciones: {item}" for item in issues])
        if not raw_df.empty:
            results["cotizaciones"] = processor.process_data(raw_df, "cotizaciones")

    st.session_state.bundle_results = results
    st.session_state.bundle_messages = messages
    if results:
        build_bundle_file(results)


def render_bundle():
    st.markdown("<h2 class='section-title'>Conjunto</h2>", unsafe_allow_html=True)
    cols = st.columns(3, gap="small")

    with cols[0]:
        st.markdown("<div class='bucket-title'>Emisiones</div>", unsafe_allow_html=True)
        emision_files = st.file_uploader(
            "Emisiones",
            type=["xlsx", "xls"],
            accept_multiple_files=True,
            key="bundle_em",
            label_visibility="collapsed",
        )
        render_file_list(emision_files)

    with cols[1]:
        st.markdown("<div class='bucket-title'>Vencimientos</div>", unsafe_allow_html=True)
        vencimiento_files = st.file_uploader(
            "Vencimientos",
            type=["xlsx", "xls"],
            accept_multiple_files=True,
            key="bundle_ven",
            label_visibility="collapsed",
        )
        render_file_list(vencimiento_files)

    with cols[2]:
        st.markdown("<div class='bucket-title'>Cotizaciones</div>", unsafe_allow_html=True)
        cotizacion_files = st.file_uploader(
            "Cotizaciones",
            type=["pdf"],
            accept_multiple_files=True,
            key="bundle_cot",
            label_visibility="collapsed",
        )
        render_file_list(cotizacion_files)

    if st.button("Generar conjunto", key="generate_bundle", type="primary", use_container_width=True):
        if not any([emision_files, vencimiento_files, cotizacion_files]):
            reset_bundle()
            st.session_state.bundle_messages = ["Carga al menos un archivo."]
        else:
            with st.spinner("Generando..."):
                process_bundle(emision_files or [], vencimiento_files or [], cotizacion_files or [])

    if st.session_state.bundle_messages:
        render_messages(st.session_state.bundle_messages)

    if st.session_state.bundle_download:
        st.download_button(
            "Descargar conjunto",
            data=st.session_state.bundle_download,
            file_name=st.session_state.bundle_download_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    if st.session_state.bundle_results:
        summary = {
            config.get_report_config(report_key)["name"]: len(df)
            for report_key, df in st.session_state.bundle_results.items()
        }
        cols = st.columns(len(summary), gap="small")
        for col, (label, value) in zip(cols, summary.items()):
            col.metric(label, value)

        tabs = st.tabs(list(summary.keys()))
        for tab, (report_key, df) in zip(tabs, st.session_state.bundle_results.items()):
            with tab:
                render_preview(df, f"bundle_{report_key}")


st.set_page_config(page_title="Montse Reportes", layout="wide", initial_sidebar_state="collapsed")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Manrope', sans-serif;
    }

    .stApp {
        background:
            radial-gradient(circle at top left, rgba(255,255,255,0.96), rgba(255,255,255,0) 36%),
            linear-gradient(180deg, #f4f7fa 0%, #ebf0f5 100%);
        color: #152334;
    }

    .block-container {
        max-width: 1240px;
        padding-top: 2rem;
        padding-bottom: 2.4rem;
    }

    .hero,
    .login-brand {
        margin-bottom: 1rem;
    }

    .hero-kicker,
    .login-kicker {
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        color: #637487;
    }

    .hero h1,
    .login-brand h1 {
        margin: 0.15rem 0 0 0;
        font-size: 2.45rem;
        line-height: 1;
        letter-spacing: -0.05em;
        color: #17324d;
    }

    .login-brand {
        text-align: center;
        margin-top: 5rem;
    }

    .account-chip {
        display: flex;
        align-items: center;
        justify-content: center;
        min-height: 2.8rem;
        margin-top: 0.55rem;
        margin-bottom: 0.5rem;
        border: 1px solid rgba(23, 50, 77, 0.12);
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.74);
        color: #17324d;
        font-size: 0.92rem;
        font-weight: 600;
    }

    .section-title {
        margin: 1.5rem 0 0.85rem 0;
        font-size: 1.4rem;
        letter-spacing: -0.04em;
        color: #17324d;
    }

    .bucket-title,
    .field-label {
        margin-bottom: 0.4rem;
        font-size: 0.84rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: #6a7b8d;
    }

    .file-list {
        display: grid;
        gap: 0.5rem;
        margin: 0.9rem 0 1rem 0;
    }

    .file-pill {
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        padding: 0.78rem 0.95rem;
        border: 1px solid rgba(23, 50, 77, 0.1);
        border-radius: 18px;
        background: rgba(255, 255, 255, 0.72);
        font-size: 0.9rem;
        color: #17324d;
    }

    div[data-testid="stFileUploaderDropzone"] {
        border: 1px dashed rgba(23, 50, 77, 0.22);
        border-radius: 22px;
        background: rgba(255, 255, 255, 0.72);
        padding: 0.9rem;
    }

    div[data-testid="stFileUploaderDropzone"] button,
    div[data-testid="stDownloadButton"] button,
    div[data-testid="stButton"] button {
        border-radius: 999px;
        min-height: 2.8rem;
        font-weight: 700;
        border: 1px solid rgba(23, 50, 77, 0.12);
    }

    div[data-testid="stButton"] button[kind="secondary"],
    div[data-testid="stDownloadButton"] button,
    div[data-testid="stFileUploaderDropzone"] button {
        background: rgba(255, 255, 255, 0.78);
        color: #17324d;
    }

    div[data-testid="stButton"] button[kind="primary"] {
        background: #17324d;
        color: #ffffff;
        border-color: #17324d;
        box-shadow: 0 14px 32px rgba(23, 50, 77, 0.16);
    }

    div[data-testid="stMetric"] {
        border: 1px solid rgba(23, 50, 77, 0.1);
        border-radius: 22px;
        background: rgba(255, 255, 255, 0.78);
        padding: 0.35rem 0.55rem;
    }

    div[data-testid="stTabs"] button {
        border-radius: 999px;
    }

    div[data-testid="stDataFrame"] {
        border-radius: 18px;
        overflow: hidden;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

initialize_state()

if not st.session_state.authenticated:
    render_login()
    st.stop()

render_header()
render_mode_selector()

if get_mode()["key"] == "conjunto":
    render_bundle()
else:
    render_single_flow()
