"""Every mapping in this repo must produce exactly what upstream produces.

Runs both implementations over every row of every real CSV and compares the
resulting dicts. This is what makes "faithful" a checked claim rather than an
assertion in a README.
"""

import csv
import os

import pytest

from sm3_mongo.mapping import COLLECTION_NAMES, MAPPINGS


@pytest.mark.parametrize("collection", COLLECTION_NAMES)
def test_mapping_matches_upstream(collection, upstream_module, csv_dir):
    filename, ours = MAPPINGS[collection]
    theirs = getattr(upstream_module.LocalServer, f"map_{collection}")

    path = os.path.join(csv_dir, filename)
    if not os.path.isfile(path):
        pytest.skip(f"missing {filename}")

    compared = 0
    with open(path) as handle:
        for line_number, row in enumerate(csv.DictReader(handle), start=2):
            mine = ours(row)
            upstream = theirs(dict(row))
            assert mine == upstream, (
                f"{filename} line {line_number}: mapping differs\n"
                f"  ours:     {mine}\n"
                f"  upstream: {upstream}"
            )
            compared += 1

    assert compared > 0, f"{filename} produced no rows to compare"


def test_every_upstream_mapping_is_reproduced(upstream_module):
    """No map_* method exists upstream that this repo does not implement."""
    upstream_names = {
        name for name in dir(upstream_module.LocalServer) if name.startswith("map_")
    }
    ours = {f"map_{name}" for name in COLLECTION_NAMES}
    assert upstream_names == ours
