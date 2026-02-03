import os
import asyncio
from typing import Dict, Any
from novalm.core.tools.base import Tool

try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

WORKSPACE_DIR = os.path.abspath("workspace")

class PDFReaderTool(Tool):
    name = "pdf_reader"
    description = "Extracts text from a PDF file. The file must be in the workspace."
    parameters = {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Name of the PDF file to read (e.g., 'paper.pdf')"
            },
            "page_start": {
                "type": "integer",
                "description": "Optional start page (0-indexed)"
            },
            "page_end": {
                "type": "integer",
                "description": "Optional end page"
            }
        },
        "required": ["filename"]
    }

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        if not PYPDF_AVAILABLE:
            return {"status": "error", "output": "pypdf library not installed. Cannot read PDFs."}

        filename = input_data.get("filename")
        page_start = input_data.get("page_start", 0)
        page_end = input_data.get("page_end", None)

        safe_path = os.path.abspath(os.path.join(WORKSPACE_DIR, filename))
        if not safe_path.startswith(WORKSPACE_DIR):
             return {"status": "error", "output": "Access denied: Path outside workspace."}
             
        if not os.path.exists(safe_path):
            return {"status": "error", "output": f"File {filename} not found in workspace."}
            
        try:
            # CPU-bound blocking call, run in executor
            loop = asyncio.get_event_loop()
            text = await loop.run_in_executor(None, self._extract_text, safe_path, page_start, page_end)
            return {"status": "success", "content": text}
        except Exception as e:
            return {"status": "error", "output": f"Failed to read PDF: {str(e)}"}

    def _extract_text(self, path, start, end):
        reader = PdfReader(path)
        text = ""
        total_pages = len(reader.pages)
        
        # Validate range
        if start < 0: start = 0
        if end is None or end > total_pages: end = total_pages
        
        for i in range(start, end):
            page = reader.pages[i]
            extracted = page.extract_text()
            if extracted:
                text += f"\n--- Page {i+1} ---\n{extracted}"
        
        return text
