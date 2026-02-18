import pandas as pd
from typing import Dict, Any, List, Optional
from loguru import logger
from .config import ConfigLoader

class ReportProcessor:
    def __init__(self, config: ConfigLoader):
        self.config = config

    def process_data(self, df: pd.DataFrame, report_type: str) -> pd.DataFrame:
        """
        Applies business logic to clean and structure the data for the report.
        """
        report_config = self.config.get_report_config(report_type)
        if not report_config:
             raise ValueError(f"Report type '{report_type}' not found.")
             
        # Select only required columns (they are already validated and mapped)
        required_columns = [col["name"] for col in report_config.get("columns", [])]
        
        # Ensure all columns exist (validation should have caught this, but double check)
        existing_cols = [col for col in required_columns if col in df.columns]
        
        processed_df = df[existing_cols].copy()
        
        # Apply specific transformations here if needed (e.g. standardizing text)
        processed_df = self._standardize_text(processed_df)
        
        return processed_df

    def _standardize_text(self, df: pd.DataFrame) -> pd.DataFrame:
        """Standardizes string columns to title case or upper case as per business rules."""
        # For this example, let's just strip whitespace again to be safe
        df_obj = df.select_dtypes(['object'])
        df[df_obj.columns] = df_obj.apply(lambda x: x.str.strip())
        return df

class KPIEngine:
    """Calculates dynamic KPIs based on the report type."""
    
    @staticmethod
    def calculate(df: pd.DataFrame, report_type: str) -> Dict[str, Any]:
        kpis = {}
        
        if report_type == "emision_mensual":
            kpis['Total Pólizas'] = len(df)
            if 'Prima total' in df.columns:
                kpis['Prima Total Emitida'] = df['Prima total'].sum()
            if 'Ejecutivo' in df.columns:
                 # Top performing executive
                 top_exec = df.groupby('Ejecutivo')['Prima total'].sum().idxmax()
                 kpis['Top Ejecutivo'] = top_exec

        elif report_type == "renovaciones":
            total = len(df)
            if 'Renovada' in df.columns:
                renovadas = len(df[df['Renovada'].str.lower() == 'si'])
                kpis['% Renovación'] = round((renovadas / total * 100), 2) if total > 0 else 0
        
        elif report_type == "cotizaciones":
            kpis['Total Cotizaciones'] = len(df)
            if 'Estatus' in df.columns:
                accepted = len(df[df['Estatus'].str.lower() == 'aceptada'])
                kpis['Tasa de Cierre'] = round((accepted / len(df) * 100), 2) if len(df) > 0 else 0

        return kpis
