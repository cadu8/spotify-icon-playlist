import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

try:
    cliente = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    print("🔎 Buscando modelos disponíveis para a sua chave API...\n")
    for modelo in cliente.models.list():
        if 'generateContent' in modelo.supported_actions:
            print(f"✅ Nome válido: {modelo.name}")
except Exception as e:
    print(f"Erro ao buscar modelos: {e}")