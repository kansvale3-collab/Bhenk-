from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from pathlib import Path
import json, re, tempfile, os, glob
import yt_dlp
import signal, sys

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

# User Agent Chrome Terbaru (Windows 10/11) - Kunci agar tidak dianggap bot
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'

def valid_url(raw):
    try:
        u = urlparse(raw)
        host = (u.hostname or '').lower().rstrip('.')
        return u.scheme in ('http', 'https') and any(host == d or host.endswith('.' + d) for d in ALLOWED)
    except Exception:
        return False

def get_ydl_opts(download=False, temp_dir=None, fmt=None):
    opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'socket_timeout': 30,
        'retries': 3,
        'extractor_retries': 3,
        'user_agent': USER_AGENT,
        'geo_bypass': True, # Penting untuk YouTube agar tidak kena block region
        'no_check_certificate': True, # Kadang membantu di server cloud
        'http_headers': {
            'User-Agent': USER_AGENT,
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.youtube.com/'
        }
    }
    
    if download:
        opts.update({
            'outtmpl': os.path.join(temp_dir, '%(title).120B.%(ext)s'),
            'merge_output_format': 'mp4',
            'max_filesize': 500 * 1024 * 1024,
            'format': fmt or FORMATS['best']
        })
    else:
        opts['skip_download'] = True
        
    return opts

def info(url):
    opts = get_ydl_opts(download=False)
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
        print(f"[LOG] {fmt % args}")
    
    def do_GET(self):
        path = self.path.split('?', 1)[0]
        if path not in ('/', '/index.html', '/style.css', '/script.js'):
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
        if length > 10000: raise ValueError('Payload terlalu besar')
        return json.loads(self.rfile.read(length) or b'{}')
    
    def do_POST(self):
        if self.path not in ('/api/info', '/api/download'):
            return self.reply({'error': 'Endpoint tidak valid'}, 404)
            
        try:
            data = self.body()
            url = str(data.get('url', '')).strip()
            
            if not valid_url(url):
                return self.reply({'error': 'Link tidak didukung.'}, 400)
            
            # --- API INFO ---
            if self.path == '/api/info':
                try:
                    return self.reply(info(url))
                except Exception as e:
                    err_msg = str(e)
                    # Deteksi error khusus YouTube Bot
                    if 'not a bot' in err_msg or 'Sign in' in err_msg:
                        print("[YOUTUBE BLOCK] Terdeteksi blokir bot YouTube.")
                        return self.reply({'error': 'YouTube memblokir server sementara. Coba lagi dalam 5 menit atau gunakan link lain.'}, 429)
                    return self.reply({'error': f'Gagal mengambil info: {err_msg[:100]}'}, 422)
            
            # --- API DOWNLOAD ---
            quality = data.get('quality', 'best')
            fmt = FORMATS.get(quality)
            if not fmt:
                return self.reply({'error': 'Kualitas tidak valid'}, 400)
                
            print(f"[DOWNLOAD] Memproses: {url}")
            
            with tempfile.TemporaryDirectory(prefix='bhenk-') as temp:
                opts = get_ydl_opts(download=True, temp_dir=temp, fmt=fmt)
                
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
                
                files = [f for f in glob.glob(os.path.join(temp, '*')) if os.path.isfile(f)]
                if not files:
                    return self.reply({'error': 'File gagal diunduh oleh server.'}, 422)
                
                path = files[0]
                name = re.sub(r'[^\w\-_.]', '_', os.path.basename(path))
                size = os.path.getsize(path)
                
                print(f"[SUCCESS] Mengirim: {name} ({size} bytes)")
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Length', str(size))
                self.send_header('Content-Disposition', f'attachment; filename="{name}"')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                
                with open(path, 'rb') as f:
                    while chunk := f.read(1024 * 512):
                        self.wfile.write(chunk)
                        
        except (ValueError, json.JSONDecodeError):
            self.reply({'error': 'Format request salah'}, 400)
        except Exception as e:
            err_msg = str(e)
            if 'not a bot' in err_msg or 'Sign in' in err_msg:
                 return self.reply({'error': 'YouTube memblokir server sementara. Coba lagi nanti.'}, 429)
            print(f"[CRITICAL] {e}")
            self.reply({'error': f'Unduhan gagal: {err_msg[:100]}'}, 422)

def shutdown(sig, frame):
    print("Server dimatikan...")
    sys.exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGTERM, shutdown)
    port = int(os.environ.get('PORT', '8000'))
    print(f"🚀 BHENK.INC Server running on port {port}")
    
    server = ThreadingHTTPServer(('0.0.0.0', port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
