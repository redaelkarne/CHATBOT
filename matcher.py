from fuzzywuzzy import fuzz
import re
from operations_data import operations

FALLBACK_OPERATION_NAME = "Demande de rappel"
DIRECT_MATCH_THRESHOLD = 80
CATEGORY_MATCH_THRESHOLD = 70
FALLBACK_THRESHOLD = 45

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

def match_issue_to_operations(user_input: str) -> list:
    """
    Return top 3 matching operations using your multi-step logic.
    """
    user_input = user_input.strip().lower()
    
    if any(phrase in user_input for phrase in ["je ne sais pas", "je sais pas", "aucune idée", 
                                             "pas sûr", "pas sure", "je ne comprends pas"]):
        return [get_fallback_operation()]
    
    # 1. Direct operation matches (score-based, top 3)
    direct_matches = get_direct_operation_matches(user_input)
    if direct_matches:
        return direct_matches
    
    # 2. Category-based matches (top 3)
    category_matches = get_category_matches(user_input)
    if category_matches:
        return category_matches
    
    # 3. Automotive term matches (top 3)
    automotive_matches = get_automotive_matches(user_input)
    if automotive_matches:
        return automotive_matches
    
    # 4. Fuzzy matches fallback (top 3)
    fuzzy_matches = get_fuzzy_matches(user_input)
    if fuzzy_matches:
        return fuzzy_matches
    
    # Fallback
    return [get_fallback_operation()]

def get_direct_operation_matches(user_input: str) -> list:
    scored = []
    for operation in operations:
        op_name = operation["operation_name"].lower()
        if op_name in user_input or user_input in op_name:
            score = fuzz.ratio(user_input, op_name)
            if score >= DIRECT_MATCH_THRESHOLD:
                scored.append((score, operation))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [op for score, op in scored[:3]] if scored else []

def get_category_matches(user_input: str) -> list:
    categories = {op["category"] for op in operations if "category" in op}
    scored = []
    best_category = None
    best_score = 0
    
    for category in categories:
        score = fuzz.token_set_ratio(user_input, category.lower())
        if score > best_score:
            best_score = score
            best_category = category
    
    if best_score >= CATEGORY_MATCH_THRESHOLD and best_category:
        category_ops = [op for op in operations if op.get("category") == best_category]
        # Prefer operations requesting more details first
        detail_ops = [op for op in category_ops if op.get("additionnal_comment") and "Merci de donner plus d'indications" in op.get("additionnal_comment", "")]
        if detail_ops:
            return detail_ops[:3]
        return category_ops[:3]
    return []

def get_automotive_matches(user_input: str) -> list:
    words = set(re.findall(r'\b\w+\b', user_input.lower()))
    parts = words.intersection(AUTO_PARTS)
    actions = words.intersection(AUTO_ACTIONS)
    
    scored = []
    if parts and actions:
        for operation in operations:
            op_name = operation["operation_name"].lower()
            op_cat = operation.get("category", "").lower()
            
            part_match = any(part in op_name or part in op_cat for part in parts)
            action_match = any(action in op_name or action in op_cat for action in actions)
            
            score = 0
            if part_match:
                score += 50
            if action_match:
                score += 30
            score += 5 * sum(1 for part in parts if part in op_name or part in op_cat)
            score += 3 * sum(1 for action in actions if action in op_name or action in op_cat)
            
            if score >= 60:
                scored.append((score, operation))
        scored.sort(key=lambda x: x[0], reverse=True)
        if scored:
            return [op for score, op in scored[:3]]
    
    # Special cases fallback as single-element lists (can be expanded similarly if needed)
    def check_and_return(keyword_list, operation_keyword):
        if any(kw in user_input for kw in keyword_list):
            ops = [op for op in operations if operation_keyword in op["operation_name"].lower()]
            if ops:
                return ops[:3]
        return []

    # Examples of special cases - return as list of matches (up to 3)
    special_cases = [
        (["pneu", "pneumatique", "roue"], "pneumatique"),
        (["contrôl", "control", "technique"], "contrôle technique"),
        (["pare-brise", "parebrise", "vitre"], "pare-brise"),
        (["embrayage"], "embrayage"),
        (["amortisseur", "suspension"], "amortisseur"),
        (["carrosserie", "carross", "tôle", "tole"], "carrosserie")
    ]

    for keywords, op_keyword in special_cases:
        matches = check_and_return(keywords, op_keyword)
        if matches:
            return matches

    return []

def get_fuzzy_matches(user_input: str) -> list:
    scored = []
    for operation in operations:
        op_name = operation["operation_name"].lower()
        partial_score = fuzz.partial_ratio(user_input, op_name)
        token_sort_score = fuzz.token_sort_ratio(user_input, op_name)
        token_set_score = fuzz.token_set_ratio(user_input, op_name)
        
        category_score = 0
        if "category" in operation:
            category_score = fuzz.token_set_ratio(user_input, operation["category"].lower()) * 0.5
        
        score = (partial_score * 0.4) + (token_sort_score * 0.2) + (token_set_score * 0.2) + category_score
        
        if score >= FALLBACK_THRESHOLD:
            scored.append((score, operation))
    
    scored.sort(key=lambda x: x[0], reverse=True)
    return [op for score, op in scored[:3]] if scored else []

def get_fallback_operation():
    return next((op for op in operations if op["operation_name"] == FALLBACK_OPERATION_NAME), operations[0])
