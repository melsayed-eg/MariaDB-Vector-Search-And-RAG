"""Provide command-line access to the WikiRAG application."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from contextlib import closing

from wikirag.config import load_settings
from wikirag.db.connection import get_connection
from wikirag.db.schema import init_schema
from wikirag.errors import WikiRagError


def build_parser() -> argparse.ArgumentParser:
    """Build the WikiRAG command-line parser.

    Returns:
        argparse.ArgumentParser: Parser with available commands.
    """
    parser = argparse.ArgumentParser(
        prog="wikirag",
        description="Wikipedia vector search and RAG using MariaDB.",
    )
    commands = parser.add_subparsers(
        dest="command",
        required=True,
    )
    commands.add_parser(
        "init-db",
        help="Create or verify the MariaDB schema.",
    )
    return parser


def run_init_db() -> None:
    """Initialize or verify the application database schema.

    Returns:
        None: The database schema has been verified.

    Raises:
        WikiRagError: If configuration or database setup fails.
    """
    config = load_settings().db

    with closing(get_connection(config)) as conn:
        init_schema(conn)

    print("MariaDB schema initialized and verified.")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the selected WikiRAG command.

    Args:
        argv: Optional command-line arguments.

    Returns:
        int: Zero on success and one on application failure.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "init-db":
            run_init_db()
    except WikiRagError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
