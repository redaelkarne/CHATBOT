from fuzzywuzzy import fuzz
import re
from operations_data import operations

FALLBACK_OPERATION_NAME = "Demande de rappel"
DIRECT_MATCH_THRESHOLD = 80   # High confidence direct match
CATEGORY_MATCH_THRESHOLD = 70 # Medium confidence for category matching
FALLBACK_THRESHOLD = 45       # Low confidence fallback threshold

# Automotive-specific French vocabulary for better matching
AUTO_PARTS = {
    "pneu", "pneumatique", "roue", "jante", "amortisseur", "suspension",
    "frein", "plaquette", "disque", "pare-brise", "vitre", "phare", "feu",
    "batterie", "huile", "filtre", "moteur", "embrayage", "boîte", "boite",
    "transmission", "échappement", "pot", "carrosserie", "carrossier"
}

AUTO_ACTIONS = {
    "changer", "remplacer", "réparer", "reparer", "vérifier", "verifier",
    "contrôler", "controler", "réviser", "reviser", "vidanger", "niveler",
    "régler", "regler", "installer", "nettoyer", "diagnostiquer", "aligner"
}

def match_issue_to_operation(user_input: str) -> dict:
    """
    Enhanced matching algorithm specialized for automotive operations
    """
    # Normalize input
    user_input = user_input.strip().lower()
    
    # Direct fallback triggers - explicitly handle "I don't know" responses
    if any(phrase in user_input for phrase in ["je ne sais pas", "je sais pas", "aucune idée", 
                                             "pas sûr", "pas sure", "je ne comprends pas"]):
        return get_fallback_operation()
    
    # 1. Try direct operation name matching with high threshold
    direct_match = try_direct_operation_match(user_input)
    if direct_match:
        return direct_match
    
    # 2. Try category-based matching
    category_match = try_category_match(user_input)
    if category_match:
        return category_match
    
    # 3. Try automotive term matching
    auto_match = try_automotive_match(user_input)
    if auto_match:
        return auto_match
    
    # 4. Last resort fuzzy match with lower threshold
    fuzzy_match = try_fuzzy_match(user_input)
    if fuzzy_match:
        return fuzzy_match
    
    # Fall back if no match is found
    return get_fallback_operation()

def try_direct_operation_match(user_input: str) -> dict:
    """Attempt to directly match the operation name with high confidence"""
    best_score = 0
    best_match = None
    
    for operation in operations:
        # Try exact match first (case insensitive)
        op_name = operation["operation_name"].lower()
        if op_name in user_input or user_input in op_name:
            score = fuzz.ratio(user_input, op_name)
            if score > best_score:
                best_score = score
                best_match = operation
    
    if best_score >= DIRECT_MATCH_THRESHOLD:
        return best_match
    return None

def try_category_match(user_input: str) -> dict:
    """Match based on the category field"""
    best_score = 0
    best_match = None
    best_category = None
    
    # First, find the best matching category
    categories = {op["category"] for op in operations if "category" in op}
    
    for category in categories:
        # Use token set ratio to handle different word orders and partial matches
        score = fuzz.token_set_ratio(user_input, category.lower())
        if score > best_score:
            best_score = score
            best_category = category
    
    # If we have a good category match
    if best_score >= CATEGORY_MATCH_THRESHOLD and best_category:
        # Find the most general operation in that category
        # or the one with the shortest name (likely most general)
        category_ops = [op for op in operations if op.get("category") == best_category]
        
        if category_ops:
            # Check for operations with additional comments requesting more details
            detail_ops = [op for op in category_ops 
                         if op.get("additionnal_comment") and 
                         "Merci de donner plus d'indications" in op.get("additionnal_comment", "")]
            
            if detail_ops:
                # Return the general operation that asks for more details
                return detail_ops[0]
            else:
                # Just return the first operation in the category
                return category_ops[0]
    
    return None

def try_automotive_match(user_input: str) -> dict:
    """Try to match based on automotive-specific terms"""
    words = set(re.findall(r'\b\w+\b', user_input.lower()))
    
    # Extract automotive terms from input
    parts = words.intersection(AUTO_PARTS)
    actions = words.intersection(AUTO_ACTIONS)
    
    best_score = 0
    best_match = None
    
    # If we found both parts and actions, this is a strong signal
    if parts and actions:
        for operation in operations:
            op_name = operation["operation_name"].lower()
            op_category = operation.get("category", "").lower()
            
            # Check if any part or action words match the operation
            part_match = any(part in op_name or part in op_category for part in parts)
            action_match = any(action in op_name or action in op_category for action in actions)
            
            # Calculate score based on matches
            score = 0
            if part_match:
                score += 50  # 50 points for matching a part
            if action_match:
                score += 30  # 30 points for matching an action
            
            # Extra points for each additional match
            score += 5 * sum(1 for part in parts if part in op_name or part in op_category)
            score += 3 * sum(1 for action in actions if action in op_name or action in op_category)
            
            if score > best_score:
                best_score = score
                best_match = operation
        
        # Return if we have a decent automotive match (at least 60 points)
        if best_score >= 60:
            return best_match
    
    # Special case handling for common automotive terms
    if "pneu" in words or "pneumatique" in words or "roue" in words:
        pneumatic_ops = [op for op in operations 
                        if "pneumatique" in op["operation_name"].lower() or 
                           "pneu" in op["operation_name"].lower()]
        if pneumatic_ops:
            # If they mention pressure, prioritize pressure check
            if "pression" in words or "gonfl" in user_input:
                pressure_ops = [op for op in pneumatic_ops if "pression" in op["operation_name"].lower()]
                if pressure_ops:
                    return pressure_ops[0]
            # Otherwise, prioritize tire replacement
            replacement_ops = [op for op in pneumatic_ops if "remplacement" in op["operation_name"].lower()]
            if replacement_ops:
                return replacement_ops[0]
            return pneumatic_ops[0]
    
    if "contrôl" in user_input or "control" in user_input or "technique" in user_input:
        tech_control_ops = [op for op in operations if "contrôle technique" in op["operation_name"].lower()]
        if tech_control_ops:
            return tech_control_ops[0]
    
    if "pare-brise" in user_input or "parebrise" in user_input or "vitre" in user_input:
        windshield_ops = [op for op in operations if "pare-brise" in op["operation_name"].lower()]
        if windshield_ops:
            return windshield_ops[0]
    
    if "embrayage" in user_input:
        clutch_ops = [op for op in operations if "embrayage" in op["operation_name"].lower()]
        if clutch_ops:
            return clutch_ops[0]
    
    if "amortisseur" in user_input or "suspension" in user_input:
        shock_ops = [op for op in operations if "amortisseur" in op["operation_name"].lower()]
        if shock_ops:
            return shock_ops[0]
    
    if "carrosserie" in user_input or "carross" in user_input or "tôle" in user_input or "tole" in user_input:
        body_ops = [op for op in operations if "carrosserie" in op["operation_name"].lower()]
        if body_ops:
            return body_ops[0]
    
    return None

def try_fuzzy_match(user_input: str) -> dict:
    """Fall back to fuzzy matching with a lower threshold"""
    best_score = 0
    best_match = None

    for operation in operations:
        # Use a combination of matching algorithms for better results
        partial_score = fuzz.partial_ratio(user_input, operation["operation_name"].lower())
        token_sort_score = fuzz.token_sort_ratio(user_input, operation["operation_name"].lower())
        token_set_score = fuzz.token_set_ratio(user_input, operation["operation_name"].lower())
        
        # Include category in matching if available
        category_score = 0
        if "category" in operation:
            category_score = fuzz.token_set_ratio(user_input, operation["category"].lower()) * 0.5
        
        # Calculate a weighted average of the different matching algorithms
        score = (partial_score * 0.4) + (token_sort_score * 0.2) + (token_set_score * 0.2) + category_score
        
        if score > best_score:
            best_score = score
            best_match = operation

    if best_score >= FALLBACK_THRESHOLD:
        return best_match
    return None

def get_fallback_operation():
    """Get the fallback operation"""
    return next((op for op in operations if op["operation_name"] == FALLBACK_OPERATION_NAME), operations[0])