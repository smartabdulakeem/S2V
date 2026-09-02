"""
Thinking must not eat the answer.

On Gemini 2.5 the model's own reasoning is billed against maxOutputTokens, so a
caller asking for 4096 tokens of answer was not getting 4096 tokens of answer.
Measured on the owner's real description batches, thinking took 1683, 1911 and
2895 tokens of the 4096. That is why the board said "described 3 of 8 shots in
one batch - the reply was cut short" on one run and described all eight on the
next with nothing changed between them: whether the answer fitted was decided by
how long the model happened to think.

The provider now asks for the caller's budget plus headroom, so every caller is
fixed at once rather than each one guessing its own padding.
"""

import json

import pytest

from pipeline.llm import gemini


def test_the_caller_gets_the_budget_it_asked_for():
    """4096 of answer means 4096 of answer, whatever thinking costs."""
    asked = gemini._with_thinking_headroom(4096)
    assert asked == 4096 + gemini.THINKING_HEADROOM
    assert asked - gemini.THINKING_HEADROOM >= 4096


def test_the_headroom_clears_the_worst_measured_run():
    """2895 tokens of thinking is the most that has been seen. Clear it."""
    assert gemini.THINKING_HEADROOM > 2895


def test_the_model_ceiling_still_holds():
    """Padding must never ask for more than the model accepts."""
    assert gemini._with_thinking_headroom(gemini.MAX_OUTPUT_TOKENS) == gemini.MAX_OUTPUT_TOKENS
    assert gemini._with_thinking_headroom(10 ** 9) == gemini.MAX_OUTPUT_TOKENS


def test_a_nonsense_budget_does_not_crash_the_call():
    assert gemini._with_thinking_headroom(None) > 0
    assert gemini._with_thinking_headroom("lots") > 0


def test_both_entry_points_pad_the_budget(monkeypatch):
    """complete() and complete_text() must not disagree about this."""
    sent = []

    def fake_urlopen(req, timeout=60):
        sent.append(json.loads(req.data.decode("utf-8")))
        return json.dumps({
            "candidates": [{"content": {"parts": [{"text": "{}"}]}, "finishReason": "STOP"}],
            "usageMetadata": {},
        }).encode("utf-8")

    monkeypatch.setattr(gemini, "urlopen_with_backoff", fake_urlopen)
    p = gemini.GeminiProvider(api_key="test-key")

    p.complete_text(system="hello", max_tokens=1000)
    p.complete(system="hello", user="", max_tokens=1000)

    assert len(sent) == 2
    for payload in sent:
        budget = payload["generationConfig"]["maxOutputTokens"]
        assert budget == 1000 + gemini.THINKING_HEADROOM, (
            "the answer's budget was spent on thinking again")


def test_a_cut_off_reply_says_so(monkeypatch, capsys):
    """
    Truncation reached no one. `complete_text` returned the short string, or ""
    when thinking consumed the lot, and the caller could not tell that from a
    genuinely brief answer - so shots dropped to keyword search in silence.
    """
    def fake_urlopen(req, timeout=60):
        return json.dumps({
            "candidates": [{"content": {"parts": [{"text": "1. half a descrip"}]},
                            "finishReason": "MAX_TOKENS"}],
            "usageMetadata": {"thoughtsTokenCount": 2895},
        }).encode("utf-8")

    monkeypatch.setattr(gemini, "urlopen_with_backoff", fake_urlopen)
    out = gemini.GeminiProvider(api_key="test-key").complete_text(system="go", max_tokens=100)

    assert out == "1. half a descrip", "the text itself must still come back"
    err = capsys.readouterr().err
    assert "cut off" in err
    assert "2895" in err, "say what the thinking cost, so the next person can size it"


def test_a_complete_reply_says_nothing(monkeypatch, capsys):
    """No noise on the normal path."""
    def fake_urlopen(req, timeout=60):
        return json.dumps({
            "candidates": [{"content": {"parts": [{"text": "1. a whole description"}]},
                            "finishReason": "STOP"}],
            "usageMetadata": {"thoughtsTokenCount": 900},
        }).encode("utf-8")

    monkeypatch.setattr(gemini, "urlopen_with_backoff", fake_urlopen)
    gemini.GeminiProvider(api_key="test-key").complete_text(system="go", max_tokens=4096)

    assert capsys.readouterr().err == ""
