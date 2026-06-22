"""Hand-rolled GDB/MI output record parser (stdlib only, no pygdbmi)."""

_KEPT_FIELDS = frozenset({"reason", "name", "value", "type", "msg", "bkpt", "frame", "thread-id"})

_RESULT_KINDS = {"^": "result", "*": "async", "=": "async"}
_STREAM_PREFIXES = {"~", "@", "&"}


def _scan_fields(text: str) -> dict:
    """Extract top-level key=value pairs, respecting quoted strings and {}/[] nesting."""
    fields: dict = {}
    pos = 0
    length = len(text)
    while pos < length:
        # Skip leading comma separators
        if text[pos] == ",":
            pos += 1
            continue
        # Find key (alphanumeric, hyphens, underscores)
        key_start = pos
        while pos < length and text[pos] not in ("=", ","):
            pos += 1
        if pos >= length or text[pos] != "=":
            break
        key = text[key_start:pos]
        pos += 1  # skip '='
        if pos >= length:
            break
        # Parse value
        value, pos = _scan_value(text, pos)
        if key in _KEPT_FIELDS:
            fields[key] = value
    return fields


def _scan_value(text: str, pos: int) -> tuple:
    """Parse a single MI value starting at pos; return (value_str_or_dict, new_pos)."""
    length = len(text)
    if pos >= length:
        return ("", pos)
    ch = text[pos]
    if ch == '"':
        return _scan_quoted(text, pos)
    if ch in ("{", "["):
        return _scan_nested(text, pos)
    # Bare (unquoted) value - read until comma or end
    start = pos
    while pos < length and text[pos] != ",":
        pos += 1
    return (text[start:pos], pos)


def _scan_quoted(text: str, pos: int) -> tuple:
    """Parse a double-quoted MI string; return (unescaped_content, pos_after_closing_quote)."""
    pos += 1  # skip opening '"'
    result = []
    length = len(text)
    while pos < length:
        ch = text[pos]
        if ch == "\\":
            pos += 1
            if pos < length:
                result.append(text[pos])
            pos += 1
        elif ch == '"':
            pos += 1
            return ("".join(result), pos)
        else:
            result.append(ch)
            pos += 1
    return ("".join(result), pos)


def _scan_nested(text: str, pos: int) -> tuple:
    """Parse a {}-or-[]-bracketed block; return (raw_content_str, pos_after_close)."""
    opener = text[pos]
    closer = "}" if opener == "{" else "]"
    depth = 0
    start = pos
    length = len(text)
    in_quote = False
    while pos < length:
        ch = text[pos]
        if in_quote:
            if ch == "\\" and pos + 1 < length:
                pos += 2
                continue
            if ch == '"':
                in_quote = False
        else:
            if ch == '"':
                in_quote = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    pos += 1
                    return (text[start:pos], pos)
        pos += 1
    return (text[start:pos], pos)


def parse_mi_line(line: str) -> dict:
    """Parse one GDB/MI output line into a structured dict.

    Returns a dict with keys:
    - kind: "result" | "async" | "stream" | "prompt"
    - class: the class token (present for result/async)
    - fields: dict of kept fields (present for result/async/stream)
    """
    line = line.rstrip("\r\n")

    if line == "(gdb)":
        return {"kind": "prompt"}

    # Strip optional leading numeric token (e.g. "1^done")
    prefix = line
    i = 0
    while i < len(prefix) and prefix[i].isdigit():
        i += 1
    if i > 0 and i < len(prefix) and prefix[i] in _RESULT_KINDS:
        prefix = prefix[i:]

    if prefix and prefix[0] in _RESULT_KINDS:
        kind = _RESULT_KINDS[prefix[0]]
        rest = prefix[1:]
        comma = rest.find(",")
        if comma == -1:
            cls = rest
            field_text = ""
        else:
            cls = rest[:comma]
            field_text = rest[comma + 1:]
        return {"kind": kind, "class": cls, "fields": _scan_fields(field_text)}

    if prefix and prefix[0] in _STREAM_PREFIXES:
        return {"kind": "stream", "class": "console", "fields": {"text": line}}

    # Unrecognized / plain console text
    return {"kind": "stream", "class": "console", "fields": {"text": line}}
