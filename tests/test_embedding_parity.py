"""The embed spec table must match what upstream's methods actually do.

Rather than trusting a transcription, this parses upstream's source and derives,
per ``embed_*`` method: the collection iterated, the collection dropped, the
``$push`` path, and the collection counted for the progress bar. Any drift --
including a future upstream fix to the careplans bug -- fails here.
"""

import ast
import re

import pytest

from sm3_mongo.embedding import EMBED_SPECS, UNCALLED_EMBED_SPEC

ALL_SPECS = {spec.name: spec for spec in EMBED_SPECS}
ALL_SPECS[UNCALLED_EMBED_SPEC.name] = UNCALLED_EMBED_SPEC

COLLECTION_RE = r"self\.client\[f'\{self\.database_name\}'\]\.(\w+)"


def _methods(source):
    tree = ast.parse(source)
    cls = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "LocalServer"
    )
    return {
        node.name: ast.get_source_segment(source, node)
        for node in cls.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("embed_")
    }


@pytest.fixture(scope="module")
def upstream_methods(upstream_source):
    return _methods(upstream_source)


def test_all_embed_methods_are_modelled(upstream_methods):
    assert set(upstream_methods) == set(ALL_SPECS)


@pytest.mark.parametrize("name", sorted(ALL_SPECS))
def test_spec_matches_upstream_method(name, upstream_methods):
    source = upstream_methods[name]
    spec = ALL_SPECS[name]

    read_from = re.search(COLLECTION_RE + r"\.find\(\)", source)
    assert read_from, f"{name}: no .find() call found"
    assert spec.read_from == read_from.group(1)

    dropped = re.search(COLLECTION_RE + r"\.drop\(\)", source)
    assert dropped, f"{name}: no .drop() call found"
    assert spec.drop == dropped.group(1)

    counted = re.search(COLLECTION_RE + r"\.count_documents\(\{\}\)", source)
    assert counted, f"{name}: no count_documents call found"
    assert spec.count_from == counted.group(1)

    push = re.search(r'"\$push":\s*\{"([^"]+)"', source)
    assert push, f"{name}: no $push path found"
    assert spec.push_path == push.group(1)

    deleted = set(re.findall(r'del \w+\["(\w+)"\]', source))
    assert {doc_field for doc_field, _ in spec.parent_keys} == deleted


def test_embedding_update_calls_exactly_these_specs_in_order(upstream_source):
    """The call order in embedding_update is the order of EMBED_SPECS."""
    tree = ast.parse(upstream_source)
    cls = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "LocalServer"
    )
    update = next(
        node for node in cls.body
        if isinstance(node, ast.FunctionDef) and node.name == "embedding_update"
    )
    called = [
        node.func.attr
        for node in ast.walk(update)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr.startswith("embed_")
    ]
    assert called == [spec.name for spec in EMBED_SPECS]
    assert UNCALLED_EMBED_SPEC.name not in called


def test_careplans_defect_is_still_present_upstream(upstream_methods):
    """Pin the defect explicitly: if upstream fixes it, this repo must follow."""
    source = upstream_methods["embed_careplans_in_patients"]
    read_from = re.search(COLLECTION_RE + r"\.find\(\)", source).group(1)
    assert read_from == "medications", (
        "upstream embed_careplans_in_patients no longer reads medications -- "
        "the careplans defect was fixed upstream and this repo must be updated"
    )
