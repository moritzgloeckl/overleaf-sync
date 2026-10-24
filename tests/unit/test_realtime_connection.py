"""get_project_infos must fail instead of hanging when the real-time service can't be reached."""
import threading

import pytest
import requests
import responses

from olsync.olclient import OverleafClient

BASE = "http://overleaf.example.test"


def test_project_infos_fail_fast_when_the_real_time_service_is_unreachable():
    outcome = {}

    def call():
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            # Our own handshake request succeeds, the Socket.IO connection afterwards does not
            rsps.add(responses.GET, f"{BASE}/socket.io/1/", body="sid:60:60:websocket,xhr-polling")
            rsps.add(responses.GET, f"{BASE}/socket.io/1/", body=requests.ConnectionError("connection refused"))
            try:
                OverleafClient({"overleaf_session2": "s"}, "csrf", base_url=BASE).get_project_infos("p1")
                outcome["result"] = "returned"
            except Exception as e:  # noqa: BLE001 - any error is fine, hanging is not
                outcome["result"] = type(e).__name__

    thread = threading.Thread(target=call, daemon=True)
    thread.start()
    thread.join(timeout=15)
    if thread.is_alive():
        pytest.fail("get_project_infos hangs (socketIO-client retries forever) instead of failing")
    assert outcome["result"] != "returned"


@pytest.mark.filterwarnings("error::pytest.PytestUnraisableExceptionWarning")
def test_no_reconnect_when_the_socket_is_cleaned_up():
    # socketIO-client's __del__ calls disconnect(), which opens a brand-new connection if the old one is closed
    import gc
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{BASE}/socket.io/1/", body="sid:60:60:websocket,xhr-polling")
        rsps.add(responses.GET, f"{BASE}/socket.io/1/", body=requests.ConnectionError("connection refused"))
        with pytest.raises(Exception):
            OverleafClient({"overleaf_session2": "s"}, "csrf", base_url=BASE).get_project_infos("p1")
        gc.collect()
        handshakes = [c for c in rsps.calls if "/socket.io/1/" in c.request.url]
    assert len(handshakes) == 2, "no further connection attempts after get_project_infos is done"
