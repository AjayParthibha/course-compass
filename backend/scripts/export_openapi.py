"""Print the API's OpenAPI spec. Used by `npm run gen:api` in web/."""

import json

from app.main import app

print(json.dumps(app.openapi(), indent=1))
