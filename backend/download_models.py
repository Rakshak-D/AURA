from huggingface_hub import snapshot_download
import os

os.makedirs('./models', exist_ok=True)

# Qwen2 1.5B GGUF (quantized for speed)
snapshot_download(repo_id="Qwen/Qwen2-1.5B-Instruct-GGUF", local_dir="./models/qwen2-1.5b", local_dir_use_symlinks=False)

# Embeddings
snapshot_download(repo_id="sentence-transformers/all-MiniLM-L6-v2", local_dir="./models/sentence-transformer")

  # Whisper Tiny
snapshot_download(repo_id="openai/whisper-tiny", local_dir="./models/whisper-tiny")

  # Silero TTS
snapshot_download(repo_id="snakers4/silero-models", local_dir="./models/silero-en", allow_patterns=["*.pt"])
  