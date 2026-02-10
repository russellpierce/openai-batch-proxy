from openai_batch_proxy.batch.hasher import hash_request


def test_same_request_same_hash() -> None:
    """Same request body produces same hash across calls."""
    body: dict[str, object] = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "Hello"}],
    }
    assert hash_request(body) == hash_request(body)


def test_different_requests_different_hashes() -> None:
    """Different request bodies produce different hashes."""
    body1: dict[str, object] = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "Hello"}],
    }
    body2: dict[str, object] = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "World"}],
    }
    assert hash_request(body1) != hash_request(body2)


def test_excluded_fields_dont_affect_hash() -> None:
    """Excluded fields (stream, stream_options, user) don't change hash."""
    base: dict[str, object] = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "Hello"}],
    }
    with_stream: dict[str, object] = {**base, "stream": True}
    with_user: dict[str, object] = {**base, "user": "user123"}
    with_stream_options: dict[str, object] = {**base, "stream_options": {"include_usage": True}}
    with_all: dict[str, object] = {
        **base,
        "stream": True,
        "user": "user123",
        "stream_options": {},
    }

    base_hash = hash_request(base)
    assert hash_request(with_stream) == base_hash
    assert hash_request(with_user) == base_hash
    assert hash_request(with_stream_options) == base_hash
    assert hash_request(with_all) == base_hash


def test_non_excluded_fields_affect_hash() -> None:
    """Non-excluded optional fields do affect the hash."""
    base: dict[str, object] = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "Hello"}],
    }
    with_temp: dict[str, object] = {**base, "temperature": 0.7}
    assert hash_request(base) != hash_request(with_temp)


def test_key_order_independent() -> None:
    """Dict key insertion order doesn't affect hash."""
    body1: dict[str, object] = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "Hi"}],
    }
    body2: dict[str, object] = {
        "messages": [{"role": "user", "content": "Hi"}],
        "model": "gpt-4o-mini",
    }
    assert hash_request(body1) == hash_request(body2)


def test_hash_is_hex_string() -> None:
    """Hash output is a valid hex string."""
    body: dict[str, object] = {"model": "gpt-4o-mini", "messages": []}
    result = hash_request(body)
    assert len(result) == 64  # SHA-256 hex
    int(result, 16)  # Valid hex
