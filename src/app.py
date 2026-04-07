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
LABEL_TO_KEY = {mode["label"]: mode["key"] for mode in MODES}


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
        <div class="login-shell">
            <div class="eyebrow">Montse</div>
            <h1>Reportes</h1>
        </div>
        """,
        unsafe_allow_html=True,
    )
    left, center, right = st.columns([1.4, 1, 1.4])
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
    left, right = st.columns([7, 1.4], gap="small")
    with left:
        st.markdown(
            """
            <div class="hero-shell">
                <div class="eyebrow">Montse</div>
                <h1>Reportes</h1>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(f"<div class='user-chip'>{st.session_state.username}</div>", unsafe_allow_html=True)
        if st.button("Salir", use_container_width=True, key="logout"):
            st.session_state.authenticated = False
            st.session_state.username = ""
            reset_single()
            reset_bundle()
            st.rerun()


def render_mode_selector():
    selected = st.segmented_control(
        "Modulo",
        options=[mode["label"] for mode in MODES],
        default=get_mode()["label"],
        selection_mode="single",
        label_visibility="collapsed",
    )
    selected_key = LABEL_TO_KEY.get(selected, st.session_state.active_mode)
    if selected_key != st.session_state.active_mode:
        activate_mode(selected_key)
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


def render_section_heading(title, caption=None):
    st.markdown(f"<div class='section-title'>{title}</div>", unsafe_allow_html=True)
    if caption:
        st.caption(caption)


def render_file_list(files):
    if not files:
        return

    rows = "".join(
        f"<div class='file-pill'><span>{file.name}</span><span>{format_bytes(file.size)}</span></div>" for file in files
    )
    st.markdown(f"<div class='file-list'>{rows}</div>", unsafe_allow_html=True)


def render_template_status(report_cfg, template_file):
    if template_file is not None:
        st.markdown(
            f"<div class='template-chip'>Plantilla: {template_file.name}</div>",
            unsafe_allow_html=True,
        )
        return

    default_name = os.path.basename(report_cfg.get("template_path", "plantilla interna"))
    st.markdown(
        f"<div class='template-chip muted'>Plantilla interna: {default_name}</div>",
        unsafe_allow_html=True,
    )


def render_messages(messages):
    for message in messages:
        lowered = message.lower()
        if "plantilla destino" in lowered:
            st.info(message)
        elif "carga al menos un archivo" in lowered or "falta el archivo fuente" in lowered:
            st.warning(message)
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
            chart_col = st.selectbox(
                "Agrupar por",
                text_cols,
                key=f"{key_prefix}_chart",
                label_visibility="collapsed",
            )
            counts = df[chart_col].replace("", "Sin dato").value_counts().reset_index()
            counts.columns = [chart_col, "Cantidad"]
            fig = px.bar(counts.head(12), x=chart_col, y="Cantidad", color_discrete_sequence=["#15324a"])
            fig.update_layout(
                margin=dict(l=0, r=0, t=10, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                xaxis_title=None,
                yaxis_title=None,
                showlegend=False,
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


def build_report_file(df, report_key, label, template_file=None):
    output = filler.fill_template(
        df,
        config.get_report_config(report_key),
        report_key=report_key,
        template_bytes=template_file.getvalue() if template_file is not None else None,
    )
    st.session_state.download_bytes = output.getvalue()
    st.session_state.download_name = f"{label}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"


def process_single(files, mode, template_file=None):
    reset_single()
    report_key = mode["report_key"]
    raw_df, messages = loader.load_and_validate(files, report_key)
    st.session_state.messages = messages
    if raw_df.empty:
        return

    processed_df = processor.process_data(raw_df, report_key)
    st.session_state.processed_df = processed_df
    st.session_state.kpis = KPIEngine.calculate(processed_df, report_key)
    build_report_file(processed_df, report_key, mode["label"], template_file=template_file)


def render_single_flow():
    mode = get_mode()
    report_cfg = get_report_config()
    source_types = [ext.lstrip(".") for ext in report_cfg.get("input_extensions", [".xlsx", ".xls"])]

    render_section_heading(mode["label"])
    source_col, template_col = st.columns([1.8, 1], gap="large")

    with source_col:
        st.markdown("<div class='panel-label'>Fuente</div>", unsafe_allow_html=True)
        files = st.file_uploader(
            "Fuente",
            type=source_types,
            accept_multiple_files=True,
            key=f"source_{mode['key']}",
            label_visibility="collapsed",
        )
        render_file_list(files)

    with template_col:
        st.markdown("<div class='panel-label'>Plantilla</div>", unsafe_allow_html=True)
        template_file = st.file_uploader(
            "Plantilla",
            type=["xlsx", "xlsm", "xls"],
            accept_multiple_files=False,
            key=f"template_{mode['key']}",
            label_visibility="collapsed",
        )
        render_template_status(report_cfg, template_file)

    action_col, download_col = st.columns([1.2, 1], gap="small")
    with action_col:
        if st.button("Generar reporte", key=f"generate_{mode['key']}", type="primary", use_container_width=True):
            if not files:
                reset_single()
                st.session_state.messages = ["Falta el archivo fuente."]
            else:
                with st.spinner("Generando..."):
                    process_single(files, mode, template_file=template_file)
    with download_col:
        if st.session_state.download_bytes:
            st.download_button(
                "Descargar",
                data=st.session_state.download_bytes,
                file_name=st.session_state.download_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

    if st.session_state.messages:
        render_messages(st.session_state.messages)

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
    render_section_heading("Conjunto")
    cols = st.columns(3, gap="large")
    labels = [
        ("Emisiones", ["xlsx", "xls"], "bundle_em"),
        ("Vencimientos", ["xlsx", "xls"], "bundle_ven"),
        ("Cotizaciones", ["pdf"], "bundle_cot"),
    ]
    uploaded = {}

    for col, (label, file_types, key) in zip(cols, labels):
        with col:
            st.markdown(f"<div class='panel-label'>{label}</div>", unsafe_allow_html=True)
            uploaded[key] = st.file_uploader(
                label,
                type=file_types,
                accept_multiple_files=True,
                key=key,
                label_visibility="collapsed",
            )
            render_file_list(uploaded[key])

    action_col, download_col = st.columns([1.2, 1], gap="small")
    with action_col:
        if st.button("Generar conjunto", key="generate_bundle", type="primary", use_container_width=True):
            if not any(uploaded.values()):
                reset_bundle()
                st.session_state.bundle_messages = ["Falta al menos un archivo fuente."]
            else:
                with st.spinner("Generando..."):
                    process_bundle(
                        uploaded["bundle_em"] or [],
                        uploaded["bundle_ven"] or [],
                        uploaded["bundle_cot"] or [],
                    )
    with download_col:
        if st.session_state.bundle_download:
            st.download_button(
                "Descargar",
                data=st.session_state.bundle_download,
                file_name=st.session_state.bundle_download_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

    if st.session_state.bundle_messages:
        render_messages(st.session_state.bundle_messages)

    if st.session_state.bundle_results:
        summary = {
            config.get_report_config(report_key)["name"]: len(df)
            for report_key, df in st.session_state.bundle_results.items()
        }
        metric_cols = st.columns(len(summary), gap="small")
        for col, (label, value) in zip(metric_cols, summary.items()):
            col.metric(label, value)

        tabs = st.tabs(list(summary.keys()))
        for tab, (report_key, df) in zip(tabs, st.session_state.bundle_results.items()):
            with tab:
                render_preview(df, f"bundle_{report_key}")


st.set_page_config(page_title="Montse Reportes", layout="wide", initial_sidebar_state="collapsed")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,700&family=Manrope:wght@400;500;600;700;800&display=swap');

    :root {
        --bg-top: #f8f4ee;
        --bg-bottom: #eef2f5;
        --surface: rgba(255,255,255,0.72);
        --surface-strong: rgba(255,255,255,0.88);
        --ink: #15324a;
        --muted: #6f7b86;
        --line: rgba(21, 50, 74, 0.12);
        --accent: #c7a574;
    }

    html, body, [class*="css"] {
        font-family: 'Manrope', sans-serif;
    }

    .stApp {
        background:
            radial-gradient(circle at top left, rgba(255,255,255,0.92), rgba(255,255,255,0) 33%),
            linear-gradient(180deg, var(--bg-top) 0%, var(--bg-bottom) 100%);
        color: var(--ink);
    }

    .block-container {
        max-width: 1240px;
        padding-top: 2rem;
        padding-bottom: 2.6rem;
    }

    .login-shell,
    .hero-shell {
        margin-bottom: 1rem;
    }

    .login-shell {
        text-align: center;
        margin-top: 4.4rem;
    }

    .eyebrow {
        font-size: 0.78rem;
        font-weight: 800;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        color: var(--muted);
    }

    .login-shell h1,
    .hero-shell h1 {
        margin: 0.2rem 0 0 0;
        font-family: 'Fraunces', serif;
        font-size: 2.6rem;
        line-height: 1;
        letter-spacing: -0.04em;
        color: var(--ink);
    }

    .user-chip {
        display: flex;
        align-items: center;
        justify-content: center;
        min-height: 2.85rem;
        margin-top: 0.55rem;
        margin-bottom: 0.45rem;
        border-radius: 999px;
        border: 1px solid var(--line);
        background: var(--surface);
        color: var(--ink);
        font-size: 0.92rem;
        font-weight: 700;
    }

    .section-title {
        margin: 1.45rem 0 0.85rem 0;
        font-family: 'Fraunces', serif;
        font-size: 1.5rem;
        letter-spacing: -0.03em;
        color: var(--ink);
    }

    .panel-label {
        margin-bottom: 0.55rem;
        font-size: 0.8rem;
        font-weight: 800;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: var(--muted);
    }

    .file-list {
        display: grid;
        gap: 0.5rem;
        margin-top: 0.9rem;
    }

    .file-pill,
    .template-chip {
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        padding: 0.8rem 0.95rem;
        border-radius: 18px;
        border: 1px solid var(--line);
        background: var(--surface);
        color: var(--ink);
        font-size: 0.9rem;
    }

    .template-chip {
        margin-top: 0.9rem;
    }

    .template-chip.muted {
        color: var(--muted);
    }

    div[data-testid="stFileUploaderDropzone"] {
        border-radius: 24px;
        border: 1px dashed rgba(21, 50, 74, 0.22);
        background: var(--surface);
        padding: 1.1rem;
    }

    div[data-testid="stSegmentedControl"] {
        margin-bottom: 0.7rem;
    }

    div[data-testid="stSegmentedControl"] button {
        min-height: 2.85rem;
        border-radius: 999px;
        font-weight: 700;
    }

    div[data-testid="stButton"] button,
    div[data-testid="stDownloadButton"] button,
    div[data-testid="stFileUploaderDropzone"] button,
    div[data-testid="stFormSubmitButton"] button {
        min-height: 2.9rem;
        border-radius: 999px;
        font-weight: 700;
        border: 1px solid var(--line);
    }

    div[data-testid="stButton"] button[kind="primary"],
    div[data-testid="stFormSubmitButton"] button[kind="primary"] {
        background: var(--ink);
        border-color: var(--ink);
        color: #ffffff;
        box-shadow: 0 16px 34px rgba(21, 50, 74, 0.16);
    }

    div[data-testid="stButton"] button[kind="secondary"],
    div[data-testid="stDownloadButton"] button,
    div[data-testid="stFileUploaderDropzone"] button {
        background: var(--surface-strong);
        color: var(--ink);
    }

    div[data-testid="stMetric"] {
        border-radius: 22px;
        border: 1px solid var(--line);
        background: var(--surface-strong);
        padding: 0.35rem 0.55rem;
    }

    div[data-testid="stTabs"] button {
        border-radius: 999px;
    }

    div[data-testid="stAlert"] {
        border-radius: 18px;
    }

    div[data-testid="stDataFrame"] {
        border-radius: 20px;
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
