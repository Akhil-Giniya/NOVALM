import sys
import os

# Add parent dir to path to import novalm
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from novalm.core.memory import AdvancedMemory

def bootstrap():
    print("Bootstrapping Procedural Memory...")
    mem = AdvancedMemory()
    
    heuristics = [
        {
            "trigger": "Debugging Python Recursion Errors",
            "routine": "1. Check base case. 2. Verify state changes in recursive call. 3. If depth is large, convert to Iterative approach using a Stack."
        },
        {
            "trigger": "Optimizing Matrix Multiplication",
            "routine": "1. Use numpy vectorized operations. 2. Avoid explicit loops. 3. Check for broadcasting opportunities."
        },
        {
            "trigger": "Writing Unit Tests",
            "routine": "1. Import unittest or pytest. 2. Create distinct test class. 3. Test edge cases (empty inputs, large inputs). 4. Mock external dependencies."
        },
        {
            "trigger": "Handling File I/O",
            "routine": "1. Always use 'with open(...)'. 2. Handle FileNotFoundError. 3. Ensure encoding='utf-8'."
        },
        {
            "trigger": "Designing REST API",
            "routine": "1. Use standard verbs (GET, POST). 2. Return JSON. 3. Use standard HTTP status codes (200, 400, 404, 500)."
        }
    ]
    
    for h in heuristics:
        mem.add_procedural(h["trigger"], h["routine"])
        
    print("Done! Procedural Memory seeded.")

if __name__ == "__main__":
    bootstrap()
