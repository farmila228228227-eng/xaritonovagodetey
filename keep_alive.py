import threading
import http.server
import socketserver

PORT = 8080

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run():
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()

def keep_alive():
    t = threading.Thread(target=run)
    t.daemon = True
    t.start()
