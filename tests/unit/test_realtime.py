"""Overleaf's real-time service (Socket.IO 0.9 protocol) over xhr-polling, without socketIO-client."""

import json
import threading

import pytest
import requests
import responses

from olsync import olclient, realtime
from olsync.olclient import OverleafClient

BASE = "http://overleaf.example.test"
HANDSHAKE = f"{BASE}/socket.io/1/"
POLL = f"{BASE}/socket.io/1/xhr-polling/sid123"
PROJECT = {"_id": "p1", "name": "Thesis", "rootFolder": [{"_id": "root", "docs": [], "fileRefs": [], "folders": []}]}


def event(name, *args):
    return "5:::" + json.dumps({"name": name, "args": list(args)})


def framed(*packets):
    return "".join(f"�{len(p)}�{p}" for p in packets)


@pytest.fixture
def rsps(monkeypatch):
    monkeypatch.setattr(olclient, "RATE_LIMIT_WAITS", ())
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        yield mock


def handshake(rsps, transports="websocket,xhr-polling"):
    rsps.add(responses.GET, HANDSHAKE, body=f"sid123:60:60:{transports}")


def polls(rsps, *bodies):
    for body in bodies:
        rsps.add(responses.GET, POLL, body=body)


def test_joins_the_project_and_returns_its_tree(rsps):
    handshake(rsps)
    polls(rsps, "1::", event("joinProjectResponse", {"publicId": "x", "project": PROJECT}), "")
    infos = OverleafClient({"overleaf.sid": "s"}, "csrf", base_url=BASE).get_project_infos("p1")
    assert infos == PROJECT
    first = rsps.calls[0].request
    assert "projectId=p1" in first.url
    assert first.headers["Cookie"] == "overleaf.sid=s"


def test_framed_payloads_with_several_packets(rsps):
    handshake(rsps)
    polls(rsps, framed("1::", event("joinProjectResponse", {"project": PROJECT})), "")
    assert OverleafClient({}, "c", base_url=BASE).get_project_infos("p1") == PROJECT


def test_heartbeats_are_answered(rsps):
    handshake(rsps)
    polls(rsps, "1::", "2::", event("joinProjectResponse", {"project": PROJECT}), "")
    rsps.add(responses.POST, POLL, body="1")
    assert OverleafClient({}, "c", base_url=BASE).get_project_infos("p1") == PROJECT
    heartbeats = [c for c in rsps.calls if c.request.method == "POST"]
    assert [c.request.body for c in heartbeats] == ["2::"]


def test_disconnects_when_done(rsps):
    handshake(rsps)
    polls(rsps, "1::", event("joinProjectResponse", {"project": PROJECT}), "")
    OverleafClient({}, "c", base_url=BASE).get_project_infos("p1")
    assert "disconnect" in rsps.calls[-1].request.url


def test_cookies_set_by_the_handshake_are_sent_with_the_polls(rsps):
    # overleaf.com's load balancer sets a fresh GCLB affinity cookie on the handshake; the polls need it
    rsps.add(responses.GET, HANDSHAKE, body="sid123:60:60:xhr-polling", headers={"Set-Cookie": "GCLB=affinity; Path=/"})
    polls(rsps, "1::", event("joinProjectResponse", {"project": PROJECT}), "")
    OverleafClient({"overleaf_session2": "s"}, "c", base_url=BASE).get_project_infos("p1")
    assert "GCLB=affinity" in rsps.calls[1].request.headers["Cookie"]


def test_rejected_connection_raises(rsps):
    handshake(rsps)
    polls(rsps, "1::", event("connectionRejected", {"message": "not authorized"}), "")
    with pytest.raises(realtime.RealtimeError, match="not authorized"):
        OverleafClient({}, "c", base_url=BASE).get_project_infos("p1")


def test_error_packet_raises(rsps):
    handshake(rsps)
    polls(rsps, "7:::1+0")
    with pytest.raises(realtime.RealtimeError):
        OverleafClient({}, "c", base_url=BASE).get_project_infos("p1")


def test_server_without_xhr_polling_raises(rsps):
    handshake(rsps, transports="websocket")
    with pytest.raises(realtime.RealtimeError, match="xhr-polling"):
        OverleafClient({}, "c", base_url=BASE).get_project_infos("p1")


def test_unreachable_service_fails_fast_instead_of_hanging(rsps):
    handshake(rsps)
    rsps.add(responses.GET, POLL, body=requests.ConnectionError("connection refused"))
    outcome = {}

    def call():
        try:
            OverleafClient({}, "c", base_url=BASE).get_project_infos("p1")
        except Exception as e:  # noqa: BLE001 - the exception type is checked below
            outcome["error"] = e

    thread = threading.Thread(target=call, daemon=True)
    thread.start()
    thread.join(timeout=15)
    assert not thread.is_alive(), "get_project_infos hangs instead of failing"
    assert isinstance(outcome.get("error"), requests.ConnectionError)


def test_gives_up_when_the_project_never_arrives(rsps, monkeypatch):
    monkeypatch.setattr(realtime, "JOIN_TIMEOUT", 0.2)
    handshake(rsps)
    for _ in range(50):
        polls(rsps, "8::")  # noop
    with pytest.raises(realtime.RealtimeError, match="did not send"):
        OverleafClient({}, "c", base_url=BASE).get_project_infos("p1")
