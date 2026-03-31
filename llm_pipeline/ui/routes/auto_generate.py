"""Auto-generate introspection endpoint."""
import enum

from fastapi import APIRouter

from llm_pipeline.prompts.variables import _AUTO_GENERATE_REGISTRY

router = APIRouter(prefix="/auto-generate", tags=["auto-generate"])

_PY_TYPE_MAP = {str: "str", int: "int", float: "float", bool: "bool"}


@router.get("")
def list_auto_generate_objects() -> dict:
    """Return registered auto_generate objects (enums and constants)."""
    objects = []
    for name, obj in sorted(_AUTO_GENERATE_REGISTRY.items()):
        if isinstance(obj, type) and issubclass(obj, enum.Enum):
            objects.append({
                "name": name,
                "kind": "enum",
                "members": [
                    {"name": m.name, "value": str(m.value)} for m in obj
                ],
            })
        else:
            objects.append({
                "name": name,
                "kind": "constant",
                "value_type": _PY_TYPE_MAP.get(type(obj), "str"),
                "value": obj,
            })
    return {"objects": objects}
