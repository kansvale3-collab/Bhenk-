from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from pathlib import Path
import json, re, tempfile, os, glob
import yt_dlp
import signal
import sys

ROOT = Path(__file__).resolve().parent
ALLOWED = {
    'tiktok.com', 'instagram.com', 'youtube.com', 'youtu.be', 'x.com', 'twitter.com',
    'spotify.com', 'open.spotify.com', 'music.apple.com', 'apple.com', 'pinterest.com',
    'pin.it', 'facebook.com', 'fb.watch', 'threads.net', 'bilibili.com', 'b23.tv',
    'pixiv.net', 'douyin.com', 'iesdouyin.com', 'xiaohongshu.com', 'xhslink.com',
    'bandcamp.com', 'reddit.com', 'redd.it', 'terabox.com', '1024tera.com', 'teraboxapp.com'
}
FORMATS = {
    'best': 'bestvideo*+bestaudio/best',
    '720': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
    'audio': 'bestaudio/best'
}

# User Agent standar Chrome agar tidak diblokir platform
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

def valid_url(raw):
    try:
        u = urlparse(raw)
        host = (u.hostname or '').lower().rstrip('.')
        return u.scheme in ('http', 'https') and any(host == d or host.endswith('.' + d) for d in ALLOWED)
    except Exception:
        return False

def info(url):
    opts = {
        'quiet': True, 
        'no_warnings': True, 
        'skip_download': True, 
        'noplaylist': True, 
        'socket_timeout': 30, 
        'extractor_retries': 2,
        'user_agent': USER_AGENT
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        data = ydl.extract_info(url, download=False)
        return {
            'title': data.get('title') or 'Media',
            'thumbnail': data.get('thumbnail') or '',
            'duration': data.get('duration'),
            'ext': data.get('ext') or '',
            'extractor': data.get('extractor_key') or data.get('extractor') or 'Media'
        }

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)
    
    def log_message(self, fmt, *args):
        # Log ke console Railway agar bisa dicek jika error
        print(f"[LOG] {fmt % args}")
    
    def do_GET(self):
        if self.path.split('?', 1)[0] not in ('/', '/index.html', '/style.css', '/script.js'):
            return self.reply({'error': 'Tidak ditemukan.'}, 404)
        return super().do_GET()
    
    def reply(self, obj, status=200):
        raw = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(raw)
    
    def body(self):
        length = int(self.headers.get('Content-Length', '0'))
        if length > 10000:
            raise ValueError('Permintaan terlalu besar.')
        return json.loads(self.rfile.read(length) or b'{}')
    
    def do_POST(self):
        if self.path not in ('/api/info', '/api/download'):
            return self.reply({'error': 'Endpoint tidak ditemukan.'}, 404)
        try:
            data = self.body()
            url = str(data.get('url', '')).strip()
            if not valid_url(url):
                return self.reply({'error': 'Masukkan tautan publik dari salah satu platform yang didukung.'}, 400)
            
            if self.path == '/api/info':
                try:
                    return self.reply(info(url))
                except Exception as e:
                    print(f"[ERROR INFO] {str(e)}")
                    return self.reply({'error': f'Media tidak ditemukan: {str(e)}'}, 422)
            
            quality = data.get('quality', 'best')
            fmt = FORMATS.get(quality)
            if not fmt:
                return self.reply({'error': 'Pilihan kualitas tidak valid.'}, 400)
            
            print(f"[DOWNLOAD] Memulai unduhan untuk: {url}")
            
            with tempfile.TemporaryDirectory(prefix='mori-') as temp:
                opts = {
                    'quiet': True, 
                    'no_warnings': True, 
                    'noplaylist': True,
                    'socket_timeout': 60, # Timeout lebih panjang untuk download
                    'retries': 3, 
                    'format': fmt,
                    'outtmpl': os.path.join(temp, '%(title).120B.%(ext)s'),
                    'merge_output_format': 'mp4', 
                    'max_filesize': 500 * 1024 * 1024, # Batas 500MB
                    'user_agent': USER_AGENT
                }
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
                
                files = [f for f in glob.glob(os.path.join(temp, '*')) if os.path.isfile(f)]
                if not files:
                    return self.reply({'error': 'File unduhan tidak ditemukan setelah proses selesai.'}, 422)
                
                path = files[0]
                name = re.sub(r'[\r\n "\/]+', '_', os.path.basename(path))
                size = os.path.getsize(path)
                
                print(f"[SUCCESS] File siap dikirim: {name} ({size} bytes)")
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Length', str(size))
                self.send_header('Content-Disposition', f'attachment; filename="{name}"')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                
                with open(path, 'rb') as media:
                    while chunk := media.read(1024 * 256):
                        self.wfile.write(chunk)
                        
        except (ValueError, json.JSONDecodeError):
            self.reply({'error': 'Permintaan tidak valid.'}, 400)
        except Exception as e:
            print(f"[CRITICAL ERROR] {str(e)}")
            self.reply({'error': f'Unduhan gagal: {str(e)}'}, 422)

def signal_handler(sig, frame):
    print('Shutting down server...')
    sys.exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    port = int(os.environ.get('PORT', '8000'))
    print(f'Server BHENK.INC starting on port {port}...')
    
    server = ThreadingHTTPServer(('0.0.0.0', port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print('Server stopped.')
