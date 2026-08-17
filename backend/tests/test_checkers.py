import json

import pytest

from checkers import CheckerConfig, load_checkers


def fake_factory(calls):
    def factory(provider, model, **kwargs):
        calls.append((provider, model, kwargs))
        return object()

    return factory


def write(tmp_path, data):
    p = tmp_path / "checkers.json"
    p.write_text(json.dumps(data))
    return str(p)


VALID = {
    "checkers": [
        {"name": "terra", "provider": "openai", "model": "gpt-5.6-terra", "default": True},
        {"name": "qwen8", "provider": "openai", "model": "qwen3:8b",
         "base_url": "http://host.docker.internal:11434/v1"},
    ]
}


def test_loads_a_valid_file(tmp_path):
    calls: list[tuple[str, str, dict]] = []
    cs = load_checkers(write(tmp_path, VALID), fallback_provider="openai",
                       fallback_model="x", openai_api_key="k", factory=fake_factory(calls))
    assert list(cs.configs) == ["terra", "qwen8"]
    assert cs.default == "terra"
    assert cs.configs["qwen8"].base_url == "http://host.docker.internal:11434/v1"
    assert [(p, m) for p, m, _ in calls] == [("openai", "gpt-5.6-terra"), ("openai", "qwen3:8b")]
    assert calls[0][2]["openai_api_key"] == "k"


def test_missing_file_falls_back_to_env_settings(tmp_path):
    cs = load_checkers(str(tmp_path / "absent.json"), fallback_provider="openai",
                       fallback_model="gpt-5.6-luna", factory=fake_factory([]))
    assert list(cs.configs) == ["default"]
    assert cs.default == "default"
    assert cs.configs["default"] == CheckerConfig(
        name="default", provider="openai", model="gpt-5.6-luna", default=True
    )


def test_a_directory_counts_as_absent(tmp_path):
    # docker compose creates a directory when the host file does not exist.
    (tmp_path / "checkers.json").mkdir()
    cs = load_checkers(str(tmp_path / "checkers.json"), fallback_provider="openai",
                       fallback_model="m", factory=fake_factory([]))
    assert list(cs.configs) == ["default"]


@pytest.mark.parametrize(
    "data,match",
    [
        ({"checkers": []}, "at least one"),
        ({"checkers": [{"name": "a", "provider": "openai", "model": "m"}]}, "default"),
        ({"checkers": [
            {"name": "a", "provider": "openai", "model": "m", "default": True},
            {"name": "b", "provider": "openai", "model": "m", "default": True},
        ]}, "default"),
        ({"checkers": [
            {"name": "dup", "provider": "openai", "model": "m", "default": True},
            {"name": "dup", "provider": "openai", "model": "m2"},
        ]}, "dup"),
        ({"checkers": [{"name": "Bad Name", "provider": "openai", "model": "m",
                        "default": True}]}, "slug"),
        ({"checkers": [{"name": "a", "provider": "openai", "default": True}]}, "model"),
        ({"checkers": ["oops"]}, "must be an object"),
    ],
)
def test_invalid_configs_die_loudly(tmp_path, data, match):
    with pytest.raises(ValueError, match=match):
        load_checkers(write(tmp_path, data), fallback_provider="openai",
                      fallback_model="m", factory=fake_factory([]))


def test_malformed_json_dies_loudly(tmp_path):
    p = tmp_path / "checkers.json"
    p.write_text("{nope")
    with pytest.raises(ValueError, match=r"checkers\.json"):
        load_checkers(str(p), fallback_provider="openai", fallback_model="m",
                      factory=fake_factory([]))


def test_reasoning_effort_reaches_the_factory(tmp_path):
    calls: list[tuple[str, str, dict]] = []
    data = {
        "checkers": [
            {"name": "cloud", "provider": "openai", "model": "m", "default": True},
            {"name": "local", "provider": "openai", "model": "q",
             "base_url": "http://x/v1", "reasoning_effort": "none"},
        ]
    }
    cs = load_checkers(write(tmp_path, data), fallback_provider="openai",
                       fallback_model="m", factory=fake_factory(calls))
    assert cs.configs["local"].reasoning_effort == "none"
    assert cs.configs["cloud"].reasoning_effort == ""
    assert calls[0][2]["reasoning_effort"] == ""
    assert calls[1][2]["reasoning_effort"] == "none"
