from pydantic import BaseModel, ConfigDict


class Schema(BaseModel):
    # fields with defaults are always present in responses, so mark them required
    # in the generated TypeScript types
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)
