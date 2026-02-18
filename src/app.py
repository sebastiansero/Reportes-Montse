import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys
import os
import io
from datetime import datetime

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.config import ConfigLoader
from src.data_loader import ExcelLoader
from src.services import ReportProcessor, KPIEngine
from src.template_engine import TemplateFiller
from src.logger import setup_logging
from loguru import logger

# ── Initialize Services ──────────────────────────────────────────────
setup_logging()
config = ConfigLoader()
loader = ExcelLoader(config)
processor = ReportProcessor(config)
filler = TemplateFiller()

# ── Page Config ───────────────────────────────────────────────────────
st.set_page_config(
    page_title="Reporteador Comercial Enterprise",
    layout="wide",
    page_icon="📊",
    initial_sidebar_state="expanded"
)

# ── Custom CSS ────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

* { font-family: 'Inter', sans-serif; }

.main-title {
    font-size: 2.2rem;
    font-weight: 700;
    background: linear-gradient(135deg, #003366, #0066CC);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    text-align: center;
    margin-bottom: 0.2rem;
}
.main-subtitle {
    text-align: center;
    color: #666;
    font-size: 1rem;
    margin-bottom: 2rem;
}

/* Step indicator */
.step-container {
    display: flex;
    justify-content: center;
    gap: 0.5rem;
    margin-bottom: 2rem;
}
.step {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1.2rem;
    border-radius: 25px;
    font-size: 0.85rem;
    font-weight: 500;
}
.step-active {
    background: linear-gradient(135deg, #003366, #0066CC);
    color: white;
}
.step-done {
    background: #d4edda;
    color: #155724;
}
.step-pending {
    background: #e9ecef;
    color: #999;
}

/* File cards */
.file-card {
    background: white;
    border: 1px solid #e0e0e0;
    border-radius: 10px;
    padding: 1rem 1.2rem;
    margin-bottom: 0.5rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    transition: all 0.2s;
}
.file-card:hover {
    border-color: #0066CC;
    box-shadow: 0 2px 8px rgba(0,102,204,0.15);
}
.file-info {
    display: flex;
    align-items: center;
    gap: 0.8rem;
}
.file-icon { font-size: 1.5rem; }
.file-name { font-weight: 600; color: #333; }
.file-size { font-size: 0.8rem; color: #999; }
.file-status-ok { color: #28a745; font-weight: 600; font-size: 0.85rem; }
.file-status-err { color: #dc3545; font-weight: 600; font-size: 0.85rem; }

/* Metric cards */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem;
    margin: 1.5rem 0;
}
.kpi-card {
    background: white;
    border-radius: 12px;
    padding: 1.5rem;
    text-align: center;
    box-shadow: 0 2px 12px rgba(0,0,0,0.08);
    border-top: 4px solid #0066CC;
    transition: transform 0.2s;
}
.kpi-card:hover { transform: translateY(-4px); }
.kpi-value {
    font-size: 2rem;
    font-weight: 700;
    color: #003366;
    margin: 0.5rem 0;
}
.kpi-label {
    font-size: 0.85rem;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 1.5px;
}

/* Quality score */
.quality-bar {
    background: #e9ecef;
    border-radius: 10px;
    height: 12px;
    overflow: hidden;
    margin: 0.5rem 0;
}
.quality-fill {
    height: 100%;
    border-radius: 10px;
    transition: width 0.8s ease;
}
.quality-high { background: linear-gradient(90deg, #28a745, #20c997); }
.quality-mid { background: linear-gradient(90deg, #ffc107, #fd7e14); }
.quality-low { background: linear-gradient(90deg, #dc3545, #e83e8c); }

/* Sidebar */
.sidebar-brand {
    text-align: center;
    padding: 1rem 0;
    border-bottom: 1px solid #eee;
    margin-bottom: 1rem;
}
.sidebar-brand-name {
    font-size: 1.1rem;
    font-weight: 700;
    color: #003366;
}
.sidebar-version {
    font-size: 0.75rem;
    color: #999;
}

/* Toast */
.toast-success {
    background: #d4edda;
    border: 1px solid #c3e6cb;
    color: #155724;
    padding: 1rem;
    border-radius: 8px;
    margin: 1rem 0;
}
</style>
""", unsafe_allow_html=True)


# ── Session State Init ────────────────────────────────────────────────
if 'processed_df' not in st.session_state:
    st.session_state.processed_df = None
if 'raw_df' not in st.session_state:
    st.session_state.raw_df = None
if 'errors' not in st.session_state:
    st.session_state.errors = []
if 'step' not in st.session_state:
    st.session_state.step = 1
if 'kpis' not in st.session_state:
    st.session_state.kpis = {}
if 'file_details' not in st.session_state:
    st.session_state.file_details = []


# ── Helper Functions ──────────────────────────────────────────────────
def format_bytes(size):
    """Convert bytes to human readable string."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"

def calculate_quality_score(df, report_type):
    """Calculate a data quality score (0-100)."""
    if df.empty:
        return 0
    
    report_config = config.get_report_config(report_type)
    if not report_config:
        return 0
    
    required_cols = [c['name'] for c in report_config.get('columns', []) if c.get('required')]
    total_checks = 0
    passed_checks = 0
    
    # Check 1: All required columns present
    for col in required_cols:
        total_checks += 1
        if col in df.columns:
            passed_checks += 1
    
    # Check 2: Null percentage per required column
    for col in required_cols:
        if col in df.columns:
            total_checks += 1
            null_pct = df[col].isnull().mean()
            if null_pct < 0.05:
                passed_checks += 1
            elif null_pct < 0.2:
                passed_checks += 0.5
    
    # Check 3: Duplicate rows
    total_checks += 1
    dup_pct = df.duplicated().mean()
    if dup_pct < 0.01:
        passed_checks += 1
    elif dup_pct < 0.1:
        passed_checks += 0.5
    
    return round((passed_checks / total_checks) * 100) if total_checks > 0 else 0

def render_step_indicator(current):
    """Render the step progress indicator."""
    steps = [
        ("1", "Cargar Datos"),
        ("2", "Análisis"),
        ("3", "Exportar")
    ]
    html = '<div class="step-container">'
    for num, label in steps:
        step_num = int(num)
        if step_num < current:
            cls = "step step-done"
            icon = "✅"
        elif step_num == current:
            cls = "step step-active"
            icon = "▶"
        else:
            cls = "step step-pending"
            icon = "○"
        html += f'<div class="{cls}">{icon} {label}</div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

def render_kpi_cards(kpis):
    """Render KPI cards with HTML."""
    html = '<div class="kpi-grid">'
    for label, value in kpis.items():
        if isinstance(value, float):
            display_val = f"{value:,.2f}"
        elif isinstance(value, int):
            display_val = f"{value:,}"
        else:
            display_val = str(value)
        html += f'''
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{display_val}</div>
        </div>'''
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

def render_quality_score(score):
    """Render data quality gauge."""
    if score >= 80:
        cls = "quality-high"
        emoji = "🟢"
        text = "Excelente"
    elif score >= 50:
        cls = "quality-mid"
        emoji = "🟡"
        text = "Aceptable"
    else:
        cls = "quality-low"
        emoji = "🔴"
        text = "Necesita revisión"
    
    st.markdown(f"""
    <div style="background:white; padding:1.2rem; border-radius:12px; box-shadow:0 2px 8px rgba(0,0,0,0.06); margin:1rem 0;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.5rem;">
            <span style="font-weight:600; color:#333;">Calidad de Datos</span>
            <span style="font-weight:700; color:#003366;">{emoji} {score}% — {text}</span>
        </div>
        <div class="quality-bar">
            <div class="quality-fill {cls}" style="width:{score}%;"></div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ── Sidebar ───────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div class="sidebar-brand">
        <div style="font-size:2.5rem;">📊</div>
        <div class="sidebar-brand-name">Reporteador Enterprise</div>
        <div class="sidebar-version">v1.0.0</div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("##### Tipo de Reporte")
    report_keys = list(config.reports.keys())
    report_labels = [config.reports[k]['name'] for k in report_keys]
    selected_idx = st.selectbox("Seleccione", range(len(report_keys)), format_func=lambda i: report_labels[i], label_visibility="collapsed")
    selected_report = report_keys[selected_idx]
    selected_name = report_labels[selected_idx]
    
    st.markdown(f"""
    <div style="background:#e8f4fd; padding:0.8rem; border-radius:8px; margin:0.5rem 0; border-left:4px solid #0066CC;">
        <span style="font-size:0.85rem; color:#003366; font-weight:500;">Modo: {selected_name}</span>
    </div>
    """, unsafe_allow_html=True)
    
    # Show expected columns
    report_cfg = config.get_report_config(selected_report)
    if report_cfg:
        with st.expander("📋 Columnas Esperadas"):
            for col_def in report_cfg.get("columns", []):
                req = "🔴" if col_def.get("required") else "⚪"
                aliases = col_def.get("aliases", [])
                alias_text = f" *(también: {', '.join(aliases)})*" if aliases else ""
                st.markdown(f"{req} **{col_def['name']}** `{col_def['type']}`{alias_text}")
    
    st.divider()
    
    with st.expander("🛠️ Diagnóstico"):
        if os.path.exists("logs/app.log"):
            try:
                with open("logs/app.log", "r", encoding="utf-8") as f:
                    lines = f.readlines()[-15:]
                st.code("".join(lines), language="text")
            except Exception:
                st.info("Sin logs disponibles.")
        else:
            st.info("Sin logs aún.")
    
    st.divider()
    st.caption("© 2026 Reporteador Enterprise")


# ── Main Content ──────────────────────────────────────────────────────
st.markdown('<div class="main-title">Reporteador Comercial Enterprise</div>', unsafe_allow_html=True)
st.markdown('<div class="main-subtitle">Automatización inteligente de reportes comerciales</div>', unsafe_allow_html=True)

render_step_indicator(st.session_state.step)


# ═══════════════════════════════════════════════════════════════════════
# STEP 1: FILE UPLOAD
# ═══════════════════════════════════════════════════════════════════════
st.markdown("### 📂 Paso 1 — Carga de Archivos")

uploaded_files = st.file_uploader(
    "Arrastre o seleccione archivos Excel",
    type=["xlsx", "xls"],
    accept_multiple_files=True,
    key="file_uploader",
    help="Puede subir múltiples archivos. El sistema los consolidará automáticamente."
)

if uploaded_files:
    # Show file cards
    st.markdown(f"**{len(uploaded_files)} archivo(s) cargado(s):**")
    for f in uploaded_files:
        size_str = format_bytes(f.size)
        st.markdown(f"""
        <div class="file-card">
            <div class="file-info">
                <span class="file-icon">📄</span>
                <div>
                    <div class="file-name">{f.name}</div>
                    <div class="file-size">{size_str}</div>
                </div>
            </div>
            <span class="file-status-ok">✓ Listo</span>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("")  # spacing
    
    # Process button
    if st.button("🚀 Procesar Datos", type="primary", use_container_width=True):
        with st.spinner("🧠 Analizando estructura, validando reglas y procesando datos..."):
            df, errors = loader.load_and_validate(uploaded_files, selected_report)
            
            if errors:
                st.session_state.errors = errors
                st.session_state.raw_df = None
                st.session_state.processed_df = None
                st.session_state.step = 1
            else:
                processed_df = processor.process_data(df, selected_report)
                kpis = KPIEngine.calculate(processed_df, selected_report)
                
                st.session_state.raw_df = df
                st.session_state.processed_df = processed_df
                st.session_state.kpis = kpis
                st.session_state.errors = []
                st.session_state.step = 2
                
                # Store file details
                st.session_state.file_details = [
                    {"name": f.name, "size": f.size, "rows": "—"} for f in uploaded_files
                ]
        
        st.rerun()

    # Show errors if any
    if st.session_state.errors:
        st.error("⚠️ Se encontraron errores de validación:")
        for err in st.session_state.errors:
            st.warning(err)
        st.info("💡 **Sugerencia:** Revise que su archivo tenga las columnas esperadas (ver panel lateral).")


# ═══════════════════════════════════════════════════════════════════════
# STEP 2: ANALYSIS DASHBOARD
# ═══════════════════════════════════════════════════════════════════════
if st.session_state.processed_df is not None and not st.session_state.processed_df.empty:
    processed_df = st.session_state.processed_df
    kpis = st.session_state.kpis
    
    st.divider()
    st.markdown("### 📈 Paso 2 — Análisis y Dashboard")
    
    # Quality Score
    quality = calculate_quality_score(processed_df, selected_report)
    render_quality_score(quality)
    
    # KPIs
    if kpis:
        render_kpi_cards(kpis)
    
    # Summary stats
    col_stats1, col_stats2, col_stats3 = st.columns(3)
    with col_stats1:
        st.metric("Total Registros", f"{len(processed_df):,}")
    with col_stats2:
        st.metric("Columnas Procesadas", len(processed_df.columns))
    with col_stats3:
        null_pct = round(processed_df.isnull().mean().mean() * 100, 1)
        st.metric("Datos Vacíos", f"{null_pct}%")
    
    # Charts
    st.markdown("#### 📊 Visualizaciones")
    tab1, tab2, tab3 = st.tabs(["📊 Distribución", "🥧 Composición", "📋 Datos"])
    
    with tab1:
        # Find a good column to chart
        text_cols = processed_df.select_dtypes(['object']).columns.tolist()
        numeric_cols = processed_df.select_dtypes(['number']).columns.tolist()
        
        if text_cols:
            chart_col = st.selectbox("Agrupar por:", text_cols, key="bar_col")
            counts = processed_df[chart_col].value_counts().reset_index()
            counts.columns = [chart_col, 'Cantidad']
            fig = px.bar(
                counts.head(15), x=chart_col, y='Cantidad',
                title=f"Distribución por {chart_col}",
                color='Cantidad',
                color_continuous_scale='Blues'
            )
            fig.update_layout(
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(family="Inter"),
                title_font_size=16
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No hay columnas de texto para graficar distribución.")
    
    with tab2:
        if text_cols and numeric_cols:
            pie_group = st.selectbox("Agrupar por:", text_cols, key="pie_col")
            pie_value = st.selectbox("Valor:", numeric_cols, key="pie_val")
            fig2 = px.pie(
                processed_df, values=pie_value, names=pie_group,
                title=f"{pie_value} por {pie_group}",
                color_discrete_sequence=px.colors.sequential.Blues_r
            )
            fig2.update_layout(
                font=dict(family="Inter"),
                title_font_size=16
            )
            st.plotly_chart(fig2, use_container_width=True)
        elif text_cols:
            pie_group = st.selectbox("Agrupar por:", text_cols, key="pie_col")
            counts = processed_df[pie_group].value_counts().reset_index()
            counts.columns = [pie_group, 'Cantidad']
            fig2 = px.pie(
                counts, values='Cantidad', names=pie_group,
                title=f"Distribución por {pie_group}",
                color_discrete_sequence=px.colors.sequential.Blues_r
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No hay datos para graficar composición.")
    
    with tab3:
        # Search / Filter
        search = st.text_input("🔍 Buscar en datos:", placeholder="Escriba para filtrar...")
        if search:
            mask = processed_df.apply(lambda row: row.astype(str).str.contains(search, case=False).any(), axis=1)
            display_df = processed_df[mask]
            st.caption(f"Mostrando {len(display_df)} de {len(processed_df)} registros")
        else:
            display_df = processed_df
        
        st.dataframe(display_df, use_container_width=True, height=400)
        
        # Column statistics
        with st.expander("📊 Estadísticas por Columna"):
            st.dataframe(processed_df.describe(include='all').T, use_container_width=True)
    
    # ═══════════════════════════════════════════════════════════════════
    # STEP 3: EXPORT
    # ═══════════════════════════════════════════════════════════════════
    st.divider()
    st.markdown("### 💾 Paso 3 — Exportar Reporte")
    
    exp_col1, exp_col2 = st.columns(2)
    
    with exp_col1:
        st.markdown("""
        <div style="background:white; padding:1.5rem; border-radius:12px; box-shadow:0 2px 8px rgba(0,0,0,0.06); height:100%;">
            <h4 style="margin:0 0 0.5rem 0;">📥 Excel Consolidado</h4>
            <p style="color:#666; font-size:0.9rem;">Exporta todos los datos procesados en un archivo Excel profesional con formato.</p>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("Generar Excel", type="primary", use_container_width=True, key="gen_excel"):
            try:
                template_path = f"templates/template_{selected_report}.xlsx"
                output = filler.fill_template(processed_df, template_path)
                
                st.download_button(
                    label="📥 Descargar Excel",
                    data=output,
                    file_name=f"Reporte_{selected_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
                st.session_state.step = 3
                st.toast("¡Reporte generado!", icon="🎉")
            except Exception as e:
                st.error(f"Error: {e}")
    
    with exp_col2:
        st.markdown("""
        <div style="background:white; padding:1.5rem; border-radius:12px; box-shadow:0 2px 8px rgba(0,0,0,0.06); height:100%;">
            <h4 style="margin:0 0 0.5rem 0;">📄 CSV Rápido</h4>
            <p style="color:#666; font-size:0.9rem;">Exporta los datos en formato CSV para uso en otras herramientas o sistemas.</p>
        </div>
        """, unsafe_allow_html=True)
        
        csv_data = processed_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📄 Descargar CSV",
            data=csv_data,
            file_name=f"Reporte_{selected_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True
        )
    
    # Reset button
    st.markdown("")
    if st.button("🔄 Nuevo Reporte", use_container_width=True):
        st.session_state.processed_df = None
        st.session_state.raw_df = None
        st.session_state.kpis = {}
        st.session_state.errors = []
        st.session_state.step = 1
        st.session_state.file_details = []
        st.rerun()

# ═══════════════════════════════════════════════════════════════════════
# EMPTY STATE (no data loaded)
# ═══════════════════════════════════════════════════════════════════════
elif not uploaded_files and st.session_state.processed_df is None:
    st.markdown("")
    col_empty1, col_empty2, col_empty3 = st.columns([1, 2, 1])
    with col_empty2:
        st.markdown("""
        <div style="text-align:center; padding:3rem; background:white; border-radius:16px; box-shadow:0 2px 12px rgba(0,0,0,0.06); margin-top:1rem;">
            <div style="font-size:4rem; margin-bottom:1rem;">📂</div>
            <h3 style="color:#333; margin-bottom:0.5rem;">Comience subiendo sus archivos</h3>
            <p style="color:#888; max-width:400px; margin:0 auto;">
                Arrastre sus archivos Excel al área de carga superior, o haga clic para seleccionarlos.
                El sistema validará y procesará automáticamente toda la información.
            </p>
            <div style="margin-top:1.5rem; padding:1rem; background:#f0f7ff; border-radius:8px;">
                <p style="color:#0066CC; font-size:0.85rem; margin:0;">
                    💡 <strong>Tip:</strong> Seleccione primero el tipo de reporte en el panel lateral
                </p>
            </div>
        </div>
        """, unsafe_allow_html=True)
