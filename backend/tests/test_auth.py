import pytest

from auth import TokenAuth


@pytest.fixture
def auth():
    return TokenAuth("tests/fixtures/tokens.json")


def test_valid_token(auth):
    assert auth.validate("tok_test_abc") == "alice"


def test_invalid_token(auth):
    assert auth.validate("tok_invalid") is None


def test_empty_token(auth):
    assert auth.validate("") is None
