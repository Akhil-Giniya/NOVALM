import sys
import io
import asyncio
from typing import Dict, Any
from novalm.core.tools.base import Tool

class PythonExecTool(Tool):
    name = "python_exec"
    description = "Executes Python code. Input should be a valid python script. Returns stdout and stderr."
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "The python code to execute."
            }
        },
        "required": ["code"]
    }

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        code = input_data.get("code", "")
        if not code:
            return {"status": "error", "output": "No code provided."}

        # Capture stdout/stderr
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        redirected_output = io.StringIO()
        redirected_error = io.StringIO()
        
        sys.stdout = redirected_output
        sys.stderr = redirected_error
        
        try:
            # Run in a separate thread/executor to avoid blocking the async loop
            # But exec is tricky with async. For MVP, we run sync or use run_in_executor if needed.
            # exec() runs in the current context global/local. 
            # We should give it a restricted scope.
            local_scope = {}
            exec(code, {}, local_scope)
            result = "Executed successfully."
        except Exception as e:
            result = f"Error: {e}"
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            
        stdout = redirected_output.getvalue()
        stderr = redirected_error.getvalue()
        
        return {
            "status": "success" if not stderr and "Error" not in result else "error", 
            "stdout": stdout,
            "stderr": stderr,
            "result_summary": result
        }
