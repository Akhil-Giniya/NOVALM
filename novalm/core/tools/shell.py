import asyncio
from typing import Dict, Any
from novalm.core.tools.base import Tool

WHITELISTED_COMMANDS = ["ls", "grep", "cat", "git status", "echo"]

class ShellTool(Tool):
    name = "shell_tool"
    description = f"Execute shell commands. Allowed: {', '.join(WHITELISTED_COMMANDS)}"
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string"}
        },
        "required": ["command"]
    }

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        command = input_data.get("command", "")
        
        # Simple whitelist check (naive, splitting by space)
        cmd_base = command.split()[0] if command else ""
        if cmd_base not in WHITELISTED_COMMANDS:
             return {"status": "error", "output": f"Command '{cmd_base}' is not allowed."}
        
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        return {
            "status": "success" if proc.returncode == 0 else "error",
            "stdout": stdout.decode(),
            "stderr": stderr.decode(),
            "returncode": proc.returncode
        }
