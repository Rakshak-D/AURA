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