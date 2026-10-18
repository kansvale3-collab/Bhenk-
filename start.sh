#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

PYTHON=/data/data/com.termux/files/usr/bin/python3
PIP=/data/data/com.termux/files/usr/bin/pip
if [ ! -x "$PYTHON" ]; then PYTHON=python3; fi
if [ ! -x "$PIP" ]; then PIP=pip3; fi

if ! "$PYTHON" -c 'import yt_dlp' >/dev/null 2>&1; then
  echo 'Memasang komponen downloader…'
  "$PIP" install -r requirements.txt
fi

if "$PYTHON" - <<'PY'
import socket,sys
s=socket.socket()
try:
 s.connect(('127.0.0.1',8000));sys.exit(0)
except OSError:sys.exit(1)
finally:s.close()
PY
then
  echo 'Port 8000 sedang dipakai. Hentikan server lama lalu jalankan ./start.sh lagi.'
  exit 1
fi

CLOUDFLARED=/root/.local/bin/cloudflared
if [ ! -x "$CLOUDFLARED" ]; then
  mkdir -p /root/.local/bin
  echo 'Menyiapkan Cloudflare Tunnel…'
  "$PYTHON" - <<'PY'
import platform,urllib.request,os
arch=platform.machine().lower()
asset={'aarch64':'arm64','arm64':'arm64','x86_64':'amd64','amd64':'amd64'}.get(arch)
if not asset: raise SystemExit('Arsitektur belum didukung: '+arch)
url='https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-'+asset
path='/root/.local/bin/cloudflared'
with urllib.request.urlopen(url,timeout=120) as src,open(path,'wb') as dst:
 while True:
  chunk=src.read(1024*1024)
  if not chunk: break
  dst.write(chunk)
os.chmod(path,0o755)
PY
fi

"$PYTHON" server.py &
SERVER_PID=$!
cleanup(){ kill "$SERVER_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
sleep 1
if ! kill -0 "$SERVER_PID" 2>/dev/null; then
  echo 'Server gagal dijalankan.'
  exit 1
fi
echo 'Web lokal: http://localhost:8000'
if [ -n "${CLOUDFLARE_TUNNEL_TOKEN:-}" ]; then
  echo 'Menjalankan Cloudflare Named Tunnel…'
  echo 'Pastikan hostname domain sudah diarahkan ke tunnel di Cloudflare Zero Trust.'
  "$CLOUDFLARED" tunnel --no-autoupdate run --token "$CLOUDFLARE_TUNNEL_TOKEN"
else
  echo 'Menyiapkan Quick Tunnel Cloudflare (URL sementara)…'
  echo 'Untuk memakai domain sendiri, set CLOUDFLARE_TUNNEL_TOKEN dari dashboard Cloudflare.'
  "$CLOUDFLARED" tunnel --url http://localhost:8000
fi
