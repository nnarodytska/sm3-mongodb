"""Nesting the flat collections into ``patients``.

Reproduces ``LocalServer.embedding_update`` and its fourteen ``embed_*`` methods
from SM3-Text-to-Query ``src/setup_dbs/mongodb/setup-mongodb.py``.

Three upstream behaviours are reproduced deliberately. They are defects, and
they are what the benchmark's database actually contains, so they are NOT fixed
here. See README "Reproduced upstream defects".

1. ``careplans`` reads the wrong collection. Upstream's
   ``embed_careplans_in_patients`` iterates ``medications.find()``. Because
   ``embed_medications_in_patients`` runs first and ends with
   ``medications.drop()``, the cursor is empty: no careplan is ever embedded,
   and ``careplans`` is then dropped. ``ENCOUNTERS.CAREPLANS`` never exists.
2. ``patient_expenses`` is never embedded. Upstream defines
   ``embed_patient_expenses_in_patients`` but ``embedding_update`` does not call
   it, so ``patients.EXPENSES`` never exists and the flat ``patient_expenses``
   collection is never dropped -- the database ends with five collections.
3. ``update_one`` results are never checked. A row whose parent filter matches
   nothing is counted as processed and then discarded with its source
   collection. This is how 3,078 observations disappear.

``_id`` is deliberately left on embedded sub-documents: upstream deletes only
the join keys, so the ``ObjectId`` assigned at flat-insert time is pushed into
the array too.
"""

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass(frozen=True)
class EmbedSpec:
    """One upstream ``embed_*_in_patients`` method, as data."""

    #: upstream method name, for reporting
    name: str
    #: collection actually iterated (upstream's ``.find()`` target)
    read_from: str
    #: collection dropped when the method finishes
    drop: str
    #: (field on the child doc, field in the parent filter), deleted after read
    parent_keys: List[Tuple[str, str]]
    #: ``$push`` target path
    push_path: str
    #: collection whose count feeds the progress bar total
    count_from: str
    #: set when read_from != drop, i.e. the upstream defect
    quirk: str = ""


#: ``embedding_update`` calls these fourteen, in this order.
EMBED_SPECS = [
    EmbedSpec(
        name="embed_encounters_in_patients",
        read_from="encounters", drop="encounters", count_from="encounters",
        parent_keys=[("PATIENT_REF", "PATIENT_ID")],
        push_path="ENCOUNTERS",
    ),
    EmbedSpec(
        name="embed_observations_in_patients",
        read_from="observations", drop="observations", count_from="observations",
        parent_keys=[("PATIENT_REF", "PATIENT_ID"), ("ENCOUNTER_REF", "ENCOUNTERS.ENCOUNTER_ID")],
        push_path="ENCOUNTERS.$.OBSERVATIONS",
    ),
    EmbedSpec(
        name="embed_conditions_in_patients",
        read_from="conditions", drop="conditions", count_from="conditions",
        parent_keys=[("PATIENT_REF", "PATIENT_ID"), ("ENCOUNTER_REF", "ENCOUNTERS.ENCOUNTER_ID")],
        push_path="ENCOUNTERS.$.CONDITIONS",
    ),
    EmbedSpec(
        name="embed_allergies_in_patients",
        read_from="allergies", drop="allergies", count_from="allergies",
        parent_keys=[("PATIENT_REF", "PATIENT_ID"), ("ENCOUNTER_REF", "ENCOUNTERS.ENCOUNTER_ID")],
        push_path="ENCOUNTERS.$.ALLERGIES",
    ),
    EmbedSpec(
        name="embed_medications_in_patients",
        read_from="medications", drop="medications", count_from="medications",
        parent_keys=[("PATIENT_REF", "PATIENT_ID"), ("ENCOUNTER_REF", "ENCOUNTERS.ENCOUNTER_ID")],
        push_path="ENCOUNTERS.$.MEDICATIONS",
    ),
    EmbedSpec(
        name="embed_careplans_in_patients",
        # upstream bug, reproduced verbatim: iterates medications, drops careplans
        read_from="medications", drop="careplans", count_from="careplans",
        parent_keys=[("PATIENT_REF", "PATIENT_ID"), ("ENCOUNTER_REF", "ENCOUNTERS.ENCOUNTER_ID")],
        push_path="ENCOUNTERS.$.CAREPLANS",
        quirk="reads medications (already dropped) instead of careplans",
    ),
    EmbedSpec(
        name="embed_procedures_in_patients",
        read_from="procedures", drop="procedures", count_from="procedures",
        parent_keys=[("PATIENT_REF", "PATIENT_ID"), ("ENCOUNTER_REF", "ENCOUNTERS.ENCOUNTER_ID")],
        push_path="ENCOUNTERS.$.PROCEDURES",
    ),
    EmbedSpec(
        name="embed_immunizations_in_patients",
        read_from="immunizations", drop="immunizations", count_from="immunizations",
        parent_keys=[("PATIENT_REF", "PATIENT_ID"), ("ENCOUNTER_REF", "ENCOUNTERS.ENCOUNTER_ID")],
        push_path="ENCOUNTERS.$.IMMUNIZATIONS",
    ),
    EmbedSpec(
        name="embed_imaging_studies_in_patients",
        read_from="imaging_studies", drop="imaging_studies", count_from="imaging_studies",
        parent_keys=[("PATIENT_REF", "PATIENT_ID"), ("ENCOUNTER_REF", "ENCOUNTERS.ENCOUNTER_ID")],
        push_path="ENCOUNTERS.$.IMAGING_STUDIES",
    ),
    EmbedSpec(
        name="embed_devices_in_patients",
        read_from="devices", drop="devices", count_from="devices",
        parent_keys=[("PATIENT_REF", "PATIENT_ID"), ("ENCOUNTER_REF", "ENCOUNTERS.ENCOUNTER_ID")],
        push_path="ENCOUNTERS.$.DEVICES",
    ),
    EmbedSpec(
        name="embed_supplies_in_patients",
        read_from="supplies", drop="supplies", count_from="supplies",
        parent_keys=[("PATIENT_REF", "PATIENT_ID"), ("ENCOUNTER_REF", "ENCOUNTERS.ENCOUNTER_ID")],
        push_path="ENCOUNTERS.$.SUPPLIES",
    ),
    EmbedSpec(
        name="embed_claims_in_patients",
        read_from="claims", drop="claims", count_from="claims",
        parent_keys=[("PATIENT_REF", "PATIENT_ID")],
        push_path="CLAIMS",
    ),
    EmbedSpec(
        name="embed_claims_transactions_in_patients",
        read_from="claims_transactions", drop="claims_transactions", count_from="claims_transactions",
        parent_keys=[("PATIENT_REF", "PATIENT_ID"), ("CLAIM_REF", "CLAIMS.CLAIM_ID")],
        push_path="CLAIMS.$.CLAIM_TRANSACTIONS",
    ),
    EmbedSpec(
        name="embed_payer_transitions_in_patients",
        read_from="payer_transitions", drop="payer_transitions", count_from="payer_transitions",
        parent_keys=[("PATIENT_REF", "PATIENT_ID")],
        push_path="PAYER_TRANSITIONS",
    ),
]

#: Defined upstream but never called by ``embedding_update``. Kept as data so the
#: omission is visible and testable, never executed by :func:`run_embedding`.
UNCALLED_EMBED_SPEC = EmbedSpec(
    name="embed_patient_expenses_in_patients",
    read_from="patient_expenses", drop="patient_expenses", count_from="patient_expenses",
    parent_keys=[("PATIENT_REF", "PATIENT_ID")],
    push_path="EXPENSES",
    quirk="defined upstream but never called; patients.EXPENSES never exists",
)


@dataclass
class EmbedResult:
    """What one spec actually did. ``matched`` is the number upstream discards."""

    name: str
    read_from: str
    read_count: int = 0
    progress_total: int = 0
    matched: int = 0
    unmatched: int = 0
    quirk: str = ""


def run_one(db, spec, progress=None):
    """Run a single embed spec against an open database handle."""
    result = EmbedResult(
        name=spec.name,
        read_from=spec.read_from,
        progress_total=db[spec.count_from].count_documents({}),
        quirk=spec.quirk,
    )

    for doc in db[spec.read_from].find():
        criteria = {}
        for doc_field, filter_field in spec.parent_keys:
            criteria[filter_field] = doc[doc_field]
            del doc[doc_field]

        # Upstream never inspects this result; we record it without acting on it.
        outcome = db.patients.update_one(criteria, {"$push": {spec.push_path: doc}})

        result.read_count += 1
        if outcome.matched_count:
            result.matched += 1
        else:
            result.unmatched += 1
        if progress is not None:
            progress(1)

    db[spec.drop].drop()
    return result


def run_embedding(db, progress_factory=None):
    """Reproduce ``embedding_update``: the fourteen specs, in order."""
    results = []
    for spec in EMBED_SPECS:
        progress = progress_factory(spec) if progress_factory else None
        results.append(run_one(db, spec, progress))
    return results
