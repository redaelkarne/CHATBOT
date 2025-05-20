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
from matcher import match_issue_to_operation
from dealership import geocode_address_nominatim, find_closest_dealership

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
        return re.sub(r'[^a-zA-Z\s\'\-\.]', '', input_str)[:100]

    elif field_type == "phone_number":
        sanitized = re.sub(r'[^0-9\+\-\s\(\)]', '', input_str)
        if not PHONE_PATTERN.match(sanitized):
            raise ValueError("Format de numéro de téléphone invalide")
        return sanitized[:20]

    elif field_type == "address":
        if not ADDRESS_PATTERN.match(input_str):
            raise ValueError("Format d'adresse invalide")
        return input_str[:200]

    elif field_type == "car_model":
        return re.sub(r'[^a-zA-Z0-9\s\-\.]', '', input_str)[:100]

    elif field_type == "preferred_datetime":
        return re.sub(r'[^0-9\s\:\-\/\.]', '', input_str)[:50]

    return input_str[:2000]

def generate_next_question(next_field: str, collected_data: dict) -> str:
    collected_json = json.dumps(collected_data, ensure_ascii=False)
    prompt = f"""
Tu es un assistant convivial dans un atelier de réparation automobile.
Le client a déjà fourni ces informations : {collected_json}
La prochaine information à demander est : {next_field}
Formule une question claire, polie et concise en français pour demander cette information et commence par Bonjour.
"""
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
        # Fallback if Gemini API call fails
        fallback = FIELD_LABELS_FR.get(next_field, next_field)
        return f"{fallback} s'il vous plaît ?"

@app.post("/chat")
def chat_with_user(chat_request: ChatRequest, db: Session = Depends(get_db)):
    try:
        user_input = chat_request.message.strip().lower()

        # Handle follow-up for another issue
        if session_state.get("awaiting_additional_issue"):
            if user_input in ["oui", "yes", "y"]:
                prev_data = session_state.get("data", {})
                session_state["data"] = {
                    "full_name": prev_data.get("full_name", ""),
                    "phone_number": prev_data.get("phone_number", "")
                }
                session_state["current_field"] = "address"
                session_state["awaiting_additional_issue"] = False
                ai_question = generate_next_question("address", session_state["data"])
                return {"response": ai_question}
            elif user_input in ["non", "no", "n"]:
                reset_session()
                return {"response": "Merci ! N'hésitez pas à revenir si vous avez besoin d'un autre rendez-vous."}
            else:
                return {"response": "Veuillez répondre par 'oui' ou 'non'."}

        if not user_input:
            return {"response": "Veuillez entrer un message."}

        if session_state["current_field"] is None and not session_state["data"]:
            session_state["current_field"] = get_next_field()
            ai_question = generate_next_question(session_state["current_field"], session_state["data"])
            return {"response": ai_question}

        current_field = session_state["current_field"]

        try:
            sanitized_input = sanitize_input(user_input, current_field)
        except ValueError as e:
            return {"response": f"Erreur: {str(e)}. Veuillez réessayer."}

        if current_field:
            # Special logic for address field to find closest dealership
            if current_field == "address":
                # Geocode the entered address
                lat, lon = geocode_address_nominatim(sanitized_input)
                if lat is None or lon is None:
                    return {"response": "Désolé, je n'ai pas pu localiser cette adresse. Pouvez-vous préciser ou reformuler ?"}
                
                closest_dealer, distance = find_closest_dealership(lat, lon)
                if closest_dealer:
                    session_state["data"]["closest_dealer"] = closest_dealer
                    dealer_name = closest_dealer["dealership_name"]
                    city = closest_dealer["city"]
                    response_msg = (
                        f"Merci, j'ai localisé votre adresse. Le concessionnaire le plus proche est "
                        f"{dealer_name} à {city}, à environ {distance:.2f} km de chez vous."
                    )
                else:
                    response_msg = "Désolé, aucun concessionnaire proche n'a été trouvé."

                # Save the sanitized address anyway
                session_state["data"][current_field] = sanitized_input

                # Ask next question
                next_field = get_next_field()
                session_state["current_field"] = next_field
                ai_question = generate_next_question(next_field, session_state["data"])

                return {"response": response_msg + " " + ai_question}

            else:
                session_state["data"][current_field] = sanitized_input

                if current_field == "issue_description":
                    try:
                        matched_operation = match_issue_to_operation(sanitized_input)
                        session_state["data"]["matched_operation"] = matched_operation
                    except Exception:
                        session_state["data"]["matched_operation"] = {"error": "Impossible de classifier la demande"}

        next_field = get_next_field()
        if next_field:
            session_state["current_field"] = next_field
            ai_question = generate_next_question(next_field, session_state["data"])
            return {"response": ai_question}

        # No next field - save appointment to DB
        try:
            matched_operation = session_state["data"].get("matched_operation")
            if isinstance(matched_operation, dict):
                matched_operation_json = json.dumps(matched_operation)
            else:
                matched_operation_json = json.dumps({"operation": str(matched_operation)}) if matched_operation else None
            closest_dealer = session_state["data"].get("closest_dealer")
            dealership_name = closest_dealer.get("dealership_name") if closest_dealer else None
            db_data = {
                "full_name": session_state["data"].get("full_name", ""),
                "phone": session_state["data"].get("phone_number", ""),
                "address": session_state["data"].get("address", ""),
                "car_model": session_state["data"].get("car_model", ""),
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
            session_state["awaiting_additional_issue"] = True  # activate follow-up

            return {
                "response": "Merci, votre RDV a été enregistré ! Avez-vous une autre panne à déclarer ? (oui/non)",
                "data": saved_data
            }

        except Exception:
            db.rollback()
            reset_session()
            raise HTTPException(
                status_code=500,
                detail="Une erreur est survenue lors de l'enregistrement de votre rendez-vous. Veuillez réessayer."
            )

    except Exception:
        return {"response": "Une erreur est survenue. Veuillez réessayer plus tard."}