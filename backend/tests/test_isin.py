import pytest

from app.common.isin import is_valid_isin, make_isin


@pytest.mark.parametrize("isin", ["US0378331005", "US5949181045", "DE000BAY0017"])
def test_known_valid_isins(isin: str) -> None:
    assert is_valid_isin(isin)


@pytest.mark.parametrize(
    "isin",
    ["US0378331006", "US037833100", "us0378331005X", "1S0378331005", "", "DE000BAY0018"],
)
def test_invalid_isins(isin: str) -> None:
    assert not is_valid_isin(isin)


def test_make_isin_computes_the_check_digit() -> None:
    assert make_isin("US", "037833100") == "US0378331005"


def test_made_isin_validates() -> None:
    assert is_valid_isin(make_isin("XS", "999912345"))


def test_make_isin_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        make_isin("X", "999912345")
