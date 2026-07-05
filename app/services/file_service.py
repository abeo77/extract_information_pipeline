"""File helpers used by API and UI layers."""

from pathlib import Path

INPUT_DIR = Path("data/input")
OUTPUT_DIR = Path("data/output")
TEMP_DIR = Path("data/temp")


def ensure_data_dirs() -> None:
    for folder in (INPUT_DIR, OUTPUT_DIR, TEMP_DIR):
        folder.mkdir(parents=True, exist_ok=True)


def input_path(filename: str) -> Path:
    ensure_data_dirs()
    return INPUT_DIR / Path(filename).name


def output_path(stem: str) -> Path:
    ensure_data_dirs()
    return OUTPUT_DIR / f"{Path(stem).stem}_result.json"


def save_bytes(filename: str, content: bytes) -> Path:
    path = input_path(filename)
    path.write_bytes(content)
    return path
