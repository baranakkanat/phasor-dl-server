import asyncio
import base64
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI()
executor = ThreadPoolExecutor(max_workers=4)

def setup_node():
    """Install node.js at startup if not available"""
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, timeout=5)
        if result.returncode == 0:
            print(f"Node.js found: {result.stdout.decode().strip()}")
            return
    except Exception:
        pass
    
    print("Installing node.js...")
    try:
        home = os.path.expanduser("~")
        nvm_dir = os.path.join(home, ".nvm")
        
        # Install nvm
        subprocess.run(
            "curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash",
            shell=True, timeout=60
        )
        
        # Install node via nvm
        env = os.environ.copy()
        env["NVM_DIR"] = nvm_dir
        subprocess.run(
            f'source {nvm_dir}/nvm.sh && nvm install 20 && nvm use 20',
            shell=True, executable="/bin/bash", env=env, timeout=120
        )
        
        # Add node to PATH
        node_bin = None
        for root, dirs, files in os.walk(nvm_dir):
            if "node" in files and "bin" in root:
                node_bin = root
                break
        
        if node_bin:
            os.environ["PATH"] = node_bin + ":" + os.environ.get("PATH", "")
            print(f"Node.js installed at {node_bin}")
    except Exception as e:
        print(f"Failed to install node: {e}")

# Run setup at startup
setup_node()

class DownloadRequest(BaseModel):
    url: str
    format: str = "mp3"

def get_cookie_file():
    b64 = os.environ.get("YOUTUBE_COOKIES_B64")
    if not b64:
        return None
    try:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="wb")
        tmp.write(base64.b64decode(b64))
        tmp.close()
        return tmp.name
    except Exception:
        return None

def _download(url: str, fmt: str, tmp_dir: str) -> Path:
    output_template = os.path.join(tmp_dir, "audio.%(ext)s")
    _dir = os.path.dirname(os.path.abspath(__file__))
    cookie_file = next(
        (p for p in [os.path.join(_dir, "cookies.txt")] if os.path.exists(p)),
        get_cookie_file()
    )

    ydl_opts = {
        "format": "bestaudio",
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": False,
        "no_check_formats": True,
        "extractor_args": {"youtube": {"player_client": ["android_vr"]}},
        "proxy": "http://d6614fc611ae6402e4e5:9d1d6659113db558@gw.dataimpulse.com:823",
    }


    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    title = info.get("title", "audio").replace("/", "-").replace("\x00", "")

    for ext in ["m4a", "webm", "opus", "mp3", "wav"]:
        f = Path(tmp_dir) / f"audio.{ext}"
        if f.exists():
            final = Path(tmp_dir) / f"{title}.{ext}"
            f.rename(final)
            return final

    matches = list(Path(tmp_dir).glob("audio.*"))
    if matches:
        f = matches[0]
        final = Path(tmp_dir) / f"{title}{f.suffix}"
        f.rename(final)
        return final

    raise RuntimeError("No output file produced by yt-dlp")

@app.post("/download")
async def download(req: DownloadRequest):
    if not req.url:
        raise HTTPException(status_code=400, detail="No URL provided")
    url = req.url.strip()
    tmp_dir = tempfile.mkdtemp()
    loop = asyncio.get_event_loop()
    try:
        out_file = await loop.run_in_executor(executor, _download, url, req.format, tmp_dir)
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail=str(e).splitlines()[-1])
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    ext = out_file.suffix.lstrip(".")
    media_types = {
        "mp3": "audio/mpeg", "m4a": "audio/mp4",
        "wav": "audio/wav", "webm": "audio/webm", "opus": "audio/ogg"
    }
    content_type = media_types.get(ext, "application/octet-stream")

    return FileResponse(
        path=str(out_file),
        media_type=content_type,
        filename=out_file.name,
        headers={"Content-Disposition": f'attachment; filename="{out_file.name}"'},
    )

@app.get("/health")
async def health():
    node_check = subprocess.run(["node", "--version"], capture_output=True)
    return {
        "status": "ok",
        "node": node_check.stdout.decode().strip() if node_check.returncode == 0 else "not found"
    }

@app.get("/listformats")
async def listformats(url: str = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"):
    ydl_opts = {
        "quiet": True,
        "proxy": "http://d6614fc611ae6402e4e5:9d1d6659113db558@gw.dataimpulse.com:823",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    formats = [{"id": f["format_id"], "ext": f["ext"], "acodec": f.get("acodec", "-"), "vcodec": f.get("vcodec", "-")} for f in info.get("formats", [])]
    return {"formats": formats}
