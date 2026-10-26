"""Overleaf real-time client"""

##################################################
# MIT License
##################################################
# File: realtime.py
# Description: Fetches a project's file tree from Overleaf's real-time service (Socket.IO 0.9 over xhr-polling)
# Author: Moritz Glöckl
# License: MIT
##################################################

import json
import time

import requests

# How long to wait for the project after connecting, and for a single long-poll request
JOIN_TIMEOUT = 30
POLL_TIMEOUT = 60


class RealtimeError(Exception):
    """Overleaf's real-time service rejected the connection or did not send the project"""


def _now_ms():
    return int(time.time() * 1000)


def decode_payload(body):
    """
    Split an xhr-polling response into Socket.IO packets. Several packets are framed as
    "\\ufffd<length>\\ufffd<packet>\\ufffd<length>\\ufffd<packet>...", a single packet is sent as is.
    """
    if body.startswith("�"):
        return body.split("�")[2::2]
    return [body] if body else []


def join_project(session, base_url, project_id, request):
    """
    Join a project on Overleaf's real-time service and return its project details (incl. "rootFolder").

    Overleaf joins the project as part of the Socket.IO handshake (projectId query parameter) and then pushes a
    "joinProjectResponse" event. The session keeps all cookies, including the load balancer affinity cookie (GCLB)
    that overleaf.com sets on the handshake and needs for the following requests.

    Params:
    session: requests.Session with the login cookies
    base_url: the Overleaf server
    project_id: the id of the project
    request: function(method, url, session=..., **kwargs) -> response (OverleafClient's rate-limit aware request)

    Returns: the project dict
    """
    r = request(
        "GET", f"{base_url}/socket.io/1/", session=session, timeout=30, params={"t": _now_ms(), "projectId": project_id}
    )
    r.raise_for_status()
    sid, _heartbeat_timeout, _close_timeout, transports = r.text.split(":", 3)
    if "xhr-polling" not in transports.split(","):
        raise RealtimeError(f"Overleaf's real-time service does not offer xhr-polling (only: {transports})")

    poll_url = f"{base_url}/socket.io/1/xhr-polling/{sid}"
    try:
        deadline = time.monotonic() + JOIN_TIMEOUT
        while time.monotonic() < deadline:
            p = request("GET", poll_url, session=session, timeout=POLL_TIMEOUT, params={"t": _now_ms()})
            p.raise_for_status()
            for packet in decode_payload(p.text):
                # Packet format: type:id:endpoint:data
                fields = packet.split(":", 3)
                kind, data = fields[0], fields[3] if len(fields) > 3 else ""
                if kind == "2":  # heartbeat, answer it to keep the connection
                    request("POST", poll_url, session=session, timeout=30, data="2::")
                elif kind == "5":  # event
                    event = json.loads(data)
                    args = event.get("args") or []
                    if event.get("name") == "joinProjectResponse":
                        return args[0]["project"]
                    if event.get("name") == "connectionRejected":
                        reason = args[0].get("message") if args and isinstance(args[0], dict) else args
                        raise RealtimeError(f"Overleaf rejected the connection to the project: {reason}")
                elif kind == "7":  # error
                    raise RealtimeError(f"Overleaf's real-time service reported an error: {data or packet}")
                elif kind == "0":  # disconnect
                    raise RealtimeError("Overleaf's real-time service closed the connection")
        raise RealtimeError("Overleaf's real-time service did not send the project in time")
    finally:
        try:
            request("GET", poll_url, session=session, timeout=10, params={"t": _now_ms(), "disconnect": 1})
        except requests.RequestException:
            pass
