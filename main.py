import asyncio
import os
import subprocess
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
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, timeout=5)
        if result.returncode == 0:
            print(f"Node.js found: {result.stdout.decode().strip()}")
            return
    except Exception:
        pass
    home = os.path.expanduser("~")
    nvm_dir = os.path.join(home, ".nvm")
    subprocess.run("curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash", shell=True, timeout=60)
    subprocess.run(f'source {nvm_dir}/nvm.sh && nvm install 20', shell=True, executable="/bin/bash", timeout=120)

setup_node()

class DownloadRequest(BaseModel):
    url: str
    format: str = "mp3"

def _download(url: str, tmp_dir: str) -> Path:
    output_template = os.path.join(tmp_dir, "audio.%(ext)s")
    ydl_opts = {
        "format": "bestaudio",
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_check_formats": True,
        "proxy": "http://d6614fc611ae6402e4e5:9d1d6659113db558@gw.dataimpulse.com:823",
        "extractor_args": {"youtube": {"player_client": ["android_vr"]}},
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
    raise RuntimeError("No output file found")

@app.post("/download")
async def download(req: DownloadRequest):
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="No URL provided")
    tmp_dir = tempfile.mkdtemp()
    loop = asyncio.get_event_loop()
    try:
        out_file = await loop.run_in_executor(executor, _download, url, tmp_dir)
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail=str(e).splitlines()[-1])
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    ext = out_file.suffix.lstrip(".")
    media_types = {"mp3": "audio/mpeg", "m4a": "audio/mp4", "wav": "audio/wav", "webm": "audio/webm", "opus": "audio/ogg"}
    return FileResponse(path=str(out_file), media_type=media_types.get(ext, "application/octet-stream"), filename=out_file.name)

@app.get("/health")
async def health():
    return {"status": "ok"}
