
import pytest
import re
from unittest.mock import MagicMock

# Since the regex logic is embedded in main.py, we might need to extract it or import it.
# For now, let's test a standalone implementation of the logic to verify correctness.
# Ideally, we should refactor main.py to make `create_message_handler` more testable or extract the regex logic.

def create_regex_from_keywords(keywords):
    if not keywords:
        return None
    return re.compile(
        "|".join(re.escape(k) for k in sorted(keywords, key=len, reverse=True)),
        re.IGNORECASE
    )

def test_regex_matching_simple():
    keywords = ["apple", "banana"]
    regex = create_regex_from_keywords(keywords)
    assert regex.search("I like apple pie")
    assert regex.search("Banana split")
    assert not regex.search("oracle database") # "le" is not "apple"

def test_regex_matching_complex():
    keywords = ["yuk bor", "mashina kerak"]
    regex = create_regex_from_keywords(keywords)
    
    assert regex.search("Toshkentdan Buxoroga yuk bor")
    assert regex.search("YUK BOR aka")
    assert not regex.search("yuk yo'q")

def test_regex_priority():
    # Longer keywords should match first if we sort properly (which the function does)
    keywords = ["super man", "super"]
    regex = create_regex_from_keywords(keywords)
    match = regex.search("super man is here")
    assert match.group(0).lower() == "super man" # Should match the longer one first if implementation is correct
