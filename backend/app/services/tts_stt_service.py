import whisper
from TTS.api import TTS
from models.llm_models import llm  # Wait, TTS is separate
from config import config

whisper_model = whisper.load_model("./models/whisper-tiny")
tts_model = TTS(model_name="tts_models/en/ljspeech/tacotron2-DDC", progress_bar=False).to("cpu")

def stt(audio_file: str) -> str:
    result = whisper_model.transcribe(audio_file)
    return result["text"]

def tts(text: str, output_file: str):
    tts_model.tts_to_file(text=text, file_path=output_file)