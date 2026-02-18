# 📊 Reporteador Comercial Enterprise

Sistema inteligente para la **automatización de reportes comerciales** del sector asegurador. Consolida múltiples archivos Excel, valida la calidad de los datos, calcula KPIs clave y genera reportes profesionales listos para presentar.

---

## 🎯 ¿Qué hace esta aplicación?

Esta herramienta resuelve el problema de **consolidar información dispersa en múltiples archivos Excel** y generar reportes estandarizados de manera automática.

### Flujo de trabajo:
1. **Cargas tus archivos Excel** → La app acepta múltiples archivos simultáneamente.
2. **Validación automática** → El sistema verifica que los datos cumplan con las reglas de negocio (columnas correctas, tipos de dato, valores permitidos).
3. **Mapeo inteligente de columnas** → Si tu archivo dice "F. Emisión" pero el reporte espera "Fecha emisión", el sistema lo entiende automáticamente gracias a los aliases configurados.
4. **Dashboard interactivo** → Visualiza KPIs, gráficos de distribución y composición al instante.
5. **Exportación profesional** → Genera un Excel con formato empresarial o un CSV rápido.

### Tipos de reporte soportados:
| Reporte | Descripción |
|---------|-------------|
| **Emisión Mensual** | Control de pólizas emitidas, primas y producción por ejecutivo |
| **Renovaciones** | Seguimiento de renovaciones, tasas de retención y cancelación |
| **Cotizaciones** | Pipeline de cotizaciones, estatus y tasas de cierre |

---

## ✨ Características principales

- 🛡️ **Validación de datos con Pandera** — Detecta errores antes de procesar (ejemplo: "La columna Fecha en la fila 45 tiene texto en lugar de una fecha").
- 📊 **Dashboard interactivo** — Gráficos dinámicos con Plotly donde el usuario elige qué visualizar.
- 🔄 **Mapeo automático de columnas** — Reconoce variaciones de nombres de columnas (aliases) sin intervención manual.
- 📈 **Puntaje de calidad de datos** — Evalúa automáticamente la integridad de tus datos (🟢 Excelente / 🟡 Aceptable / 🔴 Revisar).
- 🔍 **Buscador integrado** — Filtra datos en tiempo real dentro de la tabla de resultados.
- 💾 **Doble exportación** — Excel con formato profesional + CSV para integración con otros sistemas.
- ⚙️ **Configuración externa (YAML)** — Cambia reglas de negocio sin modificar código.
- 📝 **Logging profesional** — Historial completo de operaciones con Loguru.

---

## 🚀 Instalación y Ejecución

### Requisitos previos
- Python 3.10 o superior
- pip (gestor de paquetes de Python)

### Pasos

```bash
# 1. Clonar el repositorio
git clone https://github.com/sebastiansero/Reportes-Montse.git
cd Reportes-Montse

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Ejecutar la aplicación
streamlit run src/app.py
```

La aplicación se abrirá automáticamente en tu navegador en `http://localhost:8501`.

---

## 📁 Estructura del Proyecto

```
Reportes-Montse/
├── .streamlit/
│   └── config.toml          # Tema visual de Streamlit
├── config/
│   └── settings.yaml        # ⭐ Reglas de negocio y definición de reportes
├── src/
│   ├── __init__.py
│   ├── app.py               # Interfaz gráfica (Streamlit + Plotly)
│   ├── config.py             # Cargador de configuración
│   ├── data_loader.py        # Carga y validación de Excel
│   ├── logger.py             # Configuración de logging
│   ├── schemas.py            # Validación dinámica con Pandera
│   ├── services.py           # Lógica de negocio (KPIs, procesamiento)
│   └── template_engine.py    # Generación de reportes Excel
├── templates/                # Plantillas Excel (se auto-generan si no existen)
├── tests/
│   ├── conftest.py
│   ├── test_services.py      # Tests de lógica de negocio
│   └── test_template.py      # Tests del generador de plantillas
├── logs/                     # Logs de ejecución (auto-generado)
├── requirements.txt
├── run.py                    # Punto de entrada alternativo
└── README.md
```

---

## ⚙️ Configuración

Toda la configuración del sistema está en `config/settings.yaml`. Aquí defines:

- **Columnas requeridas** para cada tipo de reporte
- **Tipos de dato** esperados (str, datetime, float, int)
- **Aliases** para columnas (variaciones de nombres)
- **Valores permitidos** (ejemplo: "Si", "No", "Pendiente")

### Ejemplo: Agregar una nueva columna

```yaml
# En config/settings.yaml, dentro del reporte deseado:
columns:
  - name: "Mi Nueva Columna"
    type: "str"
    required: true
    aliases: ["Nueva Col", "NC"]
```

No necesitas modificar código Python. Solo edita el YAML y reinicia la app.

---

## 🧪 Tests

```bash
python -m pytest tests/
```

---

## 🛠️ Tecnologías

| Tecnología | Uso |
|------------|-----|
| **Streamlit** | Interfaz web interactiva |
| **Pandas** | Procesamiento de datos |
| **Pandera** | Validación de esquemas |
| **Plotly** | Gráficos interactivos |
| **OpenPyXL** | Lectura/escritura de Excel |
| **Loguru** | Logging profesional |
| **PyYAML** | Configuración externa |

---

## 📄 Licencia

Proyecto privado. Todos los derechos reservados.
