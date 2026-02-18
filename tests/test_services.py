import pytest
import pandas as pd
from src.config import ConfigLoader
from src.schemas import SchemaBuilder
from src.services import ReportProcessor, KPIEngine

# Mock Config
class MockConfig:
    def get_report_config(self, report_type):
        if report_type == "test_report":
            return {
                "name": "Test Report",
                "columns": [
                    {"name": "col_str", "type": "str", "required": True},
                    {"name": "col_int", "type": "int", "required": True},
                    {"name": "col_date", "type": "datetime", "required": False}
                ]
            }
        return None

def test_schema_builder():
    config = MockConfig()
    builder = SchemaBuilder(config)
    schema = builder.build_schema("test_report")
    
    assert "col_str" in schema.columns
    assert "col_int" in schema.columns

def test_report_processor():
    config = MockConfig()
    processor = ReportProcessor(config)
    
    df = pd.DataFrame({
        "col_str": [" A ", "B"], # Needs trimming
        "col_int": [1, 2],
        "extra_col": [0, 0]
    })
    
    processed = processor.process_data(df, "test_report")
    
    assert "extra_col" not in processed.columns
    assert processed.iloc[0]["col_str"] == "A" # Check trimming

def test_kpi_engine():
    df = pd.DataFrame({
        "Prima total": [100, 200],
        "Ejecutivo": ["A", "B"]
    })
    
    # Mocking behavior for emision_mensual which expects these columns
    kpis = KPIEngine.calculate(df, "emision_mensual")
    
    assert kpis["Total Pólizas"] == 2
    assert kpis["Prima Total Emitida"] == 300
