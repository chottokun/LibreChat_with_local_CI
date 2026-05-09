"""
title: LibreChat Custom RCE Tool
author: LibreChat Community
author_url: https://github.com/danny-avila/LibreChat
description: Securely execute Python code in a sandboxed environment with file support and inline images.
version: 0.1.0
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import httpx
import base64
import json
import logging

logger = logging.getLogger(__name__)

class Tools:
    class Valves(BaseModel):
        RCE_API_BASE_URL: str = Field(
            default="http://host.docker.internal:8000",
            description="The base URL of your LibreChat RCE API."
        )
        RCE_API_KEY: str = Field(
            default="",
            description="The API Key (LIBRECHAT_CODE_API_KEY) for authentication."
        )

    def __init__(self):
        self.valves = self.Valves()

    async def execute_code(
        self,
        code: str,
        __metadata__: Dict[str, Any],
        __files__: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        Execute Python code in a secure sandboxed environment.
        You can use this to perform data analysis, generate plots, or run complex calculations.
        If you generate images, they will be automatically displayed in the chat.
        :param code: The Python code to execute.
        :param __metadata__: Metadata containing chat_id for session management.
        :param __files__: List of files uploaded in the chat.
        :return: Execution results (stdout/stderr) and Markdown for generated files.
        """
        session_id = __metadata__.get("chat_id", "default_session")
        base_url = self.valves.RCE_API_BASE_URL.rstrip("/")
        headers = {"X-Api-Key": self.valves.RCE_API_KEY} if self.valves.RCE_API_KEY else {}

        async with httpx.AsyncClient(timeout=60.0) as client:
            # 1. Handle File Uploads
            if __files__:
                for file_data in __files__:
                    filename = file_data.get("filename") or file_data.get("name", "uploaded_file")
                    # Open WebUI might provide content as bytes or base64 string
                    content = file_data.get("content")
                    if content:
                        try:
                            if isinstance(content, str):
                                # Assume Base64 if it's a string
                                content_bytes = base64.b64decode(content)
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
                        except Exception as e:
                            logger.error(f"Failed to upload file {filename}: {e}")
                            # Continue anyway, maybe the code doesn't need this file

            # 2. Execute Code
            exec_url = f"{base_url}/exec"
            payload = {
                "session_id": session_id,
                "code": code
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
            if stdout:
                output.append(stdout)
            if stderr:
                output.append(f"Error Output:\n```\n{stderr}\n```")

            # 3. Handle Generated Files (Images)
            for filename in files_generated:
                if filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                    download_url = f"{base_url}/download/{session_id}/{filename}"
                    try:
                        dl_res = await client.get(download_url, headers=headers)
                        dl_res.raise_for_status()
                        img_b64 = base64.b64encode(dl_res.content).decode("utf-8")
                        
                        # Detect mime type
                        ext = filename.lower().split(".")[-1]
                        mime_type = f"image/{ext}"
                        if ext == "jpg": mime_type = "image/jpeg"
                        
                        output.append(f"![{filename}](data:{mime_type};base64,{img_b64})")
                    except Exception as e:
                        output.append(f"Failed to render generated image {filename}: {e}")
                else:
                    output.append(f"File generated: `{filename}`")

            return "\n\n".join(output) if output else "Execution completed successfully with no output."
