"""Term sheets in German, French, Spanish, Italian and Dutch: labels, dates and number formats."""

from datetime import date

import pytest

from app.termsheets.languages import detect_language, month_number, to_float
from app.termsheets.rules import extract_with_rules, parse_coupon, parse_date, parse_size_mm

DE = """Endgültige Bedingungen
Emittentin: Beispielbank AG
ISIN: DE000A1B2C30
Währung: EUR
Gesamtnennbetrag: EUR 500.000.000
Zinssatz: 3,750 % p.a.
Begebungstag: 15. Januar 2026
Fälligkeitstag: 15. Januar 2032
Anwendbares Recht: Deutsches Recht
"""

FR = """Conditions définitives
Émetteur: Banque Exemple SA
Devise: EUR
Montant nominal total: EUR 750 000 000
Taux d'intérêt: 3,125 pour cent par an
Date d'émission: 1er mars 2026
Date d'échéance: 1 mars 2033
Droit applicable: droit français
"""

ES = """Condiciones definitivas
Emisor: Banco Ejemplo, S.A.
Divisa: EUR
Importe nominal total: EUR 300.000.000
Tipo de interés: 3,5 por ciento anual
Fecha de emisión: 10 de febrero de 2026
Fecha de vencimiento: 10 de febrero de 2031
Ley aplicable: Derecho español
"""

IT = """Condizioni definitive
Emittente: Banca Esempio S.p.A.
Valuta: EUR
Importo nominale complessivo: EUR 400.000.000
Tasso di interesse: 3,25 per cento annuo
Data di emissione: 5 maggio 2026
Data di scadenza: 5 maggio 2030
Legge applicabile: diritto italiano
"""

NL = """Definitieve voorwaarden
Uitgevende instelling: Voorbeeldbank N.V.
Valuta: EUR
Totale hoofdsom: EUR 600.000.000
Rentevoet: 3,0 procent per jaar
Uitgiftedatum: 12 september 2026
Einddatum: 12 september 2031
Toepasselijk recht: Nederlands recht
"""


@pytest.mark.parametrize(
    ("text", "issuer", "size", "coupon", "maturity"),
    [
        (DE, "Beispielbank AG", 500.0, 3.75, date(2032, 1, 15)),
        (FR, "Banque Exemple SA", 750.0, 3.125, date(2033, 3, 1)),
        (ES, "Banco Ejemplo, S.A.", 300.0, 3.5, date(2031, 2, 10)),
        (IT, "Banca Esempio S.p.A.", 400.0, 3.25, date(2030, 5, 5)),
        (NL, "Voorbeeldbank N.V.", 600.0, 3.0, date(2031, 9, 12)),
    ],
)
def test_rules_read_each_language(text, issuer, size, coupon, maturity):
    record = extract_with_rules(text)
    assert record.issuer == issuer
    assert record.currency == "EUR"
    assert record.size_mm == size
    assert record.coupon_pct == coupon
    assert record.maturity == maturity
    assert record.governing_law  # stated in every sample


def test_german_isin_is_found():
    assert extract_with_rules(DE).isin == "DE000A1B2C30"


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        ("1,500,000,000", 1.5e9),
        ("1.500.000.000", 1.5e9),
        ("3,750", 3.75),
        ("3.750", 3.75),
        ("500.000", 500000.0),
        ("1,500.5", 1500.5),
        ("15.000.000,50", 15000000.5),
    ],
)
def test_number_formats(number, expected):
    assert to_float(number) == expected


def test_dates_and_units():
    assert parse_date("13. November 2032") == date(2032, 11, 13)
    assert parse_date("15 de enero de 2032") == date(2032, 1, 15)
    assert parse_date("1er mars 2033") == date(2033, 3, 1)
    assert parse_date("13 November 2032") == date(2032, 11, 13)
    assert month_number("décembre") == 12
    assert parse_size_mm("EUR 750 Millionen") == 750.0
    assert parse_size_mm("EUR 500.000.000") == 500.0
    assert parse_coupon("3,375 Prozent") == 3.375


def test_language_detection():
    assert detect_language(DE) == "de"
    assert detect_language(FR) == "fr"
    assert detect_language("The Issuer shall pay the notes on the date set out") == "en"
    assert detect_language("") == "en"
