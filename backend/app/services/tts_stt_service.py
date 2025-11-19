import whisper
import os
from TTS.api import TTS
# Fixed relative imports below
from ..models.llm_models import llm  
from ..config import config

print("Loading Whisper...")
whisper_model = whisper.load_model("./models/whisper-tiny")

print("Loading Coqui TTS...")
# Using CPU by default. If you have a GPU, change .to("cpu") to .to("cuda")
tts_model = TTS(model_name="tts_models/en/ljspeech/tacotron2-DDC", progress_bar=False).to("cpu")

def stt(audio_file: str) -> str:
    # Check if file exists
    if not os.path.exists(audio_file):
        return ""
    result = whisper_model.transcribe(audio_file)
    return result["text"]

def tts(text: str, output_file: str):
    # Generates audio file from text
    tts_model.tts_to_file(text=text, file_path=output_file)