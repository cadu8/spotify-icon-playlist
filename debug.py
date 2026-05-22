import os
import json
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

load_dotenv()

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=os.getenv("SPOTIFY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
    redirect_uri="http://127.0.0.1:8888/callback",
    scope="playlist-read-private playlist-read-collaborative"
))

# ID da sua playlist Gym³
playlist_id = "38XkKqBbqtILEngHEDM7Sb"

print(f"🔎 Fazendo o raio-x da playlist {playlist_id}...\n")

try:
    # Pegando os itens de forma crua
    dados = sp.playlist_items(playlist_id, market="BR")
    
    # Vamos olhar para os primeiros 2 itens da lista (se existirem)
    itens = dados.get('items', [])
    
    print(f"Total de itens reportados pelo servidor: {dados.get('total')}")
    print(f"Tamanho da lista recebida: {len(itens)}\n")
    
    if len(itens) > 0:
        print("👇 Estrutura do primeiro item devolvido pelo Spotify:")
        # Imprime o JSON formatado para lermos a estrutura
        print(json.dumps(itens[0], indent=2, ensure_ascii=False))
    else:
        print("❌ A lista 'items' veio completamente vazia do servidor.")

except Exception as e:
    print(f"Erro: {e}")