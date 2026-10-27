"""Boundary contract: the optional MCP surface stays a read-only diagnostics
surface, and the ownership table keeps one owner per concern.

The MCP face is the part other agents see. If a tool that can approve, execute
or install something appears there, this plugin would own a second completion
authority and a second scheduler — the exact overlap the boundary forbids.
"""
import ast
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / 'completion_plugin' / 'server.py'
BOUNDARY = REPO / 'docs' / 'BOUNDARY.md'


def tool_functions(source):
    tree = ast.parse(source)
    names = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            call = decorator if isinstance(decorator, ast.Call) else None
            if call is not None and getattr(call.func, 'attr', None) == 'tool':
                names.append(node.name)
    return names


class McpSurfaceTests(unittest.TestCase):
    def test_mcp_surface_is_exactly_two_diagnostic_tools(self):
        source = SERVER.read_text(encoding='utf-8')
        self.assertEqual(tool_functions(source), ['capabilities', 'review_text'])

    def test_no_authority_tool_is_exposed(self):
        source = SERVER.read_text(encoding='utf-8')
        for forbidden in ('approve', 'approve_task', 'stop', 'install', 'execute', 'run_task'):
            self.assertNotIn(forbidden, tool_functions(source))

    def test_capability_report_is_honest_about_what_is_missing(self):
        source = SERVER.read_text(encoding='utf-8')
        self.assertIn("'semantic_verification':'not_configured'", source)
        self.assertIn("'user_confirmation':'trusted_host_only'", source)
        self.assertIn("'stop_installed':False", source)

    def test_server_does_not_import_project_execution_bridges(self):
        source = SERVER.read_text(encoding='utf-8')
        for forbidden in ('subprocess', 'os.system', 'shutil.rmtree'):
            self.assertNotIn(forbidden, source)


class OwnershipTableTests(unittest.TestCase):
    def test_boundary_document_names_every_owner(self):
        document = BOUNDARY.read_text(encoding='utf-8')
        for owner in ('KalciriteThinking', 'cross-agent-bridge', 'agent-memory',
                      'Agent Workbench', 'Completion Review'):
            self.assertIn(owner, document, 'boundary table must name ' + owner)

    def test_boundary_document_forbids_second_scheduler(self):
        document = BOUNDARY.read_text(encoding='utf-8')
        self.assertIn('No second scheduler', document)
        self.assertIn('No second completion authority', document)

    def test_readme_points_at_the_boundary_document(self):
        readme = (REPO / 'README.md').read_text(encoding='utf-8')
        self.assertIn('BOUNDARY.md', readme)


if __name__ == '__main__':
    unittest.main()
