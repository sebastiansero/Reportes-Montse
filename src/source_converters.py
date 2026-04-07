from __future__ import annotations

import io
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional
from zipfile import ZipFile
import xml.etree.ElementTree as ET

import pandas as pd
from PyPDF2 import PdfReader
from openpyxl.utils import column_index_from_string

from .agent_catalog import AgentCatalog, clean_text, normalize_text


PDF_AGENT_PATTERNS = [
    r"\n\s*(\d+)\s*\n([A-ZÁÉÍÓÚÑ .,&]+?)_+",
    r"\n\s*(\d+)\s+([A-ZÁÉÍÓÚÑ .,&]+?)\s+N\*VIGENCIA",
]


SPANISH_MONTHS = {
    "ENERO": 1,
    "FEBRERO": 2,
    "MARZO": 3,
    "ABRIL": 4,
    "MAYO": 5,
    "JUNIO": 6,
    "JULIO": 7,
    "AGOSTO": 8,
    "SEPTIEMBRE": 9,
    "OCTUBRE": 10,
    "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}


def read_tabular_excel(file_obj: object, expected_headers: Iterable[str]) -> pd.DataFrame:
    raw = _read_excel_matrix(file_obj)
    if raw.empty:
        return raw

    header_row = _find_header_row(raw, expected_headers)
    headers = _sanitize_headers(raw.iloc[header_row].tolist())
    body = raw.iloc[header_row + 1 :].copy()
    body.columns = headers
    body = body.dropna(axis=1, how="all").dropna(axis=0, how="all")
    body = body.loc[:, [col for col in body.columns if col]]
    return body.reset_index(drop=True)


def build_emisiones_dataframe(df: pd.DataFrame, catalog: AgentCatalog) -> pd.DataFrame:
    columns = {normalize_text(col): col for col in df.columns}

    def get_series(*names: str) -> pd.Series:
        for name in names:
            key = normalize_text(name)
            if key in columns:
                return df[columns[key]]
        return pd.Series([""] * len(df), index=df.index)

    divisional = get_series("DIVISIONAL").map(clean_text)
    policy = _clean_id_series(get_series("POLIZA"))
    renews_to = _clean_id_series(get_series("RENUEVA A"))
    status = get_series("VIGENTE").map(clean_text)
    agent_name = get_series("NOMBRE AGENTE").map(clean_text)
    official_agent, executive = catalog.enrich_series(agent_name)

    emission_type = pd.Series("EMISION", index=df.index)
    emission_type = emission_type.mask(renews_to != "", "RENOVACION")
    emission_type = emission_type.mask(status.str.contains("CANCEL", case=False, na=False), "CANCELACION")

    comments = pd.Series("", index=df.index)
    comments = comments.mask(renews_to != "", "Renueva a " + renews_to)
    comments = comments.mask(
        comments.eq("") & status.str.contains("SIN VIGOR|CANCEL", case=False, na=False),
        status,
    )

    output = pd.DataFrame(
        {
            "EJECUTIVO DE CUENTA": executive,
            "FECHA EMISION": _to_datetime_series(get_series("FECHA EMISION POLIZA")),
            "CLAVE DE AGENTE": _clean_id_series(get_series("CLAVE AGENTE")),
            "NOMBRE DE AGENTE": official_agent,
            "ASEGURADO": get_series("ASEGURADO").map(clean_text),
            "TIPO DE NEGOCIO": get_series("TIPO POLIZA").map(clean_text),
            "PRIMA TOTAL": _to_number_series(get_series("PRIMA NETA")),
            "FORMA PAGO": get_series("FORMA PAGO").map(clean_text),
            "FECHA INICIO VIGENCIA": _to_datetime_series(get_series("INICIO VIGENCIA POLIZA")),
            "FECHA FIN VIGENCIA": _to_datetime_series(get_series("FIN VIGENCIA POLIZA")),
            "N° DE POLIZA": policy,
            "EMISION / RENOVACION / REEXPEDICION / CANCELACION": emission_type,
            "COMENTARIOS": comments,
        }
    )

    mask = policy.ne("") & renews_to.eq("") & ~divisional.str.contains("TOTAL", case=False, na=False)
    return output.loc[mask].reset_index(drop=True)


def build_renovaciones_dataframe(
    df: pd.DataFrame, catalog: AgentCatalog, today: Optional[pd.Timestamp] = None
) -> pd.DataFrame:
    columns = {normalize_text(col): col for col in df.columns}

    def get_series(*names: str) -> pd.Series:
        for name in names:
            key = normalize_text(name)
            if key in columns:
                return df[columns[key]]
        return pd.Series([""] * len(df), index=df.index)

    today_value = (today or pd.Timestamp.today()).normalize()
    day = pd.to_numeric(get_series("DIA VTO"), errors="coerce")
    month = pd.to_numeric(get_series("MES"), errors="coerce")
    year = pd.to_numeric(get_series("ANIO"), errors="coerce")

    fecha_vto = pd.to_datetime(
        pd.DataFrame({"year": year, "month": month, "day": day}),
        errors="coerce",
    )

    agent_name = get_series("NOMBRE DEL AGTE.").map(clean_text)
    official_agent, executive = catalog.enrich_series(agent_name)
    renovacion = _to_number_series(get_series("PRIMA NUEVA"))
    renovada = pd.Series([""] * len(df), index=df.index)
    estatus = pd.Series(["PENDIENTE"] * len(df), index=df.index)

    output = pd.DataFrame(
        {
            "FECHA VTO": fecha_vto,
            "HOY": today_value,
            "VENCIDA": fecha_vto.map(lambda value: "SI" if pd.notna(value) and value.normalize() <= today_value else "NO"),
            "POLIZA": _clean_id_series(get_series("POLIZA")),
            "COD ASEG": _clean_id_series(get_series("COD ASEG")),
            "NOMBRE DEL ASEG.": get_series("NOMBRE DEL ASEG.").map(clean_text),
            "COD. AGTE.": _clean_id_series(get_series("COD. AGTE.")),
            "NOMBRE DEL AGTE.": official_agent.where(official_agent != "", agent_name),
            "MON.": get_series("MON.").map(clean_text),
            "PRIMA TOTAL": _to_number_series(get_series("PRIMA TOTAL")),
            "STROS": _clean_numeric_or_text(get_series("STROS")),
            "RENOVACION": renovacion,
            "EJECUTIVO": executive,
            "RENOVADA": renovada,
            "ESTATUS": estatus,
            "COMENTARIOS": pd.Series([""] * len(df), index=df.index),
        }
    )

    return output[output["POLIZA"] != ""].reset_index(drop=True)


def build_cotizaciones_dataframe(uploaded_files: list[object], catalog: AgentCatalog) -> tuple[pd.DataFrame, list[str]]:
    records = []
    errors: list[str] = []

    for file_obj in uploaded_files:
        try:
            text = extract_pdf_text(file_obj)
            records.append(parse_quote_text(text, getattr(file_obj, "name", "cotizacion.pdf"), catalog))
        except Exception as exc:
            errors.append(f"No se pudo leer {getattr(file_obj, 'name', 'archivo PDF')}: {exc}")

    return pd.DataFrame(records), errors


def parse_quote_text(text: str, filename: str, catalog: AgentCatalog) -> dict[str, object]:
    agent_code, agent_name = _extract_agent(text)
    official_agent, executive = catalog.enrich(agent_name)
    quote_date = _extract_quote_date(text)
    vehicle = _extract_vehicle(text, filename)
    tipo_negocio = _extract_tipo_negocio(text)

    return {
        "EJECUTIVO DE CUENTA": executive,
        "FECHA SOLICITUD DE COTIZACION": quote_date,
        "CLAVE DE AGENTE QUE SOLICITA": agent_code,
        "NOMBRE DE AGENTE QUE SOLICITA": official_agent or clean_text(agent_name),
        "UNIDAD": vehicle,
        "TIPO DE NEGOCIO": tipo_negocio,
        "PRIMA TOTAL": _extract_currency(text, "PRIMA TOTAL"),
        "FORMA PAGO": _extract_forma_pago(text),
        "POLIZA NUEVA EMISION / RENOVACION": "",
        "FECHA ENVIO DE COTIZACION": quote_date,
        "FECHA DE SEGUIMIENTO (Ejecutivo de Cuenta)": pd.NaT,
        "ESTATUS": "COTIZADA",
        "MOTIVO DE RECHAZO": "",
        "COMENTARIOS": f"Archivo origen: {filename}",
    }


def extract_pdf_text(file_obj: object) -> str:
    data = _get_file_bytes(file_obj)
    reader = PdfReader(io.BytesIO(data))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages)


def _get_file_bytes(file_obj: object) -> bytes:
    if isinstance(file_obj, (str, Path)):
        return Path(file_obj).read_bytes()
    if hasattr(file_obj, "getvalue"):
        return file_obj.getvalue()
    if hasattr(file_obj, "read"):
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        data = file_obj.read()
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        return data
    raise TypeError("Unsupported file object")


def _read_excel_matrix(file_obj: object) -> pd.DataFrame:
    data = _get_file_bytes(file_obj)
    try:
        return pd.read_excel(io.BytesIO(data), header=None, dtype=object)
    except Exception:
        return _read_invalid_xlsx(data)


def _read_invalid_xlsx(data: bytes) -> pd.DataFrame:
    ns = {
        "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    }

    with ZipFile(io.BytesIO(data)) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("a:si", ns):
                shared_strings.append("".join(text.text or "" for text in item.iterfind(".//a:t", ns)))

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in relationships}

        sheet = workbook.find("a:sheets/a:sheet", ns)
        if sheet is None:
            return pd.DataFrame()

        relationship_id = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
        target = "xl/" + rel_map[relationship_id]
        root = ET.fromstring(archive.read(target))
        row_nodes = root.findall(".//a:sheetData/a:row", ns)

        matrix: list[list[object]] = []
        max_col = 0
        row_values: list[dict[int, object]] = []
        for row in row_nodes:
            parsed: dict[int, object] = {}
            for cell in row.findall("a:c", ns):
                ref = cell.attrib.get("r", "A1")
                column_letters = re.match(r"([A-Z]+)", ref)
                if not column_letters:
                    continue
                column_index = column_index_from_string(column_letters.group(1)) - 1
                parsed[column_index] = _parse_xml_cell(cell, shared_strings, ns)
                max_col = max(max_col, column_index + 1)
            row_values.append(parsed)

        for parsed in row_values:
            matrix.append([parsed.get(index, None) for index in range(max_col)])

    return pd.DataFrame(matrix)


def _parse_xml_cell(cell: ET.Element, shared_strings: list[str], ns: dict[str, str]) -> object:
    value_node = cell.find("a:v", ns)
    inline_node = cell.find("a:is", ns)
    cell_type = cell.attrib.get("t")

    if cell_type == "s" and value_node is not None:
        index = int(value_node.text)
        return shared_strings[index] if index < len(shared_strings) else ""

    if cell_type == "inlineStr" and inline_node is not None:
        return "".join(text.text or "" for text in inline_node.iterfind(".//a:t", ns))

    if value_node is None:
        return ""

    value = value_node.text or ""
    try:
        number = float(value)
        if number.is_integer():
            return int(number)
        return number
    except ValueError:
        return value


def _find_header_row(raw: pd.DataFrame, expected_headers: Iterable[str]) -> int:
    expected = {normalize_text(header) for header in expected_headers}
    best_row = 0
    best_score = -1

    for index in range(min(len(raw), 10)):
        values = [normalize_text(value) for value in raw.iloc[index].tolist() if clean_text(value)]
        score = sum(1 for value in values if value in expected)
        if score > best_score:
            best_row = index
            best_score = score

    return best_row


def _sanitize_headers(headers: list[object]) -> list[str]:
    cleaned = []
    seen: dict[str, int] = {}

    for header in headers:
        value = clean_text(header)
        if not value:
            cleaned.append("")
            continue

        base = value
        count = seen.get(base, 0)
        seen[base] = count + 1
        cleaned.append(base if count == 0 else f"{base}_{count + 1}")

    return cleaned


def _clean_id_series(series: pd.Series) -> pd.Series:
    def clean_id(value: object) -> str:
        text = clean_text(value)
        if not text or text in {"-", "nan", "None"}:
            return ""
        if re.fullmatch(r"\d+\.0", text):
            text = text[:-2]
        return text.strip()

    return series.map(clean_id)


def _to_number_series(series: pd.Series) -> pd.Series:
    cleaned = (
        series.map(clean_text)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.replace("%", "", regex=False)
    )
    result = pd.to_numeric(cleaned, errors="coerce")
    return result.fillna(0)


def _to_datetime_series(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    numeric = pd.to_numeric(series, errors="coerce")
    excel_mask = numeric.between(30000, 60000, inclusive="both")
    if excel_mask.any():
        parsed.loc[excel_mask] = pd.to_datetime(numeric.loc[excel_mask], unit="D", origin="1899-12-30", errors="coerce")
    return parsed


def _clean_numeric_or_text(series: pd.Series) -> pd.Series:
    cleaned = series.map(clean_text)
    numeric = pd.to_numeric(cleaned, errors="coerce")
    return numeric.where(numeric.notna(), cleaned)


def _extract_agent(text: str) -> tuple[str, str]:
    for pattern in PDF_AGENT_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return clean_text(match.group(1)), clean_text(match.group(2))
    return "", ""


def _extract_quote_date(text: str) -> pd.Timestamp:
    header_match = re.search(r"(\d{2}/\d{2}/\d{4})\s+\d{1,2}:\d{2}", text)
    if header_match:
        return pd.to_datetime(header_match.group(1), dayfirst=True, errors="coerce")

    footer_match = re.search(r"DE FECHA\s+(\d{1,2})\s+DE\s+([A-ZÁÉÍÓÚ]+)\s+DE\s+(\d{4})", text, re.IGNORECASE)
    if footer_match:
        day = int(footer_match.group(1))
        month = SPANISH_MONTHS.get(normalize_text(footer_match.group(2)))
        year = int(footer_match.group(3))
        if month:
            return pd.Timestamp(datetime(year, month, day))

    fallback = re.search(r"(\d{2}/\d{2}/\d{4})", text)
    if fallback:
        return pd.to_datetime(fallback.group(1), dayfirst=True, errors="coerce")

    return pd.NaT


def _extract_vehicle(text: str, filename: str) -> str:
    generic = re.search(r"VEHICULO\s+(.*?)\s+COLOR", text, re.IGNORECASE | re.DOTALL)
    if generic:
        vehicle = clean_text(generic.group(1))
    else:
        compact = re.search(r"NACIONAL\s+(.*?)\s+\d{4}\s+(PARTICULAR|CARGA|PUBLICO)", text, re.IGNORECASE | re.DOTALL)
        vehicle = clean_text(compact.group(1)) if compact else ""
        vehicle = re.sub(r"^(MP|CF)\s+", "", vehicle, flags=re.IGNORECASE)
        vehicle = re.sub(r"^(MP|CF)\s+", "", vehicle, flags=re.IGNORECASE)

    model_match = re.search(r"MODELO\s*:?\s*(\d{4})", text, re.IGNORECASE)
    if model_match and model_match.group(1) not in vehicle:
        vehicle = f"{vehicle} {model_match.group(1)}".strip()

    if not model_match:
        filename_year = re.search(r"(20\d{2})", Path(filename).stem)
        if filename_year and filename_year.group(1) not in vehicle:
            vehicle = f"{vehicle} {filename_year.group(1)}".strip()

    return vehicle or Path(filename).stem


def _extract_tipo_negocio(text: str) -> str:
    negocio = re.search(r"NEGOCIO\s*:\s*([A-ZÁÉÍÓÚ ]+)", text, re.IGNORECASE)
    if negocio:
        value = clean_text(negocio.group(1)).replace("SOLICITADO POR", "").strip()
        if value:
            return value

    uso = re.search(r"\d{4}\s+([A-ZÁÉÍÓÚ ]+)\s+RIESGOS", text, re.IGNORECASE | re.DOTALL)
    if uso:
        return clean_text(uso.group(1))

    return ""


def _extract_currency(text: str, label: str) -> float:
    match = re.search(rf"{label}[:\s$]+([\d,]+\.\d{{2}})", text, re.IGNORECASE)
    if not match:
        return 0.0
    return float(match.group(1).replace(",", ""))


def _extract_forma_pago(text: str) -> str:
    match = re.search(r"FORMA DE PAGO[:\s]+([A-ZÁÉÍÓÚ ]+)", text, re.IGNORECASE)
    return clean_text(match.group(1)) if match else ""
