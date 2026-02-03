from novalm.core.tools.base import Tool
from novalm.core.tools.python_exec import PythonExecTool
from novalm.core.tools.file_system import FileTool
from novalm.core.tools.shell import ShellTool
from novalm.core.tools.pdf_reader import PDFReaderTool

ALL_TOOLS = [
    PythonExecTool(),
    FileTool(),
    ShellTool(),
    PDFReaderTool()
]

def get_tools_formatted():
    """Returns a list of tools in OpenAI format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters
            }
        }
        for t in ALL_TOOLS
    ]

def get_tool_by_name(name: str) -> Tool:
    for t in ALL_TOOLS:
        if t.name == name:
            return t
    return None
