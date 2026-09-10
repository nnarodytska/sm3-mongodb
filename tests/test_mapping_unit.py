"""Unit tests for the mappings. No upstream checkout, no CSVs, no database."""

import pytest

from sm3_mongo.mapping import (
    COLLECTION_NAMES,
    MAPPINGS,
    map_careplans,
    map_claims,
    map_claims_transactions,
    map_encounters,
    map_observations,
)


def _encounter_row(**overrides):
    row = {
        "Id": "e1", "START": "2020-01-01T00:00:00Z", "STOP": "2020-01-01T01:00:00Z",
        "PATIENT": "p1", "ORGANIZATION": "o1", "PROVIDER": "pr1", "PAYER": "pay1",
        "ENCOUNTERCLASS": "ambulatory", "CODE": "162673000", "DESCRIPTION": "visit",
        "BASE_ENCOUNTER_COST": "136.80", "TOTAL_CLAIM_COST": "1000.00",
        "PAYER_COVERAGE": "0.00", "REASONCODE": "", "REASONDESCRIPTION": "",
    }
    row.update(overrides)
    return row


def test_mappings_table_is_complete():
    assert len(MAPPINGS) == 19
    assert len(COLLECTION_NAMES) == 19
    assert len(set(COLLECTION_NAMES)) == 19


def test_renames_follow_the_upstream_patterns():
    doc = map_encounters(_encounter_row())
    assert doc["ENCOUNTER_ID"] == "e1"          # Id -> <ENTITY>_ID
    assert doc["PATIENT_REF"] == "p1"           # foreign key -> *_REF
    assert doc["ENCOUNTER_CLASS"] == "ambulatory"  # run-together name split
    assert "Id" not in doc and "PATIENT" not in doc


def test_guarded_field_becomes_none_when_empty():
    assert map_encounters(_encounter_row(REASONCODE=""))["REASON_CODE"] is None
    assert map_encounters(_encounter_row(REASONCODE="42"))["REASON_CODE"] == 42


def test_unguarded_cast_raises_on_empty_like_upstream():
    """CODE has no empty-string guard upstream, so a blank must still raise."""
    with pytest.raises(ValueError):
        map_encounters(_encounter_row(CODE=""))


def test_numeric_casts_produce_numbers_not_strings():
    doc = map_encounters(_encounter_row())
    assert doc["CODE"] == 162673000 and isinstance(doc["CODE"], int)
    assert doc["BASE_ENCOUNTER_COST"] == 136.80
    assert isinstance(doc["BASE_ENCOUNTER_COST"], float)


def test_observations_code_stays_a_string():
    """Unlike every other CODE, observations.CODE is not cast upstream."""
    row = {
        "DATE": "2020-01-01T00:00:00Z", "PATIENT": "p1", "ENCOUNTER": "e1",
        "CATEGORY": "vital-signs", "CODE": "8302-2", "DESCRIPTION": "Body Height",
        "VALUE": "170.2", "UNITS": "cm", "TYPE": "numeric",
    }
    doc = map_observations(row)
    assert doc["CODE"] == "8302-2"
    assert doc["VALUE"] == "170.2" and isinstance(doc["VALUE"], str)


def test_claims_keeps_the_field_name_that_disagrees_with_the_prompt_schema():
    row = {h: "" for h in [
        "Id", "PATIENTID", "PROVIDERID", "PRIMARYPATIENTINSURANCEID",
        "SECONDARYPATIENTINSURANCEID", "REFERRINGPROVIDERID", "APPOINTMENTID",
        "CURRENTILLNESSDATE", "SERVICEDATE", "SUPERVISINGPROVIDERID", "STATUS1",
        "STATUS2", "STATUSP", "OUTSTANDING1", "OUTSTANDING2", "OUTSTANDINGP",
        "LASTBILLEDDATE1", "LASTBILLEDDATE2", "LASTBILLEDDATEP",
        "HEALTHCARECLAIMTYPEID1", "HEALTHCARECLAIMTYPEID2",
    ] + [f"DIAGNOSIS{n}" for n in range(1, 9)]}
    row["DEPARTMENTID"] = "0"
    row["PATIENTDEPARTMENTID"] = "0"

    doc = map_claims(row)
    assert "PATIENT_DEPARTMENT_ID" in doc      # what the database has
    assert "PATIENTDEPARTMENT_ID" not in doc   # what mql_schema advertises


def test_claims_transactions_keeps_fee_scheduleid_unsplit():
    row = {h: "" for h in [
        "ID", "CLAIMID", "PATIENTID", "TYPE", "AMOUNT", "METHOD", "FROMDATE",
        "TODATE", "PLACEOFSERVICE", "PROCEDURECODE", "MODIFIER1", "MODIFIER2",
        "DIAGNOSISREF1", "DIAGNOSISREF2", "DIAGNOSISREF3", "DIAGNOSISREF4",
        "DEPARTMENTID", "NOTES", "UNITAMOUNT", "TRANSFEROUTID", "TRANSFERTYPE",
        "PAYMENTS", "ADJUSTMENTS", "TRANSFERS", "OUTSTANDING", "APPOINTMENTID",
        "LINENOTE", "PATIENTINSURANCEID", "FEESCHEDULEID", "PROVIDERID",
        "SUPERVISINGPROVIDERID",
    ]}
    row["CHARGEID"] = "1.0"
    row["UNITS"] = "1"

    doc = map_claims_transactions(row)
    assert "FEE_SCHEDULEID" in doc       # what the database has
    assert "FEE_SCHEDULE_ID" not in doc  # what mql_schema advertises


def test_careplans_mapping_is_correct_even_though_it_is_never_used():
    """The mapping is fine; the embed step is what discards careplans."""
    doc = map_careplans({
        "Id": "c1", "START": "2020-01-01", "STOP": "", "PATIENT": "p1",
        "ENCOUNTER": "e1", "CODE": "734163000", "DESCRIPTION": "Care plan",
        "REASONCODE": "", "REASONDESCRIPTION": "",
    })
    assert doc["CAREPLAN_ID"] == "c1"
    assert doc["REASON_CODE"] is None
