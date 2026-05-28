import cloudscraper
import logging
from flask import Flask, request, jsonify, Response
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
)

logger = logging.getLogger(__name__)

app = Flask(__name__)

def build_scraper() -> cloudscraper.CloudScraper:
    scraper = cloudscraper.create_scraper(
        browser={
            "browser": "chrome",
            "platform": "windows",
            "mobile": False,
        }
    )

    retry_strategy = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )

    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=100,
        pool_maxsize=100,
    )

    scraper.mount("https://", adapter)
    scraper.mount("http://", adapter)
    return scraper


scraper = build_scraper()

EXCLUDED_HEADERS = {
    "content-encoding",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "upgrade",
    "host",
}


def forward_response(resp) -> Response:
    """Convert a requests.Response into a Flask Response, forwarding headers."""
    headers = {
        k: v
        for k, v in resp.headers.items()
        if k.lower() not in EXCLUDED_HEADERS
    }
    return Response(resp.content, status=resp.status_code, headers=headers)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/proxy", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def proxy():
    body = request.get_json(silent=True) or {}

    target_url = body.get("url") or request.args.get("url")
    if not target_url:
        return jsonify({"error": "Missing required field: url"}), 400

    method  = (body.get("method") or request.method).upper()
    headers = body.get("headers") or {}
    params  = body.get("params")  or {}
    payload = body.get("payload") or None

    logger.info("Proxying  %s  %s", method, target_url)

    try:
        resp = scraper.request(
            method=method,
            url=target_url,
            headers=headers,
            params=params,
            json=payload if payload else None,
            timeout=30,
        )

        logger.info("Response  %s  %s  →  %d", method, target_url, resp.status_code)
        return forward_response(resp)

    except Exception as exc:
        logger.exception("Proxy request failed: %s", exc)
        return jsonify({"error": str(exc)}), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
