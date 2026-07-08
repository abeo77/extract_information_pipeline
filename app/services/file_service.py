"""File helpers used by API and UI layers."""

from pathlib import Path

INPUT_DIR = Path("data/input")
OUTPUT_DIR = Path("data/output")
GROUND_TRUTH_DIR = Path("data/ground_truth")
TEMP_DIR = Path("data/temp")


def ensure_data_dirs() -> None:
    for folder in (INPUT_DIR, OUTPUT_DIR, GROUND_TRUTH_DIR, TEMP_DIR):
        folder.mkdir(parents=True, exist_ok=True)


def input_path(filename: str) -> Path:
    ensure_data_dirs()
    return INPUT_DIR / Path(filename).name


def available_input_path(filename: str) -> Path:
    path = input_path(filename)
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    counter = 1
    while True:
        candidate = path.with_name(f"{stem}_{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def output_path(stem: str) -> Path:
    ensure_data_dirs()
    return OUTPUT_DIR / f"{Path(stem).stem}_result.json"


def ground_truth_path(filename: str) -> Path:
    ensure_data_dirs()
    return GROUND_TRUTH_DIR / Path(filename).name


def available_ground_truth_path(filename: str) -> Path:
    path = ground_truth_path(filename)
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    counter = 1
    while True:
        candidate = path.with_name(f"{stem}_{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def save_bytes(filename: str, content: bytes) -> Path:
    path = available_input_path(filename)
    path.write_bytes(content)
    return path


def save_ground_truth_bytes(filename: str, content: bytes) -> Path:
    path = available_ground_truth_path(filename)
    path.write_bytes(content)
    return path
