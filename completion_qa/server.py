import argparse
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from .core import Engine
from .editorial import diagnose

def make_server(root):
    engine = Engine(Path(root))
    server = FastMCP("Completion QA", instructions="Local, bounded review evidence. A passing gate applies only to the explicitly required checks. Browser/native/model are unconfigured.")
    @server.tool()
    def capabilities() -> dict:
        """Report configured capabilities and verification limits."""
        return engine.capabilities()
    @server.tool()
    def review_plan(artifacts: list[str], required: list[str], profile: str = "short_reply", scope: str = "artifacts") -> dict:
        """Freeze artifact hashes and required checks. Paths relative to configured root."""
        return engine.plan(artifacts, required, profile, scope)
    @server.tool()
    def run_check(plan_id: str, check: str, command_id: str = "parse_sources") -> dict:
        """Run an approved check, with traceable execution evidence."""
        return engine.run(plan_id, check, command_id)
    @server.tool()
    def review_text(text: str, profile: str = "short_reply") -> dict:
        """Produce local heuristic diagnostics and unapplied, reviewable suggestions."""
        return diagnose(text, profile)
    @server.tool()
    def completion_gate(plan_id: str, origin: str = "host") -> dict:
        """Fail-closed decision on current evidence; idempotent while evidence is unchanged."""
        return engine.gate(plan_id, origin)
    @server.tool()
    def completion_report(plan_id: str) -> dict:
        """Generate a current evidence-bound summary with verification limits; no semantic approval."""
        return engine.report(plan_id)
    return server

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    make_server(args.root).run(transport="stdio")

if __name__ == "__main__":
    main()
