import asyncio
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

MEDIA_TYPES = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
}


def _download(url: str, fmt: str, tmp_dir: str) -> Path:
    # Use a fixed stem so we can reliably find the output after postprocessing
    output_template = os.path.join(tmp_dir, "audio.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "noplaylist": True,
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

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    # After postprocessing the extension will be fmt; find that file
    expected = Path(tmp_dir) / f"audio.{fmt}"
    if expected.exists():
        # Rename to the video title for a nicer download filename
        title = info.get("title", "audio").replace("/", "-").replace("\x00", "")
        final = Path(tmp_dir) / f"{title}.{fmt}"
        expected.rename(final)
        return final

    # Fallback: pick any file with the right extension
    matches = list(Path(tmp_dir).glob(f"*.{fmt}"))
    if matches:
        return matches[0]

    # Last resort: any file that isn't a temp partial
    files = [f for f in Path(tmp_dir).iterdir() if f.suffix != ".part"]
    if not files:
        raise RuntimeError("No output file produced by yt-dlp")
    return files[0]


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
