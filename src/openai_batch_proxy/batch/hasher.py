import hashlib
import json

# Fields to exclude from hashing (non-deterministic or per-request-unique)
EXCLUDED_FIELDS: frozenset[str] = frozenset(
    {
        "stream",
        "stream_options",
        "user",
    }
)


def hash_request(request_body: dict[str, object]) -> str:
    """Compute SHA-256 hash of request body, excluding non-deterministic fields."""
    filtered = {k: v for k, v in request_body.items() if k not in EXCLUDED_FIELDS}
    canonical = json.dumps(filtered, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
