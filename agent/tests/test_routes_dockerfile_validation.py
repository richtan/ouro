"""Tests for Dockerfile COPY/ADD source validation against submitted files."""

from __future__ import annotations

import os

os.environ.setdefault("OPENAI_API_KEY", "test-key-not-real")

import pytest

from src.agent.dockerfile import parse_dockerfile


def _validate_copy_sources(dockerfile_content: str, submitted_paths: list[str], entrypoint: str | None = None):
    """Replicate the validation logic from routes.py for unit testing."""
    parsed = parse_dockerfile(dockerfile_content, require_entrypoint=entrypoint is None)

    if parsed.copy_instructions and submitted_paths:
        submitted = {p for p in submitted_paths if p.lower() != "dockerfile"}
        missing = []
        for src, _ in parsed.copy_instructions:
            if src not in submitted:
                prefix = src.rstrip("/") + "/"
                is_dir = any(p.startswith(prefix) for p in submitted)
                if not is_dir:
                    missing.append(src)
        return missing
    return []


def test_copy_source_matches_submitted_file():
    """COPY source that exists in submitted files passes validation."""
    missing = _validate_copy_sources(
        "FROM node:20-slim\nCOPY index.js /app/\nENTRYPOINT [\"node\", \"index.js\"]",
        ["index.js"],
    )
    assert missing == []


def test_copy_source_missing():
    """COPY references a file not in the submission."""
    missing = _validate_copy_sources(
        "FROM node:20-slim\nCOPY main.js /app/\nENTRYPOINT [\"node\", \"main.js\"]",
        ["index.js"],
    )
    assert missing == ["main.js"]


def test_multiple_copy_one_missing():
    """Multiple COPY instructions, only the missing one is reported."""
    missing = _validate_copy_sources(
        "FROM node:20-slim\nCOPY app.js /app/\nCOPY missing.txt /app/\nENTRYPOINT [\"node\", \"app.js\"]",
        ["app.js", "config.json"],
    )
    assert missing == ["missing.txt"]


def test_copy_subdirectory_path():
    """COPY src/main.js matches src/main.js in submitted files."""
    missing = _validate_copy_sources(
        "FROM node:20-slim\nCOPY src/main.js /app/\nENTRYPOINT [\"node\", \"main.js\"]",
        ["src/main.js"],
    )
    assert missing == []


def test_copy_directory_with_trailing_slash():
    """COPY src/ matches when files with src/ prefix exist."""
    missing = _validate_copy_sources(
        "FROM node:20-slim\nCOPY src/ /app/\nENTRYPOINT [\"node\", \"app.js\"]",
        ["src/app.js", "src/util.js"],
    )
    assert missing == []


def test_copy_directory_without_trailing_slash():
    """COPY src (no trailing slash) matches when files with src/ prefix exist."""
    missing = _validate_copy_sources(
        "FROM node:20-slim\nCOPY src /app/\nENTRYPOINT [\"node\", \"index.js\"]",
        ["src/index.js"],
    )
    assert missing == []


def test_no_copy_instructions():
    """Dockerfile without COPY → empty missing list."""
    missing = _validate_copy_sources(
        "FROM python:3.12-slim\nENTRYPOINT [\"python\", \"main.py\"]",
        ["main.py"],
    )
    assert missing == []


def test_add_source_missing():
    """ADD references a file not in the submission."""
    missing = _validate_copy_sources(
        "FROM node:20-slim\nADD missing.tar /app/\nENTRYPOINT [\"node\", \"index.js\"]",
        ["index.js"],
    )
    assert missing == ["missing.tar"]


def test_add_source_exists():
    """ADD references a file that exists."""
    missing = _validate_copy_sources(
        "FROM node:20-slim\nADD data.tar /app/\nENTRYPOINT [\"node\", \"index.js\"]",
        ["index.js", "data.tar"],
    )
    assert missing == []


def test_dockerfile_excluded_from_submitted():
    """Dockerfile itself is excluded from the submitted files set."""
    missing = _validate_copy_sources(
        "FROM node:20-slim\nCOPY Dockerfile /app/\nENTRYPOINT [\"node\", \"index.js\"]",
        ["index.js", "Dockerfile"],
    )
    assert missing == ["Dockerfile"]


def test_multiple_missing_files():
    """All missing files are reported."""
    missing = _validate_copy_sources(
        "FROM node:20-slim\nCOPY a.js /app/\nCOPY b.js /app/\nENTRYPOINT [\"node\", \"a.js\"]",
        ["other.js"],
    )
    assert sorted(missing) == ["a.js", "b.js"]


def test_directory_prefix_no_match():
    """COPY src/ fails when no files have src/ prefix."""
    missing = _validate_copy_sources(
        "FROM node:20-slim\nCOPY src/ /app/\nENTRYPOINT [\"node\", \"app.js\"]",
        ["app.js", "lib/util.js"],
    )
    assert missing == ["src/"]
