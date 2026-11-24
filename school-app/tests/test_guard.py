import pytest

from athar import guard

TUNED = [p for p in guard.PROBES if not p.held_out]


def test_enough_probes_with_held_out_ones():
    assert len(guard.PROBES) >= 40
    assert sum(p.held_out for p in guard.PROBES) == 10
    assert {p.language for p in guard.PROBES} == {"en", "fr", "sw", "ar"}


@pytest.mark.parametrize("probe", [p for p in TUNED if p.should_block], ids=lambda p: p.text[:40])
def test_blocks(probe):
    assert guard.check_statement(probe.text)


@pytest.mark.parametrize("probe", [p for p in TUNED if not p.should_block], ids=lambda p: p.text[:40])
def test_does_not_block_neutral_pattern_statements(probe):
    assert guard.check_statement(probe.text) == []


def test_messages_name_the_rule():
    assert guard.check_statement("A lazy learner.")[0].startswith('label on a child: "lazy"')
    assert "comparison with classmates" in guard.check_statement("Below the class average.")[0]
    assert "prescriptive track assignment" in guard.check_statement("She should choose art.")[0]
    assert guard.check_statement("   ") == ["statement is empty"]


def test_evaluate_reports_rates():
    report = guard.evaluate()
    assert report["tuned"]["block_rate"] == 1.0 and report["tuned"]["false_positive_rate"] == 0.0
    # Held-out probes are reported, not tuned for: the guard is a word list and misses some phrasings.
    assert report["held_out"]["n"] == 10
    assert report["held_out"]["false_positive_rate"] == 0.0
    assert 0 <= report["held_out"]["block_rate"] <= 1


def test_a_judgement_of_promise_is_a_label():
    """A drafted note said "this learner shows promise". That judges the child, not the work."""
    assert guard.check_statement("This learner shows promise but currently struggles with decimals.")
    assert guard.check_statement("Your child shows great promise in maths.")
    assert not guard.check_statement("Results in geometry have been strong for five terms.")
    assert not guard.check_statement("The teacher promised to send the book home.")
