def extract_text_from_image(image_path: str) -> str:
    try:
        import pytesseract
        from PIL import Image
        
        image = Image.open(image_path)
        text = pytesseract.image_to_string(image)
        return text
    except ImportError:
        return "OCR requires pytesseract and PIL. Install with: pip install pytesseract pillow"
    except Exception as e:
        print(f"OCR error: {e}")
        return f"Error extracting text from image: {str(e)}"