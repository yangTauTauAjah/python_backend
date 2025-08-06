from pytubefix import YouTube
from pydub import AudioSegment
import os
import io
from openai import OpenAI
from typing import List
import tempfile
import json
import asyncio
from dotenv import load_dotenv
    
load_dotenv()

api_key = os.getenv('OPENAI_API_KEY')  # Replace with your actual key
client = OpenAI(api_key=api_key)



def create_video_dir(path: str, base_path=".") -> str:
    # video_id = extract_youtube_video_id(url)
    # if not video_id:
    #     raise ValueError("Could not extract video ID from URL")

    path = os.path.join(base_path, path)
    os.makedirs(path, exist_ok=True)
    return path


# Step 1: Download YouTube and convert to MP3
def download_youtube_audio_to_buffer(video_id: str) -> io.BytesIO:
    yt = YouTube(f"https://www.youtube.com/watch?v={video_id}")
    print(f"Downloading youtube video from: https://www.youtube.com/watch?v={video_id}")
    audio_stream = yt.streams.filter(only_audio=True).order_by("abr").desc().first()

    buffer = io.BytesIO()
    audio_stream.stream_to_buffer(buffer)
    buffer.seek(0)  # Reset pointer to start of the stream
    print("Video downloaded successfully.")

    return buffer


# Step 2: Split audio if larger than 25MB
def split_audio_from_buffer(
    buffer: io.BytesIO, max_size_kb: int = 25 * 1024
) -> List[AudioSegment]:
    """
    Splits an audio file (from a buffer) into chunks under the size limit.

    Args:
        buffer (io.BytesIO): Audio file in memory
        max_size_kb (int): Max size for each chunk
    """

    # Load audio from buffer

    audio = AudioSegment.from_file(buffer)
    total_duration_ms = len(audio)

    # Estimate size per ms
    buffer.seek(0, os.SEEK_END)
    file_size_bytes = buffer.tell()
    buffer.seek(0)
    size_per_ms = file_size_bytes / total_duration_ms
    max_chunk_size_bytes = max_size_kb * 1024
    max_chunk_duration_ms = int(max_chunk_size_bytes / size_per_ms)

    print("Splitting audio file.")
    if file_size_bytes < max_chunk_size_bytes:
        print(
            f"Video size is less than {max_chunk_size_bytes/(1024*1024)}mb, returning original content."
        )
        return [audio]

    print(
        f"Video size exceeded {max_chunk_size_bytes/(1024*1024)}mb, performing split to break up to chunks."
    )

    # Split
    chunks = []
    for i in range(0, total_duration_ms, max_chunk_duration_ms):
        chunk = audio[i : i + max_chunk_duration_ms]
        chunks.append(chunk)

    print("Splitting has done successfully.")

    return chunks


# Step 3: Transcribe with OpenAI Whisper
def transcribe_audio_chunks_memory(
    audio_chunks: List[AudioSegment], model="whisper-1", language="en"
):
    transcripts = []
    start = 0

    for idx, chunk in enumerate(audio_chunks):
        # Create a temporary file but close it immediately to allow writing
        with tempfile.NamedTemporaryFile(
            suffix=".mp3", delete=False
        ) as temp_audio_file:
            temp_filename = temp_audio_file.name

        try:
            # Export chunk to the closed file
            chunk.export(temp_filename, format="mp3")

            print(f"Performing audio transcription...")
            # Open and transcribe
            with open(temp_filename, "rb") as f:
                print(f"Transcribing chunk {idx}...")
                response = client.audio.transcriptions.create(
                    model=model,
                    file=f,
                    language=language,
                    response_format="verbose_json",
                    include=["logprobs"],
                    timestamp_granularities=["segment"],
                )

            transcripts.append(
                {
                    "index": idx,
                    "start": start,
                    "end": start + len(chunk),
                    "transcript": [
                        {"start": x.start, "end": x.end, "text": x.text}
                        for x in response.segments
                    ],
                }
            )

            start = len(chunk)

        finally:
            print(f"Audio transcribed successfully.")
            # Cleanup: delete the temporary file
            if os.path.exists(temp_filename):
                os.remove(temp_filename)

    return transcripts


def save_chunks_to_file(transcripts: list, output_path: str = "transcript.json"):
    #     """
    #     Saves list of OpenAI transcription responses to a JSON file after converting them to dicts.
    #     """
    dict_transcripts = []
    for t in transcripts:
        if hasattr(t, "model_dump"):
            dict_transcripts.append(t.model_dump())
        elif hasattr(t, "__dict__"):
            dict_transcripts.append(vars(t))
        else:
            dict_transcripts.append(t)  # fallback if already a dict or primitive type

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dict_transcripts, f, ensure_ascii=False, indent=2)

    print(f"Transcript saved to {output_path}")


def translate(input: str, target_lang: str = "en", model: str = "gpt-4.1"):

    prompt = (
        f"Translate the following array of sentences to {target_lang}. "
        f"Only return the translated version without explanation:\n\n{input}"
    )
    
    print(f"Translating input: {input}")
    translated_text = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": "You are a helpful translation assistant.",
            },
            {"role": "user", "content": prompt},
        ],
    )

    return translated_text.output_text


async def translate_transcription(
    input_file: str, target_lang: str = "en", model: str = "gpt-4.1"
):

    with open(input_file, "r", encoding="utf-8") as f:
        transcription = json.load(f)

    translations = await asyncio.gather(
        *[
            asyncio.to_thread(translate, segment["text"], target_lang, model)
            for chunk in transcription
            for segment in chunk["transcript"]
        ]
    )
    counter = 0

    for i, chunk in enumerate(transcription):
        for j, segment in enumerate(chunk["transcript"]):
            original = segment.get("text", "")
            if not original:
                continue

            transcription[i]["transcript"][j]["text"] = translations[counter]
            counter += 1

    return transcription

    """ if not os.path.exists(save_dir):
        os.mkdir(save_dir)
        
    with open(f"{save_dir}/{target_lang}.json", "w", encoding="utf-8") as f:
        json.dump(transcription, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Translated transcription saved to: {save_dir}/{target_lang}.json") """


# Usage
# url = "https://www.youtube.com/watch?v=4oyYdrA9y5s&t"


def run_transcription_pipeline(platform_name: str, video_id: str, lang: str = 'ja'):
    
    create_video_dir(f'{platform_name}/{video_id}')
    
    match platform_name:
        case 'youtube':
            audio_buffer = download_youtube_audio_to_buffer(video_id)
        case _:
            raise ValueError("Invalid URL: hostname could not be determined")
        
    chunks = split_audio_from_buffer(audio_buffer)
        
    results = transcribe_audio_chunks_memory(chunks, language=lang)
    save_chunks_to_file(results, f"{platform_name}/{video_id}/{lang}.json")


async def run_translation_pipeline(platform_name: str, video_id: str, lang: str ="en"):
    match platform_name:
        case 'youtube':
            if os.path.exists(f"{platform_name}/{video_id}/en.json"):
                translation_result = await translate_transcription(f"{platform_name}/{video_id}/en.json", lang)
            else:
                translation_result = await translate_transcription(f"{platform_name}/{video_id}/jp.json", lang)
        case _:
            raise ValueError("Invalid URL: hostname could not be determined")
        
    save_chunks_to_file(translation_result, f"{platform_name}/{video_id}/{lang}.json")


# run_transcription_pipeline(url, 'ja')
# asyncio.run(run_translation_pipeline(extract_youtube_video_id(url), 'id'))