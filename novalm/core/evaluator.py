from typing import Dict, Any, Optional
from novalm.core.tools.python_exec import PythonExecTool

class Evaluator:
    """
    Evaluates generated code against provided tests.
    """
    def __init__(self):
        self.exec_tool = PythonExecTool()

    async def evaluate(self, code: str, test_code: str) -> Dict[str, Any]:
        """
        Runs the code followed by the test_code.
        Returns dictionary with status ('PASS'/'FAIL') and feedback.
        """
        # Combine code and test
        # We wrap in a try/except block in the script itself to capture assertion errors cleanly if needed,
        # but PythonExecTool captures stderr which is usually enough for unittest/assert failures.
        
        full_script = f"{code}\n\n# --- TEST HARNESS ---\n{test_code}"
        
        result = await self.exec_tool.run({"code": full_script})
        
        if result["status"] == "error":
            return {
                "status": "FAIL",
                "feedback": f"Execution Error:\n{result.get('stderr', '')}\n{result.get('result_summary', '')}"
            }
            
        # If output contains "FAIL" or "Traceback" (if execution claimed success but printed errors), treat as fail.
        # PythonExecTool usually catches exceptions and returns error status.
        # But if tests print "FAILED" but exit 0, we should check.
        # Standard unittest prints to stderr.
        
        stderr = result.get("stderr", "")
        if "Traceback" in stderr or "Error" in stderr or "FAILED" in stderr:
             return {
                "status": "FAIL",
                "feedback": f"Test Failed:\n{stderr}"
            }
            
        return {
            "status": "PASS",
            "feedback": "Tests passed successfully."
        }
