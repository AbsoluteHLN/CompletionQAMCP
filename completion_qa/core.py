from __future__ import annotations
import copy
import hashlib
import json
import os
import platform
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .editorial import diagnose
from .manifest import repository_manifest
from .reporting import build_report

CHECKS = {"code", "text", "browser", "native", "model"}

def now():
    return datetime.now(timezone.utc).isoformat()

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

class Engine:
    def __init__(self, root: Path):
        self.root = root.resolve(strict=True)
        self.plans = {}
        self.lock = threading.RLock()

    def safe_path(self, name):
        p = Path(name)
        if p.is_absolute() or ".." in p.parts:
            raise ValueError("Absolute paths and traversal are forbidden")
        resolved = (self.root / p).resolve(strict=True)
        if not resolved.is_relative_to(self.root) or not resolved.is_file():
            raise ValueError("Artifact must be a file inside the configured root")
        if resolved.stat().st_size > 1_000_000:
            raise ValueError("Artifact exceeds 1 MB limit")
        return resolved

    def snapshot(self, files):
        return {name: hashlib.sha256(self.safe_path(name).read_bytes()).hexdigest() for name in files}

    def capabilities(self):
        return {"transport": "stdio", "code": {"configured": True, "command_ids": ["parse_sources"], "scope": "Python AST and JSON syntax only; no target execution"},
                "text": {"configured": True, "scope": "Local heuristics; review-only patches"},
                "browser": {"configured": False}, "native": {"configured": False}, "model": {"configured": False},
                "network": "No network or credential implementation", "host_hook": "Not installed"}

    def plan(self, artifacts, required, profile="short_reply", scope="artifacts"):
        if scope not in {"artifacts", "repository"}:
            raise ValueError("Unknown scope")
        artifacts, required = list(artifacts), list(required)
        if not artifacts or len(artifacts) > 50 or len(set(artifacts)) != len(artifacts):
            raise ValueError("Provide 1–50 unique artifacts")
        if not required or set(required) - CHECKS or len(set(required)) != len(required):
            raise ValueError("Provide unique supported required checks")
        diagnose("", profile)
        snapshot = self.snapshot(artifacts)
        manifest = repository_manifest(self.root) if scope == "repository" else None
        identifier = uuid.uuid4().hex
        with self.lock:
            self.plans[identifier] = {"id": identifier, "artifacts": artifacts, "required": required,
                "profile": profile, "snapshot": snapshot, "scope": scope, "manifest": manifest, "created_at": now(), "evidence": {}, "gate_cache": {}}
        return copy.deepcopy({"plan_id": identifier, "artifact_hashes": snapshot, "required": required,
                "scope": scope, "repository_manifest": manifest,
                "checks": {check: "not_run" for check in required}})

    def run(self, plan_id, check, command_id="parse_sources"):
        with self.lock:
            p = self.plans[plan_id]
            if check not in p["required"]:
                raise ValueError("Check is outside this plan")
            if command_id != "parse_sources":
                raise ValueError("Command is not approved")
            started = now()
            try:
                before = self.snapshot(p["artifacts"])
                manifest_before = repository_manifest(self.root) if p["scope"] == "repository" else None
            except (OSError, ValueError):
                entry = {"id": uuid.uuid4().hex, "status": "blocked", "artifact_hashes": {}, "reason": "Review scope unavailable"}
                p["evidence"][check] = entry
                return copy.deepcopy(entry)
            entry = {"id": uuid.uuid4().hex, "plan_id": plan_id, "check": check,
                     "artifact_hashes": before, "started_at": started, "environment": {"os": platform.system(), "python": platform.python_version(), "root": str(self.root)},
                     "command": None, "exit_code": None, "source": "local_execution", "status": "blocked"}
            start = time.monotonic()
            if before != p["snapshot"] or manifest_before != p["manifest"]:
                entry["reason"] = "Plan stale: create a new plan after source changes"
            elif check in {"browser", "native", "model"}:
                entry["reason"] = "Adapter not configured; no verification performed"
                entry["source"] = "capability_declaration"
            elif check == "code":
                files = [self.safe_path(n) for n in p["artifacts"]]
                if any(f.suffix not in {".py", ".json"} for f in files):
                    entry["reason"] = "parse_sources supports .py and .json only"
                else:
                    command = [sys.executable, "-I", str(Path(__file__).with_name("checker.py")), *map(str, files)]
                    entry["command"] = command
                    entry["checker_sha256"] = hashlib.sha256(Path(__file__).with_name("checker.py").read_bytes()).hexdigest()
                    try:
                        result = subprocess.run(command, cwd=self.root, env={"PATH": os.defpath, "LANG": "C.UTF-8"}, capture_output=True, text=True, timeout=10, shell=False)
                        entry.update(status="pass" if result.returncode == 0 else "fail", exit_code=result.returncode,
                                     stdout=result.stdout[:20000], stderr=result.stderr[:20000], scope="Syntax only; no tests, imports, runtime, or security review")
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        entry.update(reason=type(exc).__name__)
            elif check == "text":
                entry.update(status="pass", results={n: diagnose(self.safe_path(n).read_text(), p["profile"]) for n in p["artifacts"]}, scope="Heuristic execution; not semantic approval")
            try:
                after = self.snapshot(p["artifacts"])
                manifest_after = repository_manifest(self.root) if p["scope"] == "repository" else None
            except (OSError, ValueError):
                after, manifest_after = None, None
            entry["repository_manifest_digest"] = digest(manifest_before)
            if before != after or manifest_before != manifest_after:
                entry.update(status="blocked", reason="Artifacts changed during review")
            entry.update(finished_at=now(), duration_seconds=round(time.monotonic()-start, 6))
            p["evidence"][check] = entry
            return copy.deepcopy(entry)

    def gate(self, plan_id, origin="host"):
        with self.lock:
            p = self.plans[plan_id]
            if origin != "host":
                return {"allow_completion": False, "status": "blocked", "reason": "Recursive or untrusted gate origin"}
            try:
                current = self.snapshot(p["artifacts"])
                manifest = repository_manifest(self.root) if p["scope"] == "repository" else None
            except (OSError, ValueError):
                return {"allow_completion": False, "status": "blocked", "reason": "Artifacts unavailable"}
            key = digest([current, manifest, p["evidence"]])
            if key in p["gate_cache"]:
                return copy.deepcopy(p["gate_cache"][key])
            statuses = {c: p["evidence"].get(c, {}).get("status", "not_run") for c in p["required"]}
            stale = manifest != p["manifest"] or current != p["snapshot"] or any(e["artifact_hashes"] != current for e in p["evidence"].values())
            allow = not stale and all(s == "pass" for s in statuses.values())
            result = {"decision_id": uuid.uuid4().hex, "allow_completion": allow, "status": "pass" if allow else "blocked",
                      "checks": statuses, "stale": stale, "evidence_refs": [e["id"] for e in p["evidence"].values()],
                      "scope": "Only required checks in this plan; never whole-project readiness", "scope_mode": p["scope"], "coverage": "Only listed artifacts are checked; repository manifest binds other file contents, not their correctness"}
            p["gate_cache"][key] = result
            return copy.deepcopy(result)

    def report(self, plan_id):
        """Refresh the gate and derive a bounded summary; never accept external pass claims."""
        with self.lock:
            p = self.plans[plan_id]
            return build_report(p, self.gate(plan_id), now())
