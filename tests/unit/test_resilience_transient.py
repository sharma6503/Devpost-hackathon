from agent_guardian.utils.resilience import _is_transient


def test_is_transient_standard():
    # Test standard transient exceptions/errors
    assert _is_transient(ValueError("500 internal server error")) is True
    assert _is_transient(Exception("rate limit exceeded")) is True
    assert _is_transient(Exception("overloaded")) is True
    assert _is_transient(Exception("timeout error")) is True


def test_is_transient_network_and_protocol():
    # Test newly added transport, connection, protocol error signatures
    assert _is_transient(Exception("RemoteProtocolError: peer closed connection")) is True
    assert _is_transient(Exception("httpx.ConnectError: [Errno 11001] getaddrinfo failed")) is True
    assert (
        _is_transient(Exception("httpcore.RemoteProtocolError: Server disconnected without sending a response")) is True
    )
    assert _is_transient(Exception("Connection reset by peer")) is True
    assert _is_transient(Exception("EOF occurred in violation of protocol")) is True
    assert _is_transient(Exception("The connection was closed unexpectedly")) is True


def test_is_transient_non_transient():
    # Test non-transient exceptions
    assert _is_transient(Exception("Permission denied")) is False
    assert _is_transient(ValueError("Invalid argument: 'foo'")) is False
