/* Web API Client SDK */

// 1. Integer-Backed HTTP Status Enum
enum HttpStatusCode {
  Ok = 200,
  Created = 201,
  BadRequest = 400,
  Unauthorized = 401,
  NotFound = 404,
  InternalError = 500,
}

// 2. Data Models
struct HttpRequest {
  let url: String;
  let method: String = "GET";
  var body: String? = none;
  var auth_header: String? = none;
}

struct HttpResponse {
  let status_code: int;
  let payload: String?;
  let error_message: String? = none;
}

// Middleware type definition: takes HttpRequest and returns transformed
// HttpRequest
var Middleware: (HttpRequest) -> HttpRequest;

// 3. API Client SDK Core Struct
struct ApiClient {
  let base_url: String;
  var api_key: String?;
  var default_timeout_ms: int = 5000;
}

impl ApiClient {
  static func create(base_url: String, api_key: String? = none): ApiClient {
    return ApiClient {
      base_url = base_url,
      api_key = api_key,
      default_timeout_ms = 5000,
    };
  }

  // Executes an HTTP call with default and named parameters
  const func send_request(
      url: String, method: String = "GET", body: String? = none,
      timeout_ms: int = 5000): HttpResponse {
    let full_url = self.base_url + url;

    // Construct initial request
    var req = HttpRequest {
      url = full_url,
      method = method,
      body = body,
      auth_header = self.api_key,
    };

    print("Executing " + req.method + " request to " + req.url);

    // Simulate successful API response
    if req.auth_header != none {
      return HttpResponse {
        status_code = HttpStatusCode.Ok,
        payload = "{\"status\": \"success\", \"data\": {\"user_id\": 42}}",
        error_message = none,
      };
    } else {
      return HttpResponse {
        status_code = HttpStatusCode.Unauthorized,
        payload = none,
        error_message = "Missing authentication API key",
      };
    }
  }
}

// --------------------------------------------------
// Usage Demonstration
// --------------------------------------------------

// Instantiating Client via static factory method
let client = ApiClient.create(
    base_url = "https://api.example.com/v1",
    api_key = "sk_live_992183811");

// Call API leveraging default parameters (method defaults to GET, timeout
// defaults to 5000)
let response = client.send_request(url = "/users/me");

// Safe Optional Unwrapping & Enum Check
if response.status_code == HttpStatusCode.Ok {
  if let json_data = response.payload {
    print("Received payload successfully: " + json_data);
  }
} else {
  if let err = response.error_message {
    print("API Error [" + response.status_code + "]: " + err);
  }
}

// Making a POST request using named arguments at call site
let post_response = client.send_request(
    url = "/users",
    method = "POST",
    body = "{\"name\": \"Alice\"}",
    timeout_ms = 10000);
