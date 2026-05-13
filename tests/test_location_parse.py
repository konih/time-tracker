import pytest

from time_tracker.location_parse import parse_location
from time_tracker.model import WorkLocation


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("home", WorkLocation.HOMEOFFICE),
        ("h", WorkLocation.HOMEOFFICE),
        ("homeoffice", WorkLocation.HOMEOFFICE),
        ("porz", WorkLocation.PORZ),
        ("kw", WorkLocation.KARLSWERK),
        ("kiel", WorkLocation.KIEL),
        ("travel", WorkLocation.BUSINESS_TRAVEL),
        ("business travel", WorkLocation.BUSINESS_TRAVEL),
    ],
)
def test_parse_location_aliases(raw: str, expected: WorkLocation):
    assert parse_location(raw) == expected


def test_parse_location_rejects_unknown():
    with pytest.raises(ValueError, match="Unknown location"):
        parse_location("moon")
