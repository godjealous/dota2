import re


def parse_kv(text: str) -> dict:
    tokens = _tokenize(text)
    result, _ = _parse_block(tokens, 0)
    return result


def _tokenize(text: str) -> list:
    tokens = []
    for line in text.splitlines():
        line = line.split("//")[0].strip()
        for token in re.findall(r'"[^"]*"|\{|\}', line):
            tokens.append(token.strip('"') if token not in ("{", "}") else token)
    return tokens


def _parse_block(tokens: list, pos: int) -> tuple:
    result = {}
    while pos < len(tokens):
        token = tokens[pos]
        if token == "}":
            return result, pos + 1
        if token == "{":
            pos += 1
            continue
        key = token
        pos += 1
        if pos >= len(tokens):
            break
        next_token = tokens[pos]
        if next_token == "{":
            value, pos = _parse_block(tokens, pos + 1)
            result[key] = value
        else:
            result[key] = next_token
            pos += 1
    return result, pos
