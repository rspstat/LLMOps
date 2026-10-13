import pytest

from evals import run
from evals.check import display_identity, host_for_display, url_for_display
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


@pytest.mark.parametrize(
    ("bad_url", "reason"),
    [
        ("<API Host>/compatible-mode/v1", "`https://` 로 시작하지 않음"),
        ("<API Host>/compatible-mode/v1", "자리표시자"),
        ("ws1.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1", "`https://` 로 시작하지 않음"),
        (
            "https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/v1",
            "허용되지 않는 문자가 있음: '{' '}'",
        ),
        ("https://<ws>.example.test/v1", "허용되지 않는 문자가 있음: '<' '>'"),
        ("https://exa mple.test/v1", "공백이 들어 있음"),
        ("ftp://example.test/v1", "`http://` 또는 `https://` 가 아님"),
        ("https:///compatible-mode/v1", "도메인(호스트) 부분이 비어 있음"),
    ],
)
def test_the_reason_a_url_is_rejected_is_named_without_echoing_it(
    tmp_path, capsys, bad_url, reason
):
    env = LIVE_QWEN + f"\nSLM_BASE_URL={bad_url}\nFRONTIER_BASE_URL=https://ok.example.test/v1\n"
    code, text = check(tmp_path, capsys, env)
    assert code == 1 and "SLM_BASE_URL 이 올바른 URL이 아닙니다 →" in text
    assert reason in text
    assert bad_url not in text and "maas.aliyuncs" not in text


def test_a_host_with_an_underscore_is_accepted(tmp_path, capsys):
    env = (
        LIVE_QWEN
        + "\nSLM_BASE_URL=https://ws_1.example.test/v1\nFRONTIER_BASE_URL=https://ws_1.example.test/v1\n"
    )
    code, text = check(tmp_path, capsys, env)
    assert code == 0 and "url=https://ws_1.example.test" in text


@pytest.mark.parametrize(
    ("url", "shown"),
    [
        ("https://ws-secretid123.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
         "https://*.ap-southeast-1.maas.aliyuncs.com"),
        ("https://api.openai.com/v1", "https://api.openai.com"),
        ("https://generativelanguage.googleapis.com/v1beta/openai/",
         "https://generativelanguage.googleapis.com"),
        ("http://localhost:8001/v1", "http://localhost:8001"),
        ("http://127.0.0.1:11434/v1", "http://127.0.0.1:11434"),
        ("https://a.b.example.test:8443/x", "https://*.b.example.test:8443"),
    ],
)  # fmt: skip
def test_host_display_hides_an_account_id_label_but_keeps_ordinary_hosts(url, shown):
    assert host_for_display(url) == shown
    assert "secretid123" not in host_for_display(url)


@pytest.mark.parametrize(
    ("identity", "shown"),
    [
        ("mock:small", "mock:small"),
        ("slm:tiny@http://localhost:11434/v1", "slm:tiny@http://localhost:11434/v1"),
        ("jev:jev-latest@https://api.typesafe.ai/v1/systemone",
         "jev:jev-latest@https://api.typesafe.ai/v1/systemone"),
        ("openai:m@https://ws-id77.region.vendor.com/compatible-mode/v1+extra:abc123",
         "openai:m@https://*.region.vendor.com/compatible-mode/v1+extra:abc123"),
        ("slm:m@https://ws-id77.region.vendor.com", "slm:m@https://*.region.vendor.com"),
    ],
)  # fmt: skip
def test_display_identity_masks_the_account_label_and_keeps_the_rest(identity, shown):
    assert display_identity(identity) == shown


def test_the_default_threshold_sweep_is_dense_near_one_where_jev_probabilities_live():
    taus = [float(t) for t in run.DEFAULT_TAUS.split(",")]
    assert taus == sorted(taus) and taus[0] <= 0.5 and taus[-1] >= 0.99
    assert sum(t >= 0.95 for t in taus) >= 4  # a judge that saturates needs a fine top end


def test_a_workspace_id_in_the_host_never_appears_in_the_check_output(tmp_path, capsys):
    url = "https://ws-secretid123.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
    env = LIVE_QWEN + f"\nSLM_BASE_URL={url}\nFRONTIER_BASE_URL={url}\n"
    code, text = check(tmp_path, capsys, env)
    assert code == 0 and "secretid123" not in text
    assert "url=https://*.ap-southeast-1.maas.aliyuncs.com" in text


ALIBABA = "https://ws1.ap-southeast-1.maas.aliyuncs.com"


def same_endpoint_env(small_key: str, frontier_key: str) -> str:
    base = f"{ALIBABA}/compatible-mode/v1"
    return LIVE_QWEN.replace(
        f"SLM_API_KEY={SECRETS['SLM_API_KEY']}", f"SLM_API_KEY={small_key}"
    ).replace(f"OPENAI_API_KEY={SECRETS['OPENAI_API_KEY']}", f"OPENAI_API_KEY={frontier_key}") + (
        f"\nSLM_BASE_URL={base}\nFRONTIER_BASE_URL={base}\n"
    )


def test_two_models_on_one_endpoint_with_different_keys_get_a_note_not_an_error(tmp_path, capsys):
    # The reported case: the small model's copy of the key lost a character.
    code, text = check(tmp_path, capsys, same_endpoint_env("sk-abcdefghij", "sk-abcdefghijk"))
    assert code == 0  # legitimate setups can use two keys
    assert "SLM_API_KEY 와 OPENAI_API_KEY 가 서로 다릅니다 (길이도 다름)" in text
    assert "sk-abcdefghij" not in text  # and nothing about the keys themselves is shown


def test_same_length_but_different_keys_are_noted_without_the_length_remark(tmp_path, capsys):
    code, text = check(tmp_path, capsys, same_endpoint_env("sk-abcdefghij", "sk-abcdefghiX"))
    assert code == 0 and "서로 다릅니다." in text and "길이도 다름" not in text


def test_identical_keys_on_one_endpoint_get_no_note(tmp_path, capsys):
    code, text = check(tmp_path, capsys, same_endpoint_env("sk-abcdefghij", "sk-abcdefghij"))
    assert code == 0 and "서로 다릅니다" not in text


def test_different_keys_on_different_endpoints_are_expected_and_not_noted(tmp_path, capsys):
    env = (
        LIVE_QWEN
        + "\nSLM_BASE_URL=https://a.example.test/v1\nFRONTIER_BASE_URL=https://b.example.test/v1\n"
    )
    code, text = check(tmp_path, capsys, env)
    assert code == 0 and "서로 다릅니다" not in text


def test_valid_base_urls_pass_and_show_the_masked_host_with_its_plain_path(tmp_path, capsys):
    env = (
        LIVE_QWEN + f"\nSLM_BASE_URL={ALIBABA}/compatible-mode/v1"
        f"\nFRONTIER_BASE_URL={ALIBABA}/compatible-mode/v1"
        "\nJEV_BASE_URL=https://api.typesafe.ai/v1/systemone\n"
    )
    code, text = check(tmp_path, capsys, env)
    assert code == 0
    assert "url=https://*.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1" in text
    assert "ws1" not in text  # the workspace id label is hidden


@pytest.mark.parametrize("path", ["", "/", "/v1", "/compatible-mode", "/compatible-mode/v2"])
def test_an_alibaba_url_without_the_compatible_mode_path_is_a_problem(tmp_path, capsys, path):
    # The reported case: the bare API host answers /chat/completions with an empty 404.
    env = (
        LIVE_QWEN
        + f"\nSLM_BASE_URL={ALIBABA}{path}\nFRONTIER_BASE_URL={ALIBABA}/compatible-mode/v1\n"
    )
    code, text = check(tmp_path, capsys, env)
    assert code == 1 and "SLM_BASE_URL 의 경로가 `/compatible-mode/v1` 로 끝나지 않습니다" in text
    assert "FRONTIER_BASE_URL 의 경로" not in text


@pytest.mark.parametrize("path", ["/compatible-mode/v1", "/compatible-mode/v1/"])
def test_the_alibaba_compatible_mode_path_passes_with_or_without_a_trailing_slash(
    tmp_path, capsys, path
):
    env = LIVE_QWEN + f"\nSLM_BASE_URL={ALIBABA}{path}\nFRONTIER_BASE_URL={ALIBABA}{path}\n"
    assert check(tmp_path, capsys, env)[0] == 0


def test_a_host_that_needs_no_path_is_not_flagged(tmp_path, capsys):
    # DeepSeek is served from the bare host; only Alibaba hosts have the /compatible-mode rule.
    env = (
        LIVE_QWEN
        + "\nSLM_BASE_URL=https://api.deepseek.com\nFRONTIER_BASE_URL=https://api.deepseek.com\n"
    )
    code, text = check(tmp_path, capsys, env)
    assert code == 0 and "url=https://api.deepseek.com" in text


@pytest.mark.parametrize(
    ("url", "shown"),
    [
        ("https://api.openai.com/v1", "https://api.openai.com/v1"),
        ("https://ws-id9.region.vendor.com/compatible-mode/v1/", "https://*.region.vendor.com/compatible-mode/v1/"),
        ("https://api.test/v1?key=query-secret-1", "https://api.test/v1"),
        ("https://user:pw-secret-2@api.test/v1", "https://api.test/v1"),
        ("https://api.test/v1#frag-secret-3", "https://api.test/v1"),
        ("https://api.test/has space/v1", "https://api.test"),
        ("https://api.test", "https://api.test"),
    ],
)  # fmt: skip
def test_url_display_keeps_a_plain_path_but_never_queries_credentials_or_odd_paths(url, shown):
    result = url_for_display(url)
    assert result == shown
    for secret in ("query-secret-1", "pw-secret-2", "frag-secret-3"):
        assert secret not in result


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
