from __future__ import annotations

import json
import os
import socket
import time
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class AgentConfig:
    api_url: str
    token: str
    device_id: str
    poll_seconds: float
    printer_host: str
    printer_port: int

    @classmethod
    def from_env(cls) -> "AgentConfig":
        api_url = os.getenv("MZ_AGENT_API_URL", "http://localhost:8000").rstrip("/")
        token = os.getenv("MZ_AGENT_TOKEN", "").strip()
        device_id = os.getenv("MZ_AGENT_DEVICE_ID", socket.gethostname()).strip()
        poll_seconds = max(float(os.getenv("MZ_AGENT_POLL_SECONDS", "2")), 1.0)
        printer_host = os.getenv("MZ_PRINTER_HOST", "127.0.0.1")
        printer_port = int(os.getenv("MZ_PRINTER_PORT", "9100"))
        if not token:
            raise RuntimeError("MZ_AGENT_TOKEN es obligatorio; enrole el dispositivo desde administración")
        if not device_id:
            raise RuntimeError("MZ_AGENT_DEVICE_ID es obligatorio")
        return cls(api_url, token, device_id, poll_seconds, printer_host, printer_port)


class PrinterBackend:
    def print_bytes(self, payload: bytes) -> None:
        raise NotImplementedError

    def open_drawer(self) -> None:
        raise NotImplementedError


class TcpEscPosBackend(PrinterBackend):
    def __init__(self, host: str, port: int = 9100) -> None:
        self.host = host
        self.port = port

    def _send(self, payload: bytes) -> None:
        with socket.create_connection((self.host, self.port), timeout=5) as sock:
            sock.sendall(payload)

    def print_bytes(self, payload: bytes) -> None:
        self._send(b"\x1b\x40" + payload + b"\n\n\n\x1d\x56\x00")

    def open_drawer(self) -> None:
        self._send(b"\x1b\x70\x00\x3c\xff")


class HardwareAgent:
    def __init__(self, config: AgentConfig, printer: PrinterBackend) -> None:
        self.config = config
        self.printer = printer
        self.client = httpx.Client(
            base_url=config.api_url,
            headers={
                "X-Device-ID": config.device_id,
                "X-Device-Token": config.token,
            },
            timeout=15,
        )

    def claim(self) -> dict | None:
        response = self.client.post("/device/print-jobs/claim")
        response.raise_for_status()
        return response.json()

    def complete(self, job_id: str, success: bool, error: str | None = None) -> None:
        response = self.client.post(
            f"/device/print-jobs/{job_id}/complete",
            params={"success": str(success).lower(), "error": error},
        )
        response.raise_for_status()

    def execute(self, job: dict) -> None:
        job_type = job["job_type"]
        payload = job.get("payload", "")
        if job_type == "drawer":
            self.printer.open_drawer()
            return
        if job_type in {"receipt", "label"}:
            try:
                decoded = json.loads(payload)
                text = decoded.get("text", payload) if isinstance(decoded, dict) else payload
            except json.JSONDecodeError:
                text = payload
            self.printer.print_bytes(str(text).encode("cp850", errors="replace"))
            return
        raise RuntimeError(f"Tipo de trabajo no permitido: {job_type}")

    def run_forever(self) -> None:
        while True:
            try:
                job = self.claim()
                if not job:
                    time.sleep(self.config.poll_seconds)
                    continue
                try:
                    self.execute(job)
                except Exception as exc:
                    self.complete(job["id"], False, str(exc)[:500])
                else:
                    self.complete(job["id"], True)
            except (httpx.HTTPError, OSError) as exc:
                print(f"[agent] conexión/hardware: {exc}", flush=True)
                time.sleep(max(self.config.poll_seconds, 3))


def main() -> None:
    config = AgentConfig.from_env()
    backend = TcpEscPosBackend(config.printer_host, config.printer_port)
    print(
        f"Mily Zebra Agent {config.device_id} | printer={config.printer_host}:{config.printer_port}",
        flush=True,
    )
    HardwareAgent(config, backend).run_forever()


if __name__ == "__main__":
    main()
