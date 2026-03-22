import os
import tempfile
import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI()


class DownloadRequest(BaseModel):
    url: str
    format: str = "mp3"


SUPPORTED_FORMATS = {"mp3", "opus", "flac", "wav", "m4a", "ogg"}


@app.post("/download")
async def download(req: DownloadRequest):
    if not req.url:
        raise HTTPException(status_code=400, detail="No URL provided")

    fmt = req.format.lower() if req.format.lower() in SUPPORTED_FORMATS else "mp3"

    tmp_dir = tempfile.mkdtemp()
    output_template = os.path.join(tmp_dir, "%(title)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-x",
        "--audio-format", fmt,
        "--audio-quality", "0",
        "-o", output_template,
        "--no-progress",
        "--age-limit", "0",
        "--extractor-args", "youtube:player_client=ios,web_embedded",
        "--add-header", "User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "--", req.url,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        error = stderr.decode(errors="replace").strip().splitlines()
        last_line = error[-1] if error else "yt-dlp failed"
        raise HTTPException(status_code=400, detail=last_line)

    files = list(Path(tmp_dir).iterdir())
    if not files:
        raise HTTPException(status_code=500, detail="No file produced by yt-dlp")

    out_file = files[0]
    filename = out_file.name

    media_types = {
        "mp3": "audio/mpeg",
        "opus": "audio/ogg",
        "flac": "audio/flac",
        "wav": "audio/wav",
        "m4a": "audio/mp4",
        "ogg": "audio/ogg",
    }
    content_type = media_types.get(out_file.suffix.lstrip("."), "application/octet-stream")

    return FileResponse(
        path=str(out_file),
        media_type=content_type,
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
