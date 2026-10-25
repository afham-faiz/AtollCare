"""Hand the packet to the crew app's engine (the teammate's FastAPI service, ENGINE_URL in inputs/.env).

The order of calls follows what their API requires:
1. create the transfer: this starts their journey clock, so it only happens on an explicit send;
2. set monitoring to `presage` (or `off` if there are no readings), otherwise their engine invents simulated vitals;
3. post each Presage reading with its own confidence;
4. post the notes.
The transfer is left in `preparing`: the crew review it on their own screen and send the handoff themselves.

Nothing here raises. A failure comes back as a step with a plain reason, so the page can show it.
"""
import httpx

from src import config
from src.models.schemas import HandshakeResult, HandshakeStep, PreArrivalPacket

_transport: httpx.BaseTransport | None = None  # tests put a fake engine here


def _client() -> httpx.Client:
    return httpx.Client(base_url=config.ENGINE_URL, timeout=config.ENGINE_TIMEOUT_S, transport=_transport)


def _unreachable(exc: Exception) -> str:
    return (f"Could not reach the crew engine at {config.ENGINE_URL} ({exc.__class__.__name__}). "
            "Is it running? The address is ENGINE_URL in inputs/.env.")


def _problem(response: httpx.Response) -> str:
    """The reason the engine gave, in plain words."""
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}: {response.text[:200]}"
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        return f"HTTP {response.status_code}: {body['error'].get('message', body['error'])}"
    if isinstance(body, dict) and "detail" in body:
        return f"HTTP {response.status_code}: {str(body['detail'])[:300]}"
    return f"HTTP {response.status_code}"


def get_options() -> dict:
    """Facilities and transport modes the crew app offers, for the From, To and Mode pickers."""
    try:
        with _client() as client:
            response = client.get("/api/meta")
    except httpx.HTTPError as exc:
        return {"error": _unreachable(exc)}
    if response.status_code >= 400:
        return {"error": f"The crew engine refused the request. {_problem(response)}"}
    region = response.json().get("region", {})
    return {
        "region": {"id": region.get("id"), "name": region.get("name")},
        "facilities": [{"id": f["id"], "name": f.get("short_name") or f["name"], "kind": f.get("kind")}
                       for f in region.get("facilities", [])],
        "modes": region.get("modes", []),
    }


def _call(client: httpx.Client, steps: list[HandshakeStep], step: str, path: str, body: dict) -> dict | None:
    try:
        response = client.post(path, json=body)
    except httpx.HTTPError as exc:
        steps.append(HandshakeStep(step=step, ok=False, detail=_unreachable(exc)))
        return None
    if response.status_code >= 400:
        steps.append(HandshakeStep(step=step, ok=False, detail=_problem(response)))
        return None
    steps.append(HandshakeStep(step=step, ok=True))
    return response.json()


def send_packet(packet: PreArrivalPacket, origin_id: str, destination_id: str, mode: str) -> HandshakeResult:
    """Create the transfer and fill it in. Never raises."""
    steps: list[HandshakeStep] = []
    with _client() as client:
        created = _call(client, steps, "Create the transfer", "/api/transfers", {
            "patient": {"label": packet.patient_label, "age": packet.age, "sex": packet.sex},
            "complaint": packet.complaint,
            "origin_id": origin_id, "destination_id": destination_id, "mode": mode,
        })
        if created is None:
            return HandshakeResult(ok=False, steps=steps, error=steps[-1].detail)
        tid = created["id"]

        _call(client, steps, "Set monitoring to Presage" if packet.vitals else "Switch simulated vitals off",
              f"/api/transfers/{tid}/monitoring", {"source": "presage" if packet.vitals else "off"})

        for vital in packet.vitals:
            body = {"source": vital.source, "confidence": vital.confidence}
            if vital.hint:
                body["hint"] = vital.hint
            if vital.heart_rate is not None:
                body["heart_rate"] = vital.heart_rate
                label = f"Send heart rate {vital.heart_rate:g}"
            else:
                body["resp_rate"] = vital.resp_rate
                label = f"Send breathing rate {vital.resp_rate:g}"
            _call(client, steps, label, f"/api/transfers/{tid}/vitals", body)

        if packet.consciousness:
            _call(client, steps, "Send consciousness (visual impression)", f"/api/transfers/{tid}/vitals", {
                "source": "manual", "consciousness": packet.consciousness,
                "hint": "Visual impression from video (AI), not entered by the crew"})

        for note in packet.notes:
            _call(client, steps, f"Send note: {note.title}", f"/api/transfers/{tid}/notes",
                  {"text": note.text, "kind": "text"})

    return HandshakeResult(ok=True, transfer_id=tid, code=created.get("code"),
                           link=f"{config.ENGINE_WEB_URL}/crew/{tid}", steps=steps)
