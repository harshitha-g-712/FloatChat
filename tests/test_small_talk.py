"""Small talk: greetings and friends are answered kindly; real questions are never swallowed."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from small_talk import small_talk_reply


@pytest.mark.parametrize("text", [
    "hi", "hii", "hiii!", "Hello", "helloo", "helo", "heyy", "hey there", "hlo", "Namaste", "good morning",
    "goodmorning", "Hi floatchat", "yo", "hi!!", "gm", "HI BRO", "hi \U0001F44B", "\U0001F44B", "hello sir",
    "hi, how are you?", "hey how r u", "how are you", "what's up", "whats up", "sup", "wassup", "thanks",
    "thank you!", "thx", "thank u so much", "ty", "bye", "goodbye", "good night", "see you later", "take care",
    "ok", "okay", "cool", "ok thanks", "help", "what can you do", "who are you", "what is floatchat",
    "how to use this", "examples", "hello everyone", "Hi there!!!", "hii bro how are you", "good evening",
])
def test_small_talk_is_answered(text):
    assert small_talk_reply(text, "2023-2024"), text


@pytest.mark.parametrize("text", [
    "hi temperature in 2023", "hey what is salinity", "history of floats", "hip", "list floats", "yes", "no",
    "hello world", "thanks for the temperature in march 2023", "thank you show salinity", "what is a thermocline",
    "help me find floats in 2023", "???", "ok show salinity", "how to use argo data in research",
    "what is up with the salinity", "sure", "", "   ", "a" * 100,
])
def test_real_questions_are_not_treated_as_small_talk(text):
    assert small_talk_reply(text) is None, text


def test_reply_kinds():
    assert "Goodbye" in small_talk_reply("bye")
    assert "welcome" in small_talk_reply("thank you")
    assert "doing well" in small_talk_reply("hi how are you")
    assert "Bay of Bengal" in small_talk_reply("help", "2023-2024")