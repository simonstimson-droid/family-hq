#!/usr/bin/env python3
"""
Simple HTTPS reverse proxy for Home Assistant
Proxies requests from HTTPS (port 8443) to HA HTTP (port 8123)
"""
import http.server
import http.client
import ssl

HA_HOST = '192.168.64.2'
HA_PORT = 8123
LISTEN_PORT = 8443
CERT_FILE = '/Users/simonstimson/caddy/ha.crt'
KEY_FILE = '/Users/simonstimson/caddy/ha.key'

class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def _add_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')

    def do_OPTIONS(self):
        self.send_response(200)
        self._add_cors_headers()
        self.end_headers()

    def do_GET(self):
        try:
            conn = http.client.HTTPConnection(HA_HOST, HA_PORT, timeout=10)
            headers = {}
            for key, val in self.headers.items():
                if key.lower() not in ('host', 'transfer-encoding'):
                    headers[key] = val
            headers['Host'] = f'{HA_HOST}:{HA_PORT}'
            conn.request('GET', self.path, headers=headers)
            resp = conn.getresponse()
            self.send_response(resp.status)
            for key, val in resp.getheaders():
                if key.lower() not in ('transfer-encoding', 'connection'):
                    self.send_header(key, val)
            self._add_cors_headers()
            self.end_headers()
            body = resp.read()
            self.wfile.write(body)
            conn.close()
        except Exception as e:
            self.send_response(502)
            self._add_cors_headers()
            self.end_headers()
            self.wfile.write(f'Proxy error: {e}'.encode())

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b''
        try:
            conn = http.client.HTTPConnection(HA_HOST, HA_PORT, timeout=10)
            headers = {}
            for key, val in self.headers.items():
                if key.lower() not in ('host', 'transfer-encoding'):
                    headers[key] = val
            headers['Host'] = f'{HA_HOST}:{HA_PORT}'
            conn.request('POST', self.path, body=body, headers=headers)
            resp = conn.getresponse()
            self.send_response(resp.status)
            for key, val in resp.getheaders():
                if key.lower() not in ('transfer-encoding', 'connection'):
                    self.send_header(key, val)
            self._add_cors_headers()
            self.end_headers()
            resp_body = resp.read()
            self.wfile.write(resp_body)
            conn.close()
        except Exception as e:
            self.send_response(502)
            self._add_cors_headers()
            self.end_headers()
            self.wfile.write(f'Proxy error: {e}'.encode())

    def log_message(self, format, *args):
        pass  # Suppress logs

server = http.server.HTTPServer(('0.0.0.0', LISTEN_PORT), ProxyHandler)
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain(CERT_FILE, KEY_FILE)
server.socket = ctx.wrap_socket(server.socket, server_side=True)
print(f'HTTPS proxy running on port {LISTEN_PORT} -> {HA_HOST}:{HA_PORT}')
server.serve_forever()
