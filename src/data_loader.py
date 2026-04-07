import os
from typing import Any, List, Tuple

import pandas as pd
import pandera.pandas as pa
from loguru import logger

from .agent_catalog import AgentCatalog, normalize_text
from .config import ConfigLoader
from .schemas import SchemaBuilder
from .source_converters import (
    build_cotizaciones_dataframe,
    build_emisiones_dataframe,
    build_renovaciones_dataframe,
    read_tabular_excel,
)


class ExcelLoader:
    def __init__(self, config: ConfigLoader):
        self.config = config
        self.schema_builder = SchemaBuilder(config)
        assets = self.config.app_settings.get("assets", {})
        self.agent_catalog = AgentCatalog(assets.get("agent_catalog_path", "config/base_agentes_2026.xlsx"))

    def load_and_validate(self, uploaded_files: List[Any], report_type: str) -> Tuple[pd.DataFrame, List[str]]:
        report_config = self.config.get_report_config(report_type)
        if not report_config:
            return pd.DataFrame(), [f"Configuration for '{report_type}' not found."]

        source_type = report_config.get("source_type", report_type)
        errors: List[str] = []

        try:
            if source_type == "cotizaciones":
                final_df, errors = build_cotizaciones_dataframe(uploaded_files, self.agent_catalog)
            else:
                final_df = self._load_excel_sources(uploaded_files, report_config, source_type, errors)
        except Exception as exc:
            logger.exception("Unexpected error loading files for {}", report_type)
            return pd.DataFrame(), [f"Error inesperado procesando archivos: {exc}"]

        if final_df.empty:
            return pd.DataFrame(), errors

        schema = self.schema_builder.build_schema(report_type)
        try:
            validated = schema.validate(final_df, lazy=True)
            logger.info("Successfully validated {} records for {}", len(validated), report_type)
            return validated, errors
        except pa.errors.SchemaErrors as err:
            logger.error("Schema errors while validating {}: {}", report_type, err.failure_cases)
            for _, row in err.failure_cases.iterrows():
                column = row.get("column", "desconocida")
                check = row.get("check", "regla")
                index = row.get("index")
                if pd.notna(index):
                    errors.append(f"Fila {index}: la columna '{column}' no cumple '{check}'.")
                else:
                    errors.append(f"La columna '{column}' no cumple '{check}'.")
            return pd.DataFrame(), errors

    def _load_excel_sources(
        self,
        uploaded_files: List[Any],
        report_config: dict,
        source_type: str,
        errors: List[str],
    ) -> pd.DataFrame:
        expected_headers = report_config.get("source_headers", [])
        collected = []

        for file_obj in uploaded_files:
            file_name = os.path.basename(str(getattr(file_obj, "name", "archivo")))
            try:
                raw_df = read_tabular_excel(file_obj, expected_headers)
                transformed = self._transform_dataframe(raw_df, source_type)

                if transformed.empty:
                    if self._looks_like_output_template(file_name, raw_df, report_config):
                        errors.append(
                            f"{file_name}: se detecto como plantilla destino. Cargala en Plantilla o agrega tambien el archivo fuente."
                        )
                    else:
                        errors.append(f"{file_name}: no se encontraron registros utiles despues de transformar el archivo.")
                    continue

                collected.append(transformed)
                logger.info("Successfully loaded {}", file_name)
            except Exception as exc:
                logger.exception("Error reading {}", file_name)
                errors.append(f"{file_name}: {exc}")

        if not collected:
            return pd.DataFrame()

        return pd.concat(collected, ignore_index=True)

    def _transform_dataframe(self, df: pd.DataFrame, source_type: str) -> pd.DataFrame:
        if source_type == "emisiones":
            return build_emisiones_dataframe(df, self.agent_catalog)
        if source_type == "renovaciones":
            return build_renovaciones_dataframe(df, self.agent_catalog)
        return df.copy()

    def _looks_like_output_template(self, file_name: str, raw_df: pd.DataFrame, report_config: dict) -> bool:
        if raw_df.empty:
            return "PLANTILLA" in normalize_text(file_name) or "TEMPLATE" in normalize_text(file_name)

        source_headers = {normalize_text(header) for header in report_config.get("source_headers", []) if header}
        report_columns = {normalize_text(col["name"]) for col in report_config.get("columns", []) if col.get("name")}
        raw_columns = {normalize_text(column) for column in raw_df.columns if normalize_text(column)}

        source_score = len(raw_columns & source_headers)
        report_score = len(raw_columns & report_columns)
        template_name = "PLANTILLA" in normalize_text(file_name) or "TEMPLATE" in normalize_text(file_name)

        if template_name and report_score >= source_score:
            return True

        return source_score <= 1 and report_score >= 3
