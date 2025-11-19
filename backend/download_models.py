from huggingface_hub import snapshot_download, hf_hub_download
import os
import shutil

# Ensure models directory exists
os.makedirs('./models', exist_ok=True)

print("--- Starting Model Downloads ---")

# 1. Qwen2 1.5B GGUF
# We use hf_hub_download to get just the specific quantized file (Q4_K_M)
# instead of the whole repo (which is huge).
print("Downloading Qwen2-1.5B (Q4_K_M)...")
gguf_file = hf_hub_download(
    repo_id="Qwen/Qwen2-1.5B-Instruct-GGUF",
    filename="qwen2-1_5b-instruct-q4_k_m.gguf",
    local_dir="./models",
    local_dir_use_symlinks=False
)

# Rename to match your .env config (MODEL_PATH=./models/qwen2-1.5b.gguf)
target_path = "./models/qwen2-1.5b.gguf"
if os.path.exists(gguf_file) and gguf_file != target_path:
    # Move/Rename the downloaded file to what .env expects
    # Note: hf_hub_download might download to a subdirectory or filename depending on version
    # We ensure it ends up at ./models/qwen2-1.5b.gguf
    shutil.move(gguf_file, target_path)
    print(f"Model moved to {target_path}")

# 2. Embeddings (Sentence Transformers)
print("Downloading Embeddings...")
snapshot_download(
    repo_id="sentence-transformers/all-MiniLM-L6-v2", 
    local_dir="./models/sentence-transformer",
    local_dir_use_symlinks=False
)

# 3. Whisper Tiny (OpenAI)
print("Downloading Whisper Tiny...")
snapshot_download(
    repo_id="openai/whisper-tiny", 
    local_dir="./models/whisper-tiny",
    local_dir_use_symlinks=False
)

# 4. Silero TTS - REMOVED
# The repository "snakers4/silero-models" is a GitHub repo, not a Hugging Face model ID.
# Since your application uses Coqui TTS (in tts_stt_service.py), this download is not needed.
# Coqui will handle its own model downloads automatically when you run the app.
print("Skipping Silero (managed by Coqui TTS internally).")

print("--- Downloads Complete ---")