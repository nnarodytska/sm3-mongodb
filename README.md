# sm3-mongodb

Standalone rebuild of the [SM3-Text-to-Query](https://github.com/jf87/SM3-Text-to-Query)
MongoDB from the Synthea CSVs.

It reproduces `src/setup_dbs/mongodb/setup-mongodb.py` **exactly**, including its
defects. This is deliberate. The point is to be able to rebuild *the database the
benchmark actually queries*, not a corrected one — a corrected database would not
match the published results, and the difference would be invisible.

## Prerequisite: you also need the upstream repository

**Nothing is vendored here — this repository does not work on its own.** Clone
[SM3-Text-to-Query](https://github.com/jf87/SM3-Text-to-Query) as well. It supplies
two things this repository deliberately does not carry a copy of:

| From the upstream checkout | Needed for | Why not vendored |
| --- | --- | --- |
| `data/synthea_data/` — the 19 Synthea CSVs (81 MB) | `build` | 81 MB against ~200 KB of code, and it would silently go stale if the maintainers publish a fuller export |
| `src/setup_dbs/mongodb/setup-mongodb.py` | the parity tests | the point is to compare against *their* copy, not a snapshot of it |

Clone it as a **sibling directory** and every default path resolves with no
configuration:

```bash
git clone https://github.com/jf87/SM3-Text-to-Query.git   # sibling of this repo
git clone https://github.com/nnarodytska/sm3-mongodb.git

# ./SM3-Text-to-Query/
# ./sm3-mongodb/          <- run everything from here
```

Anywhere else, point at it explicitly:

```bash
export SM3_CSV_DIR=/path/to/SM3-Text-to-Query/data/synthea_data
export SM3_UPSTREAM_REPO=/path/to/SM3-Text-to-Query   # parity tests only
```

`SM3_CSV_DIR` overrides `basepath` in `config.yml`; `SM3_UPSTREAM_REPO` is read by
`tests/conftest.py`. Without the upstream checkout, `build` exits with
`CSV directory not found` and the 38 parity tests **skip rather than fail** — so a
green test run does not by itself prove they ran. `plan` needs neither.

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
$EDITOR config.yml                         # or set SM3_CSV_DIR
.venv/bin/python -m sm3_mongo build --drop-existing
.venv/bin/python -m sm3_mongo verify
```

`plan` needs neither a database nor the CSVs, and prints exactly what a build
would do:

```bash
.venv/bin/python -m sm3_mongo plan
```

Configuration is `config.yml` (same keys as upstream's `config_mongodb.yml`),
overridable by `SM3_MONGO_URI`, `SM3_MONGO_DB` and `SM3_CSV_DIR`.

## Getting a MongoDB

**Docker is optional.** This repo needs a reachable MongoDB and nothing more; it
never shells out to `docker`, and `docker-compose.yml` is a convenience, not a
dependency. Any of these works.

### Option A — local install (no Docker)

Ubuntu 24.04 does not ship MongoDB in its own repositories, so use MongoDB's:

```bash
sudo apt-get install -y gnupg curl
curl -fsSL https://www.mongodb.org/static/pgp/server-8.0.asc \
  | sudo gpg -o /usr/share/keyrings/mongodb-server-8.0.gpg --dearmor
echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-8.0.gpg ] \
https://repo.mongodb.org/apt/ubuntu noble/mongodb-org/8.0 multiverse" \
  | sudo tee /etc/apt/sources.list.d/mongodb-org-8.0.list
sudo apt-get update && sudo apt-get install -y mongodb-org
sudo systemctl enable --now mongod
```

That listens on `localhost:27017` with no auth, which is what `config.yml`
already points at — nothing else to change.

### Option B — Docker

```bash
docker compose up -d          # mongo:7 on :27017
```

Data lives in the named volume `sm3-mongo-data` and survives `stop`/`start`.
`docker compose down -v` destroys it, and a rebuild costs roughly 20 minutes.

### Option C — the MongoDB the SM3 repo already runs

The upstream `docker-compose.yml` starts `mongo:6.0` on port **27018** with auth:

```bash
SM3_MONGO_URI="mongodb://sm3:sm3@localhost:27018/?authSource=admin" \
  .venv/bin/python -m sm3_mongo build --drop-existing
```

### No database at all

Most of the suite does not need one. Against an unreachable server the tests
report **56 passed, 15 skipped** — everything that establishes fidelity (mapping
parity over all 272,817 rows, and the AST-derived embed-spec parity) is pure and
runs on a bare clone. Only the integration tests need a server, and they skip
rather than fail.

## What it does

Upstream's from-scratch path, in two stages:

1. **Load.** Create the 19 collections in `LocalServer.collection_names` order and
   import each CSV through its `map_*` function — field renames (`Id` →
   `<ENTITY>_ID`, foreign keys → `*_REF`, `ENCOUNTERCLASS` → `ENCOUNTER_CLASS`),
   numeric casts, and empty-string-to-`None` guards, all exactly as upstream.
2. **Embed.** `embedding_update` nests 14 collections into `patients` with
   `$push`, dropping each source collection once it has been walked.

Upstream's `main()` also has a repair path (`create_sm3_collections_corrected`)
for a partially-populated server. That path is not reproduced: it contains an
unreachable `self.database.drop_collection()` call that raises, and it is not how
the published database is built. Start from an empty database and the two agree.

## Reproduced upstream defects

These are bugs in the upstream loader. They are **not** fixed here, because the
benchmark's database has them.

**1. `careplans` reads the wrong collection.**
`embed_careplans_in_patients` iterates `medications.find()`. Since
`embed_medications_in_patients` runs first and ends with `medications.drop()`,
that cursor is empty. No careplan is ever embedded, then `careplans` is dropped.
`ENCOUNTERS.CAREPLANS` never exists and all 388 careplan rows are gone — even
though the prompt schema advertises the array with 7 fields.

**2. `patient_expenses` is never embedded.**
`embed_patient_expenses_in_patients` is defined but `embedding_update` never
calls it. So `patients.EXPENSES` never exists, and because the `.drop()` lives
inside the uncalled function, the flat `patient_expenses` collection is never
dropped either. **The database ends with 5 collections, not the 4 the prompt
schema describes** — the fifth being one the prompt never mentions.

**3. `update_one` results are never checked.**
A row whose parent filter matches nothing is still counted as processed, and its
source collection is then dropped. This is how 3,078 observations disappear:
exactly the rows whose `DESCRIPTION` is `QOLS`, `DALY` or `QALY` — Synthea emits
those per patient, not per encounter, so the positional `ENCOUNTERS.$` filter
never matches. Those three metrics exist in PostgreSQL and are absent from
MongoDB entirely.

**4. Two field names disagree with the prompt schema.**
The loader writes `PATIENT_DEPARTMENT_ID` and `FEE_SCHEDULEID`; `mql_schema`
advertises `PATIENTDEPARTMENT_ID` and `FEE_SCHEDULE_ID`. Both source columns are
100% populated, so a model that follows the prompt queries a field that is not
there and gets nothing back.

`_id` is also left on every embedded sub-document, since upstream deletes only
the join keys.

Defects 1 and 3 are silent: the progress bar reports success for every row.

## Deliberate deviations

Two, both in control flow rather than in data. Neither changes what ends up in
the database.

**The repair path is not reproduced.** Upstream's `main()` picks between a
from-scratch build and `create_sm3_collections_corrected()` depending on what is
already on the server. Only the from-scratch path is here — it is what produces
the published database, and the repair path contains an unreachable
`self.database.drop_collection()` call (no arguments, on a `Database`) that
raises if it is ever entered.

**Exceptions propagate.** Upstream wraps the entire build, embedding included, in
`try/except Exception` that prints `Error creating database: ...` and returns
`False`. This repo lets the exception out. A partially-built database that
reports success is exactly the failure mode this repo exists to make visible, and
propagating cannot change the contents of the database — only what the process
tells you about them.

## Scale

The embedding step issues one `update_one` per row — 267,936 of them — and each
`$push` rewrites the whole patient document. `mongod`, not Python, is the
bottleneck, and it gets slower as documents grow. Budget tens of minutes for a
full build on the shipped dataset.

That growth has a ceiling worth knowing about. On the shipped 110-patient
dataset the largest patient document reaches **14.2 MB, about 85% of MongoDB's
hard 16 MB BSON document limit** — and that is *with* careplans, expenses and
3,078 observations missing because of the defects above. A larger Synthea export,
or fixing the defects so the missing rows actually land, could push the biggest
patient past the limit, at which point the embed raises and the build fails part
way through. Anyone planning to regenerate this data at a larger scale should
size that first.

## Proving it matches upstream

The strongest check is to build both databases and compare them document by
document. Upstream's script reads `config_mongodb.yml` from the current
directory, so give it its own directory and its own database name — the SM3
checkout itself is never modified:

```bash
mkdir -p .upstream-run && cd .upstream-run
cp /path/to/SM3-Text-to-Query/src/setup_dbs/mongodb/setup-mongodb.py .
cat > config_mongodb.yml <<'EOF'
server_uri: mongodb://localhost:27017/
database: sm3_upstream
basepath: /path/to/SM3-Text-to-Query/data/synthea_data/
EOF
../.venv/bin/python setup-mongodb.py
```

Then build this repo's copy as `sm3` and compare:

```bash
.venv/bin/python -m sm3_mongo build --drop-existing
.venv/bin/python -m sm3_mongo compare sm3 sm3_upstream
```

`compare` checks the collection sets, then every document in every collection,
including array element order. It exits 0 only if they match, and names the
first differing JSON path if they do not (`$.ENCOUNTERS[3].OBSERVATIONS[7].VALUE`).

`_id` is stripped recursively before comparing, and only `_id`: MongoDB assigns a
fresh random `ObjectId` on every insert, so two correct builds always differ
there and must be identical everywhere else.

## Layout

| Path | What |
| --- | --- |
| `sm3_mongo/mapping.py` | the 19 `map_*` functions, pure, no I/O |
| `sm3_mongo/embedding.py` | the 14 embed methods as a data table, plus the runner |
| `sm3_mongo/loader.py` | create collections, import CSVs, embed |
| `sm3_mongo/verify.py` | read-only report of a built database |
| `sm3_mongo/compare.py` | document-by-document equality against another build |
| `sm3_mongo/cli.py` | `build` / `verify` / `plan` / `compare` |
| `docs/mongodb-schema-and-data.md` | analysis of the upstream loader: the four defects, row loss, field coverage |

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -q
```

Fidelity is checked mechanically, not asserted:

- `test_mapping_parity.py` imports upstream's `setup-mongodb.py` by path and runs
  **both** implementations over **every row of every CSV**, comparing the
  resulting dicts. 272,836 rows.
- `test_embedding_parity.py` parses upstream's source and derives, per `embed_*`
  method, the collection iterated, the collection dropped, the `$push` path, the
  deleted join keys and the call order — then compares that to the spec table. It
  also pins defect 1 explicitly: if upstream ever fixes `careplans`, the test
  fails and tells you this repo must follow.
- `test_build_integration.py` builds a real database from synthetic CSVs and
  asserts the defects actually manifest -- not just that the source matches.
  Skipped when no MongoDB is reachable.
- `test_mapping_unit.py` and `test_compare_unit.py` run on synthetic data, so they
  need neither the upstream checkout, the CSVs, nor a database.

Parity tests skip (rather than fail) when the upstream checkout is absent. Point
them elsewhere with `SM3_UPSTREAM_REPO`.
