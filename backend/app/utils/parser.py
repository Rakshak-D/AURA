import pdfplumber
import csv
from utils.ocr import ocr_image

def parse_document(file_path: str, file_type: str) -> str:
    if file_type == 'pdf':
        with pdfplumber.open(file_path) as pdf:
            return '\n'.join(page.extract_text() for page in pdf.pages)
    elif file_type == 'image':
        return ocr_image(file_path)
    elif file_type == 'csv':
        with open(file_path, 'r') as f:
            reader = csv.reader(f)
            return '\n'.join(','.join(row) for row in reader)
    return ""

def parse_timetable(file_path: str) -> list[dict]:
    content = parse_document(file_path, 'pdf')  # Assume PDF
    # Simple regex parse: Assume lines like "Event: Time - Desc"
    events = []
    for line in content.split('\n'):
        if ' - ' in line:
            time_desc = line.split(' - ')
            events.append({"time": time_desc[0], "desc": time_desc[1]})
    return events