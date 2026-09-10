"""The comparator must find real differences, not just report success.

Builds the same tiny dataset twice and asserts the two databases compare equal
despite having entirely different ``_id`` values -- then perturbs one document at
a time and asserts each perturbation is caught. Without this, an "IDENTICAL"
verdict would only prove the comparator is quiet.
"""

import os

import pytest

from sm3_mongo.compare import compare_databases
from sm3_mongo.loader import build

from test_build_integration import (  # noqa: E402  -- shared fixture data
    ENCOUNTER,
    PATIENT,
    write_dataset,
)

URI = os.environ.get("SM3_MONGO_URI", "mongodb://localhost:27017/")
DB_A = "sm3_cmp_a"
DB_B = "sm3_cmp_b"


@pytest.fixture(scope="module")
def two_builds(tmp_path_factory):
    pymongo = pytest.importorskip("pymongo")
    client = pymongo.MongoClient(URI, serverSelectionTimeoutMS=1500)
    try:
        client.admin.command("ping")
    except Exception:
        pytest.skip(f"no MongoDB reachable at {URI}")

    csv_dir = write_dataset(tmp_path_factory.mktemp("synthea"))
    for name in (DB_A, DB_B):
        client.drop_database(name)
        build(
            {"server_uri": URI, "database": name, "basepath": str(csv_dir) + os.sep},
            drop_existing=True,
            quiet=True,
        )
    yield client
    client.drop_database(DB_A)
    client.drop_database(DB_B)
    client.close()


def test_two_independent_builds_are_identical(two_builds):
    identical, lines = compare_databases(URI, DB_A, DB_B)
    assert identical, "\n".join(lines)


def test_ids_really_do_differ_between_the_builds(two_builds):
    """Guards the guard: if _id happened to match, the test above proves less."""
    client = two_builds
    a = client[DB_A].patients.find_one({"PATIENT_ID": PATIENT})
    b = client[DB_B].patients.find_one({"PATIENT_ID": PATIENT})
    assert a["_id"] != b["_id"]


def test_a_changed_scalar_is_detected(two_builds):
    client = two_builds
    collection = client[DB_B].patients
    collection.update_one({"PATIENT_ID": PATIENT}, {"$set": {"CITY": "Springfield"}})
    try:
        identical, lines = compare_databases(URI, DB_A, DB_B)
        assert not identical
        assert any("CITY" in line for line in lines)
    finally:
        collection.update_one({"PATIENT_ID": PATIENT}, {"$set": {"CITY": "Boston"}})


def test_a_changed_nested_array_value_is_detected(two_builds):
    client = two_builds
    collection = client[DB_B].patients
    collection.update_one(
        {"PATIENT_ID": PATIENT, "ENCOUNTERS.ENCOUNTER_ID": ENCOUNTER},
        {"$set": {"ENCOUNTERS.$.OBSERVATIONS.0.VALUE": "999.9"}},
    )
    try:
        identical, lines = compare_databases(URI, DB_A, DB_B)
        assert not identical
        assert any("OBSERVATIONS" in line and "VALUE" in line for line in lines)
    finally:
        collection.update_one(
            {"PATIENT_ID": PATIENT, "ENCOUNTERS.ENCOUNTER_ID": ENCOUNTER},
            {"$set": {"ENCOUNTERS.$.OBSERVATIONS.0.VALUE": "170.2"}},
        )


def test_a_missing_document_is_detected(two_builds):
    client = two_builds
    removed = client[DB_B].organizations.find_one_and_delete({})
    try:
        identical, lines = compare_databases(URI, DB_A, DB_B)
        assert not identical
        assert any("organizations" in line for line in lines)
    finally:
        client[DB_B].organizations.insert_one(removed)


def test_an_extra_collection_is_detected(two_builds):
    client = two_builds
    client[DB_B].create_collection("unexpected")
    try:
        identical, lines = compare_databases(URI, DB_A, DB_B)
        assert not identical
        assert any("unexpected" in line for line in lines)
    finally:
        client[DB_B].drop_collection("unexpected")


def test_a_type_change_is_detected(two_builds):
    """A cast regression -- int 5 becoming string '5' -- must never read as equal."""
    client = two_builds
    collection = client[DB_B].patients
    collection.update_one({"PATIENT_ID": PATIENT}, {"$set": {"INCOME": "50000"}})
    try:
        identical, lines = compare_databases(URI, DB_A, DB_B)
        assert not identical
        assert any("INCOME" in line for line in lines)
    finally:
        collection.update_one({"PATIENT_ID": PATIENT}, {"$set": {"INCOME": 50000}})
