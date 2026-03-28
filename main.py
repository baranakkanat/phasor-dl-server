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
        "quiet": False,
        "verbose": True,
        "no_warnings": True,
        "no_check_formats": True,
        "proxy": "http://d6614fc611ae6402e4e5:9d1d6659113db558@gw.dataimpulse.com:823",
    }

    if cookie_file:
        ydl_opts["cookiefile"] = cookie_file

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
    tmp_dir = tempfile.mkdtemp()
    loop = asyncio.get_event_loop()
    try:
        out_file = await loop.run_in_executor(executor, _download, req.url, req.format, tmp_dir)
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail=str(e).splitlines()[-1])
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    ext = out_file.suffix.lstrip(".")
    media_types = {
        "mp3": "audio/mpeg",
        "m4a": "audio/mp4",
        "wav": "audio/wav",
        "webm": "audio/webm",
        "opus": "audio/ogg"
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
    return {"status": "ok"}

@app.get("/listformats")
async def listformats(url: str = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"):
    import yt_dlp
    ydl_opts = {
        "quiet": False,
        "proxy": "http://d6614fc611ae6402e4e5:9d1d6659113db558@gw.dataimpulse.com:823",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    formats = [{"id": f["format_id"], "ext": f["ext"], "acodec": f.get("acodec","-"), "vcodec": f.get("vcodec","-")} for f in info.get("formats", [])]
    return {"formats": formats}

@app.get("/listformats")
async def listformats(url: str = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"):
    ydl_opts = {
        "quiet": True,
        "proxy": "http://d6614fc611ae6402e4e5:9d1d6659113db558@gw.dataimpulse.com:823",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    formats = [{"id": f["format_id"], "ext": f["ext"], "acodec": f.get("acodec","-"), "vcodec": f.get("vcodec","-")} for f in info.get("formats", [])]
    return {"formats": formats}
