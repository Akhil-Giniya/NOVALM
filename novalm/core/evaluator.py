from typing import Dict, Any, Optional
import asyncio
import logging
from novalm.core.tools.python_exec import PythonExecTool

logger = logging.getLogger(__name__)

class Evaluator:
    """
    Evaluates generated code against provided tests.
    
    WARNING: This executes code. In production, this MUST run in a sandboxed environment
    (e.g., Docker, gVisor, Firecracker).
    Current implementation is for local development/research only.
    """
    def __init__(self, timeout_seconds: int = 10):
        self.exec_tool = PythonExecTool()
        self.timeout_seconds = timeout_seconds

    async def evaluate(self, code: str, test_code: str) -> Dict[str, Any]:
        """
        Runs the code followed by the test_code.
        Returns dictionary with status ('PASS'/'FAIL') and feedback.
        Enforces timeout.
        """
        # Combine code and test
        full_script = f"{code}\n\n# --- TEST HARNESS ---\n{test_code}"
        
        try:
            # Enforce Timeout
            result = await asyncio.wait_for(
                self.exec_tool.run({"code": full_script}),
                timeout=self.timeout_seconds
            )
        except asyncio.TimeoutError:
            logger.warning("Evaluation timed out.")
            return {
                "status": "FAIL",
                "feedback": f"Timeout: Test execution exceeded {self.timeout_seconds} seconds. Infinite loop or slow code detected."
            }
        except Exception as e:
            logger.error(f"Evaluation error: {e}")
            return {
                "status": "FAIL",
                "feedback": f"System Error during evaluation: {e}"
            }
        
        # Check Result
        if result.get("status") == "error":
            return {
                "status": "FAIL",
                "feedback": f"Execution Error:\n{result.get('stderr', '')}\n{result.get('result_summary', '')}"
            }
            
        # Exit Code Check (if tool supports it)
        # Assuming tool returns 'status'='success' only on 0 exit code.
        # But we double check stderr for common failures that might not crash python interpreter (e.g. caught exceptions but printed)
        stderr = result.get("stderr", "")
        if "Traceback" in stderr or "Error" in stderr or "FAILED" in stderr:
             return {
                "status": "FAIL",
                "feedback": f"Test Failed (Error Detected in Output):\n{stderr}"
            }
            
        return {
            "status": "PASS",
            "feedback": "Tests passed successfully."
        }
