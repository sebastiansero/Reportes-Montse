import pandas as pd
from typing import Any, Dict


class ReportProcessor:
    def __init__(self, config):
        self.config = config

    def process_data(self, df: pd.DataFrame, report_type: str) -> pd.DataFrame:
        report_config = self.config.get_report_config(report_type)
        if not report_config:
            raise ValueError(f"Report type '{report_type}' not found.")

        required_columns = [col["name"] for col in report_config.get("columns", [])]
        existing_cols = [col for col in required_columns if col in df.columns]
        processed_df = df[existing_cols].copy()
        return self._standardize_text(processed_df)

    def _standardize_text(self, df: pd.DataFrame) -> pd.DataFrame:
        obj_columns = df.select_dtypes(include=["object"]).columns
        for column in obj_columns:
            df[column] = df[column].fillna("").astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
        return df


class KPIEngine:
    @staticmethod
    def calculate(df: pd.DataFrame, report_type: str) -> Dict[str, Any]:
        kpis: Dict[str, Any] = {}

        if report_type == "emision_mensual":
            kpis["Total Pólizas"] = len(df)
            if "PRIMA TOTAL" in df.columns:
                kpis["Prima Total Emitida"] = round(float(df["PRIMA TOTAL"].fillna(0).sum()), 2)
            if "EJECUTIVO DE CUENTA" in df.columns and df["EJECUTIVO DE CUENTA"].replace("", pd.NA).dropna().any():
                top_exec = df["EJECUTIVO DE CUENTA"].replace("", pd.NA).dropna().value_counts().idxmax()
                kpis["Top Ejecutivo"] = top_exec

        elif report_type == "renovaciones":
            kpis["Total Renovaciones"] = len(df)
            if "VENCIDA" in df.columns:
                vencidas = int((df["VENCIDA"] == "SI").sum())
                kpis["Vencidas"] = vencidas
            if "EJECUTIVO" in df.columns and df["EJECUTIVO"].replace("", pd.NA).dropna().any():
                top_exec = df["EJECUTIVO"].replace("", pd.NA).dropna().value_counts().idxmax()
                kpis["Top Ejecutivo"] = top_exec

        elif report_type == "vencimientos":
            kpis["Total Vencimientos"] = len(df)
            if "VENCIDA" in df.columns:
                kpis["Ya Vencidas"] = int((df["VENCIDA"] == "SI").sum())
            if "PRIMA TOTAL" in df.columns:
                kpis["Prima por Vencer"] = round(float(df["PRIMA TOTAL"].fillna(0).sum()), 2)
            if "EJECUTIVO" in df.columns and df["EJECUTIVO"].replace("", pd.NA).dropna().any():
                top_exec = df["EJECUTIVO"].replace("", pd.NA).dropna().value_counts().idxmax()
                kpis["Top Ejecutivo"] = top_exec

        elif report_type == "cotizaciones":
            kpis["Total Cotizaciones"] = len(df)
            if "PRIMA TOTAL" in df.columns:
                kpis["Prima Total Cotizada"] = round(float(df["PRIMA TOTAL"].fillna(0).sum()), 2)
            if "EJECUTIVO DE CUENTA" in df.columns and df["EJECUTIVO DE CUENTA"].replace("", pd.NA).dropna().any():
                top_exec = df["EJECUTIVO DE CUENTA"].replace("", pd.NA).dropna().value_counts().idxmax()
                kpis["Top Ejecutivo"] = top_exec

        return kpis
