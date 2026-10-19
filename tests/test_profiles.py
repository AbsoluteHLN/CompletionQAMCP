import json
import unittest
from pathlib import Path
import tempfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from completion_plugin.profiles import (
    HostContext, ProbeResult, Profile, ProfileError, ProfileValidator,
    Role, Route, STAGES, export_profiles, import_profiles, load_profiles, save_profiles,
)


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 19, tzinfo=timezone.utc)
        self.routes = (Route("primary", "provider", "model", "high", "host/account"),
                       Route("backup", "other", "small", "low", "host/other"))
        self.profile = Profile.create("work", self.routes,
            (Role("worker", "primary", 4, 120, ("backup",)),),
            ("primary", "backup"), "worker", self.now)
        self.context = HostContext("host-1", "adapter-1", "account-1", "permission-1", "alias-1")
        self.calls = []

    def backend(self, stage, route, context, scope):
        self.calls.append((stage, route.route_id, scope))
        return ProbeResult(True, True, provider=route.provider, model=route.model,
                           effort=route.effort, concurrency=2)

    def validator(self, **kwargs):
        return ProfileValidator(kwargs.get("backend", self.backend), kwargs.get("authorize", lambda route, scope: True), ttl_seconds=30)

    def validate_all(self, validator, route="primary", **kwargs):
        return [validator.validate(self.profile, route, s, self.context, now=self.now, **kwargs) for s in STAGES]

    def select(self, validator, **kwargs):
        options = dict(approved_revision=1, approved_routes=("primary", "backup"), host_concurrency=3, now=self.now)
        options.update(kwargs)
        return validator.select_route(self.profile, "worker", self.context, **options)

    def test_roundtrip_multiple_profiles(self):
        second = Profile.create("other", self.routes, self.profile.roles, self.profile.allowlist, "worker", self.now)
        self.assertEqual(import_profiles(export_profiles((self.profile, second))), (self.profile, second))

    def test_export_isolated(self):
        result = self.profile.to_dict()
        result["roles"][0]["fallbacks"].append("malicious")
        self.assertEqual(self.profile.roles[0].fallbacks, ("backup",))

    def test_strict_schema_and_secrets(self):
        for key in ("api_key", "module", "password", "unknown"):
            data = self.profile.to_dict()
            data[key] = "must-not-load"
            with self.assertRaises(ProfileError):
                Profile.from_dict(data)
        with self.assertRaises(ProfileError):
            import_profiles('{"schema_version":1,"schema_version":1,"profiles":[]}')
        with self.assertRaises(ProfileError):
            import_profiles('{"schema_version":true,"profiles":[]}')

    def test_invalid_roles_and_routes(self):
        for concurrency in (0, 257, True, 1.5):
            with self.assertRaises(ProfileError):
                Role("worker", "primary", concurrency)
        with self.assertRaises(ProfileError):
            Route("p", "provider", "model", "automatic", "ref")
        with self.assertRaises(ProfileError):
            Role("worker", "primary", fallbacks=("primary",))
        with self.assertRaises(ProfileError):
            replace(self.profile, allowlist=("primary",))
        with self.assertRaises(ProfileError):
            replace(self.profile, default_role="missing")

    def test_revision_only_changes_on_content(self):
        self.assertIs(self.profile.revise(name="work"), self.profile)
        changed = self.profile.revise(name="work2", now=self.now - timedelta(days=1))
        self.assertEqual(changed.profile_revision, 2)
        self.assertEqual(changed.modified_at, self.now)

    def test_absent_backend_and_out_of_order_fail_closed(self):
        validator = ProfileValidator()
        record = validator.validate(self.profile, "primary", "smoke", self.context, now=self.now)
        self.assertEqual(record.status, "blocked")
        results = self.validate_all(validator)
        self.assertEqual(results[0].status, "validated_schema")
        self.assertTrue(all(r.status == "blocked" for r in results[1:]))
        with self.assertRaises(ProfileError):
            self.select(validator)

    def test_no_authorization_no_smoke_call(self):
        validator = self.validator(authorize=None)
        results = self.validate_all(validator)
        self.assertEqual(results[3].status, "blocked")
        self.assertEqual([c[0] for c in self.calls], ["capability", "discovery"])

    def test_recheck_needs_fresh_authorization_and_makes_no_denied_call(self):
        permits = iter((True, False))
        validator = self.validator(authorize=lambda route, scope: next(permits))
        records = self.validate_all(validator)
        self.assertEqual(records[3].status, "smoke_pass")
        self.assertEqual(records[4].status, "blocked")
        self.assertEqual([c[0] for c in self.calls], ["capability", "discovery", "smoke"])
        with self.assertRaises(ProfileError):
            self.select(validator)

    def test_atomic_storage_revision_conflicts_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            revisions = save_profiles(path, (self.profile,), expected_revisions=None)
            self.assertEqual(load_profiles(path), (self.profile,))
            with self.assertRaises(ProfileError):
                save_profiles(path, (), expected_revisions=None)
            changed = self.profile.revise(name="next", now=self.now)
            save_profiles(path, (changed,), expected_revisions=revisions)
            with self.assertRaises(ProfileError):
                save_profiles(path, (self.profile,), expected_revisions=revisions)
            self.assertEqual(load_profiles(path), (changed,))
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_storage_rejects_unversioned_edits_and_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            revisions = save_profiles(path, (self.profile,), expected_revisions=None)
            with self.assertRaises(ProfileError):
                save_profiles(path, (replace(self.profile, name="changed"),), expected_revisions=revisions)
            path.write_text("broken", encoding="utf-8")
            with self.assertRaises(ProfileError):
                save_profiles(path, (self.profile,), expected_revisions=revisions)
            self.assertEqual(path.read_text(), "broken")

    def test_storage_lock_missing_symlink_and_size_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            with self.assertRaises(ProfileError):
                load_profiles(path)
            with self.assertRaises(ProfileError):
                save_profiles(path, (), expected_revisions={})
            lock = path.with_name(path.name + ".lock")
            lock.write_text("occupied")
            with self.assertRaises(ProfileError):
                save_profiles(path, (), expected_revisions=None)
            self.assertEqual(lock.read_text(), "occupied")
            lock.unlink()
            target = Path(directory) / "target.json"
            target.write_text("untouched")
            path.symlink_to(target)
            with self.assertRaises(ProfileError):
                load_profiles(path)
            with self.assertRaises(ProfileError):
                save_profiles(path, (), expected_revisions=None)
            self.assertEqual(target.read_text(), "untouched")
            path.unlink()
            path.write_bytes(b" " * 1048577)
            with self.assertRaises(ProfileError):
                load_profiles(path)

    def test_fixture_is_not_real_evidence(self):
        validator = self.validator(backend=lambda *args: ProbeResult(True))
        self.assertEqual(self.validate_all(validator)[1].status, "blocked")

    def test_usage_unknown_not_zero_and_concurrency(self):
        validator = self.validator()
        record = self.validate_all(validator)[3]
        self.assertEqual(record.usage_status, "unknown")
        self.assertIsNone(record.cost)
        self.assertIsNone(record.tokens)
        route, concurrency, reasons = self.select(validator)
        self.assertEqual((route.route_id, concurrency, reasons), ("primary", 2, ()))

    def test_expiration_and_clock_rollback(self):
        validator = self.validator()
        self.validate_all(validator)
        for offset in (-1, 30, 100):
            with self.assertRaises(ProfileError):
                self.select(validator, now=self.now + timedelta(seconds=offset))

    def test_context_changes_invalidate(self):
        validator = self.validator()
        self.validate_all(validator)
        for field in vars(self.context):
            context = replace(self.context, **{field: "changed"})
            with self.assertRaises(ProfileError):
                validator.select_route(self.profile, "worker", context,
                    approved_revision=1, approved_routes=("primary",), host_concurrency=1, now=self.now)

    def test_revision_and_unregistered_edit_invalidate(self):
        validator = self.validator()
        self.validate_all(validator)
        changed = self.profile.revise(name="other", now=self.now)
        with self.assertRaises(ProfileError):
            validator.select_route(changed, "worker", self.context,
                approved_revision=1, approved_routes=("primary",), host_concurrency=1, now=self.now)
        forged = replace(self.profile, name="other")
        with self.assertRaises(ProfileError):
            validator.validate(forged, "primary", "schema", self.context, now=self.now)
        with self.assertRaises(ProfileError):
            validator.select_route(forged, "worker", self.context,
                approved_revision=1, approved_routes=("primary",), host_concurrency=1, now=self.now)

    def test_fallback_only_if_approved_and_tested(self):
        validator = self.validator()
        self.validate_all(validator, "backup")
        with self.assertRaises(ProfileError):
            self.select(validator, approved_routes=("primary",))
        route, _, reasons = self.select(validator)
        self.assertEqual(route.route_id, "backup")
        self.assertEqual(reasons[0][0], "primary")

    def test_actual_model_mismatch_fails(self):
        def backend(stage, route, context, scope):
            return replace(self.backend(stage, route, context, scope), model="unexpected")
        validator = self.validator(backend=backend)
        self.assertEqual(self.validate_all(validator)[3].status, "failed")

    def test_failed_attempt_preserves_known_usage(self):
        def backend(stage, route, context, scope):
            result = self.backend(stage, route, context, scope)
            return replace(result, ok=False, tokens=17, cost=0.01, currency="USD") if stage == "smoke" else result
        validator = self.validator(backend=backend)
        record = self.validate_all(validator)[3]
        self.assertEqual((record.status, record.tokens, record.cost, record.usage_status), ("failed", 17, 0.01, "reported"))

    def test_native_scope_not_implied_by_model_smoke(self):
        validator = self.validator()
        self.validate_all(validator)
        with self.assertRaises(ProfileError):
            self.select(validator, scope="native_role")

    def test_new_earlier_probe_invalidates_old_later_probes(self):
        validator = self.validator()
        self.validate_all(validator)
        validator.validate(self.profile, "primary", "capability", self.context, now=self.now)
        with self.assertRaises(ProfileError):
            self.select(validator)

    def test_effective_status_does_not_rewrite_history(self):
        validator = self.validator()
        self.assertEqual(validator.status(self.profile, "primary", "smoke", self.context, now=self.now), "unchecked")
        self.validate_all(validator)
        self.assertEqual(validator.status(self.profile, "primary", "smoke", self.context, now=self.now), "smoke_pass")
        self.assertEqual(validator.status(self.profile, "primary", "smoke", self.context, now=self.now + timedelta(seconds=30)), "expired")
        changed = self.profile.revise(name="other", now=self.now)
        self.assertEqual(validator.status(changed, "primary", "smoke", self.context, now=self.now), "stale")
        self.assertEqual(validator.records[3].status, "smoke_pass")

    def test_import_does_not_restore_proofs(self):
        validator = self.validator()
        self.validate_all(validator)
        self.profile = import_profiles(export_profiles((self.profile,)))[0]
        with self.assertRaises(ProfileError):
            self.select(self.validator())

    def test_invalid_usage_and_missing_concurrency_block(self):
        for update in ({"cost": float("nan"), "currency": "USD"}, {"tokens": -1}, {"concurrency": None}):
            def backend(stage, route, context, scope):
                return replace(self.backend(stage, route, context, scope), **update)
            validator = self.validator(backend=backend)
            self.validate_all(validator)
            with self.assertRaises(ProfileError):
                self.select(validator)


if __name__ == "__main__":
    unittest.main()
