import os
from pathlib import Path
from huggingface_hub import hf_hub_download

def download_models():
    BASE_DIR = Path(__file__).resolve().parent.parent
    MODELS_DIR = BASE_DIR / "models"
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    
    MODEL_FILENAME = "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
    MODEL_PATH = MODELS_DIR / MODEL_FILENAME
    
    if MODEL_PATH.exists():
        print(f"✅ Model already exists: {MODEL_PATH}")
        return
    
    print("📥 Downloading AI model from Hugging Face...")
    print("   This may take a few minutes...")
    
    try:
        downloaded_path = hf_hub_download(
            repo_id="TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF",
            filename=MODEL_FILENAME,
            local_dir=MODELS_DIR,
            local_dir_use_symlinks=False
        )
        print(f"✅ Model downloaded successfully: {downloaded_path}")
        
    except Exception as e:
        print(f"❌ Error downloading model: {e}")
        print("\n📝 Manual Download Instructions:")
        print("1. Visit: https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF")
        print(f"2. Download: {MODEL_FILENAME}")
        print(f"3. Place in: {MODELS_DIR}")

if __name__ == "__main__":
    download_models()