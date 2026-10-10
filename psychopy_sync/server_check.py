"""Bounded readiness checks; no PsychoPy, EyeLink or GPU packages required."""

from dataclasses import dataclass
from http.client import HTTPException
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import urlopen

from shared.contracts import TTS_PROTOCOL_VERSION, TTS_SERVICE


@dataclass(frozen=True)
class ServerCheck:
    status: str
    message: str
    can_start: bool


def check_gpu_server(url, allow_demo=False, timeout=3.0):
    if not url:
        return ServerCheck("not_configured", "GPU server not configured. Audio requests will be saved without WAVs.", True)
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.query or parsed.fragment:
            raise ValueError("Use an HTTP server origin, for example http://192.168.1.20:8765")
        # Access the port property to reject malformed port numbers.
        _ = parsed.port
        try:
            response = urlopen(url.rstrip("/") + "/ready", timeout=timeout)
        except HTTPError as exc:
            if exc.code != 503:
                exc.close()
                return ServerCheck("incompatible", "GPU readiness endpoint unavailable. Update and restart the GPU server.", False)
            response = exc
        with response:
            body = response.read(65537)
            if len(body) > 65536:
                raise ValueError("GPU readiness response is too large")
            data = json.loads(body)
            http_status = response.code
        if (not isinstance(data, dict) or data.get("service") != TTS_SERVICE
                or data.get("protocol_version") != TTS_PROTOCOL_VERSION):
            return ServerCheck("incompatible", "This address does not identify a compatible experiment TTS server.", False)
        if data.get("status") == "starting":
            return ServerCheck("starting", "GPU server is loading the model and testing audio generation...", False)
        if data.get("status") == "failed":
            error = str(data.get("error") or "See the GPU server console.")
            return ServerCheck("failed", "GPU startup test failed: " + error[:240], False)
        if (http_status != 200 or data.get("status") != "ready" or data.get("ready") is not True
                or data.get("warmup_verified") is not True):
            return ServerCheck("not_ready", "GPU server has not passed its startup audio test.", False)
        if data.get("mode") == "demo":
            return ServerCheck("demo", "Demo server ready: silent test audio only." if allow_demo else
                               "Demo server detected. Start the real F5-TTS server for EyeLink experiments.", allow_demo)
        if data.get("mode") != "f5-tts":
            return ServerCheck("incompatible", "GPU server reported an unknown audio generation mode.", False)
        return ServerCheck("ready", "GPU server ready. Startup audio test passed.", True)
    except (URLError, OSError, TimeoutError, HTTPException) as exc:
        return ServerCheck("unavailable", "Cannot reach GPU server. Check its address, server console and port. " + str(exc), False)
    except (ValueError, TypeError, UnicodeDecodeError) as exc:
        return ServerCheck("invalid", "Invalid GPU address or readiness response: " + str(exc), False)
