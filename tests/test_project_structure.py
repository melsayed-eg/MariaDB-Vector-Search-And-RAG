from pathlib import Path


def test_required_directories_exist():
    # Find the root directory of our project.
    root = Path(__file__).resolve().parents[1]

    # List all directories our project should contain.
    required_directories = [
        "src/ingest",
        "src/database",
        "src/retrieval",
        "src/rag",
        "sql",
        "data",
        "evaluation",
        "app",
        "tests",
        "docs",
    ]

    # Check that every required directory exists.
    for directory in required_directories:
        assert (root / directory).is_dir()