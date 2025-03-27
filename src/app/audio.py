import asyncio
import base64
import websockets
import json
import os

from dotenv import load_dotenv
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if OPENAI_API_KEY is None:
    raise ValueError("OPENAI_API_KEY is not set")

with open("C:\\dev\\twilio-agent\\sample.wav", "rb") as f:
    audio_bytes = f.read()

chunk_duration = 0.5  # 500 ms per chunk
sample_rate = 16000   # Hz
bytes_per_sample = 2  # PCM16 (16 bits)
chunk_size = int(sample_rate * chunk_duration * bytes_per_sample)  # e.g., 16,000 bytes
overlap_size = int(sample_rate * 0.2 * bytes_per_sample)  # 200 ms overlap (e.g., 6,400 bytes)

chunks = []
start = 0

while start + chunk_size <= len(audio_bytes):
    chunk = audio_bytes[start : start + chunk_size]
    chunk_b64 = base64.b64encode(chunk).decode('utf-8')
    chunks.append(chunk_b64)
    # Move the window; include overlap from the previous chunk
    start += chunk_size - overlap_size


async def send_audio_chunks(ws, _chunks):
    for _chunk in _chunks:
        message = {
            "type": "input_audio_buffer.append",
            "audio": _chunk  # each chunk is a base64-encoded string
        }
        await ws.send(json.dumps(message))
        # Optionally, add a small delay to avoid overwhelming the server
        await asyncio.sleep(0.05)  # 50ms delay

async def realtime_transcription():
    uri = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Beta": "realtime=v1"
    }



    async with websockets.connect(uri, additional_headers=headers) as ws:
        session_update = {
            "type": "session.update",
            "session": {
                "turn_detection": {"type": "server_vad"},
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {"model": "whisper-1"},
                "voice": "alloy",
                "modalities": ["text", "audio"],
                "temperature": 0.8
            }
        }

        await ws.send(json.dumps(session_update))

        # Now, send your audio chunks using input_audio_buffer.append events.
        # For example:
        # audio_chunk = "base64-encoded audio data"
        # await ws.send(json.dumps({
        #     "type": "input_audio_buffer.append",
        #     "audio": audio_chunk
        # }))

        await send_audio_chunks(ws, chunks)

        while True:
            response = await ws.recv()
            event = json.loads(response)
            if event.get("type") == "conversation.item.input_audio_transcription.completed":
                print("Transcription:", event.get("transcript", ""))
            # You can ignore audio-related events if you don't need audio output.



asyncio.run(realtime_transcription())