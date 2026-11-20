
"""Export the FastAPI application's OpenAPI specification."""

import json
import sys
from pathlib import Path

# Add the project root to Python's import path.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import app


def main() -> None:
    """Generate openapi.json in the project root."""
    specification = app.openapi()

    output_file = PROJECT_ROOT / "openapi.json"

    output_file.write_text(
        json.dumps(specification, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"OpenAPI specification exported successfully: {output_file}")


if __name__ == "__main__":
    main()
