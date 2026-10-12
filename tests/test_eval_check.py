import pytest

from evals import run
from gateway.settings import Settings

SECRETS = {
    "OPENAI_API_KEY": "sk-secret-openai-0001",
    "SLM_API_KEY": "slm-secret-0002",
    "JEV_API_KEY": "jev-secret-0003",
    "ANTHROPIC_API_KEY": "anthropic-secret-0004",
    "OPEN_AI_API_KEY": "typo-secret-0005",
}


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """Settings reads os.environ first; the developer's own shell must not leak into these tests."""
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)
    for name in ("ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "HF_TOKEN", "OPEN_AI_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def check(tmp_path, capsys, env_text: str | None):
    path = tmp_path / ".env"
    if env_text is not None:
        path.write_text(env_text, encoding="utf-8")
    code = run.main(["check", "--env-file", str(path)], {})
    out = capsys.readouterr()
    return code, out.out + out.err


def assert_no_secret_printed(text: str):
    for value in SECRETS.values():
        assert value not in text, "a secret value was printed"


def test_an_all_mock_config_with_no_keys_is_coherent(tmp_path, capsys):
    code, text = check(tmp_path, capsys, "SMALL_PROVIDER=mock\nJUDGE_PROVIDER=mock\n")
    assert code == 0 and "문제 없음" in text
    assert "소형(small)   : mock" in text and "판정기(judge) : mock" in text


def test_a_filled_key_behind_a_mock_switch_is_called_out_the_reported_situation(tmp_path, capsys):
    # The reported case: a Jev key is filled in but JUDGE_PROVIDER is still mock.
    env = f"JEV_API_KEY={SECRETS['JEV_API_KEY']}\nJUDGE_PROVIDER=mock\nSMALL_PROVIDER=mock\n"
    code, text = check(tmp_path, capsys, env)
    assert code == 1
    assert "JEV_API_KEY 가 채워져 있지만 JUDGE_PROVIDER=mock" in text
    assert "JUDGE_PROVIDER=jev 로 바꾸세요" in text
    assert_no_secret_printed(text)


def test_small_and_frontier_keys_behind_mock_switches_are_called_out_too(tmp_path, capsys):
    env = (
        f"SLM_API_KEY={SECRETS['SLM_API_KEY']}\nSLM_MODEL=tiny\nSMALL_PROVIDER=mock\n"
        f"OPENAI_API_KEY={SECRETS['OPENAI_API_KEY']}\nFRONTIER_PROVIDER=mock\n"
    )
    code, text = check(tmp_path, capsys, env)
    assert code == 1
    assert (
        "SMALL_PROVIDER=slm 으로 바꾸세요" in text
        and "FRONTIER_PROVIDER=openai 로 바꾸세요" in text
    )
    assert_no_secret_printed(text)


def test_a_fully_configured_live_setup_passes_and_prints_no_secret(tmp_path, capsys):
    env = "\n".join(
        [
            "SMALL_PROVIDER=slm",
            "SLM_BASE_URL=https://small.example.test/v1",
            "SLM_MODEL=tiny",
            f"SLM_API_KEY={SECRETS['SLM_API_KEY']}",
            "SMALL_PRICE_IN_PER_MTOK=0.1",
            "SMALL_PRICE_OUT_PER_MTOK=0.4",
            "FRONTIER_PROVIDER=openai",
            "FRONTIER_MODEL=big",
            f"OPENAI_API_KEY={SECRETS['OPENAI_API_KEY']}",
            "FRONTIER_PRICE_IN_PER_MTOK=2",
            "FRONTIER_PRICE_OUT_PER_MTOK=8",
            "JUDGE_PROVIDER=jev",
            f"JEV_API_KEY={SECRETS['JEV_API_KEY']}",
            "JEV_PRICE_IN_PER_MTOK=0.042",
        ]
    )
    code, text = check(tmp_path, capsys, env)
    assert code == 0 and "문제 없음" in text
    assert (
        "model=tiny" in text and "https://small.example.test" in text
    )  # hosts and models are fine
    assert "호스팅 API (키 있음)" in text
    assert_no_secret_printed(text)


def test_live_models_without_prices_are_reported(tmp_path, capsys):
    env = "\n".join(
        [
            "SMALL_PROVIDER=slm",
            "SLM_MODEL=tiny",
            f"SLM_API_KEY={SECRETS['SLM_API_KEY']}",
            "FRONTIER_PROVIDER=openai",
            "FRONTIER_MODEL=big",
            f"OPENAI_API_KEY={SECRETS['OPENAI_API_KEY']}",
            "JUDGE_PROVIDER=jev",
            f"JEV_API_KEY={SECRETS['JEV_API_KEY']}",
        ]
    )
    code, text = check(tmp_path, capsys, env)
    assert code == 1
    assert "SMALL_PRICE_IN/OUT_PER_MTOK" in text
    assert "FRONTIER_PRICE_IN/OUT_PER_MTOK" in text
    assert "JEV_PRICE_IN_PER_MTOK" in text
    assert_no_secret_printed(text)


def test_a_self_hosted_small_model_needs_no_key_or_price(tmp_path, capsys):
    env = "SMALL_PROVIDER=slm\nSLM_MODEL=qwen\nSLM_BASE_URL=http://localhost:11434/v1\n"
    code, text = check(tmp_path, capsys, env)
    assert code == 0 and "자체 서빙" in text


def test_keys_for_providers_this_project_does_not_use_are_flagged(tmp_path, capsys):
    code, text = check(tmp_path, capsys, f"ANTHROPIC_API_KEY={SECRETS['ANTHROPIC_API_KEY']}\n")
    assert code == 1 and "ANTHROPIC_API_KEY 는 채워져 있지만 이 프로젝트가 읽지 않습니다" in text
    assert_no_secret_printed(text)


def test_a_misspelled_variable_name_is_flagged_without_its_value(tmp_path, capsys):
    code, text = check(tmp_path, capsys, f"OPEN_AI_API_KEY={SECRETS['OPEN_AI_API_KEY']}\n")
    assert code == 1 and "OPEN_AI_API_KEY: 알 수 없는 변수 이름" in text
    assert_no_secret_printed(text)


def test_empty_values_do_not_count_as_filled(tmp_path, capsys):
    code, text = check(tmp_path, capsys, "JEV_API_KEY=\nOPENAI_API_KEY=   \nJUDGE_PROVIDER=mock\n")
    assert code == 0 and "문제 없음" in text


def test_a_missing_env_file_tells_you_how_to_create_it(tmp_path, capsys):
    code, text = check(tmp_path, capsys, None)
    assert code == 1 and "Copy-Item .env.example .env" in text and "없음" in text


def test_an_inconsistent_config_reports_the_setting_without_dumping_secrets(tmp_path, capsys):
    env = f"SMALL_PROVIDER=slm\nSLM_API_KEY={SECRETS['SLM_API_KEY']}\n"  # slm without SLM_MODEL
    code, text = check(tmp_path, capsys, env)
    assert code == 1 and "SLM_MODEL is required" in text
    assert_no_secret_printed(text)


def test_the_shipped_example_file_is_coherent_as_is(capsys):
    # `cp .env.example .env` must give a config that `check` accepts (all mock, nothing filled).
    code = run.main(["check", "--env-file", ".env.example"], {})
    text = capsys.readouterr().out
    assert code == 0 and "문제 없음" in text
