import http.server
import json
import socketserver
import os
import re
from datetime import datetime
from pathlib import Path

PORT = 8000

class ViewerHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/files':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            # Find all .tdpm.json files in output directory recursively
            files = []
            output_dir = Path("output")
            if output_dir.exists() and output_dir.is_dir():
                for f in output_dir.rglob("*.tdpm.json"):
                    if f.is_file():
                        # Try to extract the timestamp (YYYYMMDD_HHMMSS) right before .tdpm.json
                        match = re.search(r"(\d{8}_\d{6})\.tdpm\.json$", f.name)
                        if match:
                            timestamp = match.group(1)
                        else:
                            # Fallback: format modification time as YYYYMMDD_HHMMSS
                            timestamp = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y%m%d_%H%M%S")

                        files.append({
                            "name": f.name,
                            "path": f"/output/{f.relative_to(output_dir).as_posix()}",
                            "timestamp": timestamp
                        })

            # Sort files descending by timestamp
            files.sort(key=lambda x: x["timestamp"], reverse=True)
            for f in files:
                del f["timestamp"]

            self.wfile.write(json.dumps(files).encode())
            return

        elif self.path == '/' or self.path == '/index.html':
            self.path = '/viewer/index.html'

        return super().do_GET()

if __name__ == "__main__":
    os.chdir(Path(__file__).parent)
    with socketserver.TCPServer(("", PORT), ViewerHandler) as httpd:
        print(f"Serving TDPM-20 Viewer at http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
