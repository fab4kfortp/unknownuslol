import re
from typing import Dict, Any, Tuple, List

def extract_numbers(text: str) -> List[float]:
    """Extracts all numbers from text, handling commas and decimals."""
    # Match numbers like -1,234.56 or 500 or .45
    matches = re.findall(r'-?\d+(?:,\d{3})*(?:\.\d+)?', text)
    nums = []
    for m in matches:
        try:
            nums.append(float(m.replace(',', '')))
        except ValueError:
            pass
    return nums

def _flatten_dict(d: Any) -> List[float]:
    """Recursively flattens a dictionary or list to extract all numerical values."""
    out = []
    if isinstance(d, dict):
        for v in d.values():
            out.extend(_flatten_dict(v))
    elif isinstance(d, list):
        for v in d:
            out.extend(_flatten_dict(v))
    elif isinstance(d, (int, float)):
        out.append(float(d))
    return out

def verify_claims(draft_answer: str, tool_outputs: Dict[str, Any]) -> Tuple[str, bool, List[str]]:
    """
    Extract every numerical figure in draft_answer and match it against tool_outputs.
    Flags unmatched numbers and returns a list of unmatched numbers as strings.
    """
    draft_nums = extract_numbers(draft_answer)
    valid_nums = set(_flatten_dict(tool_outputs))
    
    unmatched_nums = []
    for n in draft_nums:
        # We consider it a match if it's exact or within a small floating point tolerance (e.g. rounded to 2 decimal places)
        is_match = False
        for vn in valid_nums:
            # Check exact match, or rounded match
            if abs(n - vn) < 0.01:
                is_match = True
                break
            # Also check if it's a percentage representation (e.g. 0.05 in tools, 5 in text)
            if abs((n / 100.0) - vn) < 0.0001:
                is_match = True
                break
                
        if not is_match:
            unmatched_nums.append(n)
            
    # Format unmatched numbers for the UI
    unmatched_str = [str(n) for n in unmatched_nums]
    verified = len(unmatched_str) == 0
    
    return draft_answer, verified, unmatched_str
