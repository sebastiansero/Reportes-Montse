import pandera.pandas as pa
from .config import ConfigLoader

class SchemaBuilder:
    def __init__(self, config: ConfigLoader):
        self.config = config

    def build_schema(self, report_type: str) -> pa.DataFrameSchema:
        """Dynamically builds a Pandera schema based on the report configuration."""
        report_config = self.config.get_report_config(report_type)
        if not report_config:
            raise ValueError(f"Report type '{report_type}' not found in configuration.")

        columns = {}
        for col_def in report_config.get("columns", []):
            col_name = col_def["name"]
            col_type = col_def["type"]
            required = col_def.get("required", True)
            allowed_values = col_def.get("allowed_values")

            pa_type = self._map_type(col_type)
            checks = []
            
            if allowed_values:
                checks.append(pa.Check.isin(allowed_values))

            # Allow nullable if not required
            columns[col_name] = pa.Column(
                pa_type, 
                required=required, 
                checks=checks, 
                nullable=not required,
                coerce=True
            )

        return pa.DataFrameSchema(columns=columns, strict=False)

    def _map_type(self, type_str: str):
        mapping = {
            "str": pa.String,
            "int": pa.Int,
            "float": pa.Float,
            "datetime": pa.DateTime,
            "bool": pa.Bool
        }
        return mapping.get(type_str, pa.String)
