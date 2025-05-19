from fuzzywuzzy import fuzz
from operations_data import operations

FALLBACK_OPERATION_NAME = "Demande de rappel"
FALLBACK_THRESHOLD = 40 # Tweak this threshold based on testing

def match_issue_to_operation(user_input: str) -> dict:
    # Normalize input
    user_input = user_input.strip().lower()

    # Direct fallback triggers
    if "je ne sais pas" in user_input or "je sais pas" in user_input:
        return get_fallback_operation()

    best_score = 0
    best_match = None

    for operation in operations:
        score = fuzz.partial_ratio(user_input, operation["operation_name"].lower())
        if score > best_score:
            best_score = score
            best_match = operation

    if best_score >= FALLBACK_THRESHOLD:
        return best_match
    else:
        return get_fallback_operation()

def get_fallback_operation():
    return next(op for op in operations if op["operation_name"] == FALLBACK_OPERATION_NAME)
