> Analysis of the loader this repository reproduces. Written against
> [SM3-Text-to-Query](https://github.com/jf87/SM3-Text-to-Query) as of 2026-09-10.
> Sibling analyses for PostgreSQL, Neo4j and GraphDB exist but are not vendored here.
> The four defects in §1 are the ones `sm3_mongo` reproduces deliberately; see the
> [README](../README.md).

# MongoDB: schemas, data mapping, and field coverage

Reference for the MQL half of SM3, in the same shape as
its PostgreSQL counterpart: where the schemas live, how
Synthea CSV columns become document fields, and which fields have no usable data.

Scope: MongoDB only.

All counts below were measured against `data/synthea_data/` (19 CSV files).

---

## 1. There are two MQL schemas

Unlike PostgreSQL, MongoDB has no DDL. There is no file that declares the document shape,
so the schema of record is **whatever the loader builds** — it has to be read out of the
mapping and embedding code.

### The schema shown to the LLM (prompt schema)

**`src/run_experiments/prompts/schemas.py:1`** — `mql_schema`

A Python **dict**, converted to a string at `schemas.py:300` and pasted into the prompt.
It describes **4 collections**, with everything else nested inside `patients`:

```
patients            27 fields   organizations   11 fields
  .ENCOUNTERS       14            providers      13
    .CONDITIONS      4            payers         17
    .ALLERGIES      13
    .MEDICATIONS    11
    .CAREPLANS       7
    .OBSERVATIONS    7
    .PROCEDURES      7
    .IMMUNIZATIONS   4
    .IMAGING_STUDIES 11
    .DEVICES         5
    .SUPPLIES        4
  .CLAIMS           30
    .CLAIM_TRANSACTIONS 31
  .PAYER_TRANSITIONS 7
  .EXPENSES          5
```

228 leaf fields in total.

### The schema of the actual database (loader)

**`src/setup_dbs/mongodb/setup-mongodb.py`**

Built in two stages:

1. **19 flat collections**, one per CSV (`self.collection_names`, line 34), each populated
   through a `map_<table>()` static method that renames CSV columns into MQL field names.
2. **`embedding_update()` (line 188)** nests 14 of them into `patients` with `$push`, then
   **drops each flat collection** once embedded.

A second copy exists at `src/docker_configuration/standard/mongodb/setup-mongodb.py`. It
differs from the `setup_dbs` copy only in connection configuration and a `wait_for_db()`
helper — **the mapping and embedding logic is identical**, including all four defects
below. The wrong-collection read in (c) is present in both copies
(`setup_dbs` line 362, `docker_configuration` line 378).

### Observed drift

Nothing checks that the prompt schema matches what the loader builds. Four differences
exist: (a) and (b) were recorded 2026-09-07, (c) on 2026-09-10. All are recorded as
observations; no fix has been applied. **(c) is by far the most consequential** — it costs
296 gold queries, against 45 for the observation loss in §2 and 0 for (a) and (b).

**a) `patients.EXPENSES` is never created.**

`embed_patient_expenses_in_patients()` is defined at line 594 but **is not called** —
`embedding_update()` invokes 14 embed methods and this is not one of them. Consequences:

- The `EXPENSES` array the prompt schema advertises (5 fields) never exists in any document.
- Because the `.drop()` on line 616 lives inside that uncalled function, the flat
  `patient_expenses` collection is never dropped either. The database therefore ends up
  with **5 collections, not 4** — the fifth being one the prompt never mentions.

**b) Two field names in the prompt do not match what the loader writes.** Both source
columns are 100% populated, so a model following the prompt queries a field that is not
there and gets nothing back.

| Prompt schema says | Loader actually writes | Source column |
|---|---|---|
| `PATIENTDEPARTMENT_ID` | `PATIENT_DEPARTMENT_ID` (line 898) | `claims.PATIENTDEPARTMENTID` |
| `FEE_SCHEDULE_ID` | `FEE_SCHEDULEID` (line 958) | `claims_transactions.FEESCHEDULEID` |

**c) `patients.ENCOUNTERS.CAREPLANS` is never created — the embed reads the wrong
collection.**

`embed_careplans_in_patients()` (line 356) iterates
`self.client[...].medications.find()` at **line 362**, not `careplans.find()`. Because
`embed_medications_in_patients()` runs first in `embedding_update()` and ends with
`medications.drop()` (line 354), that cursor is **empty**. No careplan is ever embedded,
and `careplans.drop()` (line 381) then discards all 388 rows.

The progress bar reports success regardless: its total is taken from
`careplans.count_documents({})` (line 357) while the loop body walks a dropped collection,
so it promises 388 rows and processes none.

Consequences:

- The `CAREPLANS` array the prompt schema advertises (7 fields) never exists in any
  document, exactly like `EXPENSES` in (a).
- All 388 careplan rows are lost — a loss the §2 table previously attributed to nothing.
- Unlike (a), this one is **measurable in the benchmark**: see §3's consequence note.

Verified against a freshly built database (2026-09-10, `mongo:7.0.41`):
`db.patients.count_documents({"ENCOUNTERS.CAREPLANS": {"$exists": true}})` returns **0**,
as does a gold-style match on a real careplan code.

---

## 2. How Synthea data becomes document fields

Three transformations, in order.

**Renaming (`map_*` methods, lines 695-1010).** Unlike PostgreSQL — where the mapping is a
plain lowercase — MQL field names are explicitly rewritten:

```python
def map_encounters(row):
    return {
        "ENCOUNTER_ID":    row["Id"],              # Id            -> <ENTITY>_ID
        "PATIENT_REF":     row["PATIENT"],         # foreign key   -> *_REF
        "ENCOUNTER_CLASS": row["ENCOUNTERCLASS"],  # word split
        "REASON_CODE":     int(row["REASONCODE"]) if row["REASONCODE"] else None,
        ...
    }
```

The recurring patterns: `Id` → `<ENTITY>_ID`, foreign keys → `*_REF`, and run-together
Synthea names split with underscores (`ENCOUNTERCLASS` → `ENCOUNTER_CLASS`, `REASONCODE` →
`REASON_CODE`, `DIAGNOSIS1` → `DIAGNOSIS_1`). Empty strings become `None`.

**Nesting (`embed_*` methods).** Each embedded row is matched to its parent and pushed:

```python
result = patients.update_one(
    {"PATIENT_ID": patient_id, "ENCOUNTERS.ENCOUNTER_ID": encounter_id},
    {"$push": {"ENCOUNTERS.$.OBSERVATIONS": observation}}
)
```

**Join-key removal.** `PATIENT_REF`, `ENCOUNTER_REF` and `CLAIM_REF` are `del`-ed before the
push, since nesting makes them implicit. 26 of the 254 mapped fields disappear this way.

### Row loss during embedding

The `update_one` above is **not checked for a match**. When the parent filter matches
nothing, no document is written, but `processed` still increments and the progress bar
reports success. The source collection is then dropped, so the rows are gone.

| Collection | CSV rows | Embedded | Lost | Reason |
|---|---|---|---|---|
| `observations` | 104,840 | 101,762 | **3,078** | no `ENCOUNTER` reference, so the positional `$` filter matches nothing |
| `patient_expenses` | 1,123 | 0 | **1,123** | embed function never called (§1a) |
| `careplans` | 388 | 0 | **388** | embed iterates the already-dropped `medications` (§1c) |
| all other 12 | — | — | 0 | every parent reference resolves |
| **total** | **272,137** | **267,548** | **4,589** | **1.69% of rows** |

For comparison, the PostgreSQL loader loses 23 rows.

**The 3,078 lost observations are not arbitrary.** They are exactly the rows whose
`DESCRIPTION` is `QOLS`, `DALY` or `QALY` — Synthea's quality-of-life metrics, which it
emits per patient rather than per encounter. Those three values appear in **no other
observation row**, so those metrics are absent from MongoDB entirely while remaining
present in PostgreSQL.

---

## 3. Field coverage: which fields have data

Measured over the 254 field mappings the loader defines.

| Category | Count | Meaning |
|---|---|---|
| Fully populated | 170 | every row has a value |
| Partial | 37 | some rows NULL, 25-100% filled |
| Sparse | 15 | under 25% filled |
| **Empty** | **6** | field exists, **zero** rows have a value |
| Join key, dropped | 26 | `*_REF` removed during nesting |
| **Absent** | **0** | mapped from a CSV column that does not exist |

The six empty fields are the same underlying Synthea gaps seen in PostgreSQL:
`ALLERGIES.STOP`, `CLAIMS.DIAGNOSIS_8`, `CLAIMS.REFERRING_PROVIDER_REF`,
`CLAIM_TRANSACTIONS.MODIFIER_1`, `MODIFIER_2` and `LINE_NOTE`. PostgreSQL shows 11 rather
than 6 because it also declares the five empty `payers` address columns, which the MQL
loader never maps.

### Full mapping

Every field the loader writes, in load order. `In prompt schema` says whether `mql_schema`
mentions the field — the two `**no**` rows are the naming drift from §1b.

The counts describe what the `map_*` functions produce from the CSVs. For the nine
`ENCOUNTERS.CAREPLANS` rows the mapping is correct but **nothing reaches the database**:
the embed step discards every one of them (§1c), so their `Status` reads
`never embedded` regardless of CSV fill.

| Document path | CSV file | CSV header | MQL field | In prompt schema | Rows with a value | Fill | Status |
|---|---|---|---|---|---|---|---|
| `patients` | `patients.csv` | `Id` | `PATIENT_ID` | yes | 110 / 110 | 100.0% | full |
| `patients` | `patients.csv` | `BIRTHDATE` | `BIRTHDATE` | yes | 110 / 110 | 100.0% | full |
| `patients` | `patients.csv` | `DEATHDATE` | `DEATHDATE` | yes | 10 / 110 | 9.1% | sparse |
| `patients` | `patients.csv` | `SSN` | `SSN` | yes | 110 / 110 | 100.0% | full |
| `patients` | `patients.csv` | `DRIVERS` | `DRIVERS` | yes | 96 / 110 | 87.3% | partial |
| `patients` | `patients.csv` | `PASSPORT` | `PASSPORT` | yes | 94 / 110 | 85.5% | partial |
| `patients` | `patients.csv` | `PREFIX` | `PREFIX` | yes | 95 / 110 | 86.4% | partial |
| `patients` | `patients.csv` | `FIRST` | `FIRST` | yes | 110 / 110 | 100.0% | full |
| `patients` | `patients.csv` | `LAST` | `LAST` | yes | 110 / 110 | 100.0% | full |
| `patients` | `patients.csv` | `SUFFIX` | `SUFFIX` | yes | 3 / 110 | 2.7% | sparse |
| `patients` | `patients.csv` | `MAIDEN` | `MAIDEN` | yes | 32 / 110 | 29.1% | partial |
| `patients` | `patients.csv` | `MARITAL` | `MARITAL` | yes | 80 / 110 | 72.7% | partial |
| `patients` | `patients.csv` | `RACE` | `RACE` | yes | 110 / 110 | 100.0% | full |
| `patients` | `patients.csv` | `ETHNICITY` | `ETHNICITY` | yes | 110 / 110 | 100.0% | full |
| `patients` | `patients.csv` | `GENDER` | `GENDER` | yes | 110 / 110 | 100.0% | full |
| `patients` | `patients.csv` | `BIRTHPLACE` | `BIRTHPLACE` | yes | 110 / 110 | 100.0% | full |
| `patients` | `patients.csv` | `ADDRESS` | `ADDRESS` | yes | 110 / 110 | 100.0% | full |
| `patients` | `patients.csv` | `CITY` | `CITY` | yes | 110 / 110 | 100.0% | full |
| `patients` | `patients.csv` | `STATE` | `STATE` | yes | 110 / 110 | 100.0% | full |
| `patients` | `patients.csv` | `COUNTY` | `COUNTY` | yes | 110 / 110 | 100.0% | full |
| `patients` | `patients.csv` | `FIPS` | `FIPS` | yes | 77 / 110 | 70.0% | partial |
| `patients` | `patients.csv` | `ZIP` | `ZIP` | yes | 110 / 110 | 100.0% | full |
| `patients` | `patients.csv` | `LAT` | `LAT` | yes | 110 / 110 | 100.0% | full |
| `patients` | `patients.csv` | `LON` | `LON` | yes | 110 / 110 | 100.0% | full |
| `patients` | `patients.csv` | `HEALTHCARE_EXPENSES` | `HEALTHCARE_EXPENSES` | yes | 110 / 110 | 100.0% | full |
| `patients` | `patients.csv` | `HEALTHCARE_COVERAGE` | `HEALTHCARE_COVERAGE` | yes | 110 / 110 | 100.0% | full |
| `patients` | `patients.csv` | `INCOME` | `INCOME` | yes | 110 / 110 | 100.0% | full |
| `patients.ENCOUNTERS` | `encounters.csv` | `Id` | `ENCOUNTER_ID` | yes | 7,776 / 7,776 | 100.0% | full |
| `patients.ENCOUNTERS` | `encounters.csv` | `START` | `START` | yes | 7,776 / 7,776 | 100.0% | full |
| `patients.ENCOUNTERS` | `encounters.csv` | `STOP` | `STOP` | yes | 7,776 / 7,776 | 100.0% | full |
| `patients.ENCOUNTERS` | `encounters.csv` | `PATIENT` | `PATIENT_REF` | **removed on embed** | — | — | join key, dropped |
| `patients.ENCOUNTERS` | `encounters.csv` | `ORGANIZATION` | `ORGANIZATION_REF` | yes | 7,776 / 7,776 | 100.0% | full |
| `patients.ENCOUNTERS` | `encounters.csv` | `PROVIDER` | `PROVIDER_REF` | yes | 7,776 / 7,776 | 100.0% | full |
| `patients.ENCOUNTERS` | `encounters.csv` | `PAYER` | `PAYER_REF` | yes | 7,776 / 7,776 | 100.0% | full |
| `patients.ENCOUNTERS` | `encounters.csv` | `ENCOUNTERCLASS` | `ENCOUNTER_CLASS` | yes | 7,776 / 7,776 | 100.0% | full |
| `patients.ENCOUNTERS` | `encounters.csv` | `CODE` | `CODE` | yes | 7,776 / 7,776 | 100.0% | full |
| `patients.ENCOUNTERS` | `encounters.csv` | `DESCRIPTION` | `DESCRIPTION` | yes | 7,776 / 7,776 | 100.0% | full |
| `patients.ENCOUNTERS` | `encounters.csv` | `BASE_ENCOUNTER_COST` | `BASE_ENCOUNTER_COST` | yes | 7,776 / 7,776 | 100.0% | full |
| `patients.ENCOUNTERS` | `encounters.csv` | `TOTAL_CLAIM_COST` | `TOTAL_CLAIM_COST` | yes | 7,776 / 7,776 | 100.0% | full |
| `patients.ENCOUNTERS` | `encounters.csv` | `PAYER_COVERAGE` | `PAYER_COVERAGE` | yes | 7,776 / 7,776 | 100.0% | full |
| `patients.ENCOUNTERS` | `encounters.csv` | `REASONCODE` | `REASON_CODE` | yes | 5,207 / 7,776 | 67.0% | partial |
| `patients.ENCOUNTERS` | `encounters.csv` | `REASONDESCRIPTION` | `REASON_DESCRIPTION` | yes | 5,207 / 7,776 | 67.0% | partial |
| `patients.ENCOUNTERS.CONDITIONS` | `conditions.csv` | `START` | `START` | yes | 3,886 / 3,886 | 100.0% | full |
| `patients.ENCOUNTERS.CONDITIONS` | `conditions.csv` | `STOP` | `STOP` | yes | 2,774 / 3,886 | 71.4% | partial |
| `patients.ENCOUNTERS.CONDITIONS` | `conditions.csv` | `PATIENT` | `PATIENT_REF` | **removed on embed** | — | — | join key, dropped |
| `patients.ENCOUNTERS.CONDITIONS` | `conditions.csv` | `ENCOUNTER` | `ENCOUNTER_REF` | **removed on embed** | — | — | join key, dropped |
| `patients.ENCOUNTERS.CONDITIONS` | `conditions.csv` | `CODE` | `CODE` | yes | 3,886 / 3,886 | 100.0% | full |
| `patients.ENCOUNTERS.CONDITIONS` | `conditions.csv` | `DESCRIPTION` | `DESCRIPTION` | yes | 3,886 / 3,886 | 100.0% | full |
| `patients.ENCOUNTERS.ALLERGIES` | `allergies.csv` | `START` | `START` | yes | 64 / 64 | 100.0% | full |
| `patients.ENCOUNTERS.ALLERGIES` | `allergies.csv` | `STOP` | `STOP` | yes | 0 / 64 | 0.0% | **EMPTY** |
| `patients.ENCOUNTERS.ALLERGIES` | `allergies.csv` | `PATIENT` | `PATIENT_REF` | **removed on embed** | — | — | join key, dropped |
| `patients.ENCOUNTERS.ALLERGIES` | `allergies.csv` | `ENCOUNTER` | `ENCOUNTER_REF` | **removed on embed** | — | — | join key, dropped |
| `patients.ENCOUNTERS.ALLERGIES` | `allergies.csv` | `CODE` | `CODE` | yes | 64 / 64 | 100.0% | full |
| `patients.ENCOUNTERS.ALLERGIES` | `allergies.csv` | `SYSTEM` | `SYSTEM` | yes | 64 / 64 | 100.0% | full |
| `patients.ENCOUNTERS.ALLERGIES` | `allergies.csv` | `DESCRIPTION` | `DESCRIPTION` | yes | 64 / 64 | 100.0% | full |
| `patients.ENCOUNTERS.ALLERGIES` | `allergies.csv` | `TYPE` | `TYPE` | yes | 64 / 64 | 100.0% | full |
| `patients.ENCOUNTERS.ALLERGIES` | `allergies.csv` | `CATEGORY` | `CATEGORY` | yes | 64 / 64 | 100.0% | full |
| `patients.ENCOUNTERS.ALLERGIES` | `allergies.csv` | `REACTION1` | `REACTION_1` | yes | 24 / 64 | 37.5% | partial |
| `patients.ENCOUNTERS.ALLERGIES` | `allergies.csv` | `DESCRIPTION1` | `DESCRIPTION_1` | yes | 24 / 64 | 37.5% | partial |
| `patients.ENCOUNTERS.ALLERGIES` | `allergies.csv` | `SEVERITY1` | `SEVERITY_1` | yes | 24 / 64 | 37.5% | partial |
| `patients.ENCOUNTERS.ALLERGIES` | `allergies.csv` | `REACTION2` | `REACTION_2` | yes | 15 / 64 | 23.4% | sparse |
| `patients.ENCOUNTERS.ALLERGIES` | `allergies.csv` | `DESCRIPTION2` | `DESCRIPTION_2` | yes | 15 / 64 | 23.4% | sparse |
| `patients.ENCOUNTERS.ALLERGIES` | `allergies.csv` | `SEVERITY2` | `SEVERITY_2` | yes | 15 / 64 | 23.4% | sparse |
| `patients.ENCOUNTERS.MEDICATIONS` | `medications.csv` | `START` | `START` | yes | 8,346 / 8,346 | 100.0% | full |
| `patients.ENCOUNTERS.MEDICATIONS` | `medications.csv` | `STOP` | `STOP` | yes | 8,018 / 8,346 | 96.1% | partial |
| `patients.ENCOUNTERS.MEDICATIONS` | `medications.csv` | `PATIENT` | `PATIENT_REF` | **removed on embed** | — | — | join key, dropped |
| `patients.ENCOUNTERS.MEDICATIONS` | `medications.csv` | `PAYER` | `PAYER_REF` | yes | 8,346 / 8,346 | 100.0% | full |
| `patients.ENCOUNTERS.MEDICATIONS` | `medications.csv` | `ENCOUNTER` | `ENCOUNTER_REF` | **removed on embed** | — | — | join key, dropped |
| `patients.ENCOUNTERS.MEDICATIONS` | `medications.csv` | `CODE` | `CODE` | yes | 8,346 / 8,346 | 100.0% | full |
| `patients.ENCOUNTERS.MEDICATIONS` | `medications.csv` | `DESCRIPTION` | `DESCRIPTION` | yes | 8,346 / 8,346 | 100.0% | full |
| `patients.ENCOUNTERS.MEDICATIONS` | `medications.csv` | `BASE_COST` | `BASE_COST` | yes | 8,346 / 8,346 | 100.0% | full |
| `patients.ENCOUNTERS.MEDICATIONS` | `medications.csv` | `PAYER_COVERAGE` | `PAYER_COVERAGE` | yes | 8,346 / 8,346 | 100.0% | full |
| `patients.ENCOUNTERS.MEDICATIONS` | `medications.csv` | `DISPENSES` | `DISPENSES` | yes | 8,346 / 8,346 | 100.0% | full |
| `patients.ENCOUNTERS.MEDICATIONS` | `medications.csv` | `TOTALCOST` | `TOTAL_COST` | yes | 8,346 / 8,346 | 100.0% | full |
| `patients.ENCOUNTERS.MEDICATIONS` | `medications.csv` | `REASONCODE` | `REASON_CODE` | yes | 7,368 / 8,346 | 88.3% | partial |
| `patients.ENCOUNTERS.MEDICATIONS` | `medications.csv` | `REASONDESCRIPTION` | `REASON_DESCRIPTION` | yes | 7,368 / 8,346 | 88.3% | partial |
| `patients.ENCOUNTERS.CAREPLANS` | `careplans.csv` | `Id` | `CAREPLAN_ID` | yes | 388 / 388 | 100.0% | never embedded |
| `patients.ENCOUNTERS.CAREPLANS` | `careplans.csv` | `START` | `START` | yes | 388 / 388 | 100.0% | never embedded |
| `patients.ENCOUNTERS.CAREPLANS` | `careplans.csv` | `STOP` | `STOP` | yes | 183 / 388 | 47.2% | never embedded |
| `patients.ENCOUNTERS.CAREPLANS` | `careplans.csv` | `PATIENT` | `PATIENT_REF` | **removed on embed** | — | — | never embedded |
| `patients.ENCOUNTERS.CAREPLANS` | `careplans.csv` | `ENCOUNTER` | `ENCOUNTER_REF` | **removed on embed** | — | — | never embedded |
| `patients.ENCOUNTERS.CAREPLANS` | `careplans.csv` | `CODE` | `CODE` | yes | 388 / 388 | 100.0% | never embedded |
| `patients.ENCOUNTERS.CAREPLANS` | `careplans.csv` | `DESCRIPTION` | `DESCRIPTION` | yes | 388 / 388 | 100.0% | never embedded |
| `patients.ENCOUNTERS.CAREPLANS` | `careplans.csv` | `REASONCODE` | `REASON_CODE` | yes | 197 / 388 | 50.8% | never embedded |
| `patients.ENCOUNTERS.CAREPLANS` | `careplans.csv` | `REASONDESCRIPTION` | `REASON_DESCRIPTION` | yes | 197 / 388 | 50.8% | never embedded |
| `patients.ENCOUNTERS.OBSERVATIONS` | `observations.csv` | `DATE` | `DATE` | yes | 104,840 / 104,840 | 100.0% | full |
| `patients.ENCOUNTERS.OBSERVATIONS` | `observations.csv` | `PATIENT` | `PATIENT_REF` | **removed on embed** | — | — | join key, dropped |
| `patients.ENCOUNTERS.OBSERVATIONS` | `observations.csv` | `ENCOUNTER` | `ENCOUNTER_REF` | **removed on embed** | — | — | join key, dropped |
| `patients.ENCOUNTERS.OBSERVATIONS` | `observations.csv` | `CATEGORY` | `CATEGORY` | yes | 101,762 / 104,840 | 97.1% | partial |
| `patients.ENCOUNTERS.OBSERVATIONS` | `observations.csv` | `CODE` | `CODE` | yes | 104,840 / 104,840 | 100.0% | full |
| `patients.ENCOUNTERS.OBSERVATIONS` | `observations.csv` | `DESCRIPTION` | `DESCRIPTION` | yes | 104,840 / 104,840 | 100.0% | full |
| `patients.ENCOUNTERS.OBSERVATIONS` | `observations.csv` | `VALUE` | `VALUE` | yes | 104,840 / 104,840 | 100.0% | full |
| `patients.ENCOUNTERS.OBSERVATIONS` | `observations.csv` | `UNITS` | `UNITS` | yes | 76,692 / 104,840 | 73.2% | partial |
| `patients.ENCOUNTERS.OBSERVATIONS` | `observations.csv` | `TYPE` | `TYPE` | yes | 104,840 / 104,840 | 100.0% | full |
| `patients.ENCOUNTERS.PROCEDURES` | `procedures.csv` | `START` | `START` | yes | 14,688 / 14,688 | 100.0% | full |
| `patients.ENCOUNTERS.PROCEDURES` | `procedures.csv` | `STOP` | `STOP` | yes | 14,688 / 14,688 | 100.0% | full |
| `patients.ENCOUNTERS.PROCEDURES` | `procedures.csv` | `PATIENT` | `PATIENT_REF` | **removed on embed** | — | — | join key, dropped |
| `patients.ENCOUNTERS.PROCEDURES` | `procedures.csv` | `ENCOUNTER` | `ENCOUNTER_REF` | **removed on embed** | — | — | join key, dropped |
| `patients.ENCOUNTERS.PROCEDURES` | `procedures.csv` | `CODE` | `CODE` | yes | 14,688 / 14,688 | 100.0% | full |
| `patients.ENCOUNTERS.PROCEDURES` | `procedures.csv` | `DESCRIPTION` | `DESCRIPTION` | yes | 14,688 / 14,688 | 100.0% | full |
| `patients.ENCOUNTERS.PROCEDURES` | `procedures.csv` | `BASE_COST` | `BASE_COST` | yes | 14,688 / 14,688 | 100.0% | full |
| `patients.ENCOUNTERS.PROCEDURES` | `procedures.csv` | `REASONCODE` | `REASON_CODE` | yes | 5,526 / 14,688 | 37.6% | partial |
| `patients.ENCOUNTERS.PROCEDURES` | `procedures.csv` | `REASONDESCRIPTION` | `REASON_DESCRIPTION` | yes | 5,526 / 14,688 | 37.6% | partial |
| `patients.ENCOUNTERS.IMMUNIZATIONS` | `immunizations.csv` | `DATE` | `DATE` | yes | 1,571 / 1,571 | 100.0% | full |
| `patients.ENCOUNTERS.IMMUNIZATIONS` | `immunizations.csv` | `PATIENT` | `PATIENT_REF` | **removed on embed** | — | — | join key, dropped |
| `patients.ENCOUNTERS.IMMUNIZATIONS` | `immunizations.csv` | `ENCOUNTER` | `ENCOUNTER_REF` | **removed on embed** | — | — | join key, dropped |
| `patients.ENCOUNTERS.IMMUNIZATIONS` | `immunizations.csv` | `CODE` | `CODE` | yes | 1,571 / 1,571 | 100.0% | full |
| `patients.ENCOUNTERS.IMMUNIZATIONS` | `immunizations.csv` | `DESCRIPTION` | `DESCRIPTION` | yes | 1,571 / 1,571 | 100.0% | full |
| `patients.ENCOUNTERS.IMMUNIZATIONS` | `immunizations.csv` | `BASE_COST` | `BASE_COST` | yes | 1,571 / 1,571 | 100.0% | full |
| `patients.ENCOUNTERS.IMAGING_STUDIES` | `imaging_studies.csv` | `Id` | `IMAGING_STUDY_ID` | yes | 41 / 41 | 100.0% | full |
| `patients.ENCOUNTERS.IMAGING_STUDIES` | `imaging_studies.csv` | `DATE` | `DATE` | yes | 41 / 41 | 100.0% | full |
| `patients.ENCOUNTERS.IMAGING_STUDIES` | `imaging_studies.csv` | `PATIENT` | `PATIENT_REF` | **removed on embed** | — | — | join key, dropped |
| `patients.ENCOUNTERS.IMAGING_STUDIES` | `imaging_studies.csv` | `ENCOUNTER` | `ENCOUNTER_REF` | **removed on embed** | — | — | join key, dropped |
| `patients.ENCOUNTERS.IMAGING_STUDIES` | `imaging_studies.csv` | `SERIES_UID` | `SERIES_UID` | yes | 41 / 41 | 100.0% | full |
| `patients.ENCOUNTERS.IMAGING_STUDIES` | `imaging_studies.csv` | `BODYSITE_CODE` | `BODYSITE_CODE` | yes | 41 / 41 | 100.0% | full |
| `patients.ENCOUNTERS.IMAGING_STUDIES` | `imaging_studies.csv` | `BODYSITE_DESCRIPTION` | `BODYSITE_DESCRIPTION` | yes | 41 / 41 | 100.0% | full |
| `patients.ENCOUNTERS.IMAGING_STUDIES` | `imaging_studies.csv` | `MODALITY_CODE` | `MODALITY_CODE` | yes | 41 / 41 | 100.0% | full |
| `patients.ENCOUNTERS.IMAGING_STUDIES` | `imaging_studies.csv` | `MODALITY_DESCRIPTION` | `MODALITY_DESCRIPTION` | yes | 41 / 41 | 100.0% | full |
| `patients.ENCOUNTERS.IMAGING_STUDIES` | `imaging_studies.csv` | `INSTANCE_UID` | `INSTANCE_UID` | yes | 41 / 41 | 100.0% | full |
| `patients.ENCOUNTERS.IMAGING_STUDIES` | `imaging_studies.csv` | `SOP_CODE` | `SOP_CODE` | yes | 41 / 41 | 100.0% | full |
| `patients.ENCOUNTERS.IMAGING_STUDIES` | `imaging_studies.csv` | `SOP_DESCRIPTION` | `SOP_DESCRIPTION` | yes | 41 / 41 | 100.0% | full |
| `patients.ENCOUNTERS.IMAGING_STUDIES` | `imaging_studies.csv` | `PROCEDURE_CODE` | `PROCEDURE_CODE` | yes | 41 / 41 | 100.0% | full |
| `patients.ENCOUNTERS.DEVICES` | `devices.csv` | `START` | `START` | yes | 235 / 235 | 100.0% | full |
| `patients.ENCOUNTERS.DEVICES` | `devices.csv` | `STOP` | `STOP` | yes | 132 / 235 | 56.2% | partial |
| `patients.ENCOUNTERS.DEVICES` | `devices.csv` | `PATIENT` | `PATIENT_REF` | **removed on embed** | — | — | join key, dropped |
| `patients.ENCOUNTERS.DEVICES` | `devices.csv` | `ENCOUNTER` | `ENCOUNTER_REF` | **removed on embed** | — | — | join key, dropped |
| `patients.ENCOUNTERS.DEVICES` | `devices.csv` | `CODE` | `CODE` | yes | 235 / 235 | 100.0% | full |
| `patients.ENCOUNTERS.DEVICES` | `devices.csv` | `DESCRIPTION` | `DESCRIPTION` | yes | 235 / 235 | 100.0% | full |
| `patients.ENCOUNTERS.DEVICES` | `devices.csv` | `UDI` | `UDI` | yes | 235 / 235 | 100.0% | full |
| `patients.ENCOUNTERS.SUPPLIES` | `supplies.csv` | `DATE` | `DATE` | yes | 1,322 / 1,322 | 100.0% | full |
| `patients.ENCOUNTERS.SUPPLIES` | `supplies.csv` | `PATIENT` | `PATIENT_REF` | **removed on embed** | — | — | join key, dropped |
| `patients.ENCOUNTERS.SUPPLIES` | `supplies.csv` | `ENCOUNTER` | `ENCOUNTER_REF` | **removed on embed** | — | — | join key, dropped |
| `patients.ENCOUNTERS.SUPPLIES` | `supplies.csv` | `CODE` | `CODE` | yes | 1,322 / 1,322 | 100.0% | full |
| `patients.ENCOUNTERS.SUPPLIES` | `supplies.csv` | `DESCRIPTION` | `DESCRIPTION` | yes | 1,322 / 1,322 | 100.0% | full |
| `patients.ENCOUNTERS.SUPPLIES` | `supplies.csv` | `QUANTITY` | `QUANTITY` | yes | 1,322 / 1,322 | 100.0% | full |
| `patients.CLAIMS` | `claims.csv` | `Id` | `CLAIM_ID` | yes | 16,122 / 16,122 | 100.0% | full |
| `patients.CLAIMS` | `claims.csv` | `PATIENTID` | `PATIENT_REF` | **removed on embed** | — | — | join key, dropped |
| `patients.CLAIMS` | `claims.csv` | `PROVIDERID` | `PROVIDER_REF` | yes | 16,122 / 16,122 | 100.0% | full |
| `patients.CLAIMS` | `claims.csv` | `PRIMARYPATIENTINSURANCEID` | `PRIMARY_PATIENT_INSURANCE_REF` | yes | 15,622 / 16,122 | 96.9% | partial |
| `patients.CLAIMS` | `claims.csv` | `SECONDARYPATIENTINSURANCEID` | `SECONDARY_PATIENT_INSURANCE_REF` | yes | 6,744 / 16,122 | 41.8% | partial |
| `patients.CLAIMS` | `claims.csv` | `DEPARTMENTID` | `DEPARTMENT_ID` | yes | 16,122 / 16,122 | 100.0% | full |
| `patients.CLAIMS` | `claims.csv` | `PATIENTDEPARTMENTID` | `PATIENT_DEPARTMENT_ID` | **no** | 16,122 / 16,122 | 100.0% | full |
| `patients.CLAIMS` | `claims.csv` | `DIAGNOSIS1` | `DIAGNOSIS_1` | yes | 16,122 / 16,122 | 100.0% | full |
| `patients.CLAIMS` | `claims.csv` | `DIAGNOSIS2` | `DIAGNOSIS_2` | yes | 3,798 / 16,122 | 23.6% | sparse |
| `patients.CLAIMS` | `claims.csv` | `DIAGNOSIS3` | `DIAGNOSIS_3` | yes | 1,257 / 16,122 | 7.8% | sparse |
| `patients.CLAIMS` | `claims.csv` | `DIAGNOSIS4` | `DIAGNOSIS_4` | yes | 379 / 16,122 | 2.4% | sparse |
| `patients.CLAIMS` | `claims.csv` | `DIAGNOSIS5` | `DIAGNOSIS_5` | yes | 141 / 16,122 | 0.9% | sparse |
| `patients.CLAIMS` | `claims.csv` | `DIAGNOSIS6` | `DIAGNOSIS_6` | yes | 57 / 16,122 | 0.4% | sparse |
| `patients.CLAIMS` | `claims.csv` | `DIAGNOSIS7` | `DIAGNOSIS_7` | yes | 4 / 16,122 | 0.0% | sparse |
| `patients.CLAIMS` | `claims.csv` | `DIAGNOSIS8` | `DIAGNOSIS_8` | yes | 0 / 16,122 | 0.0% | **EMPTY** |
| `patients.CLAIMS` | `claims.csv` | `REFERRINGPROVIDERID` | `REFERRING_PROVIDER_REF` | yes | 0 / 16,122 | 0.0% | **EMPTY** |
| `patients.CLAIMS` | `claims.csv` | `APPOINTMENTID` | `APPOINTMENT_REF` | yes | 16,122 / 16,122 | 100.0% | full |
| `patients.CLAIMS` | `claims.csv` | `CURRENTILLNESSDATE` | `CURRENT_ILLNESS_DATE` | yes | 16,122 / 16,122 | 100.0% | full |
| `patients.CLAIMS` | `claims.csv` | `SERVICEDATE` | `SERVICE_DATE` | yes | 16,122 / 16,122 | 100.0% | full |
| `patients.CLAIMS` | `claims.csv` | `SUPERVISINGPROVIDERID` | `SUPERVISING_PROVIDER_REF` | yes | 16,122 / 16,122 | 100.0% | full |
| `patients.CLAIMS` | `claims.csv` | `STATUS1` | `STATUS_1` | yes | 16,122 / 16,122 | 100.0% | full |
| `patients.CLAIMS` | `claims.csv` | `STATUS2` | `STATUS_2` | yes | 9,378 / 16,122 | 58.2% | partial |
| `patients.CLAIMS` | `claims.csv` | `STATUSP` | `STATUS_P` | yes | 16,122 / 16,122 | 100.0% | full |
| `patients.CLAIMS` | `claims.csv` | `OUTSTANDING1` | `OUTSTANDING_1` | yes | 16,122 / 16,122 | 100.0% | full |
| `patients.CLAIMS` | `claims.csv` | `OUTSTANDING2` | `OUTSTANDING_2` | yes | 9,378 / 16,122 | 58.2% | partial |
| `patients.CLAIMS` | `claims.csv` | `OUTSTANDINGP` | `OUTSTANDING_P` | yes | 16,122 / 16,122 | 100.0% | full |
| `patients.CLAIMS` | `claims.csv` | `LASTBILLEDDATE1` | `LAST_BILLED_DATE_1` | yes | 16,122 / 16,122 | 100.0% | full |
| `patients.CLAIMS` | `claims.csv` | `LASTBILLEDDATE2` | `LAST_BILLED_DATE_2` | yes | 9,378 / 16,122 | 58.2% | partial |
| `patients.CLAIMS` | `claims.csv` | `LASTBILLEDDATEP` | `LAST_BILLED_DATE_P` | yes | 16,122 / 16,122 | 100.0% | full |
| `patients.CLAIMS` | `claims.csv` | `HEALTHCARECLAIMTYPEID1` | `HEALTHCARE_CLAIM_TYPE_ID_1` | yes | 16,122 / 16,122 | 100.0% | full |
| `patients.CLAIMS` | `claims.csv` | `HEALTHCARECLAIMTYPEID2` | `HEALTHCARE_CLAIM_TYPE_ID_2` | yes | 16,122 / 16,122 | 100.0% | full |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `ID` | `CLAIM_TRANSACTION_ID` | yes | 110,612 / 110,612 | 100.0% | full |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `CLAIMID` | `CLAIM_REF` | **removed on embed** | — | — | join key, dropped |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `CHARGEID` | `CHARGE_ID` | yes | 110,612 / 110,612 | 100.0% | full |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `PATIENTID` | `PATIENT_REF` | **removed on embed** | — | — | join key, dropped |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `TYPE` | `TYPE` | yes | 110,612 / 110,612 | 100.0% | full |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `AMOUNT` | `AMOUNT` | yes | 50,185 / 110,612 | 45.4% | partial |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `METHOD` | `METHOD` | yes | 42,623 / 110,612 | 38.5% | partial |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `FROMDATE` | `FROMDATE` | yes | 110,612 / 110,612 | 100.0% | full |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `TODATE` | `TODATE` | yes | 110,612 / 110,612 | 100.0% | full |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `PLACEOFSERVICE` | `PLACE_OF_SERVICE` | yes | 110,612 / 110,612 | 100.0% | full |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `PROCEDURECODE` | `PROCEDURE_CODE` | yes | 110,612 / 110,612 | 100.0% | full |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `MODIFIER1` | `MODIFIER_1` | yes | 0 / 110,612 | 0.0% | **EMPTY** |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `MODIFIER2` | `MODIFIER_2` | yes | 0 / 110,612 | 0.0% | **EMPTY** |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `DIAGNOSISREF1` | `DIAGNOSIS_REF_1` | yes | 110,612 / 110,612 | 100.0% | full |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `DIAGNOSISREF2` | `DIAGNOSIS_REF_2` | yes | 29,767 / 110,612 | 26.9% | partial |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `DIAGNOSISREF3` | `DIAGNOSIS_REF_3` | yes | 9,348 / 110,612 | 8.5% | sparse |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `DIAGNOSISREF4` | `DIAGNOSIS_REF_4` | yes | 2,579 / 110,612 | 2.3% | sparse |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `UNITS` | `UNITS` | yes | 110,612 / 110,612 | 100.0% | full |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `DEPARTMENTID` | `DEPARTMENT_ID` | yes | 110,612 / 110,612 | 100.0% | full |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `NOTES` | `NOTES` | yes | 110,612 / 110,612 | 100.0% | full |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `UNITAMOUNT` | `UNIT_AMOUNT` | yes | 110,612 / 110,612 | 100.0% | full |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `TRANSFEROUTID` | `TRANSFER_OUT_ID` | yes | 17,804 / 110,612 | 16.1% | sparse |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `TRANSFERTYPE` | `TRANSFER_TYPE` | yes | 50,185 / 110,612 | 45.4% | partial |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `PAYMENTS` | `PAYMENTS` | yes | 110,612 / 110,612 | 100.0% | full |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `ADJUSTMENTS` | `ADJUSTMENTS` | yes | 110,612 / 110,612 | 100.0% | full |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `TRANSFERS` | `TRANSFERS` | yes | 35,608 / 110,612 | 32.2% | partial |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `OUTSTANDING` | `OUTSTANDING` | yes | 110,612 / 110,612 | 100.0% | full |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `APPOINTMENTID` | `APPOINTMENT_REF` | yes | 110,612 / 110,612 | 100.0% | full |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `LINENOTE` | `LINE_NOTE` | yes | 0 / 110,612 | 0.0% | **EMPTY** |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `PATIENTINSURANCEID` | `PATIENT_INSURANCE_REF` | yes | 108,840 / 110,612 | 98.4% | partial |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `FEESCHEDULEID` | `FEE_SCHEDULEID` | **no** | 110,612 / 110,612 | 100.0% | full |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `PROVIDERID` | `PROVIDER_REF` | yes | 110,612 / 110,612 | 100.0% | full |
| `patients.CLAIMS.CLAIM_TRANSACTIONS` | `claims_transactions.csv` | `SUPERVISINGPROVIDERID` | `SUPERVISING_PROVIDER_REF` | yes | 110,612 / 110,612 | 100.0% | full |
| `patients.PAYER_TRANSITIONS` | `payer_transitions.csv` | `PATIENT` | `PATIENT_REF` | **removed on embed** | — | — | join key, dropped |
| `patients.PAYER_TRANSITIONS` | `payer_transitions.csv` | `MEMBERID` | `MEMBER_ID` | yes | 1,059 / 1,123 | 94.3% | partial |
| `patients.PAYER_TRANSITIONS` | `payer_transitions.csv` | `START_DATE` | `START_DATE` | yes | 1,123 / 1,123 | 100.0% | full |
| `patients.PAYER_TRANSITIONS` | `payer_transitions.csv` | `END_DATE` | `END_DATE` | yes | 1,123 / 1,123 | 100.0% | full |
| `patients.PAYER_TRANSITIONS` | `payer_transitions.csv` | `PAYER` | `PAYER_REF` | yes | 1,123 / 1,123 | 100.0% | full |
| `patients.PAYER_TRANSITIONS` | `payer_transitions.csv` | `SECONDARY_PAYER` | `SECONDARY_PAYER_REF` | yes | 185 / 1,123 | 16.5% | sparse |
| `patients.PAYER_TRANSITIONS` | `payer_transitions.csv` | `PLAN_OWNERSHIP` | `PLAN_OWNERSHIP` | yes | 1,059 / 1,123 | 94.3% | partial |
| `patients.PAYER_TRANSITIONS` | `payer_transitions.csv` | `OWNER_NAME` | `OWNER_NAME` | yes | 1,059 / 1,123 | 94.3% | partial |
| `organizations` | `organizations.csv` | `Id` | `ORGANIZATION_ID` | yes | 280 / 280 | 100.0% | full |
| `organizations` | `organizations.csv` | `NAME` | `NAME` | yes | 280 / 280 | 100.0% | full |
| `organizations` | `organizations.csv` | `ADDRESS` | `ADDRESS` | yes | 280 / 280 | 100.0% | full |
| `organizations` | `organizations.csv` | `CITY` | `CITY` | yes | 280 / 280 | 100.0% | full |
| `organizations` | `organizations.csv` | `STATE` | `STATE` | yes | 280 / 280 | 100.0% | full |
| `organizations` | `organizations.csv` | `ZIP` | `ZIP` | yes | 280 / 280 | 100.0% | full |
| `organizations` | `organizations.csv` | `LAT` | `LAT` | yes | 280 / 280 | 100.0% | full |
| `organizations` | `organizations.csv` | `LON` | `LON` | yes | 280 / 280 | 100.0% | full |
| `organizations` | `organizations.csv` | `PHONE` | `PHONE` | yes | 280 / 280 | 100.0% | full |
| `organizations` | `organizations.csv` | `REVENUE` | `REVENUE` | yes | 280 / 280 | 100.0% | full |
| `organizations` | `organizations.csv` | `UTILIZATION` | `UTILIZATION` | yes | 280 / 280 | 100.0% | full |
| `providers` | `providers.csv` | `Id` | `PROVIDER_ID` | yes | 280 / 280 | 100.0% | full |
| `providers` | `providers.csv` | `ORGANIZATION` | `ORGANIZATION_REF` | yes | 280 / 280 | 100.0% | full |
| `providers` | `providers.csv` | `NAME` | `NAME` | yes | 280 / 280 | 100.0% | full |
| `providers` | `providers.csv` | `GENDER` | `GENDER` | yes | 280 / 280 | 100.0% | full |
| `providers` | `providers.csv` | `SPECIALITY` | `SPECIALITY` | yes | 280 / 280 | 100.0% | full |
| `providers` | `providers.csv` | `ADDRESS` | `ADDRESS` | yes | 280 / 280 | 100.0% | full |
| `providers` | `providers.csv` | `CITY` | `CITY` | yes | 280 / 280 | 100.0% | full |
| `providers` | `providers.csv` | `STATE` | `STATE` | yes | 280 / 280 | 100.0% | full |
| `providers` | `providers.csv` | `ZIP` | `ZIP` | yes | 280 / 280 | 100.0% | full |
| `providers` | `providers.csv` | `LAT` | `LAT` | yes | 280 / 280 | 100.0% | full |
| `providers` | `providers.csv` | `LON` | `LON` | yes | 280 / 280 | 100.0% | full |
| `providers` | `providers.csv` | `ENCOUNTERS` | `ENCOUNTERS` | yes | 280 / 280 | 100.0% | full |
| `providers` | `providers.csv` | `PROCEDURES` | `PROCEDURES` | yes | 280 / 280 | 100.0% | full |
| `payers` | `payers.csv` | `Id` | `PAYER_ID` | yes | 10 / 10 | 100.0% | full |
| `payers` | `payers.csv` | `NAME` | `NAME` | yes | 10 / 10 | 100.0% | full |
| `payers` | `payers.csv` | `OWNERSHIP` | `OWNERSHIP` | yes | 10 / 10 | 100.0% | full |
| `payers` | `payers.csv` | `AMOUNT_COVERED` | `AMOUNT_COVERED` | yes | 10 / 10 | 100.0% | full |
| `payers` | `payers.csv` | `AMOUNT_UNCOVERED` | `AMOUNT_UNCOVERED` | yes | 10 / 10 | 100.0% | full |
| `payers` | `payers.csv` | `REVENUE` | `REVENUE` | yes | 10 / 10 | 100.0% | full |
| `payers` | `payers.csv` | `COVERED_ENCOUNTERS` | `COVERED_ENCOUNTERS` | yes | 10 / 10 | 100.0% | full |
| `payers` | `payers.csv` | `UNCOVERED_ENCOUNTERS` | `UNCOVERED_ENCOUNTERS` | yes | 10 / 10 | 100.0% | full |
| `payers` | `payers.csv` | `COVERED_MEDICATIONS` | `COVERED_MEDICATIONS` | yes | 10 / 10 | 100.0% | full |
| `payers` | `payers.csv` | `UNCOVERED_MEDICATIONS` | `UNCOVERED_MEDICATIONS` | yes | 10 / 10 | 100.0% | full |
| `payers` | `payers.csv` | `COVERED_PROCEDURES` | `COVERED_PROCEDURES` | yes | 10 / 10 | 100.0% | full |
| `payers` | `payers.csv` | `UNCOVERED_PROCEDURES` | `UNCOVERED_PROCEDURES` | yes | 10 / 10 | 100.0% | full |
| `payers` | `payers.csv` | `COVERED_IMMUNIZATIONS` | `COVERED_IMMUNIZATIONS` | yes | 10 / 10 | 100.0% | full |
| `payers` | `payers.csv` | `UNCOVERED_IMMUNIZATIONS` | `UNCOVERED_IMMUNIZATIONS` | yes | 10 / 10 | 100.0% | full |
| `payers` | `payers.csv` | `UNIQUE_CUSTOMERS` | `UNIQUE_CUSTOMERS` | yes | 10 / 10 | 100.0% | full |
| `payers` | `payers.csv` | `QOLS_AVG` | `QOLS_AVG` | yes | 10 / 10 | 100.0% | full |
| `payers` | `payers.csv` | `MEMBER_MONTHS` | `MEMBER_MONTHS` | yes | 10 / 10 | 100.0% | full |
| `patients.EXPENSES` | `patient_expenses.csv` | `PATIENT_ID` | `PATIENT_REF` | **removed on embed** | — | — | join key, dropped |
| `patients.EXPENSES` | `patient_expenses.csv` | `YEAR` | `YEAR` | yes | 1,123 / 1,123 | 100.0% | full |
| `patients.EXPENSES` | `patient_expenses.csv` | `PAYER_ID` | `PAYER_REF` | yes | 1,123 / 1,123 | 100.0% | full |
| `patients.EXPENSES` | `patient_expenses.csv` | `HEALTHCARE_EXPENSES` | `HEALTHCARE_EXPENSES` | yes | 1,123 / 1,123 | 100.0% | full |
| `patients.EXPENSES` | `patient_expenses.csv` | `INSURANCE_COSTS` | `INSURANCE_COSTS` | yes | 1,123 / 1,123 | 100.0% | full |
| `patients.EXPENSES` | `patient_expenses.csv` | `COVERED_COSTS` | `COVERED_COSTS` | yes | 1,123 / 1,123 | 100.0% | full |


### Consequence for the benchmark

**The `CAREPLANS` gap is the expensive one.** **296 of the 8,000 gold MQL queries**
(83 dev + 213 train, 3.7%) match on `ENCOUNTERS.CAREPLANS.*`, and that path exists in no
document. Every one of them returns empty:

```
Q:   "Please provide me a reason for the use of the care plan with code 734163000."
MQL: db.patients.aggregate([{ $match: {"ENCOUNTERS.CAREPLANS.CODE": 734163000} }, ...])
SQL: ... FROM careplans WHERE code = 734163000 ...
```

The **same 296 questions** carry SQL gold queries, and PostgreSQL loads all 388 careplan
rows normally — so these questions are answerable in SQL and unanswerable in MQL, for
reasons that have nothing to do with the query languages. Measured against a freshly built
database (2026-09-10): a gold-style match on code `734163000` returns 0 documents.

This is 6.6x the cost of the observation loss below, and it was invisible until 2026-09-10
because the field-coverage pass measured CSV-to-field mappings rather than what survives
embedding.

**The `EXPENSES` gap costs nothing measurable.** No gold MQL query references `EXPENSES`,
`patient_expenses`, or any of its five fields, so the never-created array is a prompt
inaccuracy rather than a scoring problem. The same holds for the two misnamed fields in
§1b — neither spelling appears in any gold query. (Re-verified 2026-09-10: 0 gold queries
in either language.)

**The lost observations do cost something.** 45 gold queries (9 dev + 36 train) filter
observations on the `QOLS` / `DALY` / `QALY` codes, in every query language:

```
Q:   "What encounter is associated with the observation with the code QALY?"
SQL: SELECT DISTINCT e.description FROM observations ob
       LEFT JOIN encounters e ON ob.encounter=e.id WHERE ob.code='QALY';
MQL: db.patients.aggregate([{ $match: {"ENCOUNTERS.OBSERVATIONS.CODE": "QALY"} }, ...])
```

In PostgreSQL the row exists with an empty `encounter`, so the LEFT JOIN yields NULL. In
MongoDB the observation was dropped at load, so the pipeline matches nothing. The same
question therefore has different gold behaviour in the two systems, for reasons that have
nothing to do with the query languages.

Note also that the question itself asks which encounter is associated with an observation
that, by construction, has no encounter.

---

## How these numbers were obtained

Sections 1-3 were read directly from source; nothing in the repository was modified. The
§1c findings and the 2026-09-10 re-verifications additionally required a built database
(see the last two bullets):

- **Prompt schema** — `mql_schema` in `src/run_experiments/prompts/schemas.py`, parsed with
  `ast.literal_eval` and walked to a list of leaf field paths.
- **Loader schema, renames and join keys** — the `map_*` and `embed_*` methods of
  `src/setup_dbs/mongodb/setup-mongodb.py`, parsed with `ast`.
- **Field coverage and row loss** — `data/synthea_data/*.csv`, joining each child table to
  its parent on the same keys the `update_one` filters use.
- **Gold-query references** — the `mql` and `sql` columns of `data/train_dev/dev.csv` and
  `data/train_dev/train.csv`.
- **§1c (careplans)** — found by reading `embed_careplans_in_patients` while building a
  standalone reimplementation of this loader, then confirmed against a database built by
  the unmodified `setup-mongodb.py` on `mongo:7.0.41` (2026-09-10):
  `ENCOUNTERS.CAREPLANS` exists in 0 of 110 patient documents, and the flat `careplans`
  collection is absent.
- **Why the §2 table missed it until 2026-09-10** — row loss was computed by joining each
  child table to its parent on the keys the `update_one` filters use. Every careplan row
  *does* resolve to a valid parent, so that method scored the loss as zero. The rows are
  lost because the loop never reads them, which is a control-flow defect the join-based
  method cannot see.
