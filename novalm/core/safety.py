import re
from typing import Optional

class SafetyLayer:
    """
    Safety Layer responsible for Pre-Inference (Input) and Post-Inference (Output) checks.
    """
    
    def __init__(self):
        # Simple regex for demonstration. In production, load classifiers here.
    def __init__(self):
        # Blocking explicit keywords (MVP) - Using word boundaries for safety
        self.blocked_patterns = [
            re.compile(r"\bbadword\b", re.IGNORECASE),
            re.compile(r"\bfailmode\b", re.IGNORECASE),
        ]
        
        # Heuristics for Prompt Injection
        self.injection_patterns = [
            re.compile(r"ignore previous instructions", re.IGNORECASE),
            re.compile(r"system override", re.IGNORECASE),
            re.compile(r"you are now.*unrestricted", re.IGNORECASE),
        ]
        
    def check_input(self, text: str) -> None:
        """
        Checks input text for safety violations.
        Raises ValueError if a violation is found.
        """
        for pattern in self.blocked_patterns:
            if pattern.search(text):
                raise ValueError(f"Safety violation: Blocked content detected in input.")
                
        for pattern in self.injection_patterns:
            if pattern.search(text):
                raise ValueError(f"Safety violation: Potential Prompt Injection detected.")

    def check_output(self, text: str) -> str:
        """
        Checks output text for safety violations.
        Returns the sanitized text (or raises exception if strict).
        For MVP, we will redact/replace.
        """
        # Example PII redaction stub (Email)
        # Simple regex for email
        email_pattern = re.compile(r'[\w\.-]+@[\w\.-]+\.\w+')
        sanitized_text = email_pattern.sub("[EMAIL_REDACTED]", text)
        
        return sanitized_text
