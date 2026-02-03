import json
import re
from typing import Type, TypeVar, Any
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

class JsonOutputParser:
    """
    Parses and validates LLM output against strict Pydantic models.
    """
    
    @staticmethod
    def parse(text: str, model_class: Type[T]) -> T:
        """
        Extracts JSON from text and validates it against model_class.
        Raises ValueError if parsing or validation fails.
        """
        # 1. Clean Markdown Code Blocks
        # Look for ```json ... ``` or just ``` ... ```
        pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
        match = re.search(pattern, text)
        if match:
             json_str = match.group(1)
        else:
             # Try to find the first '{' and last '}'
             start = text.find("{")
             end = text.rfind("}")
             if start != -1 and end != -1:
                 json_str = text[start:end+1]
             else:
                 # Last resort: Try the whole text
                 json_str = text

        # 2. Parse JSON
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format: {e}")

        # 3. Validate Logic (Pydantic)
        try:
            return model_class(**data)
        except ValidationError as e:
            raise ValueError(f"Schema Validation Failed: {e}")
