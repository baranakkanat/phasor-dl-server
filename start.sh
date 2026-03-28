#!/bin/bash
warp-cli --accept-tos registration new 2>/dev/null || true
warp-cli mode proxy
warp-cli proxy port 40000
warp-cli connect
sleep 8
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}
