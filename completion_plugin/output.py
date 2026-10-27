"""Output that does not depend on the active console code page."""
import json
import sys


def emit(text, stream=None):
    """Write one line of text like print, without depending on the console code page.

    Redirected output is written as UTF-8 bytes so downstream UTF-8 consumers read
    it unchanged. An interactive console keeps its own encoding and falls back to
    escaped text instead of raising UnicodeEncodeError.
    """
    stream = sys.stdout if stream is None else stream
    buffer = getattr(stream, 'buffer', None)
    isatty = getattr(stream, 'isatty', None)
    if buffer is not None and not (isatty and isatty()):
        try:
            stream.flush()
        except (OSError, ValueError):
            pass
        try:
            buffer.write((text + '\n').encode('utf-8'))
            buffer.flush()
            return
        except (OSError, ValueError):
            pass
    try:
        stream.write(text + '\n')
        stream.flush()
    except UnicodeEncodeError:
        encoding = getattr(stream, 'encoding', None) or 'utf-8'
        stream.write((text + '\n').encode(encoding, 'backslashreplace').decode(encoding, 'replace'))
        stream.flush()


def emit_json(value, stream=None):
    """Write one JSON document as UTF-8."""
    emit(json.dumps(value, ensure_ascii=False, indent=2), stream)
