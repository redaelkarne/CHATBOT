import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")

API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={API_KEY}"

HEADERS = {
    "Content-Type": "application/json"
}

available_services = {
    "oil change": True,
    "brake inspection": True,
    "engine diagnostics": False,
    "tire replacement": True,
    "car wash": True
}

def chat_with_gemini(user_message: str) -> str:
    available = ", ".join([s for s, is_available in available_services.items() if is_available])

    prompt = f"""
Vous êtes un assistant serviable dans un atelier de réparation automobile.
Votre travail est d’aider les clients à prendre des rendez-vous de réparation.

Les services actuellement disponibles sont : {available}.
Si un utilisateur demande un service indisponible, expliquez-le poliment et suggérez des alternatives.

Vous devez recueillir ces informations étape par étape :
- Nom complet
- Numéro de téléphone
- Adresse
- Modèle de la voiture
- Description du problème
- Date et heure préférées

Ne posez qu’une seule question à la fois et gardez vos réponses courtes et amicales.

Utilisateur : {user_message}
"""

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }

    try:
        response = requests.post(API_URL, headers=HEADERS, data=json.dumps(payload))
        response.raise_for_status()
        content = response.json()
        return content["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"Erreur : {str(e)}"
