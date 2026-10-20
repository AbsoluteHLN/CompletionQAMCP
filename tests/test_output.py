"""Redirected output must not depend on the active console code page."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from completion_plugin.output import emit, emit_json


class _Buffer:
    def __init__(self):
        self.data = b''

    def write(self, chunk):
        self.data += chunk
        return len(chunk)

    def flush(self):
        pass


class _Redirect:
    """Stand-in for a redirected stdout: not a terminal, narrow code page."""

    def __init__(self, encoding='gbk'):
        self.buffer = _Buffer()
        self.encoding = encoding

    def isatty(self):
        return False

    def write(self, text):
        raise AssertionError('redirected output must use the UTF-8 byte path')

    def flush(self):
        pass


class _Console:
    """Stand-in for an interactive console whose code page cannot hold every character."""

    def __init__(self, encoding='gbk'):
        self.encoding = encoding
        self.written = []

    def isatty(self):
        return True

    def write(self, text):
        text.encode(self.encoding)
        self.written.append(text)
        return len(text)

    def flush(self):
        pass


class OutputTests(unittest.TestCase):
    def test_redirected_output_is_utf8(self):
        stream = _Redirect()
        emit_json({'message': '结果 🚀'}, stream)
        payload = stream.buffer.data.decode('utf-8')
        self.assertIn('🚀', payload)
        self.assertEqual(json.loads(payload), {'message': '结果 🚀'})

    def test_console_falls_back_to_escaped_text(self):
        console = _Console('gbk')
        emit('结果 🚀', console)
        self.assertIn('\\U0001f680', ''.join(console.written))

    def test_console_keeps_encodable_text(self):
        console = _Console('gbk')
        emit('结果', console)
        self.assertEqual(''.join(console.written), '结果\n')

    def test_cli_process_emits_utf8_when_redirected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            draft = root / 'draft.txt'
            draft.write_text('结果已经完成 🚀', encoding='utf-8')
            env = dict(os.environ)
            env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1])
            env['PYTHONIOENCODING'] = 'gbk'
            env['PYTHONDONTWRITEBYTECODE'] = '1'
            proc = subprocess.run(
                [sys.executable, '-B', '-m', 'completion_plugin.cli', 'text', str(draft),
                 '--profile', 'conversation_summary'],
                cwd=str(root), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(proc.returncode, 0, proc.stderr.decode('utf-8', 'replace'))
            payload = proc.stdout.decode('utf-8')
            self.assertIn('🚀', payload)
            self.assertEqual(json.loads(payload)['profile'], 'conversation_summary')
