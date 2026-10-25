"""Read the name and ID number from a photo of an ID document.

    python scan_id.py inputs/ID_David.jpg

Uses the vision model set as GEMINI_ID_MODEL in inputs/.env. The attempt is saved to recordings/
and logged to logs/id_scans.json, exactly like the demo page's ID card.
"""
import sys
from pathlib import Path

from src.services.id_log import log_id_scan
from src.services.ocr_service import parse_identity_doc
from src.services.recordings import save_recording


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 1

    image = path.read_bytes()
    result = parse_identity_doc(image)
    log_id_scan(path.name, result, save_recording("id", image, path.suffix.lstrip(".") or "jpg", label=path.name))

    print(f"Document     : {result.document_type or '-'}")
    print(f"Name         : {result.full_name or '-'}")
    print(f"ID number    : {result.id_number or '-'}")
    print(f"Date of birth: {result.date_of_birth or '-'}   (age {result.age if result.age is not None else '-'})")
    print(f"Insurance    : {result.insurance_status}")
    print(f"Needs review : {'YES' if result.needs_review else 'no'}")
    for issue in result.issues:
        print(f"  - {issue}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
