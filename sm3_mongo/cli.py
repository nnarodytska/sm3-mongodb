"""Command line entry point: ``python -m sm3_mongo``."""

import argparse
import os
import sys

from .embedding import EMBED_SPECS, UNCALLED_EMBED_SPEC
from .compare import compare_databases
from .loader import build, load_config
from .mapping import COLLECTION_NAMES, MAPPINGS
from .verify import format_report, inspect

DEFAULT_CONFIG = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yml")


def _progress_factory(spec):
    try:
        from tqdm import tqdm
    except ImportError:
        return None

    bar = tqdm(
        total=None,
        desc=f"Processing {spec.drop}",
        bar_format="{l_bar}{bar}| {n_fmt} [{elapsed}]",
        leave=True,
    )
    return bar.update


def cmd_build(args):
    config = load_config(args.config)
    if not config.get("basepath"):
        sys.exit("no CSV directory configured: set basepath in config.yml or SM3_CSV_DIR")
    if not os.path.isdir(config["basepath"]):
        sys.exit(f"CSV directory not found: {config['basepath']}")

    print(f"server:   {config['server_uri']}")
    print(f"database: {config['database']}")
    print(f"csv dir:  {config['basepath']}")
    print()

    report = build(
        config,
        drop_existing=args.drop_existing,
        quiet=args.quiet,
        progress_factory=None if args.quiet else _progress_factory,
    )

    print()
    print(f"{'method':42s} {'read':>8s} {'matched':>8s} {'unmatched':>10s}")
    for result in report.embed_results:
        note = f"  <-- {result.quirk}" if result.quirk else ""
        print(
            f"{result.name:42s} {result.read_count:>8,} "
            f"{result.matched:>8,} {result.unmatched:>10,}{note}"
        )

    print()
    print(f"csv rows read:      {report.rows_read:>9,}")
    print(f"embedded into arrays:{report.rows_embedded:>8,}")
    print(f"left in collections: {report.rows_surviving:>8,}")
    print(f"lost:                {report.rows_lost:>8,}")
    print(f"elapsed:             {report.seconds:>8.1f}s")
    return 0


def cmd_verify(args):
    config = load_config(args.config)
    print(format_report(inspect(config["server_uri"], config["database"])))
    return 0


def cmd_plan(args):
    print(f"load order ({len(COLLECTION_NAMES)} collections):")
    for i, name in enumerate(COLLECTION_NAMES, 1):
        print(f"  {i:2d}. {name:22s} <- {MAPPINGS[name][0]}")

    print()
    print(f"embedding order ({len(EMBED_SPECS)} methods):")
    for i, spec in enumerate(EMBED_SPECS, 1):
        note = f"   <-- {spec.quirk}" if spec.quirk else ""
        print(
            f"  {i:2d}. {spec.name:42s} {spec.read_from:20s} "
            f"-> patients.{spec.push_path}{note}"
        )

    print()
    print(f"never called: {UNCALLED_EMBED_SPEC.name}")
    print(f"              would push -> patients.{UNCALLED_EMBED_SPEC.push_path}")
    print(f"              {UNCALLED_EMBED_SPEC.quirk}")
    return 0


def cmd_compare(args):
    config = load_config(args.config)
    identical, lines = compare_databases(config["server_uri"], args.left, args.right)
    print("\n".join(lines))
    print()
    if identical:
        print(f"IDENTICAL: {args.left} and {args.right} match in every document")
        print("(_id excluded: MongoDB assigns a fresh ObjectId per insert)")
        return 0
    print(f"DIFFERENT: {args.left} and {args.right} do not match")
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="sm3_mongo",
        description="Rebuild the SM3 MongoDB from the Synthea CSVs, faithfully.",
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="path to config.yml")
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="create the database and load the CSVs")
    p_build.add_argument(
        "--drop-existing", action="store_true", help="drop the database first if it exists"
    )
    p_build.add_argument("--quiet", action="store_true", help="no per-collection output")
    p_build.set_defaults(func=cmd_build)

    p_verify = sub.add_parser("verify", help="report what a built database contains")
    p_verify.set_defaults(func=cmd_verify)

    p_plan = sub.add_parser("plan", help="print load and embedding order, no database needed")
    p_plan.set_defaults(func=cmd_plan)

    p_compare = sub.add_parser(
        "compare", help="compare two built databases document by document"
    )
    p_compare.add_argument("left", help="first database name")
    p_compare.add_argument("right", help="second database name")
    p_compare.set_defaults(func=cmd_compare)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
