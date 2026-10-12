"""Public PDF text with explicit scanned-document recovery and extraction receipts."""
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
from pypdf import PdfReader


def extract_primary_pdf(content):
    reader=PdfReader(io.BytesIO(content))
    text='\n'.join(p.extract_text() or '' for p in reader.pages)
    if len(text.strip())>=80:return text,'pdf_text'
    if not shutil.which('pdftoppm') or not shutil.which('tesseract'):return text,'scanned_ocr_unavailable'
    with tempfile.TemporaryDirectory(prefix='radar-primary-') as tmp:
        root=Path(tmp);(root/'document.pdf').write_bytes(content)
        subprocess.run(['pdftoppm','-r','160','-f','1','-l','5','-png',str(root/'document.pdf'),str(root/'page')],check=True,capture_output=True,timeout=60)
        pieces=[]
        for page in sorted(root.glob('page-*.png')):
            result=subprocess.run(['tesseract',str(page),'stdout','-l','eng'],check=True,capture_output=True,text=True,timeout=45)
            pieces.append(result.stdout)
        return '\n'.join(pieces),'ocr_eng_public_document'
