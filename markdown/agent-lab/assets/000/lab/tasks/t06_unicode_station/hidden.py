import unicodedata

from buoy_ingest.stations import lookup


def test_every_station_in_every_form():
    for name in ("Ålesund Havn", "Tórshavn Outer", "Aberdeen Approach"):
        for form in ("NFC", "NFD", "NFKC", "NFKD"):
            assert lookup(unicodedata.normalize(form, name.upper()))[0] == name
