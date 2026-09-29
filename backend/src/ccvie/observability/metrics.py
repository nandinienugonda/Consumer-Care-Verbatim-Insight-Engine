from prometheus_client import Counter, Histogram

REQUEST_LATENCY = Histogram(
    "ccvie_http_request_duration_seconds",
    "HTTP request latency by route template.",
    ["method", "route", "status"],
)

REQUESTS_REJECTED = Counter(
    "ccvie_http_requests_rejected_total",
    "Requests rejected by authentication or authorization.",
    ["code"],
)
