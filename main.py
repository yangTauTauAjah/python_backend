from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os
import json
from transcribe import run_transcription_pipeline, run_translation_pipeline
from urllib.parse import urlparse, parse_qs
from db_utils import get_video_status, update_video_status
import asyncio
import os
from dotenv import load_dotenv
    
load_dotenv()
app = FastAPI()
security = HTTPBearer()  # This handles "Authorization: Bearer <token>"

# Dummy token for example purposes
BACKEND_VALID_TOKEN = os.getenv("BACKEND_VALID_TOKEN")

def extract_hostname(url: str) -> str | None:
    try:
        parsed_url = urlparse(url)
        return parsed_url.hostname
    except Exception as e:
        print(f"Invalid URL: {url} -> {e}")
        return None

def extract_youtube_video_id(url: str) -> str:
    # Handle standard YouTube URL
    parsed = urlparse(url)
    if parsed.hostname in ["www.youtube.com", "youtube.com"]:
        query = parse_qs(parsed.query)
        return query.get("v", [None])[0]

    # Handle shortened youtu.be URL
    if parsed.hostname == "youtu.be":
        return parsed.path.lstrip("/")

def extract_platform_name(url: str) -> str:
    hostname = urlparse(url).hostname
    if hostname is None:
        raise ValueError("Invalid URL: hostname could not be determined")
    
    # Remove 'www.' if present
    if hostname.startswith('www.'):
        hostname = hostname[4:]
    
    # Extract the second-level domain (like 'youtube' from 'youtube.com')
    domain_parts = hostname.split('.')
    if len(domain_parts) < 2:
        raise ValueError(f"Unexpected hostname format: {hostname}")
    
    platform_name = domain_parts[-2]  # e.g. 'youtube', 'vimeo'
    
    return platform_name

def read_json_file(path: str):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    if token != BACKEND_VALID_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return token  # or return user info if decoded

@app.get("/protected")
def protected_route(token: str = Depends(verify_token)):
    return {"message": "You are authorized!"}

@app.get("/")
async def index():
    return JSONResponse(content={"message": 'hello world'})
  
@app.get("/transcribe")  
async def transcribe(video_url: str, lang: str = 'ja', token: str = Depends(verify_token)):
    platform = extract_platform_name(video_url)
    video_id = extract_youtube_video_id(video_url)
    path = f"{platform}/{video_id}/{lang}.json"

    try:

        if os.path.exists(path):
            update_video_status(platform, video_id, transcripting=False)
            data = read_json_file(path)
            return JSONResponse({"status": "done", "data": data})

        status = get_video_status(platform, video_id)
        
        if not status or not status.get("transcripting"):
            update_video_status(platform, video_id, transcripting=True)
            asyncio.create_task(asyncio.to_thread(run_transcription_pipeline, platform, video_id, lang))
            
        return JSONResponse({"status": "processing"})
        
    except Exception as e:
        update_video_status(platform, video_id, transcripting=False)
        print(f"An error occured: ${str(e)}")
        return JSONResponse({"status": "error", "message": "An error occured while transcribing video"}, status_code=500)

@app.get("/translate")
async def translate(video_url: str, lang: str = "en", token: str = Depends(verify_token)):
    platform = extract_platform_name(video_url)
    video_id = extract_youtube_video_id(video_url)
    path = f"{platform}/{video_id}/{lang}.json"

    try:

        if os.path.exists(path):
            update_video_status(platform, video_id, translating=False)
            data = read_json_file(path)
            return JSONResponse({"status": "done", "data": data})

        status = get_video_status(platform, video_id)
        
        if not status or not status.get("translating"):
            update_video_status(platform, video_id, translating=True)
            asyncio.create_task(run_translation_pipeline(platform, video_id, lang))
            
        return JSONResponse({"status": "processing"})
    except Exception as e:
        update_video_status(platform, video_id, translating=False)
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    
@app.on_event("shutdown")
async def on_shutdown():
    from supabase_client import reset_all_processing_flags
    await reset_all_processing_flags()
    
    

# @app.get("/transcribe")
# async def transcribe(video_url: str):
#     hostname = extract_platform_name(video_url)
#     video_id = extract_youtube_video_id(video_url)
#     print(hostname)
#     file_path = f"{hostname}/{video_id}/ja.json"
    
#     if os.path.exists(file_path):
#         result = read_json_file(file_path)
#         return JSONResponse(content=result) 

#     try:
#         run_transcription_pipeline(hostname, video_id, 'ja')
#         result = read_json_file(file_path)
#         return JSONResponse(content=result)
#     except Exception as e:
#         return JSONResponse(status_code=500, content={"error": str(e)})

# @app.get("/translate")
# async def translate(video_url: str, target_lang: str = "en"):
#     hostname = extract_platform_name(video_url)
#     video_id = extract_youtube_video_id(video_url)
#     file_path = f"{hostname}/{video_id}/{target_lang}.json"

#     if os.path.exists(file_path):
#         result = read_json_file(file_path)
#         return JSONResponse(content=result)
    
#     try:
#         await run_translation_pipeline(hostname, video_id, target_lang)
#         result = read_json_file(file_path)
#         return JSONResponse(content=result)
#     except Exception as e:
#         return JSONResponse(status_code=500, content={"error": str(e)})