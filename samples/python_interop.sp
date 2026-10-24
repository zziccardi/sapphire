/*
 * Sample Sapphire program demonstrating Python host runtime interoperability.
 *
 * Uses Sapphire's `@extern` and `@export` annotations to interoperate directly
 * with Python standard library components (`wsgiref.simple_server`).
 */

// 1. Opaque resource handles for Python binary data and server instances
trait BytesHandle {
  func decode(self): String;
}

trait WsgiServer {
  func server_close(self);
}

// 2. Trait method aliasing: maps Sapphire method call to Python's `str.encode`
trait StrEncoder {
  @export("encode")
  func to_bytes(text: String, encoding: String = "utf-8"): BytesHandle;
}

// 3. Module interface for Python's `wsgiref.simple_server`
trait WsgiModule {
  func make_server(
      self, host: String, port: int,
      app: ([String: String],
            (String, [[String]]) -> void) -> [BytesHandle]): WsgiServer;
}

// 4. Host variable bindings
@extern
var str: StrEncoder;

@extern("wsgiref.simple_server")
var wsgiref: WsgiModule;

// 5. Exported WSGI application callback
@export("app")
func wsgi_handler(
    environ: [String: String],
    start_response: (String, [[String]]) -> void): [BytesHandle] {
  let method = environ.get("REQUEST_METHOD") ?? "GET";
  let path = environ.get("PATH_INFO") ?? "/";
  print("Processing " + method + " request for " + path);

  var headers: [[String]] = [];
  headers.push(["Content-Type", "text/plain; charset=utf-8"]);
  headers.push(["Server", "Sapphire-WSGI/1.0"]);

  start_response("200 OK", headers);

  let message = "Hello from Sapphire Web Server running on Python!\n";
  let byte_payload = str.to_bytes(message);

  return [byte_payload];
}

func main() {
  print("Initializing Sapphire HTTP server with Python wsgiref...");
  let server = wsgiref.make_server("127.0.0.1", 8080, wsgi_handler);
  print("Server successfully bound to http://127.0.0.1:8080");
  print("Exported WSGI entrypoint 'app' is ready for requests.");

  // Simulate handling a request via the exported WSGI callback
  var mock_env: [String: String] = {
    "REQUEST_METHOD": "GET",
    "PATH_INFO": "/api/status",
  };

  let mock_start_response = (status: String, headers: [[String]]) -> void {
    print("HTTP Response Status: " + status);
  };

  let response_chunks = wsgi_handler(mock_env, mock_start_response);
  print("Generated " + String.from(response_chunks.size()) +
        " response chunk.");

  server.server_close();
  print("Server closed cleanly.");
}
