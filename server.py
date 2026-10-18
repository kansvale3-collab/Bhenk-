from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from pathlib import Path
import json, re, tempfile, os, glob
import yt_dlp

ROOT=Path(__file__).resolve().parent
ALLOWED={
 'tiktok.com','instagram.com','youtube.com','youtu.be','x.com','twitter.com','spotify.com','open.spotify.com','music.apple.com','apple.com','pinterest.com','pin.it','facebook.com','fb.watch','threads.net','bilibili.com','b23.tv','pixiv.net','douyin.com','iesdouyin.com','xiaohongshu.com','xhslink.com','bandcamp.com','reddit.com','redd.it','terabox.com','1024tera.com','teraboxapp.com'
}
FORMATS={'best':'bestvideo*+bestaudio/best','720':'bestvideo[height<=720]+bestaudio/best[height<=720]/best','audio':'bestaudio/best'}
def valid_url(raw):
    try:
        u=urlparse(raw);host=(u.hostname or '').lower().rstrip('.')
        return u.scheme in ('http','https') and any(host==d or host.endswith('.'+d) for d in ALLOWED)
    except Exception:return False
def info(url):
    opts={'quiet':True,'no_warnings':True,'skip_download':True,'noplaylist':True,'socket_timeout':20,'extractor_retries':1}
    with yt_dlp.YoutubeDL(opts) as ydl:
        data=ydl.extract_info(url,download=False)
    return {'title':data.get('title') or 'Media','thumbnail':data.get('thumbnail') or '', 'duration':data.get('duration'), 'ext':data.get('ext') or '', 'extractor':data.get('extractor_key') or data.get('extractor') or 'Media'}
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(ROOT),**kwargs)
    def log_message(self,fmt,*args):pass
    def do_GET(self):
        if self.path.split('?',1)[0] not in ('/','/index.html','/style.css','/script.js'):
            return self.reply({'error':'Tidak ditemukan.'},404)
        return super().do_GET()
    def reply(self,obj,status=200):
        raw=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
    def body(self):
        length=int(self.headers.get('Content-Length','0'))
        if length>10000:raise ValueError('Permintaan terlalu besar.')
        return json.loads(self.rfile.read(length) or b'{}')
    def do_POST(self):
        if self.path not in ('/api/info','/api/download'):return self.reply({'error':'Endpoint tidak ditemukan.'},404)
        try:
            data=self.body();url=str(data.get('url','')).strip()
            if not valid_url(url):return self.reply({'error':'Masukkan tautan publik dari salah satu platform yang didukung.'},400)
            if self.path=='/api/info':
                try:return self.reply(info(url))
                except Exception as exc:return self.reply({'error':'Media tidak ditemukan atau tidak dapat diakses. Pastikan tautan bersifat publik.'},422)
            quality=data.get('quality','best');fmt=FORMATS.get(quality)
            if not fmt:return self.reply({'error':'Pilihan kualitas tidak valid.'},400)
            with tempfile.TemporaryDirectory(prefix='mori-') as temp:
                opts={'quiet':True,'no_warnings':True,'noplaylist':True,'socket_timeout':25,'retries':1,'format':fmt,'outtmpl':os.path.join(temp,'%(title).120B.%(ext)s'),'merge_output_format':'mp4','max_filesize':500*1024*1024}
                with yt_dlp.YoutubeDL(opts) as ydl:ydl.download([url])
                files=[f for f in glob.glob(os.path.join(temp,'*')) if os.path.isfile(f)]
                if not files:return self.reply({'error':'File unduhan tidak ditemukan.'},422)
                path=files[0];name=re.sub(r'[\r\n"\\/]+','_',os.path.basename(path));size=os.path.getsize(path)
                self.send_response(200);self.send_header('Content-Type','application/octet-stream');self.send_header('Content-Length',str(size));self.send_header('Content-Disposition',f'attachment; filename="{name}"');self.send_header('Cache-Control','no-store');self.end_headers()
                with open(path,'rb') as media:
                    while chunk:=media.read(1024*256):self.wfile.write(chunk)
        except (ValueError,json.JSONDecodeError):self.reply({'error':'Permintaan tidak valid.'},400)
        except Exception:self.reply({'error':'Unduhan gagal. Coba tautan publik lain atau kualitas berbeda.'},422)
if __name__=='__main__':
    port=int(os.environ.get('PORT','8000'))
    print(f'Mori berjalan di http://localhost:{port}')
    ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
