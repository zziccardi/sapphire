"""End-to-end stdio JSON-RPC smoke tests for the Sapphire LSP server."""

import json
import os
import subprocess
import sys
import threading
import unittest
from typing import Any

_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)


def _encode_lsp_message(payload: dict[str, Any]) -> bytes:
  body = json.dumps(payload).encode("utf-8")
  header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
  return header + body


def _read_lsp_message(stream) -> dict[str, Any] | None:
  headers: dict[str, str] = {}
  while True:
    line = stream.readline()
    if not line:
      return None
    if line in (b"\r\n", b"\n"):
      break
    if b":" in line:
      k, v = line.decode("ascii", errors="replace").split(":", 1)
      headers[k.strip().lower()] = v.strip()
  length = int(headers.get("content-length", "0"))
  if length <= 0:
    return None
  body = stream.read(length)
  if not body:
    return None
  return json.loads(body.decode("utf-8"))


class _StdioLspClient:
  """Minimal Content-Length framed JSON-RPC 2.0 client for testing `src.lsp.server`."""

  def __init__(self, proc: subprocess.Popen):
    self.proc = proc
    self.notifications: list[dict[str, Any]] = []
    self._responses: dict[int, dict[str, Any]] = {}
    self._cond = threading.Condition()
    self._closed = False
    self._next_id = 1
    self._reader = threading.Thread(target=self._read_loop, daemon=True)
    self._reader.start()

  def _read_loop(self) -> None:
    try:
      while True:
        msg = _read_lsp_message(self.proc.stdout)
        if msg is None:
          break
        with self._cond:
          if "id" in msg and "method" not in msg:
            self._responses[msg["id"]] = msg
          else:
            self.notifications.append(msg)
          self._cond.notify_all()
    finally:
      with self._cond:
        self._closed = True
        self._cond.notify_all()

  def notify(self, method: str, params: Any = None) -> None:
    msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
      msg["params"] = params
    self.proc.stdin.write(_encode_lsp_message(msg))
    self.proc.stdin.flush()

  def request(self, method: str, params: Any = None, timeout: float = 10.0) -> dict[str, Any]:
    req_id = self._next_id
    self._next_id += 1
    msg: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
      msg["params"] = params
    self.proc.stdin.write(_encode_lsp_message(msg))
    self.proc.stdin.flush()

    with self._cond:
      ok = self._cond.wait_for(
          lambda: req_id in self._responses or self._closed, timeout=timeout
      )
      if not ok or req_id not in self._responses:
        raise TimeoutError(f"Timed out waiting for LSP response to {method} (id={req_id})")
      return self._responses.pop(req_id)

  def wait_for_diagnostics(self, uri: str, min_count: int = 1, timeout: float = 10.0) -> dict[str, Any]:
    def _matching():
      return [
          n for n in self.notifications
          if n.get("method") == "textDocument/publishDiagnostics"
          and n.get("params", {}).get("uri") == uri
      ]

    with self._cond:
      ok = self._cond.wait_for(
          lambda: len(_matching()) >= min_count or self._closed, timeout=timeout
      )
      matches = _matching()
      if not ok or len(matches) < min_count:
        raise TimeoutError(f"Timed out waiting for publishDiagnostics for {uri}")
      return matches[-1]


class TestLspServerStdio(unittest.TestCase):
  """Spawns `python -m src.lsp.server` over stdio and validates JSON-RPC flows."""

  def test_stdio_lifecycle_diagnostics_hover_definition_completion_and_signature(self):
    env = os.environ.copy()
    env["PYTHONPATH"] = _REPO_ROOT + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "src.lsp.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=_REPO_ROOT,
        env=env,
    )
    client = _StdioLspClient(proc)
    try:
      # 1. Initialize handshake
      init_resp = client.request(
          "initialize",
          {
              "processId": os.getpid(),
              "rootUri": f"file://{_REPO_ROOT}",
              "capabilities": {},
          },
      )
      caps = init_resp["result"]["capabilities"]
      self.assertTrue(caps.get("hoverProvider"))
      self.assertTrue(caps.get("definitionProvider"))
      self.assertIn("completionProvider", caps)
      self.assertIn("signatureHelpProvider", caps)
      self.assertTrue(caps.get("documentSymbolProvider"))
      self.assertIn("semanticTokensProvider", caps)

      client.notify("initialized", {})

      # 2. didOpen with a UTF-16 surrogate pair emoji before an identifier
      uri = "file:///stdio_smoke.sp"
      source_v1 = "\n".join([
          "struct Counter {",
          "  var value: int;",
          "}",
          "impl Counter {",
          "  var func add(delta: int, label: String): int {",
          "    return self.value + delta;",
          "  }",
          "}",
          "func demo(): int {",
          '  let emoji = "😀"; var c = Counter { value = 1 };',
          '  return c.add(2, "ok");',
          "}",
      ])
      client.notify(
          "textDocument/didOpen",
          {
              "textDocument": {
                  "uri": uri,
                  "languageId": "sapphire",
                  "version": 1,
                  "text": source_v1,
              }
          },
      )
      diag_msg = client.wait_for_diagnostics(uri, min_count=1)
      self.assertEqual(diag_msg["params"]["diagnostics"], [])

      # 3. Hover on Counter (line 0, col 8)
      hover_resp = client.request(
          "textDocument/hover",
          {
              "textDocument": {"uri": uri},
              "position": {"line": 0, "character": 8},
          },
      )
      self.assertIsNotNone(hover_resp["result"])
      self.assertIn("Counter", hover_resp["result"]["contents"]["value"])

      # 4. Go-to-definition on `c` in `return c.add(...)` -> jumps to UTF-16 col of `var c`
      lines = source_v1.splitlines()
      use_col = lines[10].index("c.add")
      decl_u16_col = (
          len(lines[9][: lines[9].index("c = Counter")].encode("utf-16-le")) // 2
      )
      def_resp = client.request(
          "textDocument/definition",
          {
              "textDocument": {"uri": uri},
              "position": {"line": 10, "character": use_col},
          },
      )
      self.assertIsNotNone(def_resp["result"])
      self.assertEqual(def_resp["result"]["range"]["start"]["line"], 9)
      self.assertEqual(
          def_resp["result"]["range"]["start"]["character"], decl_u16_col
      )

      # 5. Document symbols
      sym_resp = client.request(
          "textDocument/documentSymbol",
          {"textDocument": {"uri": uri}},
      )
      sym_names = {s["name"] for s in sym_resp["result"]}
      self.assertIn("Counter", sym_names)
      self.assertIn("demo", sym_names)

      # 6. didChange introducing dot-completion & signature-help triggers
      source_v2 = source_v1.replace('return c.add(2, "ok");', "c.\n  c.add(2, ")
      client.notify(
          "textDocument/didChange",
          {
              "textDocument": {"uri": uri, "version": 2},
              "contentChanges": [{"text": source_v2}],
          },
      )
      client.wait_for_diagnostics(uri, min_count=2)

      comp_resp = client.request(
          "textDocument/completion",
          {
              "textDocument": {"uri": uri},
              "position": {"line": 10, "character": 4},
          },
      )
      comp_labels = {item["label"] for item in comp_resp["result"]["items"]}
      self.assertIn("value", comp_labels)
      self.assertIn("add", comp_labels)

      sig_resp = client.request(
          "textDocument/signatureHelp",
          {
              "textDocument": {"uri": uri},
              "position": {"line": 11, "character": 11},
          },
      )
      self.assertIsNotNone(sig_resp["result"])
      self.assertEqual(sig_resp["result"]["activeParameter"], 1)
      self.assertIn(
          "add(delta: int, label: String)",
          sig_resp["result"]["signatures"][0]["label"],
      )

      # 7. Clean shutdown + exit
      client.request("shutdown")
      client.notify("exit")
      rc = proc.wait(timeout=10)
      self.assertEqual(rc, 0)
    finally:
      if proc.poll() is None:
        proc.kill()
        proc.wait(timeout=5)
      if proc.stdin:
        proc.stdin.close()
      if proc.stdout:
        proc.stdout.close()
      if proc.stderr:
        proc.stderr.close()


if __name__ == "__main__":
  unittest.main()
