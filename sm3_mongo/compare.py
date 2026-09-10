"""Prove two SM3 databases are identical.

Compares a database built by this repo against one built by upstream's own
``setup-mongodb.py``. ``_id`` is stripped everywhere before comparing: MongoDB
assigns a fresh random ``ObjectId`` per insert, so two correct builds always
differ there and nowhere else.

Everything else must match exactly, including array element order -- both builds
insert in the same order and embed in natural order, so the arrays should be
element-for-element equal.
"""

def strip_ids(value):
    """Recursively drop every ``_id`` key. Returns a new structure."""
    if isinstance(value, dict):
        return {k: strip_ids(v) for k, v in value.items() if k != "_id"}
    if isinstance(value, list):
        return [strip_ids(v) for v in value]
    return value


def first_difference(left, right, path="$"):
    """Path of the first difference between two stripped structures, or None."""
    if type(left) is not type(right):
        return f"{path}: type {type(left).__name__} != {type(right).__name__}"

    if isinstance(left, dict):
        for key in sorted(set(left) | set(right)):
            if key not in left:
                return f"{path}.{key}: missing on the left"
            if key not in right:
                return f"{path}.{key}: missing on the right"
            found = first_difference(left[key], right[key], f"{path}.{key}")
            if found:
                return found
        return None

    if isinstance(left, list):
        if len(left) != len(right):
            return f"{path}: length {len(left)} != {len(right)}"
        for index, (a, b) in enumerate(zip(left, right)):
            found = first_difference(a, b, f"{path}[{index}]")
            if found:
                return found
        return None

    if left != right:
        return f"{path}: {left!r} != {right!r}"
    return None


def compare_collection(db_a, db_b, name, key=None):
    """Compare one collection exhaustively. Returns human-readable differences.

    Three checks, strictest interpretation of "identical":

    1. document counts match;
    2. **natural order** matches -- both builds ``insert_many`` the same list, so
       the on-disk document order must agree, not merely the set of documents;
    3. every document is deep-equal with ``_id`` stripped, arrays included,
       element order included.
    """
    problems = []
    count_a = db_a[name].count_documents({})
    count_b = db_b[name].count_documents({})
    if count_a != count_b:
        return [f"{name}: {count_a:,} documents vs {count_b:,}"]

    if key:
        # Patient documents are megabytes each, so stream rather than load.
        order_a = [d[key] for d in db_a[name].find({}, {key: 1, "_id": 0})]
        order_b = [d[key] for d in db_b[name].find({}, {key: 1, "_id": 0})]
        if order_a != order_b:
            if sorted(order_a) == sorted(order_b):
                problems.append(f"{name}: same {key} values but different natural order")
            else:
                problems.append(f"{name}: differing {key} sets")
                return problems

        for value in order_a:
            left = strip_ids(db_a[name].find_one({key: value}))
            right = strip_ids(db_b[name].find_one({key: value}))
            if left != right:
                problems.append(
                    f"{name}[{key}={value}]: {first_difference(left, right)}"
                )
    else:
        # Small collections: walk both cursors in lockstep, in natural order.
        for index, (a, b) in enumerate(zip(db_a[name].find(), db_b[name].find())):
            left, right = strip_ids(a), strip_ids(b)
            if left != right:
                problems.append(
                    f"{name}[position {index}]: {first_difference(left, right)}"
                )
    return problems


#: Collections with a natural unique key, streamed one document at a time.
STREAM_KEYS = {
    "patients": "PATIENT_ID",
    "organizations": "ORGANIZATION_ID",
    "providers": "PROVIDER_ID",
    "payers": "PAYER_ID",
}


def compare_databases(uri, name_a, name_b):
    """Compare two databases. Returns ``(identical, lines)``."""
    import pymongo

    client = pymongo.MongoClient(uri)
    db_a, db_b = client[name_a], client[name_b]

    lines = []
    problems = []

    collections_a = sorted(db_a.list_collection_names())
    collections_b = sorted(db_b.list_collection_names())
    lines.append(f"{name_a}: {collections_a}")
    lines.append(f"{name_b}: {collections_b}")

    if collections_a != collections_b:
        problems.append(
            f"collection sets differ: only in {name_a}: "
            f"{sorted(set(collections_a) - set(collections_b))}; "
            f"only in {name_b}: {sorted(set(collections_b) - set(collections_a))}"
        )
        client.close()
        return False, lines + [""] + problems

    lines.append("")
    for collection in collections_a:
        found = compare_collection(db_a, db_b, collection, STREAM_KEYS.get(collection))
        count = db_a[collection].count_documents({})
        status = "identical" if not found else f"{len(found)} difference(s)"
        lines.append(f"  {collection:24s} {count:>8,} documents   {status}")
        problems.extend(found)

    client.close()
    if problems:
        return False, lines + ["", "differences:"] + [f"  {p}" for p in problems]
    return True, lines
