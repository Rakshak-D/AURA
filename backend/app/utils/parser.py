from typing import BinaryIO

def parse_document(file: BinaryIO, content_type: str) -> str:
    try:
        if content_type == 'text/plain':
            return file.read().decode('utf-8')
        
        elif content_type == 'application/pdf':
            try:
                import PyPDF2
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text()
                return text
            except ImportError:
                return "PDF parsing requires PyPDF2. Install with: pip install PyPDF2"
        
        elif content_type in ['application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/msword']:
            try:
                import docx
                doc = docx.Document(file)
                text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
                return text
            except ImportError:
                return "DOCX parsing requires python-docx. Install with: pip install python-docx"
        
        elif content_type == 'text/markdown':
            return file.read().decode('utf-8')
        
        else:
            try:
                return file.read().decode('utf-8')
            except:
                return "Unsupported file format"
    
    except Exception as e:
        print(f"Document parsing error: {e}")
        return f"Error parsing document: {str(e)}"

