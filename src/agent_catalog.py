from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd


def normalize_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.upper().replace(",", " ")
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).replace("\n", " ").replace("\r", " ")
    return re.sub(r"\s+", " ", text).strip()


class AgentCatalog:
    def __init__(self, source: str | Path | pd.DataFrame):
        self._source = source
        self._df = self._load_source(source)

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> "AgentCatalog":
        return cls(df.copy())

    def _load_source(self, source: str | Path | pd.DataFrame) -> pd.DataFrame:
        if isinstance(source, pd.DataFrame):
            df = source.copy()
        else:
            path = Path(source)
            if not path.exists():
                return pd.DataFrame(columns=["EJECUTIVO", "NOMBRE AGENTE", "normalized_name"])
            df = pd.read_excel(path)

        if "EJECUTIVO" not in df.columns or "NOMBRE AGENTE" not in df.columns:
            return pd.DataFrame(columns=["EJECUTIVO", "NOMBRE AGENTE", "normalized_name"])

        df = df[["EJECUTIVO", "NOMBRE AGENTE"]].copy()
        df["EJECUTIVO"] = df["EJECUTIVO"].map(clean_text)
        df["NOMBRE AGENTE"] = df["NOMBRE AGENTE"].map(clean_text)
        df["normalized_name"] = df["NOMBRE AGENTE"].map(normalize_text)
        df = df[df["normalized_name"] != ""]
        return df.drop_duplicates(ignore_index=True)

    def match(self, agent_name: object) -> Optional[Tuple[str, str]]:
        normalized = normalize_text(agent_name)
        if not normalized or self._df.empty:
            return None

        exact = self._df[self._df["normalized_name"] == normalized]
        resolved = self._resolve_matches(exact)
        if resolved:
            return resolved

        prefix = self._df[
            self._df["normalized_name"].map(
                lambda name: min(len(name), len(normalized)) >= 12
                and (name.startswith(normalized) or normalized.startswith(name))
            )
        ]
        return self._resolve_matches(prefix)

    def enrich(self, agent_name: object) -> Tuple[str, str]:
        match = self.match(agent_name)
        if match:
            return match
        return clean_text(agent_name), ""

    def enrich_series(self, series: pd.Series) -> Tuple[pd.Series, pd.Series]:
        official_names = []
        executives = []
        for value in series.fillna(""):
            official_name, executive = self.enrich(value)
            official_names.append(official_name)
            executives.append(executive)
        return pd.Series(official_names, index=series.index), pd.Series(executives, index=series.index)

    def _resolve_matches(self, matches: pd.DataFrame) -> Optional[Tuple[str, str]]:
        if matches.empty:
            return None

        official_names = matches["NOMBRE AGENTE"].dropna().unique().tolist()
        executives = [value for value in matches["EJECUTIVO"].dropna().unique().tolist() if value]

        if len(official_names) == 1:
            return official_names[0], executives[0] if executives else ""

        if len(set(executives)) == 1:
            return official_names[0], executives[0] if executives else ""

        return None
