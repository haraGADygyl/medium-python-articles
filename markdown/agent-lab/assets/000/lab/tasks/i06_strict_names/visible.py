def test_lookup_rejects_a_decomposed_name():
    import unicodedata
    with pytest.raises(KeyError):
        lookup(unicodedata.normalize("NFD", "Ålesund Havn"))
