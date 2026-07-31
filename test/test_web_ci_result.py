from web.web import parse_automation_test_result


def test_parse_pass():
    assert parse_automation_test_result("AUTOMATION_TEST_RESULT: PASS") == {"status": "PASS", "reason": ""}


def test_parse_fail_with_reason():
    result = parse_automation_test_result("AUTOMATION_TEST_RESULT: FAIL\nReason: damage without a target")
    assert result == {"status": "FAIL", "reason": "damage without a target"}


def test_parse_is_case_insensitive():
    result = parse_automation_test_result("automation_test_result: fail\nreason: nope")
    assert result["status"] == "FAIL"
    assert result["reason"] == "nope"


def test_parse_embedded_in_larger_comment():
    result = parse_automation_test_result("### CI run\npreamble\nAUTOMATION_TEST_RESULT: PASS\ntrailing")
    assert result["status"] == "PASS"


def test_parse_multiline_reason():
    result = parse_automation_test_result("AUTOMATION_TEST_RESULT: FAIL\nReason: line one\nline two")
    assert result["status"] == "FAIL"
    assert result["reason"] == "line one\nline two"


def test_parse_non_result_returns_none():
    assert parse_automation_test_result("just a normal review comment") is None
    assert parse_automation_test_result("") is None
    assert parse_automation_test_result(None) is None
