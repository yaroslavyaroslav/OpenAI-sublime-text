from __future__ import annotations

from typing import Any, Dict, List, Union

JSONObject = Dict[str, Any]  # A JSON object is typically a dict with string keys
JSONArray = List[Any]  # A JSON array is typically a list of any types
JSONType = Union[JSONObject, JSONArray, str, int, float, bool, None]  # Any valid JSON type
