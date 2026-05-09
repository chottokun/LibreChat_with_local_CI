"""
title: Code Interpreter
author: Chottokun
author_url: 
description: Execute Python code securely, analyze data, and generate high-quality visual charts or plots.
version: 1.0.0
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import httpx
import base64
import json
import logging
import urllib.parse

logger = logging.getLogger(__name__)

class Tools:
    class Valves(BaseModel):
        RCE_API_BASE_URL: str = Field(
            default="http://host.docker.internal:8000",
            description="The base URL of your LibreChat RCE API."
        )
        RCE_API_KEY: str = Field(
            default="your_secret_key",
            description="The API Key (LIBRECHAT_CODE_API_KEY) for authentication."
        )

    def __init__(self):
        self.valves = self.Valves()

    async def execute_code(
        self,
        code: str,
        __metadata__: Dict[str, Any],
        __files__: Optional[List[Dict[str, Any]]] = None,
        __chat_id__: Optional[str] = None,
    ) -> str:
        """
        Execute Python code in a secure sandboxed environment.
        You can use this to perform data analysis, generate plots, or run complex calculations.
        
        CRITICAL: All files uploaded/attached by the user in the chat (e.g., CSV, Excel, images) are AUTOMATICALLY uploaded to your sandbox's current directory ('.') before your code runs. 
        You do NOT need to ask the user to upload them or upload them yourself. 
        Simply read them directly using their filenames (e.g., `pd.read_csv('store_sales.csv')`).
        
        CRITICAL: To display the generated images (plots) and download files to the user, you MUST copy and include the exact Markdown image and download links (e.g., `![filename.png](http://localhost:8000/download/...)`) provided in the tool's output inside your final response. Do not modify the URLs.
        
        To check what files are available in the workspace, run: `import os; print(os.listdir('.'))`
        IMPORTANT: When generating plots with matplotlib, ALWAYS use `plt.savefig('output.png')`. Do NOT use `plt.show()`, `IPython.display`, or `PIL.Image.show()`. Doing so will cause errors. To render Japanese characters correctly in matplotlib plots, ALWAYS write `import japanize_matplotlib` at the top of your code.
        Any file saved to disk (such as `.png`, `.jpg`, `.csv`) is AUTOMATICALLY detected, uploaded, and returned as download/display links in the tool output.
        :param code: The Python code to execute.
        :param __metadata__: Metadata containing chat_id for session management.
        :param __files__: List of files uploaded in the chat.
        :param __chat_id__: Direct chat ID injected by Open WebUI.
        :return: Execution results (stdout/stderr) and Markdown for generated files.
        """
        session_id = __chat_id__ or __metadata__.get("chat_id", "default_session")
        base_url = self.valves.RCE_API_BASE_URL.rstrip("/")
        headers = {"X-Api-Key": self.valves.RCE_API_KEY} if self.valves.RCE_API_KEY else {}

        async with httpx.AsyncClient(timeout=300.0) as client:
            # 1. Handle File Uploads
            files_to_upload = __files__ or __metadata__.get("files") or []
            upload_logs = []
            if not files_to_upload:
                upload_logs.append(f"No files detected. __files__ is {__files__}. __metadata__ keys: {list(__metadata__.keys()) if __metadata__ else None}.")
            else:
                for file_data in files_to_upload:
                    filename = file_data.get("filename") or file_data.get("name", "uploaded_file")
                    # Open WebUI might provide content as bytes or base64 string
                    content = file_data.get("content")
                    
                    # If content is not directly provided, read it from the local path on disk inside Open WebUI container
                    if not content:
                        file_path = (
                            file_data.get("path") or 
                            file_data.get("file", {}).get("path") or 
                            file_data.get("meta", {}).get("path")
                        )
                        if file_path:
                            try:
                                with open(file_path, "rb") as f:
                                    content = f.read()
                                upload_logs.append(f"Successfully read {filename} from local path {file_path}")
                            except Exception as e:
                                err_msg = f"Failed to read file {filename} from path {file_path}: {e}"
                                logger.error(err_msg)
                                upload_logs.append(err_msg)
                        else:
                            err_msg = f"File {filename} has no path or content available in metadata: {file_data}"
                            logger.error(err_msg)
                            upload_logs.append(err_msg)

                    if content:
                        try:
                            if isinstance(content, str):
                                # Assume Base64 if it's a string, fallback to utf-8 encoding if it's plain text
                                try:
                                    content_bytes = base64.b64decode(content)
                                except Exception:
                                    content_bytes = content.encode('utf-8')
                            else:
                                content_bytes = content
                                
                            files = {"file": (filename, content_bytes)}
                            upload_url = f"{base_url}/upload"
                            upload_res = await client.post(
                                upload_url,
                                params={"session_id": session_id},
                                files=files,
                                headers=headers
                            )
                            upload_res.raise_for_status()
                            upload_logs.append(f"Successfully uploaded {filename} to RCE workspace.")
                        except Exception as e:
                            err_msg = f"Failed to upload file {filename} to RCE workspace: {e}"
                            logger.error(err_msg)
                            upload_logs.append(err_msg)

            # 2. Execute Code
            # Clean up the code if LLM wrapped it inside markdown code fences
            cleaned_code = code.strip()
            if cleaned_code.startswith("```"):
                lines = cleaned_code.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                cleaned_code = "\n".join(lines)

            exec_url = f"{base_url}/exec"
            payload = {
                "session_id": session_id,
                "code": cleaned_code
            }
            
            try:
                response = await client.post(exec_url, json=payload, headers=headers)
                response.raise_for_status()
                result_data = response.json()
            except Exception as e:
                return f"Error connecting to Code Interpreter API: {str(e)}\nPlease check your RCE_API_BASE_URL and RCE_API_KEY settings in the tool's Valves."

            stdout = result_data.get("stdout", "")
            stderr = result_data.get("stderr", "")
            files_generated = result_data.get("files", [])

            output = []
            if upload_logs:
                output.append("### File Upload Logs:\n" + "\n".join(f"- {log}" for log in upload_logs))
                
            if stdout:
                output.append(stdout)
            if stderr:
                output.append(f"Error Output:\n```\n{stderr}\n```")

            # 3. Handle Generated Files (Images)
            for file_info in files_generated:
                if isinstance(file_info, dict):
                    filename = file_info.get("name", "")
                    file_id = file_info.get("id", filename)
                else:
                    filename = str(file_info)
                    file_id = filename
                
                if not filename:
                    continue

                encoded_filename = urllib.parse.quote(filename)
                download_url = f"{base_url}/download/{session_id}/{encoded_filename}"
                if self.valves.RCE_API_KEY:
                    download_url += f"?api_key={self.valves.RCE_API_KEY}"
                browser_url = download_url.replace("host.docker.internal", "localhost")

                if filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                    output.append(f"![{filename}]({browser_url})")
                else:
                    output.append(f"File generated: <a href=\"{browser_url}\" target=\"_blank\" rel=\"external noopener noreferrer\" download=\"{filename}\">[`{filename}`]</a>")

            return "\n\n".join(output) if output else "Execution completed successfully with no output."

    async def get_available_packages(
        self,
        __metadata__: Dict[str, Any],
        __chat_id__: Optional[str] = None,
    ) -> str:
        """
        Get a list of all pre-installed Python packages available in the Code Interpreter sandbox environment.
        Use this tool when you need to check if a specific library (e.g., pandas, scipy, seaborn, etc.) is pre-installed.
        :param __metadata__: Metadata containing session information.
        :param __chat_id__: Direct chat ID injected by Open WebUI.
        :return: List of pre-installed Python packages.
        """
        return (
            "The following core data science and visualization packages are pre-installed and ready to use in the Code Interpreter:\n\n"
            "- pandas\n"
            "- numpy\n"
            "- scipy\n"
            "- matplotlib\n"
            "- japanize-matplotlib (ALWAYS import this when generating plots with Japanese text)\n"
            "- seaborn\n\n"
            "Note: All built-in Python 3.11 standard libraries (e.g., math, datetime, os, json, sqlite3) are also available.\n"
            "You do NOT need to install these packages using pip. Simply import them directly in your code."
        )

