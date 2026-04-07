import pandas as pd

from src.schemas import SchemaBuilder
from src.services import KPIEngine, ReportProcessor


class MockConfig:
    def get_report_config(self, report_type):
        if report_type == "test_report":
            return {
                "name": "Test Report",
                "columns": [
                    {"name": "COL_A", "type": "str", "required": True},
                    {"name": "COL_B", "type": "float", "required": True},
                    {"name": "COL_C", "type": "datetime", "required": False},
                ],
            }
        return None


def test_schema_builder():
    config = MockConfig()
    builder = SchemaBuilder(config)
    schema = builder.build_schema("test_report")

    assert "COL_A" in schema.columns
    assert "COL_B" in schema.columns


def test_report_processor():
    config = MockConfig()
    processor = ReportProcessor(config)

    df = pd.DataFrame(
        {
            "COL_A": [" A  ", "B"],
            "COL_B": [1.0, 2.0],
            "EXTRA": [0, 0],
        }
    )

    processed = processor.process_data(df, "test_report")

    assert "EXTRA" not in processed.columns
    assert processed.iloc[0]["COL_A"] == "A"


def test_kpi_engine_emisiones():
    df = pd.DataFrame(
        {
            "PRIMA TOTAL": [100.5, 200.25],
            "EJECUTIVO DE CUENTA": ["Hazel Castro", "Hazel Castro"],
        }
    )

    kpis = KPIEngine.calculate(df, "emision_mensual")

    assert kpis["Total Pólizas"] == 2
    assert kpis["Prima Total Emitida"] == 300.75
    assert kpis["Top Ejecutivo"] == "Hazel Castro"
