import pandas as pd

from src.agent_catalog import AgentCatalog
from src.source_converters import (
    build_emisiones_dataframe,
    build_renovaciones_dataframe,
    parse_quote_text,
)


def test_build_renovaciones_dataframe_resolves_truncated_agent_names():
    catalog = AgentCatalog.from_dataframe(
        pd.DataFrame(
            [
                {"EJECUTIVO": "Hazel Castro", "NOMBRE AGENTE": "ESTEBAN FUENTES NIVON"},
            ]
        )
    )
    raw = pd.DataFrame(
        [
            {
                "DIA VTO": "28",
                "MES": "04",
                "ANIO": 2026,
                "POLIZA": "005233258",
                "COD ASEG": "002847464",
                "NOMBRE DEL ASEG.": "CARMEN RAMIREZ GARCI",
                "COD. AGTE.": "00355",
                "NOMBRE DEL AGTE.": "ESTEBAN FUENTES NIVO",
                "MON.": "$",
                "PRIMA TOTAL": "9,354",
                "STROS": "",
                "PRIMA NUEVA": "",
            }
        ]
    )

    result = build_renovaciones_dataframe(raw, catalog, pd.Timestamp("2026-04-07"))

    assert result.iloc[0]["EJECUTIVO"] == "Hazel Castro"
    assert result.iloc[0]["NOMBRE DEL AGTE."] == "ESTEBAN FUENTES NIVON"
    assert result.iloc[0]["VENCIDA"] == "NO"


def test_build_emisiones_dataframe_excludes_rows_with_renewal_number():
    catalog = AgentCatalog.from_dataframe(
        pd.DataFrame(
            [
                {"EJECUTIVO": "Claudia Rios", "NOMBRE AGENTE": "ANA ASESORIA Y PROTECCION PATRIMONIAL SC"},
            ]
        )
    )
    raw = pd.DataFrame(
        [
            {
                "DIVISIONAL": "QUERETARO",
                "CLAVE AGENTE": "50185",
                "NOMBRE AGENTE": "ANA ASESORIA Y PROTECCION PATRIMONIAL SC",
                "POLIZA": "005671709",
                "RENUEVA A": "005175721",
                "ASEGURADO": "MULTIFLETES SA DE CV",
                "TIPO POLIZA": "INDIVIDUAL",
                "PRIMA NETA": "91787.55",
                "FORMA PAGO": "CONTADO",
                "FECHA EMISION POLIZA": "2026-03-13",
                "INICIO VIGENCIA POLIZA": "2026-03-13",
                "FIN VIGENCIA POLIZA": "2027-03-13",
                "VIGENTE": "Vigente",
            },
            {
                "DIVISIONAL": "QUERETARO",
                "CLAVE AGENTE": "50185",
                "NOMBRE AGENTE": "ANA ASESORIA Y PROTECCION PATRIMONIAL SC",
                "POLIZA": "005671710",
                "RENUEVA A": "",
                "ASEGURADO": "CLIENTE SIN RENOVACION",
                "TIPO POLIZA": "INDIVIDUAL",
                "PRIMA NETA": "10000",
                "FORMA PAGO": "CONTADO",
                "FECHA EMISION POLIZA": "2026-03-14",
                "INICIO VIGENCIA POLIZA": "2026-03-14",
                "FIN VIGENCIA POLIZA": "2027-03-14",
                "VIGENTE": "Vigente",
            },
        ]
    )

    result = build_emisiones_dataframe(raw, catalog)

    assert len(result) == 1
    assert result.iloc[0]["EJECUTIVO DE CUENTA"] == "Claudia Rios"
    assert result.iloc[0]["EMISION / RENOVACION / REEXPEDICION / CANCELACION"] == "EMISION"
    assert result.iloc[0]["N° DE POLIZA"] == "005671710"


def test_parse_quote_text_extracts_core_fields():
    catalog = AgentCatalog.from_dataframe(
        pd.DataFrame(
            [
                {"EJECUTIVO": "Hazel Castro", "NOMBRE AGENTE": "ERNESTO VALDIVIA LOYOLA"},
            ]
        )
    )
    text = """
    COTIZACION DE SEGUROS AUTOMOVILES.
    Vigencia: 09/02/2026 AL 09/02/2027 09/02/2026 11:15:30 a. m.
    AGENTE : CLAVE TARIFA : M5004040
    21814
    ERNESTO VALDIVIA LOYOLA____________________________________
    MONEDA : NACIONAL MP CF MOTO URBANA 300 NK 300 CC
    2026 PARTICULAR
    FORMA DE PAGO: CONTADO
    PRIMA TOTAL: 8,410.66
    """

    record = parse_quote_text(text, "A1 300 NK 2026.pdf", catalog)

    assert record["EJECUTIVO DE CUENTA"] == "Hazel Castro"
    assert record["CLAVE DE AGENTE QUE SOLICITA"] == "21814"
    assert record["NOMBRE DE AGENTE QUE SOLICITA"] == "ERNESTO VALDIVIA LOYOLA"
    assert record["UNIDAD"] == "MOTO URBANA 300 NK 300 CC 2026"
    assert record["PRIMA TOTAL"] == 8410.66
