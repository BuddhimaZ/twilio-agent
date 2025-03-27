from dotenv import load_dotenv

load_dotenv()

import base64
import os
import json
import asyncio
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
import websockets


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("Missing OpenAI API key. Please set it in the .env file.")

# Constants
SYSTEM_MESSAGE = "You are a helpful and bubbly AI assistant who loves to chat about anything the user is interested about and is prepared to offer them facts."
VOICE = "alloy"
PORT = 5000
LOG_EVENT_TYPES = [
    "response.content.done", "rate_limits.updated", "response.done",
    "input_audio_buffer.committed", "input_audio_buffer.speech_stopped",
    "input_audio_buffer.speech_started", "session.created"
]
app = FastAPI()

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_text("Hello, websocket!")
    await websocket.close()

@app.websocket("/media")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("Connection accepted")

    has_seen_media = False
    message_count = 0

    try:
        while True:
            message = await websocket.receive_text()
            if not message:
                logger.info("No message received...")
                continue

            data = json.loads(message)
            event = data.get("event")

            if event == "connected":
                logger.info("Connected Message received: %s", message)
            elif event == "start":
                logger.info("Start Message received: %s", message)
            elif event == "media":
                #if not has_seen_media:
                    logger.info("Media message: %s", message)
                    payload = data['media']['payload']
                    logger.info("Payload is: %s", payload)
                    chunk = base64.b64decode(payload)
                    logger.info("That's %d bytes", len(chunk))
                    logger.info("Additional media messages from WebSocket are being suppressed....")
                    has_seen_media = True
            elif event == "closed":
                logger.info("Closed Message received: %s", message)
                break

            message_count += 1
    except WebSocketDisconnect:
        logger.info("Client disconnected")
    finally:
        logger.info("Connection closed. Received a total of %d messages", message_count)

@app.api_route("/incoming-call", methods=["GET", "POST"])
async def incoming_call():
    twiml_response = """<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Connect>
            <Stream url="wss://{host}/media-stream" />
        </Connect>
    </Response>""".format(host="troll-sterling-badly.ngrok-free.app")
    return Response(content=twiml_response, media_type="text/xml")

@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    await websocket.accept()
    logging.info("Client connected")

    openai_ws_uri = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"
    openai_headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Beta": "realtime=v1"
    }

    async with websockets.connect(openai_ws_uri, extra_headers=openai_headers) as openai_ws:
        stream_sid = None

        async def send_session_update():
            session_update = {
                "type": "session.update",
                "session": {
                    "turn_detection": {"type": "server_vad"},
                    "input_audio_format": "g711_ulaw",
                    "output_audio_format": "g711_ulaw",
                    "voice": VOICE,
                    "instructions": SYSTEM_MESSAGE,
                    "modalities": ["text", "audio.py"],
                    "temperature": 0.8,
                }
            }
            await openai_ws.send(json.dumps(session_update))
            logging.info("Session update sent")

        await asyncio.sleep(0.25)
        await send_session_update()

        async def receive_from_openai():
            async for message in openai_ws:
                try:
                    response = json.loads(message)
                    if response.get("type") in LOG_EVENT_TYPES:
                        logging.info(f"Received event: {response['type']}")
                    if response.get("type") == "response.audio.py.delta" and response.get("delta"):
                        audio_delta = {
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {"payload": response["delta"]}
                        }
                        await websocket.send_json(audio_delta)
                except Exception as e:
                    logging.error(f"Error processing OpenAI message: {e}")

        async def receive_from_twilio():
            nonlocal stream_sid
            try:
                while True:
                    data = await websocket.receive_text()
                    message = json.loads(data)
                    event_type = message.get("event")
                    if event_type == "media":
                        audio_append = {
                            "type": "input_audio_buffer.append",
                            "audio.py": message["media"]["payload"]
                        }
                        await openai_ws.send(json.dumps(audio_append))
                    elif event_type == "start":
                        stream_sid = message["start"]["streamSid"]
                        logging.info(f"Incoming stream started: {stream_sid}")
                    else:
                        logging.info(f"Received event: {event_type}")
            except WebSocketDisconnect:
                logging.info("Client disconnected.")
                await openai_ws.close()

        await asyncio.gather(receive_from_openai(), receive_from_twilio())
