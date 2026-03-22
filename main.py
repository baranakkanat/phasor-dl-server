import os
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI()
executor = ThreadPoolExecutor(max_workers=4)


class DownloadRequest(BaseModel):
    url: str
    format: str = "mp3"


SUPPORTED_FORMATS = {"mp3", "wav"}

MEDIA_TYPES = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
}


def _download(url: str, fmt: str, tmp_dir: str) -> Path:
    output_template = os.path.join(tmp_dir, "%(title)s.%(ext)s")

    postprocessors = [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": fmt,
            **({"preferredquality": "320"} if fmt == "mp3" else {}),
        }
    ]

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "noplaylist": True,
        "postprocessors": postprocessors,
        "quiet": True,
        "no_warnings": True,
        "age_limit": 0,
        "extractor_args": {"youtube": {"player_client": ["ios", "web_embedded"]}},
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        },
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    files = list(Path(tmp_dir).iterdir())
    if not files:
        raise RuntimeError("No file produced by yt-dlp")

    return files[0]


@app.post("/download")
async def download(req: DownloadRequest):
    if not req.url:
        raise HTTPException(status_code=400, detail="No URL provided")

    fmt = req.format.lower() if req.format.lower() in SUPPORTED_FORMATS else "mp3"
    tmp_dir = tempfile.mkdtemp()

    import asyncio
    loop = asyncio.get_event_loop()
    try:
        out_file = await loop.run_in_executor(executor, _download, req.url, fmt, tmp_dir)
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail=str(e).splitlines()[-1])
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    content_type = MEDIA_TYPES.get(out_file.suffix.lstrip("."), "application/octet-stream")

    return FileResponse(
        path=str(out_file),
        media_type=content_type,
        filename=out_file.name,
        headers={"Content-Disposition": f'attachment; filename="{out_file.name}"'},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
