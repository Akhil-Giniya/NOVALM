from abc import ABC, abstractmethod
from typing import Dict, Any

class Tool(ABC):
    name: str = "base_tool"
    description: str = "Base tool description"
    parameters: Dict[str, Any] = {} # JSON Schema

    @abstractmethod
    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes the tool with the given input.
        Returns a dictionary representing the output.
        """
        pass
