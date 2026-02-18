# 📊 Reporteador Comercial Enterprise

Aplicación empresarial para la automatización de reportes comerciales. Procesa archivos Excel, valida datos, calcula KPIs y genera reportes consolidados con formato profesional.

## ✨ Características

- **Validación inteligente de datos** con Pandera
- **Mapeo automático de columnas** (aliases configurables)
- **Dashboard interactivo** con gráficos dinámicos (Plotly)
- **Puntaje de calidad de datos** en tiempo real
- **Exportación dual**: Excel con formato + CSV
- **Configuración externa** vía YAML (sin tocar código)
- **Logs profesionales** con Loguru

## 🚀 Instalación

```bash
pip install -r requirements.txt
```

## ▶️ Ejecución

```bash
streamlit run src/app.py
```

## 📁 Estructura

```
├── config/settings.yaml    # Reglas de negocio
├── src/
│   ├── app.py              # Interfaz (Streamlit)
│   ├── services.py         # Lógica de negocio
│   ├── schemas.py          # Validación dinámica
│   ├── data_loader.py      # Carga inteligente de Excel
│   └── template_engine.py  # Generador de reportes
├── tests/                  # Pruebas unitarias
└── templates/              # Plantillas Excel
```

## 🧪 Tests

```bash
python -m pytest tests/
```
