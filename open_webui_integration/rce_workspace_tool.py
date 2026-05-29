"""
title: Code Interpreter
author: Chottokun
author_url: 
description: Execute Python code in a secure Docker sandbox. Analyzes data, generates plots (PNG), and produces downloadable files (CSV, etc.). Images are displayed inline; CSV files open as plain text in a new browser tab (save with Ctrl+S).
version: 1.1.0
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import httpx
import base64
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
        Execute Python code in a secure Docker-sandboxed environment.
        Use this for data analysis, generating plots/charts, running calculations, and producing output files.

        ## File Input (Automatic)
        - All files the user uploaded/attached in the chat (CSV, Excel, images, etc.) are AUTOMATICALLY
          placed in the sandbox's current directory ('.') BEFORE your code runs.
        - Do NOT ask the user to re-upload. Simply read them by filename: `pd.read_csv('data.csv')`.
        - To list available files: `import os; print(os.listdir('.'))`

        ## File Output (Automatic)
        - Any file your code saves to disk (`.png`, `.csv`, `.xlsx`, etc.) is AUTOMATICALLY detected
          and returned in the tool output as ready-to-use Markdown links.
        - You MUST copy these exact Markdown links into your final response WITHOUT modifying the URLs.

        ## Image Display Rules
        - Images (PNG/JPG/GIF/WebP) are rendered inline via `![filename](http://...)` Markdown.
        - ALWAYS use `plt.savefig('output.png')`. NEVER use `plt.show()` or `IPython.display`.
        - For Japanese text in matplotlib: ALWAYS add `import japanize_matplotlib` at the top.

        ## CSV / Non-Image File Download Rules
        - CSV files are served as inline plain text (`text/plain`) to bypass browser security restrictions
          on HTTP file downloads. When the user opens the link, the CSV content is displayed as text
          in the browser tab.
        - IMPORTANT: When presenting CSV download links to the user, ALWAYS instruct them:
          「リンクを右クリックして『新しいタブで開く』を選択してください。
          ブラウザにCSVの内容がテキストとして表示されますので、Ctrl+S で保存してください。」
          (Right-click the link and select 'Open in new tab'. The CSV content will appear as text.
          Press Ctrl+S to save it.)
        - Do NOT tell users to left-click download links directly, as Open WebUI's SvelteKit router
          will intercept the click and cause an error page.

        ## Session & Persistence
        - Each chat_id maps to a dedicated Docker container (sandbox). Files persist within the
          same chat session but are lost when the API container restarts.
        - The sandbox has a 300-second execution timeout.

        :param code: The Python code to execute.
        :param __metadata__: Metadata containing chat_id for session management.
        :param __files__: List of files uploaded in the chat.
        :param __chat_id__: Direct chat ID injected by Open WebUI.
        :return: Execution results (stdout/stderr) and Markdown links for generated files.
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
                else:
                    filename = str(file_info)
                
                if not filename:
                    continue

                encoded_filename = urllib.parse.quote(filename)
                base_download_url = f"{base_url}/download/{session_id}/{encoded_filename}".replace("host.docker.internal", "127.0.0.1")
                api_key = self.valves.RCE_API_KEY or "your_secret_key"

                if filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                    browser_url = f"{base_download_url}?api_key={api_key}" if api_key else base_download_url
                    output.append(f"![{filename}]({browser_url})")
                else:
                    browser_url = f"{base_download_url}?api_key={api_key}" if api_key else base_download_url
                    output.append(
                        f'📥 Download: <a href="{browser_url}" target="_blank" rel="external noopener noreferrer" data-sveltekit-reload download="{filename}">[`{filename}`]</a>\n\n'
                        f'*(⚠️ If clicking the link triggers an Open WebUI error, please copy & paste this direct URL into a new browser tab to download instantly:)*\n'
                        f'`{browser_url}`'
                    )

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

