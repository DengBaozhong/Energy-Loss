"""Local WebUI for OPV E1/E2/E3 energy-loss analysis."""

from __future__ import annotations

import argparse
import json
import os
import socket
import tempfile
from argparse import Namespace
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import numpy as np

from energy_loss.core import calculate


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_ROOT = PROJECT_ROOT / "frontend"
NORMALS_ROOT = PROJECT_ROOT / "normals"


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(val) for val in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def write_uploaded_file(tmpdir: Path, name: str, content: str | None, required: bool) -> Path | None:
    if not content:
        if required:
            raise ValueError(f"{name} file is required.")
        return None
    path = tmpdir / name
    path.write_text(content, encoding="utf-8-sig")
    return path


def run_calculation(payload: dict[str, Any]) -> dict[str, Any]:
    files = payload.get("files", {})
    params = payload.get("params", {})

    with tempfile.TemporaryDirectory(prefix="energy_loss_webui_") as tmp:
        tmpdir = Path(tmp)
        eqe_path = write_uploaded_file(tmpdir, "EQE.csv", files.get("eqe"), required=True)
        seqe_path = write_uploaded_file(tmpdir, "FTPS_EQE.csv", files.get("seqe"), required=False)
        eqe_el_path = write_uploaded_file(tmpdir, "EQE_EL.csv", files.get("eqeEl"), required=True)

        eqe_range_nm = as_float(params.get("eqeRangeNm"))

        args = Namespace(
            eqe=eqe_path,
            seqe=seqe_path if seqe_path is not None else tmpdir / "missing_sEQE.csv",
            eqe_el=eqe_el_path,
            no_seqe=seqe_path is None,
            solar=NORMALS_ROOT / "solar_irradiation.txt",
            sqlimit=NORMALS_ROOT / "SQlimit.txt",
            eg=None,
            el_current=as_float(params.get("elCurrent")),
            temperature=as_float(params.get("temperature")) or 300.0,
            smooth_window=9,
            seqe_switch_nm=None,
            seqe_switch_fraction=0.05,
            seqe_scale=None,
            seqe_max_nm=eqe_range_nm,
            seqe_floor=None,
        )
        results = calculate(args)

    voc = as_float(params.get("voc"))
    if voc is not None:
        results["Voc_input_V"] = voc
        results["Eg_minus_Voc_eV"] = results["Eg_eV"] - voc
        results["VocSQ_minus_Voc_eV"] = results["Voc_SQ_V"] - voc
        results["E2_plus_E3_eV"] = results["E2_eV"] + results["E3_eV"]
        results["VocSQVoc_minus_E2E3_eV"] = results["VocSQ_minus_Voc_eV"] - results["E2_plus_E3_eV"]

    return json_safe(results)


class EnergyLossHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        clean = unquote(path.split("?", 1)[0].split("#", 1)[0])
        if clean in ("", "/"):
            return str(FRONTEND_ROOT / "index.html")
        frontend_root = FRONTEND_ROOT.resolve()
        requested = (frontend_root / clean.lstrip("/")).resolve()
        try:
            requested.relative_to(frontend_root)
        except ValueError:
            return str(frontend_root / "index.html")
        return str(requested)

    def do_POST(self) -> None:
        if self.path != "/api/calculate":
            self.send_error(404, "Not found")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            results = run_calculation(payload)
            body = json.dumps({"ok": True, "results": results}).encode("utf-8")
            self.send_response(200)
        except Exception as exc:
            body = json.dumps({"ok": False, "error": str(exc)}).encode("utf-8")
            self.send_response(400)

        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local Energy Loss WebUI.")
    parser.add_argument("--host", default="127.0.0.1", help="Host address to bind.")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")), help="Preferred port.")
    return parser


def find_available_port(host: str, preferred_port: int) -> int:
    for port in range(preferred_port, preferred_port + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((host, port))
            except OSError:
                continue
            return port
    raise OSError(f"Cannot find an available port starting from {preferred_port}.")


def main() -> None:
    args = build_parser().parse_args()
    host = args.host
    port = args.port if "PORT" in os.environ else find_available_port(host, args.port)
    server = ThreadingHTTPServer((host, port), EnergyLossHandler)
    print(f"Energy Loss WebUI running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
