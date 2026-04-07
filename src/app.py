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
from src.user_store import UserStore


setup_logging()
config = ConfigLoader()
loader = ExcelLoader(config)
processor = ReportProcessor(config)
filler = TemplateFiller()
user_store = UserStore()


REPORT_MODES = [
    {"key": "emisiones", "label": "Emisiones", "report_key": "emision_mensual"},
    {"key": "renovaciones", "label": "Renovaciones", "report_key": "renovaciones"},
    {"key": "cotizaciones", "label": "Cotizaciones", "report_key": "cotizaciones"},
]
ADMIN_MODE = {"key": "accesos", "label": "Accesos", "report_key": None}


def available_modes():
    modes = list(REPORT_MODES)
    if st.session_state.get("is_admin", False):
        modes.append(ADMIN_MODE)
    return modes


def get_mode(mode_key=None):
    mode_map = {mode["key"]: mode for mode in available_modes()}
    key = mode_key or st.session_state.get("active_mode", REPORT_MODES[0]["key"])
    if key not in mode_map:
        key = REPORT_MODES[0]["key"]
    return mode_map[key]


def get_report_config(mode_key=None):
    mode = get_mode(mode_key)
    return config.get_report_config(mode["report_key"]) if mode["report_key"] else None


def initialize_state():
    defaults = {
        "authenticated": False,
        "username": "",
        "is_admin": False,
        "active_mode": "emisiones",
        "processed_df": None,
        "messages": [],
        "kpis": {},
        "download_bytes": None,
        "download_name": "",
        "access_feedback": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    if st.session_state.active_mode not in {mode["key"] for mode in available_modes()}:
        st.session_state.active_mode = REPORT_MODES[0]["key"]


def reset_single():
    st.session_state.processed_df = None
    st.session_state.messages = []
    st.session_state.kpis = {}
    st.session_state.download_bytes = None
    st.session_state.download_name = ""


def activate_mode(mode_key):
    if st.session_state.active_mode != mode_key:
        st.session_state.active_mode = mode_key
        reset_single()


def authenticate_user(username: str, password: str):
    return user_store.authenticate(username, password)


def set_access_feedback(kind: str, message: str):
    st.session_state.access_feedback = {"kind": kind, "message": message}


def render_login():
    st.markdown(
        """
        <div class="login-shell">
            <h1>Reportes</h1>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left, center, right = st.columns([1.35, 1, 1.35])
    with center:
        with st.form("login_form"):
            username = st.text_input("Usuario")
            password = st.text_input("Contrasena", type="password")
            submitted = st.form_submit_button("Entrar", use_container_width=True, type="primary")
            if submitted:
                user = authenticate_user(username, password)
                if user:
                    st.session_state.authenticated = True
                    st.session_state.username = user["username"]
                    st.session_state.is_admin = user["is_admin"]
                    st.session_state.active_mode = "accesos" if user["is_admin"] else "emisiones"
                    st.rerun()
                st.error("Credenciales invalidas.")

def render_header():
    left, right = st.columns([6.3, 1.7], gap="medium")

    with left:
        st.markdown(
            """
            <div class="header-shell">
                <div class="header-accent"></div>
                <div class="header-copy">
                    <h1>Reportes</h1>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with right:
        st.markdown(
            f"""
            <div class="account-shell">
                <div class="account-name">{st.session_state.username}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Salir", use_container_width=True, key="logout"):
            st.session_state.authenticated = False
            st.session_state.username = ""
            st.session_state.is_admin = False
            st.session_state.active_mode = "emisiones"
            reset_single()
            st.rerun()


def render_mode_selector():
    modes = available_modes()
    cols = st.columns(len(modes), gap="small")
    active_key = st.session_state.active_mode

    for col, mode in zip(cols, modes):
        with col:
            if st.button(
                mode["label"],
                key=f"nav_{mode['key']}",
                type="primary" if mode["key"] == active_key else "secondary",
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


def render_section_heading(title: str, subtitle: str):
    st.markdown(
        f"""
        <div class="section-shell">
            <div class="section-title">{title}</div>
            <div class="section-subtitle">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_file_list(files):
    if not files:
        return

    rows = "".join(
        f"<div class='file-pill'><span>{file.name}</span><span>{format_bytes(file.size)}</span></div>" for file in files
    )
    st.markdown(f"<div class='file-list'>{rows}</div>", unsafe_allow_html=True)


def render_template_status(report_cfg, template_file):
    if template_file is not None:
        st.markdown(f"<div class='template-chip'>Plantilla cargada: {template_file.name}</div>", unsafe_allow_html=True)
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
            fig = px.bar(counts.head(12), x=chart_col, y="Cantidad", color_discrete_sequence=["#c1121f"])
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

    render_section_heading(mode["label"], "Carga el archivo fuente, aplica la plantilla y descarga el resultado final.")

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


def render_access_panel():
    if not st.session_state.is_admin:
        st.warning("No tienes permisos para gestionar cuentas.")
        return

    render_section_heading("Accesos", "Crea cuentas y consulta los accesos disponibles.")

    feedback = st.session_state.get("access_feedback")
    if feedback:
        if feedback["kind"] == "success":
            st.success(feedback["message"])
        else:
            st.error(feedback["message"])

    summary_col1, summary_col2, summary_col3 = st.columns(3, gap="small")
    users = user_store.list_users()
    summary_col1.metric("Usuarios", len(users))
    summary_col2.metric("Activos", sum(1 for user in users if user["active"]))
    summary_col3.metric("Control total", sum(1 for user in users if user["is_admin"]))

    create_col, list_col = st.columns([1, 1.25], gap="large")

    with create_col:
        st.markdown(
            """
            <div class="admin-note">
                <div class="admin-note-title">Alta de cuenta</div>
                <div class="admin-note-copy">Define el usuario y una contrasena temporal para habilitar un nuevo acceso.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("create_user_form", clear_on_submit=True):
            username = st.text_input("Nuevo usuario")
            password = st.text_input("Contrasena temporal", type="password")
            confirm = st.text_input("Confirmar contrasena", type="password")
            submitted = st.form_submit_button("Crear cuenta", use_container_width=True, type="primary")
            if submitted:
                if password != confirm:
                    set_access_feedback("error", "Las contrasenas no coinciden.")
                else:
                    try:
                        created = user_store.create_user(username, password, created_by=st.session_state.username)
                        set_access_feedback("success", f"Cuenta creada: {created['username']}")
                    except ValueError as exc:
                        set_access_feedback("error", str(exc))
                st.rerun()

    with list_col:
        table = pd.DataFrame(users)
        if not table.empty:
            table["rol"] = table["is_admin"].map(lambda value: "Control total" if value else "Operativo")
            table["estado"] = table["active"].map(lambda value: "Activo" if value else "Inactivo")
            table["creado"] = (
                pd.to_datetime(table["created_at"], errors="coerce")
                .dt.tz_convert(None)
                .dt.strftime("%d/%m/%Y %H:%M")
                .fillna("")
            )
            table["creado_por"] = table["created_by"].fillna("").replace("", "system")
            view = table[["username", "rol", "estado", "creado_por", "creado"]].rename(
                columns={
                    "username": "Usuario",
                    "rol": "Rol",
                    "estado": "Estado",
                    "creado_por": "Creado por",
                    "creado": "Alta",
                }
            )
            st.dataframe(view, use_container_width=True, hide_index=True, height=360)


st.set_page_config(page_title="Montse Reportes", layout="wide", initial_sidebar_state="collapsed")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');

    :root {
        --bg: #ffffff;
        --surface: rgba(255,255,255,0.78);
        --surface-soft: rgba(255,255,255,0.62);
        --surface-strong: rgba(255,255,255,0.92);
        --ink: #121826;
        --muted: #6b7280;
        --line: rgba(15, 23, 42, 0.11);
        --accent: #c1121f;
        --accent-deep: #9f1239;
        --shadow: 0 18px 40px rgba(15, 23, 42, 0.08);
        --glass-shadow: 0 24px 50px rgba(15, 23, 42, 0.09);
    }

    html, body, [class*="css"] {
        font-family: 'IBM Plex Sans', sans-serif;
    }

    .stApp {
        background:
            radial-gradient(circle at top right, rgba(193,18,31,0.06), rgba(193,18,31,0) 28%),
            linear-gradient(180deg, #ffffff 0%, #fbfbfc 100%);
        color: var(--ink);
    }

    .stApp::before {
        content: "";
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        height: 4px;
        background: linear-gradient(90deg, var(--accent) 0%, #ef4444 65%, var(--accent-deep) 100%);
        z-index: 9999;
    }

    .block-container {
        max-width: 1220px;
        padding-top: 2.4rem;
        padding-bottom: 2.8rem;
    }

    @keyframes revealUp {
        from {
            opacity: 0;
            transform: translateY(18px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    @keyframes pulseLine {
        0% {
            transform: scaleY(0.9);
            opacity: 0.78;
        }
        100% {
            transform: scaleY(1.08);
            opacity: 1;
        }
    }

    .login-shell {
        text-align: center;
        margin-top: 5rem;
        margin-bottom: 1.4rem;
        animation: revealUp 520ms ease both;
    }

    .login-shell h1,
    .header-copy h1 {
        margin: 0.15rem 0 0 0;
        font-family: 'Space Grotesk', sans-serif;
        font-size: 2.45rem;
        line-height: 1.02;
        letter-spacing: -0.05em;
        color: var(--ink);
    }

    .header-shell {
        display: flex;
        align-items: center;
        gap: 1rem;
        min-height: 5.3rem;
        padding: 1rem 1.15rem;
        border: 1px solid var(--line);
        border-radius: 26px;
        background: linear-gradient(180deg, rgba(255,255,255,0.9) 0%, rgba(255,255,255,0.72) 100%);
        backdrop-filter: blur(18px);
        -webkit-backdrop-filter: blur(18px);
        box-shadow: var(--glass-shadow);
        animation: revealUp 480ms ease both;
    }

    .header-accent {
        width: 6px;
        height: 56px;
        border-radius: 999px;
        background: linear-gradient(180deg, var(--accent) 0%, var(--accent-deep) 100%);
        animation: pulseLine 1600ms ease-in-out infinite alternate;
    }

    .header-copy {
        display: grid;
        gap: 0.1rem;
    }

    .account-shell {
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 0.95rem 1rem;
        margin-top: 0.15rem;
        margin-bottom: 0.55rem;
        border: 1px solid var(--line);
        border-radius: 22px;
        background: linear-gradient(180deg, rgba(255,255,255,0.92) 0%, rgba(255,255,255,0.7) 100%);
        backdrop-filter: blur(18px);
        -webkit-backdrop-filter: blur(18px);
        box-shadow: var(--shadow);
        animation: revealUp 560ms ease both;
    }

    .account-name {
        font-size: 0.96rem;
        font-weight: 700;
        color: var(--ink);
    }

    .section-shell {
        margin: 1.75rem 0 0.95rem 0;
        animation: revealUp 620ms ease both;
    }

    .section-title {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 1.5rem;
        font-weight: 700;
        letter-spacing: -0.04em;
        color: var(--ink);
    }

    .section-subtitle {
        margin-top: 0.28rem;
        font-size: 0.94rem;
        color: var(--muted);
    }

    .panel-label {
        margin-bottom: 0.55rem;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: var(--muted);
    }

    .admin-note {
        margin-bottom: 0.9rem;
        padding: 1rem 1.05rem;
        border: 1px solid rgba(193,18,31,0.14);
        border-radius: 22px;
        background: linear-gradient(180deg, rgba(255,255,255,0.9) 0%, rgba(255,247,248,0.76) 100%);
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        box-shadow: var(--shadow);
    }

    .admin-note-title {
        font-size: 0.95rem;
        font-weight: 700;
        color: var(--ink);
    }

    .admin-note-copy {
        margin-top: 0.35rem;
        font-size: 0.9rem;
        color: var(--muted);
        line-height: 1.5;
    }

    .file-list {
        display: grid;
        gap: 0.5rem;
        margin-top: 0.9rem;
        animation: revealUp 700ms ease both;
    }

    .file-pill,
    .template-chip {
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        padding: 0.88rem 1rem;
        border-radius: 18px;
        border: 1px solid var(--line);
        background: linear-gradient(180deg, rgba(255,255,255,0.84) 0%, rgba(255,255,255,0.68) 100%);
        backdrop-filter: blur(18px);
        -webkit-backdrop-filter: blur(18px);
        color: var(--ink);
        font-size: 0.9rem;
        box-shadow: var(--shadow);
    }

    .template-chip {
        margin-top: 0.9rem;
    }

    .template-chip.muted {
        color: var(--muted);
    }

    div[data-testid="stFileUploaderDropzone"] {
        border-radius: 22px;
        border: 1px dashed rgba(15, 23, 42, 0.14);
        background: linear-gradient(180deg, rgba(255,255,255,0.9) 0%, rgba(255,255,255,0.7) 100%);
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        padding: 1.15rem;
        box-shadow: var(--shadow);
    }

    div[data-baseweb="input"] > div,
    div[data-baseweb="base-input"] {
        border-radius: 18px !important;
        border: 1px solid rgba(193, 18, 31, 0.26) !important;
        background: linear-gradient(180deg, rgba(255,244,245,0.95) 0%, rgba(255,236,239,0.86) 100%) !important;
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        box-shadow: var(--shadow);
    }

    div[data-baseweb="input"] input,
    div[data-baseweb="base-input"] input {
        color: var(--ink) !important;
        font-weight: 600;
    }

    div[data-baseweb="input"] input::placeholder,
    div[data-baseweb="base-input"] input::placeholder {
        color: rgba(159, 18, 57, 0.55) !important;
    }

    div[data-baseweb="input"]:focus-within > div,
    div[data-baseweb="base-input"]:focus-within {
        border-color: rgba(193, 18, 31, 0.65) !important;
        box-shadow: 0 0 0 4px rgba(193, 18, 31, 0.10), 0 18px 38px rgba(15, 23, 42, 0.1) !important;
    }

    div[data-testid="stButton"] button,
    div[data-testid="stDownloadButton"] button,
    div[data-testid="stFileUploaderDropzone"] button,
    div[data-testid="stFormSubmitButton"] button {
        min-height: 3rem;
        border-radius: 16px;
        font-weight: 700;
        border: 1px solid var(--line);
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        transition: transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease;
    }

    div[data-testid="stButton"] button[kind="primary"],
    div[data-testid="stFormSubmitButton"] button[kind="primary"] {
        background: linear-gradient(180deg, rgba(193,18,31,0.95) 0%, rgba(159,18,57,0.95) 100%);
        border-color: rgba(193,18,31,0.7);
        color: #ffffff;
        box-shadow: 0 18px 35px rgba(193,18,31,0.18);
    }

    div[data-testid="stButton"] button[kind="secondary"],
    div[data-testid="stDownloadButton"] button,
    div[data-testid="stFileUploaderDropzone"] button {
        background: linear-gradient(180deg, rgba(255,255,255,0.9) 0%, rgba(255,255,255,0.72) 100%);
        color: var(--ink);
        box-shadow: var(--shadow);
    }

    div[data-testid="stButton"] button:hover,
    div[data-testid="stDownloadButton"] button:hover,
    div[data-testid="stFileUploaderDropzone"] button:hover,
    div[data-testid="stFormSubmitButton"] button:hover {
        transform: translateY(-1px);
        box-shadow: 0 22px 44px rgba(15, 23, 42, 0.12);
    }

    div[data-testid="stMetric"] {
        border-radius: 20px;
        border: 1px solid var(--line);
        background: linear-gradient(180deg, rgba(255,255,255,0.92) 0%, rgba(255,255,255,0.75) 100%);
        backdrop-filter: blur(18px);
        -webkit-backdrop-filter: blur(18px);
        padding: 0.4rem 0.6rem;
        box-shadow: var(--shadow);
    }

    div[data-testid="stForm"] {
        padding: 0.2rem 0 0 0;
    }

    div[data-testid="stTabs"] button {
        border-radius: 14px;
    }

    div[data-testid="stAlert"] {
        border-radius: 18px;
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
    }

    div[data-testid="stDataFrame"] {
        border-radius: 18px;
        overflow: hidden;
        border: 1px solid var(--line);
        box-shadow: var(--shadow);
    }

    @media (max-width: 960px) {
        .header-copy h1,
        .login-shell h1 {
            font-size: 2rem;
        }

        .header-shell {
            min-height: auto;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

initialize_state()

if not st.session_state.authenticated:
    st.markdown(
        """
        <style>
        .login-shell {
            margin-bottom: 1.2rem;
        }

        div[data-testid="stForm"] {
            padding: 1.35rem 1.25rem 1.1rem 1.25rem;
            border-radius: 26px;
            border: 1px solid rgba(193, 18, 31, 0.18);
            background: linear-gradient(180deg, #c1121f 0%, #a50f1a 100%);
            box-shadow: 0 28px 60px rgba(193, 18, 31, 0.22);
        }

        div[data-testid="stForm"] label p,
        div[data-testid="stForm"] label span {
            color: #ffffff !important;
            font-weight: 600 !important;
        }

        div[data-testid="stForm"] div[data-baseweb="input"] > div,
        div[data-testid="stForm"] div[data-baseweb="base-input"] {
            border-radius: 16px !important;
            border: 1px solid rgba(255, 255, 255, 0.55) !important;
            background: #ffffff !important;
            box-shadow: none !important;
        }

        div[data-testid="stForm"] div[data-baseweb="input"] input,
        div[data-testid="stForm"] div[data-baseweb="base-input"] input {
            color: #111827 !important;
            font-weight: 600;
        }

        div[data-testid="stForm"] div[data-baseweb="input"]:focus-within > div,
        div[data-testid="stForm"] div[data-baseweb="base-input"]:focus-within {
            border-color: rgba(255, 255, 255, 0.95) !important;
            box-shadow: 0 0 0 4px rgba(255, 255, 255, 0.16) !important;
        }

        div[data-testid="stForm"] div[data-testid="stFormSubmitButton"] button[kind="primary"] {
            background: #ffffff;
            border-color: #ffffff;
            color: #9f1239;
            box-shadow: 0 16px 36px rgba(17, 24, 39, 0.14);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    render_login()
    st.stop()

render_header()
render_mode_selector()

if get_mode()["key"] == "accesos":
    render_access_panel()
else:
    render_single_flow()
