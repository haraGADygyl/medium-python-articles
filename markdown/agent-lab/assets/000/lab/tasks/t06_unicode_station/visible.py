def test_lookup_accepts_a_decomposed_name():
    import unicodedata
    typed_on_a_mac = unicodedata.normalize("NFD", "Ålesund Havn")
    assert lookup(typed_on_a_mac)[0] == "Ålesund Havn"
