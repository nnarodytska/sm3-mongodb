"""Building the SM3 MongoDB from the Synthea CSVs.

Reproduces ``LocalServer.create_sm3_database_new`` from SM3-Text-to-Query
``src/setup_dbs/mongodb/setup-mongodb.py``: create the nineteen collections in
``collection_names`` order, import each CSV through its ``map_*`` function, then
run ``embedding_update``.

Upstream's ``main()`` branches between a from-scratch build and a repair path
(``create_sm3_collections_corrected``) depending on what is already in the
server. Only the from-scratch path is reproduced here, because that is the path
that produces the published database; the repair path additionally contains an
unreachable ``self.database.drop_collection()`` call that raises. Start from an
empty database and the two paths agree.
"""

import csv
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List

import pymongo

from .embedding import EMBED_SPECS, run_embedding
from .mapping import COLLECTION_NAMES, MAPPINGS


@dataclass
class LoadReport:
    database: str
    csv_rows: Dict[str, int] = field(default_factory=dict)
    embed_results: List = field(default_factory=list)
    seconds: float = 0.0

    @property
    def rows_read(self):
        return sum(self.csv_rows.values())

    @property
    def rows_embedded(self):
        return sum(r.matched for r in self.embed_results)

    @property
    def rows_lost(self):
        """Rows read from a CSV that reach neither a surviving collection nor an array."""
        return self.rows_read - self.rows_embedded - self.rows_surviving

    @property
    def rows_surviving(self):
        """Rows still queryable at top level, i.e. in collections never dropped."""
        dropped = {spec.drop for spec in EMBED_SPECS}
        return sum(
            count for name, count in self.csv_rows.items() if name not in dropped
        )


def load_config(path):
    """Read the YAML config. Same keys as upstream ``config_mongodb.yml``."""
    import yaml

    with open(path) as handle:
        config = yaml.load(handle, yaml.SafeLoader)

    basepath = os.environ.get("SM3_CSV_DIR", config.get("basepath"))
    if basepath and not basepath.endswith(os.sep):
        basepath += os.sep
    config["basepath"] = basepath
    config["server_uri"] = os.environ.get("SM3_MONGO_URI", config.get("server_uri"))
    config["database"] = os.environ.get("SM3_MONGO_DB", config.get("database"))
    return config


def import_csv(database, file_path, collection_name, mapping_func):
    """Upstream ``import_csv``: read the whole file, map every row, one insert_many."""
    with open(file_path, "r") as handle:
        reader = csv.DictReader(handle)
        data = [mapping_func(row) for row in reader]
    # No empty-list guard: upstream has none, so a CSV with only a header raises
    # InvalidOperation here exactly as it does upstream.
    database[collection_name].insert_many(data)
    return len(data)


def build(config, drop_existing=False, quiet=False, progress_factory=None):
    """Create the database, import the CSVs, embed. Returns a :class:`LoadReport`."""
    client = pymongo.MongoClient(config["server_uri"])
    database_name = config["database"]
    basepath = config["basepath"]

    if database_name in client.list_database_names():
        if not drop_existing:
            raise SystemExit(
                f"database {database_name!r} already exists on {config['server_uri']}; "
                f"pass --drop-existing to rebuild it from scratch"
            )
        client.drop_database(database_name)

    database = client[database_name]
    report = LoadReport(database=database_name)
    started = time.time()

    for collection_name in COLLECTION_NAMES:
        filename, mapping_func = MAPPINGS[collection_name]
        database.create_collection(collection_name)
        count = import_csv(database, basepath + filename, collection_name, mapping_func)
        report.csv_rows[collection_name] = count
        if not quiet:
            print(f"  loaded {count:>7,}  {collection_name}")

    if not quiet:
        print(f"Created SM3 database: {database_name}")

    report.embed_results = run_embedding(database, progress_factory=progress_factory)
    report.seconds = time.time() - started
    client.close()
    return report
