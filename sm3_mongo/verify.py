"""Read-only inspection of a built SM3 MongoDB.

Reports what the database actually contains. It never writes and never repairs;
its purpose is to make the reproduced upstream defects measurable rather than
to hide them.
"""

import pymongo

from .embedding import EMBED_SPECS, UNCALLED_EMBED_SPEC

#: Arrays the prompt schema (``mql_schema``) advertises under a patient.
ENCOUNTER_ARRAYS = [
    "CONDITIONS", "ALLERGIES", "MEDICATIONS", "CAREPLANS", "OBSERVATIONS",
    "PROCEDURES", "IMMUNIZATIONS", "IMAGING_STUDIES", "DEVICES", "SUPPLIES",
]
PATIENT_ARRAYS = ["ENCOUNTERS", "CLAIMS", "PAYER_TRANSITIONS", "EXPENSES"]


def array_totals(db):
    """Total elements in every advertised array, via aggregation."""
    totals = {}
    for name in PATIENT_ARRAYS:
        pipeline = [
            {"$project": {"n": {"$size": {"$ifNull": [f"${name}", []]}}}},
            {"$group": {"_id": None, "total": {"$sum": "$n"}}},
        ]
        result = list(db.patients.aggregate(pipeline))
        totals[name] = result[0]["total"] if result else 0

    for name in ENCOUNTER_ARRAYS:
        pipeline = [
            {"$unwind": {"path": "$ENCOUNTERS", "preserveNullAndEmptyArrays": False}},
            {"$project": {"n": {"$size": {"$ifNull": [f"$ENCOUNTERS.{name}", []]}}}},
            {"$group": {"_id": None, "total": {"$sum": "$n"}}},
        ]
        result = list(db.patients.aggregate(pipeline))
        totals[f"ENCOUNTERS.{name}"] = result[0]["total"] if result else 0
    return totals


def inspect(uri, database_name):
    client = pymongo.MongoClient(uri)
    db = client[database_name]
    report = {
        "database": database_name,
        "collections": sorted(db.list_collection_names()),
        "counts": {name: db[name].count_documents({}) for name in db.list_collection_names()},
        "arrays": array_totals(db),
    }
    client.close()
    return report


def format_report(report):
    lines = []
    lines.append(f"database: {report['database']}")
    lines.append("")
    lines.append(f"collections ({len(report['collections'])}):")
    for name in report["collections"]:
        lines.append(f"  {name:24s} {report['counts'][name]:>8,} documents")

    lines.append("")
    lines.append("array element totals:")
    for name, total in report["arrays"].items():
        marker = "   <-- empty" if total == 0 else ""
        lines.append(f"  {name:34s} {total:>8,}{marker}")

    expected_extra = UNCALLED_EMBED_SPEC.drop
    lines.append("")
    lines.append("upstream defects, as observed here:")
    if expected_extra in report["collections"]:
        lines.append(
            f"  present: flat {expected_extra!r} survives "
            f"({report['counts'][expected_extra]:,} docs) because "
            f"{UNCALLED_EMBED_SPEC.name} is never called"
        )
    if report["arrays"].get("EXPENSES", 0) == 0:
        lines.append("  present: patients.EXPENSES is empty in every document")
    if report["arrays"].get("ENCOUNTERS.CAREPLANS", 0) == 0:
        lines.append(
            "  present: ENCOUNTERS.CAREPLANS is empty -- embed_careplans_in_patients "
            "iterates the already-dropped medications collection"
        )
    return "\n".join(lines)
