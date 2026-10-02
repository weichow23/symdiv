import json

from symdiv.provider import provider_result_from_response


def test_parses_responses_api_output():
    payload = {
        "id": "resp_test",
        "output": [
            {
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(
                            {
                                "findings": [
                                    {
                                        "site_id": "s1",
                                        "verdict": "bug",
                                        "path_conditions": ["x == 0"],
                                        "denominator": "x",
                                        "rationale": "reachable zero",
                                        "confidence": 0.9,
                                    }
                                ]
                            }
                        ),
                    }
                ]
            }
        ],
        "usage": {"input_tokens": 10, "output_tokens": 20},
    }
    result = provider_result_from_response(payload)
    assert result.request_id == "resp_test"
    assert result.input_tokens == 10
    assert result.hypotheses[0].path_conditions == ["x == 0"]



def test_codex_recordings_can_be_read():
    response={'provider':'codex_exec','output':{'findings':[]},
              'usage':{'input_tokens':12,'output_tokens':3}}
    result=provider_result_from_response(response)
    assert result.input_tokens==12
    assert result.hypotheses==[]
