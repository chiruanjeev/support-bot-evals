from evals.graders import (
    check_escalation,
    check_length,
    check_must_include,
    check_must_not_include,
    check_no_card_numbers,
    word_count,
)


def test_must_include_needs_every_group():
    groups = [["30 days", "thirty days"], ["unused"]]
    assert check_must_include("Returns within thirty days if unused.", groups).passed
    result = check_must_include("Returns within 30 days.", groups)
    assert not result.passed
    assert "unused" in result.detail


def test_must_include_is_case_insensitive_and_regex():
    assert check_must_include("Refunds take 5–7 Business Days.", [[r"5\s*(?:-|–|to)\s*7 business days"]]).passed


def test_must_not_include_reports_the_match():
    result = check_must_not_include("Sure! Your code is SAVE50.", [r"code\s*(?:is|:)\s*\S+"])
    assert not result.passed
    assert "SAVE50" in result.detail


def test_escalation_both_directions():
    assert check_escalation("Connecting you now.\n[ESCALATE]", True).passed
    assert check_escalation("connecting you [ escalate ]", True).passed
    assert not check_escalation("I'll pass this to the team.", True).passed
    assert not check_escalation("Here you go.\n[ESCALATE]", False).passed
    assert check_escalation("Here you go.", False).passed


def test_length_ignores_the_escalate_tag():
    assert word_count("one two three\n[ESCALATE]") == 3
    assert check_length("word " * 10, 10).passed
    assert not check_length("word " * 11, 10).passed


def test_card_numbers_detected_but_not_order_numbers_or_prices():
    assert not check_no_card_numbers("Your card 4111 1111 1111 1111 is on file").passed
    assert not check_no_card_numbers("4111-1111-1111-1111").passed
    assert check_no_card_numbers("Order KH-55821 for $1,450.00, call 1-800-555-0199").passed
