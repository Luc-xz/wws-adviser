

def test_parse_sse_chunk_content_and_reasoning() -> None:
    """SSE 增量解析：content 累积、reasoning 增量剥离、usage 末块、非法载荷容错。"""
    from wws_adviser.infrastructure.models.openai_model import parse_sse_chunk

    reasoning = '{"choices":[{"delta":{"reasoning_content":"思考中..."}}]}'
    assert parse_sse_chunk(reasoning) == ("", {})

    c1 = '{"choices":[{"delta":{"content":"{\\"summary\\":"}}]}'
    assert parse_sse_chunk(c1) == ('{"summary":', {})
    c2 = '{"choices":[{"delta":{"content":"\\"...\\")"}}]}'
    assert parse_sse_chunk(c2) == ('"...")', {})

    usage_chunk = '{"choices":[{"delta":{}}],"usage":{"prompt_tokens":10,"completion_tokens":5}}'
    assert parse_sse_chunk(usage_chunk) == ("", {"prompt_tokens": 10, "completion_tokens": 5})

    assert parse_sse_chunk("not json") == ("", {})
    assert parse_sse_chunk("{}") == ("", {})
