#!/usr/bin/env python3
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safari_records(folder, process, launches, candidate, module, target,
                   source_path, source_sha256, worker_sha256, bootstrap_sha256,
                   observer_sha256):
    folder = Path(folder)
    raw = folder / "safari-worker-events.jsonl"
    redirect = folder / "safari-redirect.html"
    if not raw.is_file() or not redirect.is_file() or len(launches) != 1:
        raise ValueError("Safari worker events, redirect, or selected launch are absent")
    match = re.search(r'location\.replace\(("[^"\n]+")\)', redirect.read_text())
    if not match:
        raise ValueError("Safari observer redirect differs")
    bootstrap_url = json.loads(match[1])
    bootstrap_address = urlsplit(bootstrap_url)
    params = parse_qs(bootstrap_address.query)
    port = process["karma_port"]
    token = process["browser_token"]
    if (bootstrap_address.scheme != "http" or bootstrap_address.hostname != "localhost"
            or bootstrap_address.port != port
            or bootstrap_address.path != "/__dyn4k_bootstrap"
            or params.get("token") != [token] or len(params.get("target", [])) != 1):
        raise ValueError("Safari observer bootstrap origin or token differs")
    target_url = params["target"][0]
    address = urlsplit(target_url)
    if (address.scheme != "http" or address.hostname != "localhost"
            or address.port != port):
        raise ValueError("Safari observed Karma target differs")
    try:
        events = [json.loads(line) for line in raw.read_text().splitlines()]
    except ValueError:
        raise ValueError("Safari worker event stream is malformed") from None
    if (len(events) < 3 or events[0].get("kind") != "control"
            or events[1].get("kind") != "navigation"
            or any(item.get("kind") not in {"navigation", "response"}
                   for item in events[1:])):
        raise ValueError("Safari worker control, navigation, or responses are absent")
    control, navigation = events[:2]
    if (set(control) != {"kind", "token", "target", "client_id",
                         "bootstrap_url", "observed_ns"}
            or control["token"] != token or control["target"] != target_url
            or control["bootstrap_url"] != bootstrap_url
            or not isinstance(control["client_id"], str) or not control["client_id"]):
        raise ValueError("Safari worker first-load control differs")
    event_keys = {"token", "kind", "request_id", "url", "client_id",
                  "fetch_client_id", "client_id_source", "eligible_count",
                  "client_url", "resulting_client_id", "status", "request_ns",
                  "response_ns", "finished_ns", "body_path", "body_size",
                  "body_sha256", "observed_ns"}
    page_client_id = navigation.get("resulting_client_id")
    if (set(navigation) != event_keys or navigation["token"] != token
            or navigation["url"] != target_url
            or navigation["client_id"] != control["client_id"]
            or navigation["client_url"] != bootstrap_url
            or not isinstance(page_client_id, str) or not page_client_id
            or navigation["body_path"] is not None
            or navigation["body_size"] != 0
            or navigation["body_sha256"] != digest(b"")):
        raise ValueError("Safari worker controlled navigation differs")
    previous_observed = control["observed_ns"]
    ids = set()
    clients = {control["client_id"]: bootstrap_url}
    navigations = []
    responses = []
    for item in events[1:]:
        if (set(item) != event_keys or item["token"] != token
                or not isinstance(item["request_id"], str)
                or not item["request_id"] or item["request_id"] in ids
                or not ((item["client_id_source"] == "fetch-event"
                         and item["fetch_client_id"] == item["client_id"]
                         and item["eligible_count"] == 0)
                        or (item["client_id_source"] == "single-controlled-client"
                            and item["kind"] == "navigation"
                            and item["fetch_client_id"] == ""
                            and item["eligible_count"] == 1))
                or item["status"] != 200
                or any(type(item[key]) is not int for key in
                       ("request_ns", "response_ns", "finished_ns", "observed_ns"))
                or not process["started_ns"] <= item["request_ns"] <= item["response_ns"]
                <= item["finished_ns"] <= item["observed_ns"]
                <= process["finished_ns"]
                or item["observed_ns"] < previous_observed):
            raise ValueError("Safari worker request identity or timing differs")
        ids.add(item["request_id"])
        previous_observed = item["observed_ns"]
        if item["client_id"] not in clients or item["client_url"] != clients[item["client_id"]]:
            raise ValueError("Safari worker request client lineage differs")
        if item["kind"] == "navigation":
            next_client = item["resulting_client_id"]
            next_url = urlsplit(item["url"])
            if (not isinstance(next_client, str) or not next_client
                    or next_client in clients or item["body_path"] is not None
                    or item["body_size"] != 0 or item["body_sha256"] != digest(b"")
                    or next_url.scheme != "http" or next_url.hostname != "localhost"
                    or next_url.port != port):
                raise ValueError("Safari worker navigation chain differs")
            clients[next_client] = item["url"]
            navigations.append({"request_id": item["request_id"],
                                "from_client_id": item["client_id"],
                                "to_client_id": next_client, "url": item["url"]})
        else:
            responses.append(item)
    if not responses:
        raise ValueError("Safari worker selected responses are absent")
    if not process["started_ns"] <= control["observed_ns"] <= navigation["observed_ns"]:
        raise ValueError("Safari worker first-load timing differs")
    sealed = []
    for index, item in enumerate(responses):
        body_path = f"safari-browser-bodies/{index:04d}.body"
        body = folder / body_path
        address = urlsplit(item["url"])
        if (item["resulting_client_id"] != ""
                or address.scheme != "http" or address.hostname != "localhost"
                or address.port != port or item["body_path"] != body_path
                or not body.is_file() or body.is_symlink()
                or body.stat().st_size != item["body_size"]
                or digest(body.read_bytes()) != item["body_sha256"]):
            raise ValueError("Safari worker selected response body or client differs")
        sealed.append({"kind": "response", "ordinal": index,
                       "request_id": item["request_id"],
                       "browser_pid": launches[0]["pid"], "url": item["url"],
                       "method": "GET", "status": item["status"],
                       "source": "service-worker-clone",
                       "request_ns": item["request_ns"],
                       "response_ns": item["response_ns"],
                       "finished_ns": item["observed_ns"],
                       "body_path": body_path, "body_size": item["body_size"],
                       "body_sha256": item["body_sha256"]})
    session = {"kind": "session", "protocol": 2, "candidate_sha": candidate,
               "module": module, "target": target,
               "browser_pid": launches[0]["pid"], "source_path": source_path,
               "source_sha256": source_sha256, "worker_sha256": worker_sha256,
               "bootstrap_sha256": bootstrap_sha256,
               "observer_sha256": observer_sha256,
               "control_client_id": control["client_id"],
               "page_client_id": page_client_id, "target_url": target_url,
               "navigations": navigations,
               "browser_token": token, "redirect_sha256": digest(redirect.read_bytes()),
               "started_ns": control["observed_ns"],
               "finished_ns": max(item["observed_ns"] for item in responses)}
    return [session, *sealed]


def seal(folder, *args):
    records = safari_records(folder, *args)
    path = Path(folder) / "safari-browser-responses.jsonl"
    with path.open("x") as stream:
        for row in records:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    return records
