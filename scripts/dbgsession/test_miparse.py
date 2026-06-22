from miparse import parse_mi_line


def test_prompt():
    assert parse_mi_line("(gdb)")["kind"] == "prompt"


def test_stopped_breakpoint():
    r = parse_mi_line('*stopped,reason="breakpoint-hit",thread-id="1"')
    assert r["kind"] == "async" and r["class"] == "stopped"
    assert r["fields"]["reason"] == "breakpoint-hit"


def test_entry_point_hit():
    r = parse_mi_line('*stopped,reason="entry-point-hit"')
    assert r["fields"]["reason"] == "entry-point-hit"


def test_var_create_result():
    r = parse_mi_line('^done,name="a",value="0",type="int"')
    assert r["kind"] == "result" and r["class"] == "done"
    assert r["fields"]["value"] == "0"


def test_error_result():
    assert parse_mi_line('^error,msg="oops"')["class"] == "error"


def test_non_mi_returns_stream():
    assert parse_mi_line("random console text")["kind"] == "stream"


def test_leading_token_result():
    r = parse_mi_line('1^done,name="var1",value="42",type="int"')
    assert r["kind"] == "result" and r["class"] == "done"
    assert r["fields"]["value"] == "42"


def test_nested_frame_field():
    r = parse_mi_line('*stopped,reason="breakpoint-hit",frame={func="main",line="10"}')
    assert r["kind"] == "async" and r["class"] == "stopped"
    assert r["fields"]["reason"] == "breakpoint-hit"
    assert "frame" in r["fields"]


def test_equals_async():
    r = parse_mi_line('=thread-created,id="1",group-id="i1"')
    assert r["kind"] == "async"


def test_stream_tilde():
    r = parse_mi_line('~"Reading symbols from hello...\n"')
    assert r["kind"] == "stream"
