import asyncio
import base64
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
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
MEDIA_TYPES = {"mp3": "audio/mpeg", "wav": "audio/wav"}

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
    cookie_file = next((p for p in ['/app/cookies.txt', os.path.join(_dir, 'cookies.txt')] if os.path.exists(p)), get_cookie_file())
    ydl_opts = {
        "format": "18/bestaudio/best",
        "outtmpl": output_template,
        "noplaylist": True,
        "extractor_args": {"youtube": {"player_client": ["android"]}},
        "http_headers": {"User-Agent": "com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip"},
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": fmt,
                **({"preferredquality": "320"} if fmt == "mp3" else {}),
            }
        ],
    }
    if cookie_file:
        ydl_opts["cookiefile"] = cookie_file

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    title = info.get("title", "audio").replace("/", "-").replace("\x00", "")
    expected = Path(tmp_dir) / f"audio.{fmt}"
    if expected.exists():
        final = Path(tmp_dir) / f"{title}.{fmt}"
        expected.rename(final)
        return final
    matches = list(Path(tmp_dir).glob(f"*.{fmt}"))
    if matches:
        return matches[0]
    raise RuntimeError("No output file produced by yt-dlp")

@app.post("/download")
async def download(req: DownloadRequest):
    if not req.url:
        raise HTTPException(status_code=400, detail="No URL provided")
    fmt = req.format.lower() if req.format.lower() in SUPPORTED_FORMATS else "mp3"
    tmp_dir = tempfile.mkdtemp()
    loop = asyncio.get_event_loop()
    try:
        out_file = await loop.run_in_executor(executor, _download, req.url, fmt, tmp_dir)
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail=str(e).splitlines()[-1])
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    content_type = MEDIA_TYPES.get(fmt, "application/octet-stream")
    return FileResponse(
        path=str(out_file),
        media_type=content_type,
        filename=out_file.name,
        headers={"Content-Disposition": f'attachment; filename="{out_file.name}"'},
    )

@app.get("/health")
async def health():
    return {"status": "ok"}
