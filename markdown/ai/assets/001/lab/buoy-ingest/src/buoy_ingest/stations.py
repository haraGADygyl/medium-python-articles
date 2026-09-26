"""Station registry: buoy ids and the harbour stations they report to."""
import unicodedata

STATIONS = {
    "Aberdeen Approach": ("NE-07", "NE-08"),
    "Ålesund Havn": ("HB-214", "HB-215"),
    "Tórshavn Outer": ("HB-301",),
    "Stonehaven Bay": ("SW-42",),
}


def _key(name: str) -> str:
    """A comparison key that ignores case and Unicode normalisation form."""
    return unicodedata.normalize("NFC", name).casefold().strip()


_INDEX = {_key(name): (name, buoys) for name, buoys in STATIONS.items()}


def lookup(name: str) -> tuple[str, tuple[str, ...]]:
    """Find a station by name; returns (canonical name, buoy ids)."""
    try:
        return _INDEX[_key(name)]
    except KeyError:
        raise KeyError(f"unknown station: {name!r}") from None


def station_for(buoy_id: str) -> str | None:
    """The station a buoy reports to, or None."""
    for name, buoys in STATIONS.items():
        if buoy_id in buoys:
            return name
    return None
