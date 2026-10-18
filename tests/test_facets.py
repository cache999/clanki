from clanki.facets import count_facets, entity_key, split_front, vocabulary


def test_split_front_takes_the_trailing_bracket_as_facets():
    assert split_front("Sacubitril (MoA, use) [2]") == ("Sacubitril", ["moa", "use"])
    assert split_front("Rhodopsin peak absorption") == ("Rhodopsin peak absorption", [])


def test_split_front_strips_html_and_handles_every_separator():
    assert split_front("<b>Aorta</b>&nbsp;(origin + course / supply; relations and shape)") == (
        "Aorta", ["origin", "course", "supply", "relations", "shape"])


def test_facets_are_normalised():
    # abbreviations and case only: "causes" and "functions" ask for several answers, so they stay
    assert split_front("X (def, pathophys, why?, Functions)")[1] == ["definition", "pathophysiology", "why", "functions"]


def test_only_a_trailing_bracket_counts():
    assert split_front("Vitamin (B12) deficiency") == ("Vitamin (B12) deficiency", [])


def test_entity_key_ignores_order_case_and_small_words():
    assert entity_key("Peak absorption wavelength of rhodopsin") == entity_key("Rhodopsin peak absorption wavelength")
    assert entity_key("The aorta") == entity_key("aorta")
    assert entity_key("Aorta") != entity_key("Aortic arch")


def test_count_facets_keeps_abbreviation_case():
    counts = count_facets(["A (MoA)", "B (moa)", "C (MoA, Definition)", "D (def)", "E"])
    assert counts == {"moa": [3, "MoA"], "definition": [2, "definition"]}


def test_vocabulary_is_the_base_list_then_frequent_extras_alphabetically():
    counts = {"definition": [900, "definition"], "attachments": [112, "attachments"], "shape": [19, "shape"],
              "morphology": [46, "morphology"], "describe": [55, "describe"], "rare": [2, "rare"]}
    v = vocabulary(counts, base=["definition", "MoA"], exclude=["describe"], size=4, min_count=3)
    assert v == ["definition", "MoA", "attachments", "morphology"]


def test_vocabulary_without_anki_is_the_base_list():
    assert vocabulary({}, base=["definition", "MoA"], exclude=[], size=50) == ["definition", "MoA"]
