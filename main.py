import os
import requests
import json
import re
import html
import bleach
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, validator, Field, constr
from sqlalchemy.orm import Session
from database import SessionLocal, engine
import models
from chat_session import session_state, get_next_field, reset_session, FIELD_LABELS_FR
from matcher import match_issue_to_operations
from dealership import geocode_address_nominatim, find_closest_dealership
import dateparser
from datetime import datetime
from fastapi import Query


app = FastAPI()

# Load Gemini API key & endpoint from env
API_KEY = os.getenv("GOOGLE_API_KEY")
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={API_KEY}"
HEADERS = {"Content-Type": "application/json"}

# Enhanced request model with validation
class ChatRequest(BaseModel):
    message: constr(strip_whitespace=True, min_length=1, max_length=2000) = Field(
        ..., description="User message input"
    )
    
    @validator('message')
    def sanitize_message(cls, v):
        sanitized = bleach.clean(v, tags=[], strip=True)
        sanitized = html.escape(sanitized)
        return sanitized

# New model for receiving user details from app
class UserDetailsRequest(BaseModel):
    full_name: constr(strip_whitespace=True, min_length=1, max_length=100) = Field(
        ..., description="User's full name"
    )
    phone_number: constr(strip_whitespace=True, min_length=5, max_length=20) = Field(
        ..., description="User's phone number"
    )
    address: constr(strip_whitespace=True, min_length=5, max_length=200) = Field(
        ..., description="User's address"
    )
    
    @validator('full_name')
    def validate_full_name(cls, v):
        sanitized = bleach.clean(v, tags=[], strip=True)
        sanitized = html.escape(sanitized)
        return sanitize_input(sanitized, "full_name")
        
    @validator('phone_number')
    def validate_phone_number(cls, v):
        sanitized = bleach.clean(v, tags=[], strip=True)
        sanitized = html.escape(sanitized)
        return sanitize_input(sanitized, "phone_number")
        
    @validator('address')
    def validate_address(cls, v):
        sanitized = bleach.clean(v, tags=[], strip=True)
        sanitized = html.escape(sanitized)
        return sanitize_input(sanitized, "address")

PHONE_PATTERN = re.compile(r'^\+?[0-9]{10,15}$')
ADDRESS_PATTERN = re.compile(r'^[a-zA-Z0-9\s\.,\-\']+$')

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def sanitize_input(input_str, field_type=None):
    if not input_str:
        return ""

    input_str = str(input_str).strip()
    input_str = bleach.clean(input_str, tags=[], strip=True)

    if field_type == "full_name":
        return re.sub(r"[^a-zA-ZÀ-ÿ\s'\-\.]", '', input_str)[:100]

    elif field_type == "phone_number":
        sanitized = re.sub(r"[^0-9\+\-\s\(\)]", '', input_str)
        if not PHONE_PATTERN.match(sanitized):
            raise ValueError("Format de numéro de téléphone invalide.")
        return sanitized[:20]

    elif field_type == "address":
        if not ADDRESS_PATTERN.match(input_str):
            raise ValueError(
                "Format d'adresse invalide. Veuillez entrer une adresse complète en France "
                "(numéro, rue, code postal et ville). Exemple : '12 Rue de la Paix, 75002 Paris'"
            )
        return input_str[:200]

    elif field_type == "car_immatriculation":
        input_str = input_str.upper()
        # Match a French plate format like AA-123-AA
        match = re.search(r"\b([A-Z]{2})[-\s]?(\d{3})[-\s]?([A-Z]{2})\b", input_str)
        if not match:
            raise ValueError("Format d'immatriculation invalide. Exemple attendu : AA-123-AA.")
        return match.group(0)

    elif field_type == "preferred_datetime":
        import dateparser
        import unicodedata
        from datetime import datetime

        now = datetime.now()

        # Normalize the input (removes accents inconsistently written)
        normalized_input = unicodedata.normalize("NFKC", input_str.strip())

        dt = dateparser.parse(
            normalized_input,
            languages=["fr"],
            settings={
                "PREFER_DATES_FROM": "future",
                "RELATIVE_BASE": now,
                "DATE_ORDER": "DMY",
                "RETURN_AS_TIMEZONE_AWARE": False,
                "STRICT_PARSING": False,
            },
        )

        if not dt:
            raise ValueError(
                "Je n'ai pas compris la date et l'heure. Essayez un format comme '12/10/2025 13:00' ou 'lundi prochain à 13h'."
            )

        # Catch unrealistically distant years
        if dt.year > now.year + 2:
            dt = dt.replace(year=now.year if dt.month >= now.month else now.year + 1)

        if dt <= now:
            raise ValueError("La date et l'heure doivent être dans le futur.")

        return dt.strftime("%Y-%m-%d %H:%M:%S")

    return input_str[:2000]



def generate_next_question(next_field: str, collected_data: dict) -> str:
    collected_json = json.dumps(collected_data, ensure_ascii=False)

    is_first = session_state.get("is_first_message", True)

    greeting_instruction = (
        "Commence ta réponse par 'Bonjour.'\n"
        if is_first else
        "Ne commence pas ta réponse par 'Bonjour.'\n"
    )

    FR_LABELS = {
        "car_immatriculation": "l'immatriculation du véhicule",
        "issue_description": "la description de la panne",
        "preferred_datetime": "la date et l'heure de disponibilité"
    }

    friendly_label = FR_LABELS.get(next_field, next_field)

    # When asking for issue_description, propose top 3 operations as choices
    if next_field == "issue_description":
        # You need the raw user input or partial issue description here.
        # Let's assume you get it from collected_data under 'issue_description' or user_input (adjust as needed)
        user_issue_input = collected_data.get("issue_description_raw", "")  
        # If not available, fallback to empty string
        if not user_issue_input:
            user_issue_input = ""

        # Get top 3 matched operations using your matching function (you'll have to implement this)
        top3_operations = match_issue_to_operations(user_issue_input)  # This returns list of dicts

        # Compose options list
        options_text = "\n".join(
            [f"{idx+1}. {op['operation_name']}" for idx, op in enumerate(top3_operations)]
        )

        prompt = (
            f"Le client a déjà donné : {collected_json}.\n"
            f"Ta tâche est de demander *uniquement* {friendly_label}.\n"
            f"{greeting_instruction}\n"
            f"Voici les trois options les plus probables pour la panne:\n{options_text}\n"
            "Merci de choisir l'une des options en indiquant son numéro."
        )

    else:
        # Usual prompt
        prompt = f"""
        Tu es un assistant d'atelier de réparation automobile. Le client a déjà donné : {collected_json}.
        Ta tâche est de demander *uniquement* {friendly_label}.
        {greeting_instruction}
        Écris une question claire, polie, concise et naturelle en français pour obtenir cette information.
        N'ajoute rien d'autre.
        """

    session_state["is_first_message"] = False

    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    try:
        response = requests.post(API_URL, headers=HEADERS, data=json.dumps(payload))
        response.raise_for_status()
        content = response.json()
        ai_text = content["candidates"][0]["content"]["parts"][0]["text"].strip()
        return ai_text
    except Exception:
        fallback = FR_LABELS.get(next_field, next_field)
        return f"{fallback} s'il vous plaît ?"

@app.get("/initialize_chat")
def initialize_chat_via_get(
    full_name: str = Query(..., min_length=1, max_length=100),
    phone_number: str = Query(..., min_length=5, max_length=20),
    address: str = Query(..., min_length=5, max_length=200),
    db: Session = Depends(get_db)
):
    try:
        # Sanitize and validate input using your sanitize_input function
        sanitized_full_name = sanitize_input(full_name, "full_name")
        sanitized_phone = sanitize_input(phone_number, "phone_number")
        sanitized_address = sanitize_input(address, "address")

        # Reset any existing chat session state
        reset_session()

        # Initialize session state for new chat
        session_state.update({
             "current_field": "car_immatriculation",
            "data": {
                "full_name": sanitized_full_name,
                "phone_number": sanitized_phone,
                "address": sanitized_address
            },
            "awaiting_additional_issue": False,
            "first_chat_message": True  # Must match /chat usage
        })

        # Attempt to find closest dealership from address
        dealership_info = ""
        try:
            lat, lon = geocode_address_nominatim(sanitized_address)
            if lat is not None and lon is not None:
                closest_dealer, distance = find_closest_dealership(lat, lon)
                if closest_dealer:
                    session_state["data"]["closest_dealer"] = closest_dealer
                    dealer_name = closest_dealer["dealership_name"]
                    city = closest_dealer["city"]
                    dealership_info = (
                        f"J'ai localisé votre adresse. Le concessionnaire le plus proche est "
                        f"{dealer_name} à {city}, à environ {distance:.2f} km de chez vous. "
                    )
        except Exception:
            # Ignore geocode or dealer lookup errors silently
            pass

        # Generate first question for car_model
        ai_question = generate_next_question("car_immatriculation", session_state["data"])

        # Compose response greeting + dealership info + first question
        if dealership_info:
            response = f"Bonjour {sanitized_full_name}. {dealership_info}{ai_question}"
        else:
            response = f"Bonjour {sanitized_full_name}. {ai_question}"

        return {"response": response}

    except ValueError as e:
        return {"response": f"Erreur: {str(e)}. Veuillez vérifier les informations fournies."}
    except Exception as e:
        return {"response": f"Une erreur est survenue lors de l'initialisation du chat: {str(e)}"}

@app.post("/chat")
def chat_with_user(chat_request: ChatRequest, db: Session = Depends(get_db)):
    try:
        user_input = chat_request.message.strip()
        if not user_input:
            return {"response": "Veuillez entrer un message."}

        if not session_state.get("data"):
            return {"response": "Veuillez d'abord initialiser le chat avec vos informations."}

        user_input_lower = user_input.lower()

        # Step 1: Handle additional issue prompt
        if session_state.get("awaiting_additional_issue"):
            if user_input_lower in ["oui", "yes", "y"]:
                prev_data = session_state.get("data", {})
                session_state["data"] = {
                    "full_name": prev_data.get("full_name", ""),
                    "phone_number": prev_data.get("phone_number", ""),
                    "address": prev_data.get("address", ""),
                    "closest_dealer": prev_data.get("closest_dealer", "")
                }
                session_state["current_field"] = "car_immatriculation"
                session_state["awaiting_additional_issue"] = False
                ai_question = generate_next_question("car_immatriculation", session_state["data"])
                return {"response": ai_question}
            elif user_input_lower in ["non", "no", "n"]:
                reset_session()
                return {"response": "Merci ! N'hésitez pas à revenir si vous avez besoin d'un autre rendez-vous."}
            else:
                return {"response": "Veuillez répondre par 'oui' ou 'non'."}

        # Step 2: Handle first interaction
        if session_state.get("first_chat_message", True):
            user_name = session_state["data"].get("full_name", "Monsieur")
            user_address = session_state["data"].get("address", "votre adresse")
            closest_dealer = session_state["data"].get("closest_dealer", None)

            dealer_text = ""
            if closest_dealer:
                dealer_name = closest_dealer.get("dealership_name", "")
                city = closest_dealer.get("city", "")
                dealer_text = f"Le concessionnaire le plus proche est {dealer_name} à {city}."

            prompt = (
                f"Tu es un assistant chaleureux et poli. "
                f"Commence ta réponse par une salutation naturelle, par exemple : "
                f'\"Bonjour Monsieur {user_name}, j’ai localisé votre adresse : {user_address}.\" '
                f"Inclus si possible l'information suivante : {dealer_text} "
                f"Ensuite, demande-lui poliment son immatriculation de manière naturelle, fluide et engageante, "
                f"comme si tu parlais à un vrai client."
            )

            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            response = requests.post(API_URL, headers=HEADERS, data=json.dumps(payload))
            response.raise_for_status()
            content = response.json()
            ai_reply = content["candidates"][0]["content"]["parts"][0]["text"].strip()

            session_state["first_chat_message"] = False
            session_state["current_field"] = "car_immatriculation"

            return {"response": ai_reply}

        current_field = session_state.get("current_field")

        # Step 3.1: If waiting for user choice from top matches
        if current_field == "awaiting_operation_choice":
            top_matches = session_state["data"].get("top_matches", [])
            if user_input.isdigit():
                choice = int(user_input)
                if 1 <= choice <= len(top_matches):
                    session_state["data"]["matched_operation"] = top_matches[choice - 1]
                    # Remove temporary keys
                    session_state["data"].pop("top_matches", None)
                    session_state["data"].pop("issue_description_raw", None)
                    session_state["current_field"] = get_next_field()
                    ai_question = generate_next_question(session_state["current_field"], session_state["data"])
                    return {"response": ai_question}
                else:
                    return {"response": f"Numéro invalide. Veuillez choisir un chiffre entre 1 et {len(top_matches)}."}
            elif user_input_lower in ["aucune", "none"]:
                session_state["data"]["matched_operation"] = {
                    "operation_name": "Demande de rappel",
                    "category": "Autre",
                    "time_unit": 0,
                    "price": 0
                }
                session_state["data"].pop("top_matches", None)
                session_state["data"].pop("issue_description_raw", None)
                session_state["current_field"] = get_next_field()
                ai_question = generate_next_question(session_state["current_field"], session_state["data"])
                return {"response": ai_question}
            else:
                return {"response": "Réponse invalide. Veuillez entrer le numéro de l'opération ou 'aucune'."}

        # Step 3.2: For normal fields (including issue_description)
        try:
            # For issue_description, keep raw input for matching and showing options
            if current_field == "issue_description":
                session_state["data"]["issue_description_raw"] = user_input
            sanitized_input = sanitize_input(user_input, current_field)
            session_state["data"][current_field] = sanitized_input
        except ValueError as e:
            return {"response": f"Erreur: {str(e)}. Veuillez réessayer."}

        # Step 4: After user enters issue_description, present top 3 matches and wait choice
        if current_field == "issue_description":
            try:
                # Use your existing matcher function, ensure it returns list of dicts with keys 'operation_name', 'category' etc.
                top_matches = match_issue_to_operations(user_input)[:3]
                if not top_matches:
                    # Fallback if no matches
                    top_matches = [{
                        "operation_name": "Demande de rappel",
                        "category": "Autre",
                        "time_unit": 0,
                        "price": 0
                    }]
                session_state["data"]["top_matches"] = top_matches
                session_state["current_field"] = "awaiting_operation_choice"

                options_text = "\n".join(
                    [f"{idx+1}. {op['operation_name']} ({op['category']})" for idx, op in enumerate(top_matches)]
                )

                return {
                    "response": (
                        "Voici les 3 opérations les plus probables :\n"
                        f"{options_text}\n"
                        "Veuillez répondre avec le numéro correspondant ou tapez 'aucune' si aucune ne convient."
                    )
                }
            except Exception:
                # On exception fallback
                session_state["data"]["matched_operation"] = {
                    "operation_name": "Demande de rappel",
                    "category": "Autre",
                    "time_unit": 0,
                    "price": 0
                }
                session_state["current_field"] = get_next_field()
                ai_question = generate_next_question(session_state["current_field"], session_state["data"])
                return {"response": ai_question}

        # Step 5: Proceed to next field or save
        next_field = get_next_field()
        if next_field:
            session_state["current_field"] = next_field
            ai_question = generate_next_question(next_field, session_state["data"])
            return {"response": ai_question}

        # Step 6: Save appointment
        try:
            matched_operation = session_state["data"].get("matched_operation")
            matched_operation_json = json.dumps(
                matched_operation if isinstance(matched_operation, dict)
                else {"operation": str(matched_operation)}
            ) if matched_operation else None

            closest_dealer = session_state["data"].get("closest_dealer")
            dealership_name = closest_dealer.get("dealership_name") if closest_dealer else None

            db_data = {
                "full_name": session_state["data"].get("full_name", ""),
                "phone": session_state["data"].get("phone_number", ""),
                "address": session_state["data"].get("address", ""),
                "car_immatriculation": session_state["data"].get("car_immatriculation", ""),
                "issue_description": session_state["data"].get("issue_description", ""),
                "preferred_datetime": session_state["data"].get("preferred_datetime", ""),
                "matched_operation": matched_operation_json,
                "dealership_name": dealership_name
            }

            appointment = models.Appointment(**db_data)
            db.add(appointment)
            db.commit()
            db.refresh(appointment)

            saved_data = session_state["data"].copy()
            session_state["awaiting_additional_issue"] = True

            return {
                "response": "Merci, votre RDV a été enregistré ! Avez-vous une autre panne à déclarer ? (oui/non)",
                "data": saved_data
            }

        except Exception as e:
            db.rollback()
            reset_session()
            raise HTTPException(
                status_code=500,
                detail=f"Une erreur est survenue lors de l'enregistrement de votre rendez-vous. {str(e)}"
            )

    except Exception as e:
        return {"response": f"Une erreur est survenue. {str(e)}"}


# Reset chat session explicitly
@app.post("/reset_chat")
def reset_chat_endpoint():
    reset_session()
    session_state.update({
        "current_field": None,
        "data": {},
        "awaiting_additional_issue": False,
        "is_first_message": True
    })
    return {"response": "Session réinitialisée avec succès."}