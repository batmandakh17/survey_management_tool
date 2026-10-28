"""A minimal Chrome DevTools Protocol client on the Python standard library (no websocket package needed).

Starts headless Chrome on a local port with a throw-away profile, connects to the page, and offers:
evaluate JavaScript, upload files into <input type=file>, take screenshots, and catch downloads.
Used only by the tests; the tool itself never talks to anything.
"""
import base64
import json
import os
import socket
import struct
import subprocess
import time
import urllib.request

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


class WS:
    def __init__(self, url):
        rest = url[len("ws://"):]
        hostport, path = rest.split("/", 1)
        host, port = hostport.split(":")
        self.sock = socket.create_connection((host, int(port)), timeout=120)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET /{path} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            resp += self.sock.recv(4096)
        head, _, self.buf = resp.partition(b"\r\n\r\n")
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise ConnectionError(head.decode(errors="replace"))
        self.mid = 0
        self.events = []

    def _recvn(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(1 << 20)
            if not chunk:
                raise ConnectionError("socket closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _frame(self):
        b1, b2 = self._recvn(2)
        fin, op, n = b1 & 0x80, b1 & 0x0F, b2 & 0x7F
        if n == 126:
            n = struct.unpack(">H", self._recvn(2))[0]
        elif n == 127:
            n = struct.unpack(">Q", self._recvn(8))[0]
        mask = self._recvn(4) if b2 & 0x80 else None
        data = self._recvn(n)
        if mask:
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        return fin, op, data

    def _send(self, op, payload):
        hdr = bytearray([0x80 | op])
        n = len(payload)
        if n < 126:
            hdr.append(0x80 | n)
        elif n < 65536:
            hdr.append(0x80 | 126); hdr += struct.pack(">H", n)
        else:
            hdr.append(0x80 | 127); hdr += struct.pack(">Q", n)
        mask = os.urandom(4)
        hdr += mask
        self.sock.sendall(bytes(hdr) + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def _msg(self):
        parts = []
        while True:
            fin, op, data = self._frame()
            if op == 9:
                self._send(0xA, data); continue
            if op == 8:
                raise ConnectionError("closed by Chrome")
            parts.append(data)
            if fin:
                return json.loads(b"".join(parts).decode())

    def call(self, method, **params):
        self.mid += 1
        mid = self.mid
        self._send(1, json.dumps({"id": mid, "method": method, "params": params}).encode())
        while True:
            m = self._msg()
            if m.get("id") == mid:
                if "error" in m:
                    raise RuntimeError(f"{method}: {m['error']}")
                return m.get("result", {})
            self.events.append(m)


class Browser:
    def __init__(self, profile, port=9339, width=1400, height=1000):
        os.makedirs(profile, exist_ok=True)
        self.proc = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
                                      "--no-first-run", "--no-default-browser-check", "--disable-gpu", f"--window-size={width},{height}",
                                      "--remote-allow-origins=*", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        targets = None
        for _ in range(200):
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2))
                if any(t["type"] == "page" for t in targets):
                    break
            except Exception:
                pass
            time.sleep(0.1)
        page = [t for t in targets if t["type"] == "page"][0]
        self.version = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2))
        self.ws = WS(page["webSocketDebuggerUrl"])
        self.bws = WS(self.version["webSocketDebuggerUrl"])
        for d in ("Page", "Runtime", "DOM", "Log"):
            self.ws.call(f"{d}.enable")

    def close(self):
        try:
            self.proc.terminate(); self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()

    def goto(self, url):
        self.ws.call("Page.navigate", url=url)
        self.wait("document.readyState === 'complete'")

    def js(self, expr, await_promise=True):
        r = self.ws.call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=await_promise)
        if "exceptionDetails" in r:
            d = r["exceptionDetails"]
            raise RuntimeError(f"JS error: {d.get('exception', {}).get('description') or d.get('text')}\n  in: {expr[:200]}")
        return r.get("result", {}).get("value")

    def wait(self, cond, timeout=15, step=0.1):
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                if self.js(cond):
                    return True
            except RuntimeError:
                pass
            time.sleep(step)
        raise TimeoutError(f"waited {timeout}s for: {cond}")

    def set_files(self, selector, paths):
        root = self.ws.call("DOM.getDocument", depth=1)["root"]["nodeId"]
        node = self.ws.call("DOM.querySelector", nodeId=root, selector=selector)["nodeId"]
        if not node:
            raise RuntimeError(f"no element {selector}")
        self.ws.call("DOM.setFileInputFiles", files=[os.path.abspath(p) for p in paths], nodeId=node)

    def click(self, selector):
        ok = self.js(f"(() => {{ const el = document.querySelector({json.dumps(selector)}); if (!el) return false; el.click(); return true; }})()")
        if not ok:
            raise RuntimeError(f"nothing to click: {selector}")

    def shot(self, path, full=False):
        r = self.ws.call("Page.captureScreenshot", format="png", captureBeyondViewport=full)
        with open(path, "wb") as f:
            f.write(base64.b64decode(r["data"]))

    def downloads_to(self, folder):
        os.makedirs(folder, exist_ok=True)
        self.bws.call("Browser.setDownloadBehavior", behavior="allow", downloadPath=os.path.abspath(folder), eventsEnabled=True)
