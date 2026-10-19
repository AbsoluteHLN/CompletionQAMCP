"""Versioned, secret-free profile configuration and fail-closed validation.

Host code supplies a trusted backend and authorization callback; neither is loaded
from configuration. Imported configuration contains intentions, never live proof.
Validation records are local observations, not tamper-resistant credentials.
"""
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import tempfile
import stat
import re
from typing import Callable, Optional
from uuid import uuid4

SCHEMA_VERSION = 1
EFFORTS = ("inherit", "low", "medium", "high", "xhigh", "max")
STAGES = ("schema", "capability", "discovery", "smoke", "recheck")


class ProfileError(ValueError):
    """Invalid configuration or unusable validation evidence."""


def _name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}", value):
        raise ProfileError("expected a bounded identifier, not secret material")
    return value


def _integer(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ProfileError("integer outside allowed range")
    return value


def _time(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ProfileError("timezone-aware timestamp required")
    return value.astimezone(timezone.utc)


def _fields(data, required):
    if type(data) is not dict or set(data) != set(required):
        raise ProfileError("missing or unknown configuration fields")


@dataclass(frozen=True)
class Route:
    route_id: str
    provider: str
    model: str
    effort: str
    auth_ref: str

    def __post_init__(self):
        for value in (self.route_id, self.provider, self.model, self.auth_ref):
            _name(value)
        if self.effort not in EFFORTS:
            raise ProfileError("unsupported effort")


@dataclass(frozen=True)
class Role:
    name: str
    route_id: str
    concurrency: int = 1
    timeout_seconds: int = 120
    fallbacks: tuple = ()

    def __post_init__(self):
        _name(self.name)
        _name(self.route_id)
        _integer(self.concurrency, 1, 256)
        _integer(self.timeout_seconds, 1, 86400)
        if type(self.fallbacks) is not tuple:
            raise ProfileError("fallbacks must be immutable")
        for route in self.fallbacks:
            _name(route)
        if len(set((self.route_id,) + self.fallbacks)) != 1 + len(self.fallbacks):
            raise ProfileError("repeated or cyclic fallback")


@dataclass(frozen=True)
class Profile:
    profile_id: str
    profile_revision: int
    name: str
    created_at: datetime
    modified_at: datetime
    routes: tuple
    roles: tuple
    allowlist: tuple
    default_role: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self):
        _name(self.profile_id)
        _name(self.name)
        _integer(self.profile_revision, 1, 2**63 - 1)
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise ProfileError("unsupported profile schema")
        if _time(self.modified_at) < _time(self.created_at):
            raise ProfileError("modified time precedes creation")
        if any(type(items) is not tuple for items in (self.routes, self.roles, self.allowlist)):
            raise ProfileError("configuration collections must be immutable")
        if not self.routes or not self.roles or len(self.routes) > 256 or len(self.roles) > 256:
            raise ProfileError("profile requires bounded routes and roles")
        if not all(isinstance(r, Route) for r in self.routes) or not all(isinstance(r, Role) for r in self.roles):
            raise ProfileError("invalid route or role")
        route_ids = {r.route_id for r in self.routes}
        if len(route_ids) != len(self.routes) or len({r.name for r in self.roles}) != len(self.roles):
            raise ProfileError("duplicate route or role")
        if len(set(self.allowlist)) != len(self.allowlist) or set(self.allowlist) != route_ids:
            raise ProfileError("every configured route must be explicitly allowlisted")
        for role in self.roles:
            if not set((role.route_id,) + role.fallbacks) <= route_ids:
                raise ProfileError("unknown route reference")
        if self.default_role not in {r.name for r in self.roles}:
            raise ProfileError("unknown default role")

    @classmethod
    def create(cls, name, routes, roles, allowlist, default_role, now=None):
        now = _time(now or datetime.now(timezone.utc))
        return cls(str(uuid4()), 1, name, now, now, tuple(routes), tuple(roles), tuple(allowlist), default_role)

    def revise(self, *, now=None, **changes):
        if not set(changes) <= {"name", "routes", "roles", "allowlist", "default_role"}:
            raise ProfileError("only configuration fields may be revised")
        candidate = replace(self, **changes)
        if candidate == self:
            return self
        now = max(_time(now or datetime.now(timezone.utc)), self.modified_at)
        return replace(candidate, profile_revision=self.profile_revision + 1, modified_at=now)

    def to_dict(self):
        return {"schema_version": self.schema_version, "profile_id": self.profile_id,
                "profile_revision": self.profile_revision, "name": self.name,
                "created_at": self.created_at.isoformat(), "modified_at": self.modified_at.isoformat(),
                "routes": [vars(r).copy() for r in self.routes],
                "roles": [{**vars(r), "fallbacks": list(r.fallbacks)} for r in self.roles],
                "allowlist": list(self.allowlist), "default_role": self.default_role}

    @classmethod
    def from_dict(cls, data):
        _fields(data, ("schema_version", "profile_id", "profile_revision", "name", "created_at", "modified_at", "routes", "roles", "allowlist", "default_role"))
        try:
            for key in ("routes", "roles", "allowlist"):
                if type(data[key]) is not list or len(data[key]) > 256:
                    raise ProfileError("bounded lists required")
            routes = []
            for item in data["routes"]:
                _fields(item, ("route_id", "provider", "model", "effort", "auth_ref"))
                routes.append(Route(**item))
            roles = []
            for item in data["roles"]:
                _fields(item, ("name", "route_id", "concurrency", "timeout_seconds", "fallbacks"))
                if type(item["fallbacks"]) is not list:
                    raise ProfileError("fallback list required")
                roles.append(Role(**{**item, "fallbacks": tuple(item["fallbacks"])}))
            return cls(**{**data, "routes": tuple(routes), "roles": tuple(roles),
                          "allowlist": tuple(data["allowlist"]),
                          "created_at": datetime.fromisoformat(data["created_at"]),
                          "modified_at": datetime.fromisoformat(data["modified_at"])})
        except (TypeError, ValueError, KeyError) as exc:
            raise ProfileError("invalid profile: " + str(exc)) from exc


def export_profiles(profiles):
    """Export only configuration. Validation must be performed again after import."""
    profiles = tuple(profiles)
    if len(profiles) > 256 or len({p.profile_id for p in profiles}) != len(profiles):
        raise ProfileError("duplicate or excessive profiles")
    return json.dumps({"schema_version": SCHEMA_VERSION, "profiles": [p.to_dict() for p in profiles]}, sort_keys=True)


def import_profiles(text):
    if not isinstance(text, str) or len(text.encode("utf-8")) > 1048576:
        raise ProfileError("profile document exceeds limit")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ProfileError("duplicate JSON field")
            result[key] = value
        return result
    try:
        data = json.loads(text, object_pairs_hook=unique)
        _fields(data, ("schema_version", "profiles"))
        if type(data["schema_version"]) is not int or data["schema_version"] != SCHEMA_VERSION or type(data["profiles"]) is not list or len(data["profiles"]) > 256:
            raise ProfileError("unsupported profile collection")
        profiles = tuple(Profile.from_dict(p) for p in data["profiles"])
        export_profiles(profiles)
        return profiles
    except (ValueError, TypeError) as exc:
        raise ProfileError(str(exc)) from exc


def load_profiles(path):
    """Read bounded configuration only; corrupt or missing files fail closed."""
    path = Path(path)
    if path.is_symlink():
        raise ProfileError("profile storage must not be a symbolic link")
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ProfileError("profile storage must be a regular file")
            data = stream.read(1048577)
        if len(data) > 1048576:
            raise ProfileError("profile document exceeds limit")
        return import_profiles(data.decode("utf-8"))
    except (OSError, UnicodeError) as exc:
        raise ProfileError("cannot read profile storage: " + type(exc).__name__) from exc


def save_profiles(path, profiles, *, expected_revisions):
    """Atomically replace configuration under an exclusive local writer lock.

    Pass None to create a previously absent file. For updates, pass the exact
    {profile_id: profile_revision} mapping previously read. Existing profiles
    must remain identical or advance exactly one revision. Lock conflicts and
    damaged files block rather than reset state. A leftover lock after a crash
    requires operator inspection. This is local coordination, not protection
    against a malicious process with the same filesystem privileges.
    """
    path = Path(path)
    profiles = tuple(profiles)
    payload = export_profiles(profiles).encode("utf-8")
    if len(payload) > 1048576:
        raise ProfileError("profile document exceeds limit")
    if expected_revisions is not None and (
        type(expected_revisions) is not dict or
        any(not isinstance(key, str) or type(value) is not int or value < 1
            for key, value in expected_revisions.items())
    ):
        raise ProfileError("expected revisions must be an exact revision mapping")
    lock_path = path.with_name(path.name + ".lock")
    lock_fd = None
    temporary = None
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        if path.is_symlink():
            raise ProfileError("profile storage must not be a symbolic link")
        if path.exists():
            current = load_profiles(path)
            observed = {p.profile_id: p.profile_revision for p in current}
            if expected_revisions is None or expected_revisions != observed:
                raise ProfileError("profile storage revision conflict")
            previous = {p.profile_id: p for p in current}
            for profile in profiles:
                old = previous.get(profile.profile_id)
                if old is None:
                    if profile.profile_revision != 1:
                        raise ProfileError("new stored profiles must begin at revision one")
                elif profile != old and (
                    profile.profile_revision != old.profile_revision + 1 or
                    profile.created_at != old.created_at or
                    profile.modified_at < old.modified_at
                ):
                    raise ProfileError("changed stored profile must advance one revision")
        elif expected_revisions is not None:
            raise ProfileError("profile storage disappeared or was never created")
        descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        return {p.profile_id: p.profile_revision for p in profiles}
    except OSError as exc:
        raise ProfileError("cannot save profile storage: " + type(exc).__name__) from exc
    finally:
        if temporary is not None:
            os.unlink(temporary)
        if lock_fd is not None:
            os.close(lock_fd)
            os.unlink(lock_path)


@dataclass(frozen=True)
class HostContext:
    host_version: str
    adapter_version: str
    auth_context: str
    permissions_revision: str
    model_resolution_revision: str

    def __post_init__(self):
        for value in vars(self).values():
            _name(value)


@dataclass(frozen=True)
class ProbeResult:
    """Trusted backend observation; fixture results MUST set real=False.

    Capability success means requested model/effort/auth/delegation are supported.
    Smoke and recheck must report actual route values. Native team testing uses
    scope='native_role'; a minimal model call uses scope='model_call'.
    """
    ok: bool
    real: bool = False
    reason: str = ""
    provider: Optional[str] = None
    model: Optional[str] = None
    effort: Optional[str] = None
    concurrency: Optional[int] = None
    tokens: Optional[int] = None
    cost: Optional[float] = None
    currency: Optional[str] = None


@dataclass(frozen=True)
class ValidationRecord:
    stage: str
    status: str
    profile_id: str
    profile_revision: int
    route: Route
    context: HostContext
    checked_at: datetime
    expires_at: datetime
    scope: str
    reason: str
    tokens: Optional[int] = None
    cost: Optional[float] = None
    currency: Optional[str] = None
    usage_status: str = "unknown"
    concurrency: Optional[int] = None


class ProfileValidator:
    """Run staged probes through trusted host callbacks, never imported code.

    backend(stage, route, context, scope) -> ProbeResult. authorize(route, scope)
    must be a trusted host callback covering the exact recipient and each smoke
    or execution-precheck call. Recheck is not assumed to be read-only.
    Construct a new validator after restart: saved config never restores proofs.
    """
    def __init__(self, backend: Optional[Callable] = None, authorize: Optional[Callable] = None, ttl_seconds=300):
        _integer(ttl_seconds, 1, 86400)
        self.backend, self.authorize, self.ttl_seconds = backend, authorize, ttl_seconds
        self._records = []
        self._snapshots = {}

    @property
    def records(self):
        return tuple(self._records)

    def _current(self, profile, route, context, scope, now, stage):
        candidates = [r for r in self._records if (r.profile_id, r.profile_revision, r.route, r.context, r.scope, r.stage) == (profile.profile_id, profile.profile_revision, route, context, scope, stage)]
        if self._snapshots.get((profile.profile_id, profile.profile_revision)) != profile or not candidates:
            return None
        result = candidates[-1]
        position = next(i for i in range(len(self._records) - 1, -1, -1) if self._records[i] is result)
        for newer in self._records[position + 1:]:
            if (newer.profile_id, newer.profile_revision, newer.route, newer.context, newer.scope) == (profile.profile_id, profile.profile_revision, route, context, scope) and STAGES.index(newer.stage) < STAGES.index(stage):
                return None
        return result if result.checked_at <= now < result.expires_at else None

    def status(self, profile, route_id, stage, context, *, scope="model_call", now=None):
        """Return current effective state without changing historical evidence."""
        now = _time(now or datetime.now(timezone.utc))
        if stage not in STAGES or scope not in ("model_call", "native_role"):
            raise ProfileError("unknown validation stage or scope")
        route = next((r for r in profile.routes if r.route_id == route_id), None)
        if route is None:
            raise ProfileError("route is not allowlisted")
        related = [r for r in self._records if r.profile_id == profile.profile_id
                   and r.route.route_id == route_id and r.stage == stage and r.scope == scope]
        if not related:
            return "unchecked"
        latest = related[-1]
        if (latest.profile_revision, latest.route, latest.context) != (profile.profile_revision, route, context):
            return "stale"
        if now >= latest.expires_at:
            return "expired"
        current = self._current(profile, route, context, scope, now, stage)
        return current.status if current is not None else "stale"

    def validate(self, profile, route_id, stage, context, *, scope="model_call", now=None):
        now = _time(now or datetime.now(timezone.utc))
        if stage not in STAGES or scope not in ("model_call", "native_role"):
            raise ProfileError("unknown validation stage or scope")
        route = next((r for r in profile.routes if r.route_id == route_id), None)
        if route is None:
            raise ProfileError("route is not allowlisted")
        key = (profile.profile_id, profile.profile_revision)
        existing = self._snapshots.get(key)
        if existing is not None and existing != profile:
            raise ProfileError("profile changed without a new revision")
        self._snapshots[key] = profile
        result = ProbeResult(False, reason="previous validation stage is absent or expired")
        status = "blocked"
        index = STAGES.index(stage)
        required = [self._current(profile, route, context, scope, now, s) for s in STAGES[:index]]
        if stage == "schema":
            status, result = "validated_schema", ProbeResult(True)
        elif all(r is not None and r.status in ("validated_schema", "validated_capability", "discovered", "smoke_pass") for r in required):
            if self.backend is None:
                result = ProbeResult(False, reason="real host backend is not configured")
            elif stage in ("smoke", "recheck") and (self.authorize is None or self.authorize(route, scope) is not True):
                result = ProbeResult(False, reason=stage + " call has no trusted authorization")
            else:
                try:
                    result = self.backend(stage, route, context, scope)
                    if not isinstance(result, ProbeResult):
                        raise ProfileError("backend returned invalid evidence")
                    if result.tokens is not None:
                        _integer(result.tokens, 0, 2**63 - 1)
                    if result.cost is not None and (type(result.cost) not in (int, float) or not math.isfinite(result.cost) or result.cost < 0 or not result.currency):
                        raise ProfileError("invalid measured cost")
                    if result.concurrency is not None:
                        _integer(result.concurrency, 1, 256)
                    matched = stage not in ("smoke", "recheck") or (result.provider, result.model, result.effort) == (route.provider, route.model, route.effort)
                    if result.ok is True and result.real is True and matched:
                        status = {"capability": "validated_capability", "discovery": "discovered", "smoke": "smoke_pass", "recheck": "smoke_pass"}[stage]
                    else:
                        status = "failed" if result.real else "blocked"
                        result = replace(result, reason=result.reason or "missing real evidence or actual route mismatch")
                except Exception as exc:
                    result = ProbeResult(False, reason="probe failed: " + type(exc).__name__)
                    status = "failed"
        record = ValidationRecord(stage, status, profile.profile_id, profile.profile_revision, route, context, now, now + timedelta(seconds=self.ttl_seconds), scope, result.reason, result.tokens, result.cost, result.currency, "reported" if result.tokens is not None or result.cost is not None else "unknown", result.concurrency)
        self._records.append(record)
        return record

    def select_route(self, profile, role_name, context, *, approved_revision, approved_routes, host_concurrency, scope="model_call", now=None):
        """Select the first validated, explicitly approved route, without calls.

        The caller must derive approved_revision/routes from trusted user approval.
        Return (route, effective concurrency, reasons for skipped candidates).
        Write-scope exclusion remains the dispatcher's separate responsibility.
        """
        now = _time(now or datetime.now(timezone.utc))
        _integer(host_concurrency, 1, 256)
        if type(approved_revision) is not int or approved_revision != profile.profile_revision:
            raise ProfileError("approval applies to a different profile revision")
        role = next((r for r in profile.roles if r.name == role_name), None)
        if role is None:
            raise ProfileError("unknown role")
        reasons = []
        for route_id in (role.route_id,) + role.fallbacks:
            route = next(r for r in profile.routes if r.route_id == route_id)
            if route_id not in approved_routes:
                reasons.append((route_id, "route is not approved"))
                continue
            records = [self._current(profile, route, context, scope, now, s) for s in STAGES]
            if any(r is None or r.status not in ("validated_schema", "validated_capability", "discovered", "smoke_pass") for r in records):
                reasons.append((route_id, "validation absent, failed, stale, or expired"))
                continue
            capability = records[1]
            if capability.concurrency is None:
                reasons.append((route_id, "host concurrency capability is unknown"))
                continue
            return route, min(role.concurrency, host_concurrency, capability.concurrency), tuple(reasons)
        raise ProfileError("no approved usable route: " + repr(reasons))
