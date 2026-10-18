"""New batch adapter: reuse the canonical lifecycle matrix without rewriting old evidence."""
import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

BATCH = Path(__file__).resolve().parent
ROOT = BATCH.parents[2]
spec = importlib.util.spec_from_file_location("canonical_lifecycle", BATCH.parent / "lifecycle_regression.py")
canonical = importlib.util.module_from_spec(spec)
spec.loader.exec_module(canonical)
canonical.FROZEN = BATCH / "dist/app/app.exe"


class HeaderSuite(canonical.Suite):
    def curl(self, item, path, status, name, auth=False):
        identity = item["handshake"]
        body = self.output / f"{name}.json"
        headers = self.output / f"{name}.headers.txt"
        args = ["curl.exe", "--silent", "--show-error", "--noproxy", "*", "--max-time", "20",
                "-D", str(headers), "-o", str(body), "-w", "%{http_code}"]
        if auth:
            args += ["-H", "Authorization: Bearer " + identity["token"]]
        args.append(f"http://127.0.0.1:{identity['port']}{path}")
        result = subprocess.run(args, capture_output=True, timeout=25)
        assert result.returncode == 0 and int(result.stdout) == status
        raw = headers.read_text(encoding="utf-8")
        assert identity["token"] not in raw
        pairs = dict(line.split(":", 1) for line in raw.splitlines() if ":" in line)
        pairs = {key.lower(): value.strip() for key, value in pairs.items()}
        if auth and path.split("?", 1)[0] == "/smoke":
            assert pairs["x-spectrumagent-boot-id"] == identity["boot_id"]
            assert pairs["x-spectrumagent-pid"] == str(identity["pid"])
        else:
            assert "x-spectrumagent-boot-id" not in pairs and "x-spectrumagent-pid" not in pairs
        payload = json.loads(body.read_bytes())
        if status == 200 and path.startswith("/smoke"):
            assert set(payload) == {"nan_ratio", "reflectance_range", "bands", "shape", "elapsed_ms"}
        self.emit(event="curl_response", path=path, http_status=status, headers=pairs, body=payload)
        if name == "smoke-blocks":
            self.curl(item, "/smoke?blocks=0", 422, "smoke-invalid", True)
            self.curl(item, "/smokeX", 404, "smoke-prefix-excluded", True)

    def stop(self, item, kind, **kwargs):
        residue = super().stop(item, kind, **kwargs)
        if kind == "taskkill" and not (self.output / "handshake-after-kill.json").exists():
            canonical.dump(self.output / "handshake-after-kill.json", canonical.redacted(residue))
            assert residue is not None, "Strong-kill residue expected before any hygiene"
        return residue


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rounds", type=int, default=5)
    args = parser.parse_args()
    if args.rounds < 5:
        parser.error("At least five rounds per mode and signal")
    sys.exit(HeaderSuite(args.output, args.rounds).run())
