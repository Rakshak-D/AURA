import os
import requests
from pathlib import Path

# Model configurations
MODELS = {
    "llm": {
        "name": "Phi-3-mini-4k-instruct (Q4)",
        "url": "https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf/resolve/main/Phi-3-mini-4k-instruct-q4.gguf",
        "filename": "phi-3-mini-4k-instruct-q4.gguf",
        "size": "3.8 GB"
    },
    "embedding": {
        "name": "all-MiniLM-L6-v2",
        "model_id": "sentence-transformers/all-MiniLM-L6-v2",
        "size": "80 MB"
    }
}

def download_file(url, filepath):
    """Download file with progress bar"""
    print(f"📥 Downloading from: {url}")
    print(f"📁 Saving to: {filepath}")
    
    response = requests.get(url, stream=True)
    total_size = int(response.headers.get('content-length', 0))
    
    if total_size == 0:
        print("⚠️  Warning: Could not determine file size")
    
    downloaded = 0
    block_size = 8192
    
    with open(filepath, 'wb') as f:
        for chunk in response.iter_content(chunk_size=block_size):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                
                if total_size > 0:
                    percent = (downloaded / total_size) * 100
                    mb_downloaded = downloaded / (1024 * 1024)
                    mb_total = total_size / (1024 * 1024)
                    print(f"\r  Progress: {percent:.1f}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)", end='')
    
    print(f"\n✅ Download complete: {filepath.name}")

def download_models():
    """Download all required models"""
    models_dir = Path("models")
    models_dir.mkdir(exist_ok=True)
    
    print("🚀 AURA Model Downloader")
    print("=" * 50)
    
    # Download LLM
    llm_config = MODELS["llm"]
    llm_path = models_dir / llm_config["filename"]
    
    if llm_path.exists():
        print(f"✅ LLM already exists: {llm_path}")
    else:
        print(f"\n📦 Downloading {llm_config['name']} ({llm_config['size']})")
        download_file(llm_config["url"], llm_path)
    
    # Embedding model info (downloaded automatically by sentence-transformers)
    emb_config = MODELS["embedding"]
    print(f"\n📦 Embedding Model: {emb_config['name']} ({emb_config['size']})")
    print(f"   Will be auto-downloaded on first run by sentence-transformers")
    
    print("\n" + "=" * 50)
    print("🎉 Model setup complete!")
    print(f"\n📊 Total size: ~{float(llm_config['size'].split()[0]) + 0.08:.1f} GB")
    print("\n💡 Phi-3 is MUCH smarter than TinyLlama!")
    print("   - Better reasoning")
    print("   - More accurate responses")
    print("   - Better instruction following")

if __name__ == "__main__":
    download_models()