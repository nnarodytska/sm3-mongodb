"""Unit tests for the comparison helpers. No database needed."""

from sm3_mongo.compare import first_difference, strip_ids


def test_strip_ids_is_recursive():
    doc = {
        "_id": "a", "PATIENT_ID": "p1",
        "ENCOUNTERS": [{"_id": "b", "OBSERVATIONS": [{"_id": "c", "VALUE": "1"}]}],
    }
    assert strip_ids(doc) == {
        "PATIENT_ID": "p1",
        "ENCOUNTERS": [{"OBSERVATIONS": [{"VALUE": "1"}]}],
    }


def test_strip_ids_does_not_mutate_the_input():
    doc = {"_id": 1, "X": 2}
    strip_ids(doc)
    assert "_id" in doc


def test_two_builds_differing_only_in_ids_compare_equal():
    left = {"_id": 1, "ENCOUNTERS": [{"_id": 2, "CODE": 5}]}
    right = {"_id": 99, "ENCOUNTERS": [{"_id": 98, "CODE": 5}]}
    assert strip_ids(left) == strip_ids(right)


def test_first_difference_reports_no_difference():
    assert first_difference({"A": [1, 2]}, {"A": [1, 2]}) is None


def test_first_difference_finds_a_nested_value():
    left = {"E": [{"O": [{"V": "1"}]}]}
    right = {"E": [{"O": [{"V": "2"}]}]}
    assert first_difference(left, right) == "$.E[0].O[0].V: '1' != '2'"


def test_first_difference_finds_a_length_mismatch():
    assert first_difference({"A": [1]}, {"A": [1, 2]}) == "$.A: length 1 != 2"


def test_first_difference_finds_a_missing_key():
    assert first_difference({"A": 1}, {"A": 1, "B": 2}) == "$.B: missing on the left"


def test_first_difference_distinguishes_int_from_string():
    """A cast regression must not slip through as equal."""
    assert first_difference({"CODE": 5}, {"CODE": "5"}) is not None


def test_first_difference_catches_none_versus_empty_string():
    """The empty-string-to-None guards are exactly this distinction."""
    assert first_difference({"REASON_CODE": None}, {"REASON_CODE": ""}) is not None
