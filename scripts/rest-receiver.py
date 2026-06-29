#!/usr/bin/env python3
"""rest-receiver.py — 接收 HAE App 从 iPhone POST 过来的健康数据
绕开 iCloud 同步延迟（7h+），秒级到达 Mac 本地。

用法:
  python3 rest-receiver.py --port 8765

HAE App 配置: Custom REST Endpoint → http://<Mac局域网IP>:8765/health

数据写入: ~/.life-log/raw-ingest/<YYYY-MM-DD>.json
仅在内网使用，不暴露到公网。
"""
import json, os, sys, argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

INGEST_DIR = os.path.expanduser("~/.life-log/raw-ingest")

class HealthReceiver(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != '/health':
            self.send_response(404)
            self.end_headers()
            return

        try:
            content_len = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_len)
            data = json.loads(body)

            # 写入日期文件
            date_str = datetime.now().strftime('%Y-%m-%d')
            os.makedirs(INGEST_DIR, exist_ok=True)
            fpath = os.path.join(INGEST_DIR, f'{date_str}.json')

            with open(fpath, 'w') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            print(f"✅ {datetime.now().strftime('%H:%M:%S')} 收到数据 → {fpath}")

        except Exception as e:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode())
            print(f"❌ {e}")

    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true,"status":"listening"}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # 关闭默认日志，用上面的 print

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()

    os.makedirs(INGEST_DIR, exist_ok=True)
    print(f"🔄 HAE REST 接收器启动: http://0.0.0.0:{args.port}/health")
    print(f"📁 数据目录: {INGEST_DIR}")
    print(f"📱 HAE App 配置: http://<Mac IP>:{args.port}/health")

    server = HTTPServer(('0.0.0.0', args.port), HealthReceiver)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n⏹ 停止")
        server.shutdown()
