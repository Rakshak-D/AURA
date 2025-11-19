import pytesseract
from PIL import Image

def ocr_image(image_path: str) -> str:
    return pytesseract.image_to_string(Image.open(image_path))