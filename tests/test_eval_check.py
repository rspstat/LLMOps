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


LIVE_QWEN = "\n".join(
    [
        "SMALL_PROVIDER=slm",
        "SLM_MODEL=qwen3.7-flash",
        f"SLM_API_KEY={SECRETS['SLM_API_KEY']}",
        "SMALL_PRICE_IN_PER_MTOK=0.03",
        "SMALL_PRICE_OUT_PER_MTOK=0.13",
        "FRONTIER_PROVIDER=openai",
        "FRONTIER_MODEL=qwen3.8-max",
        f"OPENAI_API_KEY={SECRETS['OPENAI_API_KEY']}",
        "FRONTIER_PRICE_IN_PER_MTOK=2",
        "FRONTIER_PRICE_OUT_PER_MTOK=6",
        "JUDGE_PROVIDER=jev",
        f"JEV_API_KEY={SECRETS['JEV_API_KEY']}",
        "JEV_PRICE_IN_PER_MTOK=0.042",
    ]
)


@pytest.mark.parametrize(
    "bad_url",
    [
        "<API Host>/compatible-mode/v1",  # the placeholder left in
        "abc123.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",  # no scheme
        "https://<WorkspaceId>.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
        "ftp://example.test/v1",
        "https:///compatible-mode/v1",
    ],
)
def test_a_base_url_that_is_not_a_real_url_is_reported_for_a_live_model(tmp_path, capsys, bad_url):
    env = LIVE_QWEN + f"\nSLM_BASE_URL={bad_url}\nFRONTIER_BASE_URL=https://ok.example.test/v1\n"
    code, text = check(tmp_path, capsys, env)
    assert code == 1
    assert "SLM_BASE_URL 이 올바른 URL이 아닙니다" in text and "FRONTIER_BASE_URL 이" not in text
    assert "SLM_BASE_URL = (URL 형식이 아님)" in text
    assert bad_url not in text  # the value itself is not echoed


def test_valid_base_urls_pass_and_show_only_the_host(tmp_path, capsys):
    env = (
        LIVE_QWEN + "\nSLM_BASE_URL=https://ws1.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
        "\nFRONTIER_BASE_URL=https://ws1.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
        "\nJEV_BASE_URL=https://api.typesafe.ai/v1/systemone\n"
    )
    code, text = check(tmp_path, capsys, env)
    assert code == 0 and "url=https://ws1.ap-southeast-1.maas.aliyuncs.com" in text
    assert "compatible-mode" not in text  # paths (which may hold ids) are not shown


def test_a_mock_model_is_not_blamed_for_its_unused_default_url(tmp_path, capsys):
    code, text = check(tmp_path, capsys, "SLM_BASE_URL=not a url\nSMALL_PROVIDER=mock\n")
    assert code == 0 and "문제 없음" in text


def test_problems_come_with_the_non_secret_values_so_they_can_be_verified(tmp_path, capsys):
    env = (
        f"SLM_MODEL=qwen3.7-flash\nSLM_API_KEY={SECRETS['SLM_API_KEY']}\n"
        "SLM_BASE_URL=https://x.example.test/compatible-mode/v1\nSMALL_PRICE_IN_PER_MTOK=0.03\n"
    )  # keys filled but SMALL_PROVIDER still the default mock
    code, text = check(tmp_path, capsys, env)
    assert code == 1 and "파일에 적힌 값" in text
    assert "SLM_MODEL = qwen3.7-flash" in text and "SLM_BASE_URL = https://x.example.test" in text
    assert "SMALL_PRICE_IN_PER_MTOK = 0.03" in text and "SLM_API_KEY = 채워짐" in text
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


def test_text_in_a_numeric_variable_names_the_variable_but_not_the_text(tmp_path, capsys):
    # The reported case: a note such as "free" typed where a price number belongs.
    code, text = check(tmp_path, capsys, "JEV_PRICE_OUT_PER_MTOK=free-ish-xyz\n")
    assert code == 1
    assert "JEV_PRICE_OUT_PER_MTOK: 숫자여야 합니다" in text and "JEV_PRICE_OUT_PER_MTOK=0" in text
    assert "free-ish-xyz" not in text


def test_when_the_file_cannot_load_the_non_secret_values_are_still_shown(tmp_path, capsys):
    env = "\n".join(
        [
            "SMALL_PROVIDER=slm",  # but no SLM_MODEL: the file does not load
            f"SLM_API_KEY={SECRETS['SLM_API_KEY']}",
            "SLM_BASE_URL=https://small.example.test/path/v1?token=url-secret-xyz",
            "FRONTIER_MODEL=big-model",
            "FRONTIER_PRICE_IN_PER_MTOK=2.5",
            "JEV_PRICE_OUT_PER_MTOK=free-ish-xyz",
            f"OPENAI_API_KEY={SECRETS['OPENAI_API_KEY']}",
        ]
    )
    code, text = check(tmp_path, capsys, env)
    # The bad number is a field error; the cross-field "model required" rule only runs after fields
    # pass, so it is not reported yet.
    assert code == 1 and "JEV_PRICE_OUT_PER_MTOK: 숫자여야 합니다" in text
    assert "SMALL_PROVIDER = slm" in text and "FRONTIER_MODEL = big-model" in text
    assert "SLM_MODEL = (비어 있음)" in text and "FRONTIER_PRICE_IN_PER_MTOK = 2.5" in text
    assert "JEV_PRICE_OUT_PER_MTOK = (숫자가 아님)" in text
    assert "SLM_API_KEY = 채워짐" in text and "JEV_API_KEY = (비어 있음)" in text
    assert "SLM_BASE_URL = https://small.example.test" in text
    assert "url-secret-xyz" not in text and "free-ish-xyz" not in text  # query strings, text: never
    assert_no_secret_printed(text)


def test_extra_body_fields_are_listed_by_name_only(tmp_path, capsys):
    env = "\n".join(
        [
            "SMALL_PROVIDER=slm",
            "SLM_MODEL=qwen3.7-flash",
            'SLM_EXTRA_BODY={"enable_thinking": false, "note": "extra-secret-xyz"}',
        ]
    )
    code, text = check(tmp_path, capsys, env)
    assert code == 0 and "추가 필드: enable_thinking, note" in text
    assert "extra-secret-xyz" not in text


def test_broken_json_in_an_extra_body_variable_is_explained_without_echoing_it(tmp_path, capsys):
    code, text = check(tmp_path, capsys, 'SLM_EXTRA_BODY={"token": "json-secret-xyz\n')
    assert code == 1 and "SLM_EXTRA_BODY: JSON 형식이 아닙니다" in text
    assert "json-secret-xyz" not in text and "SLM_EXTRA_BODY = 설정됨" in text


def test_extra_body_with_an_owned_field_is_reported(tmp_path, capsys):
    code, text = check(tmp_path, capsys, 'SLM_EXTRA_BODY={"max_tokens": 5}\n')
    assert code == 1 and "SLM_EXTRA_BODY may not set max_tokens" in text


def test_a_value_outside_the_allowed_choices_is_explained(tmp_path, capsys):
    code, text = check(tmp_path, capsys, "SMALL_PROVIDER=openai\n")
    assert (
        code == 1 and "SMALL_PROVIDER: 허용되지 않는 값입니다" in text and "'mock' or 'slm'" in text
    )


def test_blank_numeric_values_mean_use_the_default_not_an_error(tmp_path, capsys):
    blanks = ["JEV_PRICE_OUT_PER_MTOK", "SMALL_PRICE_IN_PER_MTOK", "ROUTER_PROMOTE_THRESHOLD"]
    code, text = check(tmp_path, capsys, "".join(f"{name}=\n" for name in blanks))
    assert code == 0 and "문제 없음" in text


def test_the_shipped_example_file_is_coherent_as_is(capsys):
    # `cp .env.example .env` must give a config that `check` accepts (all mock, nothing filled).
    code = run.main(["check", "--env-file", ".env.example"], {})
    text = capsys.readouterr().out
    assert code == 0 and "문제 없음" in text
