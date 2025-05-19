# chat_session.py

session_state = {
    "data": {},
    "current_field": None,
    "awaiting_additional_issue": False,
}

FIELDS = [
    "full_name",
    "phone_number",
    "address",
    "car_model",
    "issue_description",
    "preferred_datetime",
]

FIELD_LABELS_FR = {
    "full_name": "Quel est votre nom",
    "phone_number": "Quel est votre numéro de téléphone",
    "address": "Quelle est votre adresse",
    "car_model": "Quel est le modèle de votre voiture",
    "issue_description": "Décrivez la panne ou le problème",
    "preferred_datetime": "Quelle est votre date et heure préférée pour le rendez-vous",
}

def get_next_field():
    for field in FIELDS:
        if field not in session_state["data"] or not session_state["data"][field]:
            return field
    return None

def reset_session():
    session_state["data"] = {}
    session_state["current_field"] = None
    session_state["awaiting_additional_issue"] = False
