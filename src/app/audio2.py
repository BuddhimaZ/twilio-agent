import json
import base64
from time import sleep

from websockets.sync.client import connect
from dotenv import load_dotenv
from os import getenv

load_dotenv()

with open("C:\\dev\\twilio-agent\\sample.wav", "rb") as f:
    audio_bytes = f.read()

audio64 = base64.b64encode(audio_bytes).decode("utf-8")

def update_transcription_session(websocket):
    update_message = {
        "type": "transcription_session.update",
        "session": {
            "input_audio_format": "pcm16",
            "input_audio_transcription": {
                "model": "whisper-1",
                "prompt": "",
                "language": "en"
            },
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.5,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 500,
            },
            "input_audio_noise_reduction": {
                "type": "near_field"
            },
            "include": []
        }
    }

    websocket.send(json.dumps(update_message))

def send_whole_audio_file(websocket, base_64_encoded_audio):
    message = {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_audio",
                    "audio": base_64_encoded_audio,
                }
            ],
        },
    }

    websocket.send(json.dumps(message))

def main():
    openai_api_key = getenv("OPENAI_API_KEY")
    url = "wss://api.openai.com/v1/realtime?intent=transcription"
    headers = {
        "Authorization": f"Bearer {openai_api_key}",
        "OpenAI-Beta": "realtime=v1"
    }

    with connect(url, additional_headers=headers) as websocket:
        print("Connected to OpenAI's Realtime API")

        while True:
            response_json_string = websocket.recv()

            # The response came as a JSON string. We need to parse it into a dictionary.
            response = json.loads(response_json_string)

            match response["type"]:
                case "transcription_session.created":
                    print(f"Transcription session created: {response}")
                    update_transcription_session(websocket)
                case "transcription_session.updated":
                    print(f"Transcription session updated: {response}")
                    send_whole_audio_file(websocket, audio64)
                case "conversation.item.input_audio_transcription.completed":
                    print(f"Transcription completed: {response}")
                    # print(response["transcript"])

                case _:
                    print(f"Received a message of an unexpected type: {response}")
                    # print(response)



if __name__ == "__main__":
    main()