#!/usr/bin/env python3
import json
import selectors
import subprocess
import sys
import time


class SafariMcp:
    def __init__(self, executable="/usr/bin/safaridriver", timeout=8):
        self.timeout = timeout
        self.child = subprocess.Popen(
            [executable, "--mcp"], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.child.stdout, selectors.EVENT_READ)
        self.pending = b""
        self.next_id = 0

    def close(self):
        self.selector.close()
        if self.child.poll() is None:
            self.child.terminate()
            try:
                self.child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.child.kill()
                self.child.wait()
        self.child.stdin.close()
        self.child.stdout.close()
        self.child.stderr.close()

    def call(self, method, params):
        self.next_id += 1
        request_id = self.next_id
        message = {"jsonrpc": "2.0", "id": request_id,
                   "method": method, "params": params}
        self.child.stdin.write(json.dumps(message, separators=(",", ":")).encode() + b"\n")
        self.child.stdin.flush()
        deadline = time.monotonic() + self.timeout
        while True:
            line, separator, rest = self.pending.partition(b"\n")
            if separator:
                self.pending = rest
                reply = json.loads(line)
                if reply.get("id") == request_id:
                    if "error" in reply:
                        raise ValueError(f"Safari MCP {method} failed: {reply['error']}")
                    return reply.get("result")
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Safari MCP {method} timed out")
            if not self.selector.select(remaining):
                raise TimeoutError(f"Safari MCP {method} timed out")
            chunk = self.child.stdout.read1(65536)
            if not chunk:
                raise ValueError(f"Safari MCP {method} closed")
            self.pending += chunk


def probe():
    client = SafariMcp()
    try:
        initialized = client.call("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "dyn4k-safari-response-probe", "version": "1"}})
        if initialized.get("serverInfo", {}).get("name") != "Safari":
            raise ValueError("local Safari MCP server identity differs")
        result = client.call("tools/call", {"name": "list_tabs", "arguments": {}})
        if not isinstance(result, dict) or result.get("isError"):
            detail = result.get("content") if isinstance(result, dict) else result
            raise ValueError(f"Safari browser session unavailable: {detail}")
        return {"status": "AVAILABLE", "protocol": initialized.get("protocolVersion")}
    finally:
        client.close()


if __name__ == "__main__":
    try:
        print(json.dumps(probe(), sort_keys=True))
    except (OSError, ValueError, TimeoutError) as error:
        print(f"UNAVAILABLE: {error}", file=sys.stderr)
        sys.exit(2)
