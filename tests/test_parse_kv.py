from scripts.parse_kv import parse_kv


def test_simple_key_value():
    text = '"key" "value"'
    result = parse_kv(text)
    assert result == {"key": "value"}


def test_nested_block():
    text = '''
"root"
{
    "child" "hello"
}
'''
    result = parse_kv(text)
    assert result == {"root": {"child": "hello"}}


def test_multiple_keys():
    text = '''
"root"
{
    "a" "1"
    "b" "2"
}
'''
    result = parse_kv(text)
    assert result == {"root": {"a": "1", "b": "2"}}


def test_deeply_nested():
    text = '''
"outer"
{
    "inner"
    {
        "key" "val"
    }
}
'''
    result = parse_kv(text)
    assert result == {"outer": {"inner": {"key": "val"}}}


def test_comment_ignored():
    text = '''
// this is a comment
"key" "value"
'''
    result = parse_kv(text)
    assert result == {"key": "value"}
