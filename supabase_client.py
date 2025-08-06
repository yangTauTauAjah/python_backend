from supabase import create_client, Client
import os
from dotenv import load_dotenv

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

async def reset_all_processing_flags():
    supabase.table("video_status").update({"transcripting": False, "translating": False}).not_.is_("id", "null").execute()
