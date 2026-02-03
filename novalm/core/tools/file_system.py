import os
import aiofiles
from typing import Dict, Any
from novalm.core.tools.base import Tool

WORKSPACE_DIR = os.path.abspath("workspace")

class FileTool(Tool):
    name = "file_tool"
    description = "Read or Write files in the workspace. Operations: 'read', 'write'."
    parameters = {
        "type": "object",
        "properties": {
            "operation": {"type": "string", "enum": ["read", "write"]},
            "filename": {"type": "string"},
            "content": {"type": "string", "description": "Content to write (required for write op)"}
        },
        "required": ["operation", "filename"]
    }

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        op = input_data.get("operation")
        filename = input_data.get("filename")
        content = input_data.get("content", "")
        
        # Path safety check
        safe_path = os.path.abspath(os.path.join(WORKSPACE_DIR, filename))
        if not safe_path.startswith(WORKSPACE_DIR):
             return {"status": "error", "output": "Access denied: Path outside workspace."}
             
        if op == "read":
            if not os.path.exists(safe_path):
                return {"status": "error", "output": "File not found."}
            async with aiofiles.open(safe_path, "r") as f:
                data = await f.read()
            return {"status": "success", "content": data}
            
        elif op == "write":
            async with aiofiles.open(safe_path, "w") as f:
                await f.write(content)
            return {"status": "success", "output": f"File {filename} written."}
            
        return {"status": "error", "output": "Unknown operation."}
