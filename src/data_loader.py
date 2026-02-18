import pandas as pd
from typing import List, Tuple, Dict, Any
from loguru import logger
import pandera as pa
from .config import ConfigLoader
from .schemas import SchemaBuilder

class ExcelLoader:
    def __init__(self, config: ConfigLoader):
        self.config = config
        self.schema_builder = SchemaBuilder(config)

    def load_and_validate(self, uploaded_files: List[Any], report_type: str) -> Tuple[pd.DataFrame, List[str]]:
        """
        Loads multiple Excel files, normalizes columns using aliases, 
        and validates against the schema.
        """
        all_data = []
        errors = []
        report_config = self.config.get_report_config(report_type)
        
        if not report_config:
            return pd.DataFrame(), [f"Configuration for '{report_type}' not found."]

        schema = self.schema_builder.build_schema(report_type)

        for file in uploaded_files:
            try:
                # 1. Load Data
                df = pd.read_excel(file)
                df.columns = df.columns.str.strip() # Basic cleanup
                
                # 2. Normalize Columns (Alias Mapping)
                df = self._normalize_columns(df, report_config["columns"])
                
                # 3. Validate Schema
                try:
                    df = schema.validate(df, lazy=True)
                    all_data.append(df)
                    logger.info(f"Successfully loaded and validated {file.name}")
                except pa.errors.SchemaErrors as err:
                    logger.error(f"Schema errors in {file.name}: {err.failure_cases}")
                    # Format friendly error messages
                    for _, row in err.failure_cases.iterrows():
                        col = row['column']
                        check = row['check']
                        errors.append(f"File '{file.name}': Column '{col}' failed check '{check}'.")
            
            except Exception as e:
                logger.error(f"Error reading file {file.name}: {e}")
                errors.append(f"Error reading {file.name}: {str(e)}")

        if not all_data:
            return pd.DataFrame(), errors

        final_df = pd.concat(all_data, ignore_index=True)
        return final_df, errors

    def _normalize_columns(self, df: pd.DataFrame, col_defs: List[Dict]) -> pd.DataFrame:
        """Renames columns based on aliases defined in config."""
        rename_map = {}
        for col_def in col_defs:
            target_name = col_def["name"]
            aliases = col_def.get("aliases", [])
            
            # Direct match?
            if target_name in df.columns:
                continue
            
            # Check aliases
            for alias in aliases:
                if alias in df.columns:
                    rename_map[alias] = target_name
                    break
        
        if rename_map:
            logger.debug(f"Renaming columns: {rename_map}")
            df = df.rename(columns=rename_map)
            
        return df
