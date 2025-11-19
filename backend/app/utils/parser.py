import pdfplumber
import csv
from .ocr import ocr_image # Relative import

def parse_document(file_path: str, file_type: str) -> str:
    # (Note: file_path here might be a file-like object from UploadFile in some contexts, 
    # but pdfplumber.open handles paths. For UploadFile.file, we might need to read bytes.
    # For simplicity keeping original logic but beware of file types)
    try:
        if 'pdf' in file_type:
            with pdfplumber.open(file_path) as pdf:
                return '\n'.join(page.extract_text() for page in pdf.pages if page.extract_text())
        elif 'image' in file_type:
            return ocr_image(file_path)
        elif 'csv' in file_type:
            # Handle file-like object wrapper if needed
            content = file_path.read().decode('utf-8')
            return content
    except Exception as e:
        print(f"Error parsing: {e}")
        return ""
    return ""

def parse_timetable(file_path: str) -> list[dict]:
    # Stub implementation
    return []