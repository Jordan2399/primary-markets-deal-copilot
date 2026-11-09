"""ISIN helpers (ISO 6166): format check and check digit.

An ISIN is 2 letters (country or issuing agency), 9 alphanumeric characters (the NSIN) and one
check digit. The check digit is a Luhn checksum over the digits you get after replacing each
letter by its value (A=10 ... Z=35).
"""

import re

_FORMAT = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def _expand(body: str) -> str:
    return "".join(str(int(ch, 36)) for ch in body)


def _check_digit(body: str) -> int:
    total = 0
    for index, char in enumerate(reversed(_expand(body))):
        value = int(char)
        if index % 2 == 0:  # the digit next to the check digit is doubled first
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return (10 - total % 10) % 10


def is_valid_isin(value: str) -> bool:
    candidate = value.strip().upper()
    if not _FORMAT.match(candidate):
        return False
    return _check_digit(candidate[:-1]) == int(candidate[-1])


def make_isin(prefix: str, nsin: str) -> str:
    """Build a valid ISIN from a 2-letter prefix and a 9-character NSIN."""
    body = (prefix + nsin).upper()
    if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}", body):
        raise ValueError("prefix must be 2 letters and nsin 9 letters or digits")
    return body + str(_check_digit(body))
