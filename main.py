from fastapi import FastAPI, HTTPException, Header, Response
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import json
import httpx
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import MemoryCacheHandler
from google import genai
from dotenv import load_dotenv
import base64
from io import BytesIO
from PIL import Image

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

cliente_ia = None
try:
    cliente_ia = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
except Exception as e:
    print(f"Erro AI: {e}")

# CONFIGURAÇÃO DE SEGURANÇA OAUTH 2.0
# ATENÇÃO: O redirect_uri AQUI deve ser IDÊNTICO ao que você colocou lá no Dashboard do Spotify!
sp_oauth = SpotifyOAuth(
    client_id=os.getenv("SPOTIPY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
    redirect_uri="https://spotify-icon-playlist.onrender.com/",
    scope="playlist-read-private playlist-read-collaborative ugc-image-upload playlist-modify-public playlist-modify-private",
    cache_handler=MemoryCacheHandler(),
    show_dialog=True
)

# Modelos de Dados
class TokenRequest(BaseModel):
    code: str

class PlaylistRequest(BaseModel):
    playlist_id: str

class CapasRequest(BaseModel):
    keyword: str
    pagina: int = 1

# NOVA ROTA: Despertador (Mantém o servidor do Render acordado)
@app.get("/api/ping")
def ping_server():
    return {"status": "online", "message": "O pai ta on!"}
# NOVA ROTA: O Salão Principal (Front-end)
@app.get("/")
def painel_visual():
    # Agora o Python sabe que precisa abrir a porta da pasta 'front' para achar o visual!
    return FileResponse("front/index.html")

# ROTA 1: Pede a URL de Autorização oficial do Spotify
@app.get("/api/auth/url")
def get_auth_url():
    return {"url": sp_oauth.get_authorize_url()}

# ROTA 2: Troca o código retornado pelo token de acesso real
@app.post("/api/auth/token")
def get_token(payload: TokenRequest):
    try:
        token_info = sp_oauth.get_access_token(payload.code, as_dict=True)
        return {"access_token": token_info["access_token"]}
    except Exception as e:
        raise HTTPException(status_code=400, detail="Erro ao gerar token")

# ROTA 3: Busca a biblioteca do usuário logado
@app.get("/api/playlists")
def listar_playlists(authorization: str = Header(None)):
    if not authorization: raise HTTPException(status_code=401, detail="Token ausente")
    token = authorization.replace("Bearer ", "")
    
    try:
        sp = spotipy.Spotify(auth=token)
        user_playlists = sp.current_user_playlists(limit=50) 
        lista = []
        for item in user_playlists['items']:
            if item:
                # Tenta pegar a primeira imagem da playlist. Se não tiver, manda None.
                imagem_url = item['images'][0]['url'] if item.get('images') and len(item['images']) > 0 else None
                
                lista.append({
                    "id": item['id'],
                    "nome": item['name'],
                    "dono": item['owner']['display_name'],
                    "imagem": imagem_url # <-- NOVA INFORMAÇÃO
                })
        return {"playlists": lista}
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

# ROTA 4: Varredura de Dados (Agora exigindo token!)
@app.post("/api/playlist/generate")
def gerar_dados(payload: PlaylistRequest, authorization: str = Header(None)):
    if not authorization: raise HTTPException(status_code=401)
    token = authorization.replace("Bearer ", "")
    sp = spotipy.Spotify(auth=token)
    
    try:
        print(f"\n[SYS.LOG] INICIANDO VARREDURA NO ID: '{payload.playlist_id}'")
        
        dados_playlist = sp.playlist(payload.playlist_id, market="BR")
        nome_playlist = dados_playlist.get("name", "Sem nome")
        dono_playlist = dados_playlist.get("owner", {}).get("display_name", "UNKNOWN_USER")
        
        dados_musicas = sp.playlist_items(payload.playlist_id, market="BR")
        
        musicas = []
        for item_dict in dados_musicas.get("items", []):
            faixa = item_dict.get("track") or item_dict.get("item")
            if faixa:
                nome_musica = faixa.get("name", "Desconhecido")
                artistas = ", ".join([a.get("name", "") for a in faixa.get("artists", [])])
                musicas.append(f"{nome_musica} - {artistas}")
        
        musicas_resumo = musicas[:15]
        
        # Módulo Analista Gemini
        analise_ia = {}
        if cliente_ia:
            prompt = f"""
            Você é um analista musical e diretor de arte sênior. 
            Analise rigorosamente esta playlist do Spotify:
            Título: {nome_playlist}
            Músicas: {', '.join(musicas_resumo)}
            
            Regras CRÍTICAS para a criação das 'keywords_visuais':
            1. Devem ser OBRIGATORIAMENTE EM INGLÊS (serão injetadas na API do Unsplash).
            2. NUNCA seja literal ou óbvio (ex: não use "fire" só porque o gênero é "Corinho de Fogo").
            3. CRUZE OS CONTEXTOS: Você deve unir o tema/mensagem das músicas (ex: Fé, Adoração, Gospel) com o ambiente sugerido pelo Título da playlist (ex: GYM, Treino, Foco).
            4. Pense em fotografias compostas reais. Se for Gospel + Academia, sugira termos como: "praying athlete", "faith fitness", "heavy cross", "lion motivation", "worship strength".
            
            Retorne uma análise profunda EXATAMENTE neste formato JSON, sem NENHUM texto adicional:
            {{
                "genero_predominante": "Subgênero exato em português",
                "energia_psicologica": "2 palavras descrevendo o mood em português",
                "cor_filtro_unsplash": "Escolha UMA: black_and_white, black, white, yellow, orange, red, purple, magenta, green, teal, blue",
                "keywords_visuais": ["termo composto em ingles 1", "termo composto em ingles 2", "termo composto em ingles 3"]
            }}
            """
            resposta_ia = cliente_ia.models.generate_content(model='gemini-3.5-flash', contents=prompt)
            texto_limpo = resposta_ia.text.strip().replace('```json', '').replace('```', '')
            try:
                analise_ia = json.loads(texto_limpo)
            except:
                analise_ia = {"genero_predominante": "UNKNOWN", "energia_psicologica": "UNKNOWN", "cor_filtro_unsplash": "black", "keywords_visuais": ["dark aesthetic"]}
        
        lista_keywords = analise_ia.get("keywords_visuais", ["dark"])
        cor_filtro = analise_ia.get("cor_filtro_unsplash", "")

        # Unsplash Sync
        imagens_urls = []
        unsplash_key = os.getenv("UNSPLASH_ACCESS_KEY")
        if unsplash_key and lista_keywords:
            parametros_unsplash = {"query": lista_keywords[0], "per_page": 6, "orientation": "squarish"}
            if cor_filtro in ["black_and_white", "black", "white", "yellow", "orange", "red", "purple", "magenta", "green", "teal", "blue"]:
                parametros_unsplash["color"] = cor_filtro

            with httpx.Client(timeout=30.0) as client:
                response = client.get("https://api.unsplash.com/search/photos", params=parametros_unsplash, headers={"Authorization": f"Client-ID {unsplash_key}"})
                if response.status_code == 200:
                    imagens_urls = [img.get("urls", {}).get("regular") for img in response.json().get("results", [])]

        return {
            "id": payload.playlist_id,
            "titulo": nome_playlist,
            "dono": dono_playlist,
            "total_musicas": len(musicas),
            "analise_profunda": analise_ia,
            "capas_sugeridas": imagens_urls
        }

    except Exception as e:
        print(f"[SYS.ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ROTA 5: Buscar mais fotos (Opcional, com filtro de cor se quiser implementar depois)
@app.post("/api/capas")
def buscar_mais_capas(payload: CapasRequest):
    try:
        unsplash_key = os.getenv("UNSPLASH_ACCESS_KEY")
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                "https://api.unsplash.com/search/photos",
                params={"query": payload.keyword, "per_page": 6, "page": payload.pagina, "orientation": "squarish"},
                headers={"Authorization": f"Client-ID {unsplash_key}"}
            )
            if response.status_code == 200:
                return {"capas_sugeridas": [img.get("urls", {}).get("regular") for img in response.json().get("results", [])]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
class UpdateCoverRequest(BaseModel):
    playlist_id: str
    image_url: str

@app.post("/api/playlist/cover")
def atualizar_capa(payload: UpdateCoverRequest, authorization: str = Header(None)):
    if not authorization: raise HTTPException(status_code=401)
    token = authorization.replace("Bearer ", "")
    sp = spotipy.Spotify(auth=token)

    try:
        print(f"[SYS.LOG] BAIXANDO IMAGEM PARA INJEÇÃO: {payload.image_url}")
        
        # 1. Baixa a imagem em alta resolução do Unsplash
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(payload.image_url)
            resp.raise_for_status()
            img_data = resp.content

        # 2. Processamento de Imagem (Força para JPEG, Redimensiona e Comprime < 256KB)
        img = Image.open(BytesIO(img_data))
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        img = img.resize((500, 500)) # Tamanho perfeito pro Spotify
        
        buffered = BytesIO()
        qualidade_atual = 90
        img.save(buffered, format="JPEG", quality=qualidade_atual)
        
        # Loop de compressão caso a imagem seja muito pesada
        while len(buffered.getvalue()) > 250000 and qualidade_atual > 10:
            qualidade_atual -= 10
            buffered = BytesIO()
            img.save(buffered, format="JPEG", quality=qualidade_atual)

        # 3. Criptografa em Base64 e dispara para o Spotify!
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        sp.playlist_upload_cover_image(payload.playlist_id, img_base64)

        return {"status": "success"}

    except Exception as e:
        print(f"[SYS.ERROR] FALHA NO UPLOAD: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
# NOVA ROTA: Túnel de Passagem para imagens do Spotify
@app.get("/api/image-proxy")
async def proxy_imagem_spotify(url: str):
    try:
        # 1. Valida se a URL é do Spotify (Agora aceitando os dois domínios oficiais!)
        if "scdn.co" not in url and "spotifycdn.com" not in url:
            raise HTTPException(status_code=400, detail=f"Origem de imagem inválida: {url}")

        # 2. Faz o download da imagem pelo backend (Com o AWAIT adicionado!)
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url) # <--- A palavra chave 'await' resolve o erro da coroutine
            
            # Se der erro no download, manda um 404
            if resp.status_code != 200:
                raise HTTPException(status_code=404, detail="Imagem não encontrada no Spotify.")
            
            # 3. Devolve os bytes da imagem com o cabeçalho CORS liberado!
            return Response(
                content=resp.content, 
                media_type="image/jpeg",
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Cache-Control": "max-age=3600" 
                }
            )
            
    except Exception as e:
        print(f"[SYS.ERROR] FALHA NO TÚNEL DE IMAGEM: {e}")
        raise HTTPException(status_code=500, detail=str(e))
if __name__ == "__main__":
    import uvicorn
    import os
    # Lê a porta que o Render vai fornecer, ou usa 8000 como fallback local
    porta = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=porta, reload=False)