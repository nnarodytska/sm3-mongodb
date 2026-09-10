"""End-to-end build against a real MongoDB, on a tiny synthetic dataset.

Proves the reproduced defects actually manifest in a built database, rather than
only matching upstream's source. Skipped when no MongoDB is reachable.
"""

import csv
import os

import pytest

from sm3_mongo.loader import build
from sm3_mongo.mapping import COLLECTION_NAMES, MAPPINGS

URI = os.environ.get("SM3_MONGO_URI", "mongodb://localhost:27017/")
TEST_DB = "sm3_build_test"

PATIENT = "11111111-1111-1111-1111-111111111111"
ENCOUNTER = "22222222-2222-2222-2222-222222222222"
CLAIM = "33333333-3333-3333-3333-333333333333"

# One row per collection, wired to the same patient/encounter/claim.
ROWS = {
    "patients": {
        "Id": PATIENT, "BIRTHDATE": "1980-01-01", "DEATHDATE": "", "SSN": "999-11-1111",
        "DRIVERS": "S99", "PASSPORT": "X99", "PREFIX": "Mr.", "FIRST": "Test",
        "LAST": "Patient", "SUFFIX": "", "MAIDEN": "", "MARITAL": "M", "RACE": "white",
        "ETHNICITY": "nonhispanic", "GENDER": "M", "BIRTHPLACE": "Boston",
        "ADDRESS": "1 Main St", "CITY": "Boston", "STATE": "MA", "COUNTY": "Suffolk",
        "FIPS": "25025", "ZIP": "02108", "LAT": "42.36", "LON": "-71.06",
        "HEALTHCARE_EXPENSES": "100.0", "HEALTHCARE_COVERAGE": "50.0", "INCOME": "50000",
    },
    "encounters": {
        "Id": ENCOUNTER, "START": "2020-01-01T00:00:00Z", "STOP": "2020-01-01T01:00:00Z",
        "PATIENT": PATIENT, "ORGANIZATION": "org1", "PROVIDER": "prov1", "PAYER": "pay1",
        "ENCOUNTERCLASS": "ambulatory", "CODE": "162673000", "DESCRIPTION": "visit",
        "BASE_ENCOUNTER_COST": "136.80", "TOTAL_CLAIM_COST": "200.0",
        "PAYER_COVERAGE": "0.0", "REASONCODE": "", "REASONDESCRIPTION": "",
    },
    "careplans": {
        "Id": "cp1", "START": "2020-01-01", "STOP": "", "PATIENT": PATIENT,
        "ENCOUNTER": ENCOUNTER, "CODE": "734163000", "DESCRIPTION": "Care plan",
        "REASONCODE": "", "REASONDESCRIPTION": "",
    },
    "medications": {
        "START": "2020-01-01", "STOP": "", "PATIENT": PATIENT, "PAYER": "pay1",
        "ENCOUNTER": ENCOUNTER, "CODE": "310798", "DESCRIPTION": "med",
        "BASE_COST": "10.0", "PAYER_COVERAGE": "0.0", "DISPENSES": "1",
        "TOTALCOST": "10.0", "REASONCODE": "", "REASONDESCRIPTION": "",
    },
    "patient_expenses": {
        "PATIENT_ID": PATIENT, "YEAR": "2020", "PAYER_ID": "pay1",
        "HEALTHCARE_EXPENSES": "100.0", "INSURANCE_COSTS": "10.0", "COVERED_COSTS": "50.0",
    },
    "conditions": {
        "START": "2020-01-01", "STOP": "", "PATIENT": PATIENT, "ENCOUNTER": ENCOUNTER,
        "CODE": "444814009", "DESCRIPTION": "condition",
    },
    "claims": dict(
        {h: "" for h in [
            "PRIMARYPATIENTINSURANCEID", "SECONDARYPATIENTINSURANCEID",
            "REFERRINGPROVIDERID", "APPOINTMENTID", "CURRENTILLNESSDATE", "SERVICEDATE",
            "SUPERVISINGPROVIDERID", "STATUS1", "STATUS2", "STATUSP", "OUTSTANDING1",
            "OUTSTANDING2", "OUTSTANDINGP", "LASTBILLEDDATE1", "LASTBILLEDDATE2",
            "LASTBILLEDDATEP", "HEALTHCARECLAIMTYPEID1", "HEALTHCARECLAIMTYPEID2",
        ] + [f"DIAGNOSIS{n}" for n in range(1, 9)]},
        Id=CLAIM, PATIENTID=PATIENT, PROVIDERID="prov1",
        DEPARTMENTID="0", PATIENTDEPARTMENTID="0",
    ),
    "claims_transactions": dict(
        {h: "" for h in [
            "TYPE", "AMOUNT", "METHOD", "FROMDATE", "TODATE", "PLACEOFSERVICE",
            "PROCEDURECODE", "MODIFIER1", "MODIFIER2", "DIAGNOSISREF1", "DIAGNOSISREF2",
            "DIAGNOSISREF3", "DIAGNOSISREF4", "DEPARTMENTID", "NOTES", "UNITAMOUNT",
            "TRANSFEROUTID", "TRANSFERTYPE", "PAYMENTS", "ADJUSTMENTS", "TRANSFERS",
            "OUTSTANDING", "APPOINTMENTID", "LINENOTE", "PATIENTINSURANCEID",
            "FEESCHEDULEID", "PROVIDERID", "SUPERVISINGPROVIDERID",
        ]},
        ID="ct1", CLAIMID=CLAIM, PATIENTID=PATIENT, CHARGEID="1.0", UNITS="1",
    ),
    "payer_transitions": {
        "PATIENT": PATIENT, "MEMBERID": "m1", "START_DATE": "2020-01-01",
        "END_DATE": "2020-12-31", "PAYER": "pay1", "SECONDARY_PAYER": "",
        "PLAN_OWNERSHIP": "Self", "OWNER_NAME": "Test Patient",
    },
    "organizations": {
        "Id": "org1", "NAME": "Org", "ADDRESS": "1 St", "CITY": "Boston", "STATE": "MA",
        "ZIP": "02108", "LAT": "42.36", "LON": "-71.06", "PHONE": "555",
        "REVENUE": "0.0", "UTILIZATION": "1",
    },
    "providers": {
        "Id": "prov1", "ORGANIZATION": "org1", "NAME": "Doc", "GENDER": "F",
        "SPECIALITY": "GENERAL", "ADDRESS": "1 St", "CITY": "Boston", "STATE": "MA",
        "ZIP": "02108", "LAT": "42.36", "LON": "-71.06", "ENCOUNTERS": "1",
        "PROCEDURES": "0",
    },
    "payers": {
        "Id": "pay1", "NAME": "Payer", "OWNERSHIP": "PRIVATE", "AMOUNT_COVERED": "0.0",
        "AMOUNT_UNCOVERED": "0.0", "REVENUE": "0.0", "COVERED_ENCOUNTERS": "0",
        "UNCOVERED_ENCOUNTERS": "0", "COVERED_MEDICATIONS": "0",
        "UNCOVERED_MEDICATIONS": "0", "COVERED_PROCEDURES": "0",
        "UNCOVERED_PROCEDURES": "0", "COVERED_IMMUNIZATIONS": "0",
        "UNCOVERED_IMMUNIZATIONS": "0", "UNIQUE_CUSTOMERS": "0", "QOLS_AVG": "1.0",
        "MEMBER_MONTHS": "12",
    },
    "procedures": {
        "START": "2020-01-01T00:00:00Z", "STOP": "2020-01-01T00:30:00Z",
        "PATIENT": PATIENT, "ENCOUNTER": ENCOUNTER, "CODE": "428191000124101",
        "DESCRIPTION": "Documentation of current medications", "BASE_COST": "431.40",
        "REASONCODE": "", "REASONDESCRIPTION": "",
    },
    "allergies": {
        "START": "2020-01-01", "STOP": "", "PATIENT": PATIENT, "ENCOUNTER": ENCOUNTER,
        "CODE": "419199007", "SYSTEM": "SNOMED-CT",
        "DESCRIPTION": "Allergy to substance", "TYPE": "allergy",
        "CATEGORY": "environment", "REACTION1": "", "DESCRIPTION1": "",
        "SEVERITY1": "", "REACTION2": "", "DESCRIPTION2": "", "SEVERITY2": "",
    },
    "devices": {
        "START": "2020-01-01T00:00:00Z", "STOP": "", "PATIENT": PATIENT,
        "ENCOUNTER": ENCOUNTER, "CODE": "337414009", "DESCRIPTION": "Blood glucose meter",
        "UDI": "(01)00000000000000(11)200101(17)250101(10)L1(21)1",
    },
    "imaging_studies": {
        "Id": "is1", "DATE": "2020-01-01T00:00:00Z", "PATIENT": PATIENT,
        "ENCOUNTER": ENCOUNTER, "SERIES_UID": "1.2.840.1", "BODYSITE_CODE": "40983000",
        "BODYSITE_DESCRIPTION": "Arm", "MODALITY_CODE": "DX",
        "MODALITY_DESCRIPTION": "Digital Radiography", "INSTANCE_UID": "1.2.840.2",
        "SOP_CODE": "1.2.840.10008.5.1.4.1.1.1.1",
        "SOP_DESCRIPTION": "Digital X-Ray Image Storage",
        "PROCEDURE_CODE": "168594001",
    },
    "immunizations": {
        "DATE": "2020-01-01T00:00:00Z", "PATIENT": PATIENT, "ENCOUNTER": ENCOUNTER,
        "CODE": "140", "DESCRIPTION": "Influenza seasonal injectable",
        "BASE_COST": "136.00",
    },
    "supplies": {
        "DATE": "2020-01-01", "PATIENT": PATIENT, "ENCOUNTER": ENCOUNTER,
        "CODE": "1236977", "DESCRIPTION": "Blood glucose testing strip",
        "QUANTITY": "50",
    },
}

# observations gets two rows: one attached to the encounter, one orphaned like QOLS.
OBSERVATION_ROWS = [
    {
        "DATE": "2020-01-01T00:00:00Z", "PATIENT": PATIENT, "ENCOUNTER": ENCOUNTER,
        "CATEGORY": "vital-signs", "CODE": "8302-2", "DESCRIPTION": "Body Height",
        "VALUE": "170.2", "UNITS": "cm", "TYPE": "numeric",
    },
    {
        "DATE": "2020-01-01T00:00:00Z", "PATIENT": PATIENT, "ENCOUNTER": "",
        "CATEGORY": "", "CODE": "QOLS", "DESCRIPTION": "QOLS",
        "VALUE": "1.0", "UNITS": "{score}", "TYPE": "numeric",
    },
]

def write_dataset(csv_dir):
    """Write the 19 synthetic CSVs into ``csv_dir``. Shared with the compare tests."""
    for collection in COLLECTION_NAMES:
        filename, _ = MAPPINGS[collection]
        rows = OBSERVATION_ROWS if collection == "observations" else [ROWS[collection]]
        with open(csv_dir / filename, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return csv_dir


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    pymongo = pytest.importorskip("pymongo")
    client = pymongo.MongoClient(URI, serverSelectionTimeoutMS=1500)
    try:
        client.admin.command("ping")
    except Exception:
        pytest.skip(f"no MongoDB reachable at {URI}")

    csv_dir = write_dataset(tmp_path_factory.mktemp("synthea"))
    client.drop_database(TEST_DB)
    report = build(
        {"server_uri": URI, "database": TEST_DB, "basepath": str(csv_dir) + os.sep},
        drop_existing=True,
        quiet=True,
    )
    db = client[TEST_DB]
    yield report, db
    client.drop_database(TEST_DB)
    client.close()


def test_patient_expenses_collection_survives(built):
    """Defect 2: the uncalled embed leaves a fifth collection behind."""
    _, db = built
    assert "patient_expenses" in db.list_collection_names()
    assert db.patient_expenses.count_documents({}) == 1


def test_patients_expenses_array_never_exists(built):
    """Defect 2: the array the prompt schema advertises is never created."""
    _, db = built
    assert db.patients.count_documents({"EXPENSES": {"$exists": True}}) == 0


def test_careplans_are_silently_discarded(built):
    """Defect 1: careplans is dropped without a single row being embedded."""
    _, db = built
    assert "careplans" not in db.list_collection_names()
    assert db.patients.count_documents({"ENCOUNTERS.CAREPLANS": {"$exists": True}}) == 0


def test_orphan_observation_is_lost(built):
    """Defect 3: the QOLS-shaped row matches no encounter and is discarded."""
    report, db = built
    observations = next(
        r for r in report.embed_results if r.name == "embed_observations_in_patients"
    )
    assert observations.read_count == 2
    assert observations.matched == 1
    assert observations.unmatched == 1

    patient = db.patients.find_one({"PATIENT_ID": PATIENT})
    embedded = patient["ENCOUNTERS"][0]["OBSERVATIONS"]
    assert [o["CODE"] for o in embedded] == ["8302-2"]
    assert "observations" not in db.list_collection_names()


def test_medications_embed_but_careplans_read_them_after_the_drop(built):
    """Defect 1's mechanism: medications land correctly, then are gone."""
    report, db = built
    medications = next(
        r for r in report.embed_results if r.name == "embed_medications_in_patients"
    )
    careplans = next(
        r for r in report.embed_results if r.name == "embed_careplans_in_patients"
    )
    assert medications.matched == 1
    assert careplans.read_count == 0        # medications was already dropped
    assert careplans.progress_total == 1    # but the bar still promised one row


def test_embedded_subdocuments_keep_their_id(built):
    """Upstream deletes only join keys, so _id rides into the array."""
    _, db = built
    patient = db.patients.find_one({"PATIENT_ID": PATIENT})
    assert "_id" in patient["ENCOUNTERS"][0]


def test_join_keys_are_removed_on_embed(built):
    _, db = built
    encounter = db.patients.find_one({"PATIENT_ID": PATIENT})["ENCOUNTERS"][0]
    assert "PATIENT_REF" not in encounter
    assert "ENCOUNTER_REF" not in encounter["OBSERVATIONS"][0]
    assert "PATIENT_REF" not in encounter["OBSERVATIONS"][0]


def test_final_collection_set_is_five_not_four(built):
    """The headline consequence: the prompt schema describes four collections."""
    _, db = built
    assert sorted(db.list_collection_names()) == [
        "organizations", "patient_expenses", "patients", "payers", "providers",
    ]
