from supabase_client import supabase


def get_video_status(platform: str, video_id: str):
    response = (
        supabase.table("video_status")
        .select("*")
        .eq("platform", platform)
        .eq("video_id", video_id)
        .execute()
    )
    data = response.data
    return data[0] if data else None


def update_video_status(platform: str, video_id: str, **kwargs):
    # If already exists, update
    if get_video_status(platform, video_id):
        return (
            supabase.table("video_status")
            .update(kwargs)
            .eq("platform", platform)
            .eq("video_id", video_id)
            .execute()
        )
    # Else, insert new
    return (
        supabase.table("video_status")
        .insert({**kwargs, "platform": platform, "video_id": video_id})
        .execute()
    )
