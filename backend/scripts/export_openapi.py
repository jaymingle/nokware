"""Print the API's OpenAPI schema as JSON, for the frontend's generated types.

    backend/.venv/bin/python backend/scripts/export_openapi.py > openapi.json

The frontend's `npm run api:types` runs this and turns the schema into
TypeScript, so its request and response types always match the backend.
"""

import json
import sys

from app.main import app

if __name__ == "__main__":
    json.dump(app.openapi(), sys.stdout, indent=2)
    sys.stdout.write("\n")
