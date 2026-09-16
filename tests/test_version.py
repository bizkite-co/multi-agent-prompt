"""cmd_version dispatch, with verkit mocked out.

verkit.promote_version/tag_version do real git commits/tags/pushes — these
tests verify multi-agent-prompt's own dispatch logic (which verkit call
happens for which subcommand, with which arguments), not verkit itself.
"""

from unittest.mock import patch

import pytest

from multi_agent_prompt import cli


def test_bare_version_only_displays_info():
    parser = cli.build_parser()
    args = parser.parse_args(["version"])

    with patch("multi_agent_prompt.cli.verkit") as mock_verkit:
        rc = args.func(args)

    assert rc == 0
    mock_verkit.display_version_info.assert_called_once()
    assert mock_verkit.display_version_info.call_args[0][1] == cli.PACKAGE_NAME
    assert mock_verkit.display_version_info.call_args.kwargs.get("upgrade_cmd") == "map self-up"
    mock_verkit.promote_version.assert_not_called()
    mock_verkit.tag_version.assert_not_called()


def test_version_promote_calls_verkit_with_the_chosen_part():
    parser = cli.build_parser()
    args = parser.parse_args(["version", "promote", "minor"])

    with patch("multi_agent_prompt.cli.verkit") as mock_verkit:
        mock_verkit.promote_version.return_value = "1.1.0"
        rc = args.func(args)

    assert rc == 0
    assert mock_verkit.promote_version.call_args[0][0] == "minor"
    mock_verkit.tag_version.assert_not_called()


def test_version_tag_forwards_push_flags():
    parser = cli.build_parser()
    args = parser.parse_args(["version", "tag", "--no-push-branch"])

    with patch("multi_agent_prompt.cli.verkit") as mock_verkit:
        rc = args.func(args)

    assert rc == 0
    _call_args, call_kwargs = mock_verkit.tag_version.call_args
    assert call_kwargs["push"] is True
    assert call_kwargs["push_branch"] is False
    mock_verkit.promote_version.assert_not_called()


def test_version_release_promotes_then_tags_in_order():
    parser = cli.build_parser()
    args = parser.parse_args(["version", "release", "patch"])

    calls = []
    with patch("multi_agent_prompt.cli.verkit") as mock_verkit:
        mock_verkit.promote_version.side_effect = lambda *a, **kw: calls.append("promote") or "0.1.1"
        mock_verkit.tag_version.side_effect = lambda *a, **kw: calls.append("tag")
        rc = args.func(args)

    assert rc == 0
    assert calls == ["promote", "tag"]
    assert mock_verkit.promote_version.call_args[0][0] == "patch"


def test_version_release_respects_no_push():
    parser = cli.build_parser()
    args = parser.parse_args(["version", "release", "patch", "--no-push"])

    with patch("multi_agent_prompt.cli.verkit") as mock_verkit:
        mock_verkit.promote_version.return_value = "0.1.1"
        args.func(args)

    _call_args, call_kwargs = mock_verkit.tag_version.call_args
    assert call_kwargs["push"] is False


def test_version_command_reports_verkit_errors_without_raising():
    parser = cli.build_parser()
    args = parser.parse_args(["version", "promote", "patch"])

    with patch("multi_agent_prompt.cli.verkit") as mock_verkit:
        mock_verkit.promote_version.side_effect = RuntimeError("dirty working tree")
        rc = args.func(args)

    assert rc == 1


def test_top_level_dash_v_flag_shows_version_and_exits():
    with patch("multi_agent_prompt.cli.verkit") as mock_verkit, pytest.raises(SystemExit) as exc:
        cli.main(["-V"])

    assert exc.value.code == 0
    mock_verkit.display_version_info.assert_called_once()
    assert mock_verkit.display_version_info.call_args[0][1] == cli.PACKAGE_NAME
