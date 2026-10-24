"""get_project_infos must fail instead of hanging when the real-time service can't be reached."""
import gc
import threading

import pytest
import requests
import responses
from socketIO_client.exceptions import ConnectionError as SocketIOConnectionError

from olsync.olclient import OverleafClient

BASE = "http://overleaf.example.test"


def run_with_timeout(func, seconds=15):
    """Runs func in a daemon thread; fails the test if it doesn't finish in time (instead of hanging the test run)."""
    outcome = {}

    def target():
        try:
            outcome["result"] = func()
        except BaseException as e:  # noqa: BLE001 - re-raised in the test thread below
            outcome["error"] = e

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=seconds)
    if thread.is_alive():
        pytest.fail("get_project_infos hangs (socketIO-client retries forever) instead of failing")
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("result")


def unreachable_after_handshake(rsps):
    # Our own handshake request succeeds, the Socket.IO connection afterwards does not
    rsps.add(responses.GET, f"{BASE}/socket.io/1/", body="sid:60:60:websocket,xhr-polling")
    rsps.add(responses.GET, f"{BASE}/socket.io/1/", body=requests.ConnectionError("connection refused"))


def test_project_infos_fail_fast_when_the_real_time_service_is_unreachable():
    def call():
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            unreachable_after_handshake(rsps)
            client = OverleafClient({"overleaf_session2": "s"}, "csrf", base_url=BASE)
            with pytest.raises(SocketIOConnectionError):
                client.get_project_infos("p1")

    run_with_timeout(call)


@pytest.mark.filterwarnings("error::pytest.PytestUnraisableExceptionWarning")
def test_no_reconnect_when_the_socket_is_cleaned_up():
    # socketIO-client's __del__ calls disconnect(), which opens a brand-new connection if the old one is closed
    def call():
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            unreachable_after_handshake(rsps)
            client = OverleafClient({"overleaf_session2": "s"}, "csrf", base_url=BASE)
            with pytest.raises(SocketIOConnectionError):
                client.get_project_infos("p1")
            gc.collect()
            return [c for c in rsps.calls if "/socket.io/1/" in c.request.url]

    handshakes = run_with_timeout(call)
    assert len(handshakes) == 2, "no further connection attempts after get_project_infos is done"
