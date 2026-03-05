"""Dockerfile parser and Apptainer .def converter.

Parses a subset of Dockerfile syntax relevant to compute environments and converts
to Apptainer definition files. The entrypoint is extracted separately (not embedded
in the .def) because it's passed to the Slurm wrapper script.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
from dataclasses import dataclass, field

_DOCKER_IMAGE_RE = re.compile(
    r"^[a-zA-Z0-9]([a-zA-Z0-9._/-]*[a-zA-Z0-9])?"
    r"(:[a-zA-Z0-9][a-zA-Z0-9._-]*)?"
    r"(@sha256:[a-f0-9]{64})?$"
)
_WORKDIR_RE = re.compile(r"^/[a-zA-Z0-9._/-]+$")
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

PREBUILT_ALIASES: dict[str, str] = {
    "base": "base.sif",
    "python312": "python312.sif",
    "node20": "node20.sif",
    "pytorch": "pytorch.sif",
    "r-base": "r-base.sif",
}

IMAGES_DIR = "/ouro-jobs/images"


@dataclass
class DockerfileParsed:
    from_image: str  # "python312" or "python:3.12-slim"
    run_commands: list[str] = field(default_factory=list)
    env_vars: dict[str, str] = field(default_factory=dict)
    workdir: str | None = None
    entrypoint_cmd: list[str] = field(default_factory=list)
    needs_build: bool = False


def parse_dockerfile(content: str, *, require_entrypoint: bool = True) -> DockerfileParsed:
    """Parse Dockerfile content into a structured representation.

    Supports: FROM, RUN, ENV, WORKDIR, ENTRYPOINT, CMD.
    Silently ignores: COPY, ADD, EXPOSE, VOLUME, USER, ARG, LABEL, SHELL, HEALTHCHECK, STOPSIGNAL, ONBUILD.
    Multi-stage builds: takes the last FROM.
    """
    # Join backslash-continuation lines
    lines = _join_continuations(content)

    from_image: str | None = None
    run_commands: list[str] = []
    env_vars: dict[str, str] = {}
    workdir: str | None = None
    entrypoint: list[str] | None = None
    cmd: list[str] | None = None

    ignored = {"COPY", "ADD", "EXPOSE", "VOLUME", "USER", "ARG", "LABEL", "SHELL", "HEALTHCHECK", "STOPSIGNAL", "ONBUILD"}

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Split instruction from arguments
        parts = stripped.split(None, 1)
        instruction = parts[0].upper()
        args = parts[1] if len(parts) > 1 else ""

        if instruction == "FROM":
            # Multi-stage: last FROM wins. Strip "AS <name>" suffix.
            from_image = re.split(r"\s+[Aa][Ss]\s+", args)[0].strip()
            # V3: Validate FROM image name
            if from_image not in PREBUILT_ALIASES and not _DOCKER_IMAGE_RE.match(from_image):
                raise ValueError(f"Invalid FROM image: {from_image}")
            # V6: Reset per-stage state — only final stage's commands matter
            run_commands = []
            env_vars = {}
            workdir = None

        elif instruction == "RUN":
            if args:
                run_commands.append(args)

        elif instruction == "ENV":
            _parse_env(args, env_vars)

        elif instruction == "WORKDIR":
            workdir = args.strip()
            if not _WORKDIR_RE.match(workdir):
                raise ValueError(f"Invalid WORKDIR: must be absolute path with safe characters")

        elif instruction == "ENTRYPOINT":
            entrypoint = _parse_cmd_or_entrypoint(args)

        elif instruction == "CMD":
            cmd = _parse_cmd_or_entrypoint(args)

        elif instruction in ignored:
            continue  # silently ignore

    if not from_image:
        raise ValueError("Dockerfile must have a FROM instruction")

    # Resolve entrypoint (skip if caller provides external entrypoint)
    resolved_entrypoint = _resolve_entrypoint(entrypoint, cmd, require=require_entrypoint)

    # Determine needs_build
    is_alias = from_image in PREBUILT_ALIASES
    needs_build = not is_alias or len(run_commands) > 0 or len(env_vars) > 0 or workdir is not None

    return DockerfileParsed(
        from_image=from_image,
        run_commands=run_commands,
        env_vars=env_vars,
        workdir=workdir,
        entrypoint_cmd=resolved_entrypoint,
        needs_build=needs_build,
    )


def dockerfile_to_def(parsed: DockerfileParsed) -> str:
    """Convert a parsed Dockerfile to an Apptainer .def file.

    ENTRYPOINT/CMD are NOT embedded — they're returned via parsed.entrypoint_cmd
    and passed to the Slurm wrapper separately.
    """
    sections: list[str] = []

    # Bootstrap section
    if parsed.from_image in PREBUILT_ALIASES:
        sif_file = PREBUILT_ALIASES[parsed.from_image]
        sif_path = os.path.join(IMAGES_DIR, sif_file)
        sections.append(f"Bootstrap: localimage\nFrom: {sif_path}")
    else:
        sections.append(f"Bootstrap: docker\nFrom: {parsed.from_image}")

    # %post section (RUN + WORKDIR mkdir)
    post_lines: list[str] = []
    if parsed.workdir:
        post_lines.append(f"    mkdir -p {shlex.quote(parsed.workdir)}")
    for cmd in parsed.run_commands:
        post_lines.append(f"    {cmd}")
    if post_lines:
        sections.append("%post\n" + "\n".join(post_lines))

    # %environment section (ENV + WORKDIR)
    env_lines: list[str] = []
    for key, val in parsed.env_vars.items():
        env_lines.append(f"    export {key}={shlex.quote(val)}")
    if parsed.workdir:
        env_lines.append(f"    export APPTAINER_CWD={shlex.quote(parsed.workdir)}")
    if env_lines:
        sections.append("%environment\n" + "\n".join(env_lines))

    return "\n\n".join(sections) + "\n"


def def_content_hash(def_content: str) -> str:
    """SHA256 hash of .def content for cache keying."""
    return hashlib.sha256(def_content.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _join_continuations(content: str) -> list[str]:
    """Join backslash-continuation lines, then split into logical lines."""
    # Replace backslash + newline with space
    joined = re.sub(r"\\\s*\n", " ", content)
    return joined.split("\n")


def _parse_cmd_or_entrypoint(args: str) -> list[str]:
    """Parse ENTRYPOINT or CMD arguments.

    Exec form: ["python", "main.py"] → ["python", "main.py"]
    Shell form: python main.py → ["bash", "-c", "python main.py"]
    """
    stripped = args.strip()
    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except json.JSONDecodeError:
            pass
    # Shell form
    return ["bash", "-c", stripped]


def _parse_env(args: str, env_vars: dict[str, str]) -> None:
    """Parse ENV instruction arguments.

    Supports both forms:
    - ENV KEY=VALUE KEY2=VALUE2  (equals form)
    - ENV KEY VALUE              (space form, single var)
    """
    stripped = args.strip()
    if "=" in stripped:
        # Equals form: may have multiple KEY=VALUE pairs
        for match in re.finditer(r'(\w+)=("(?:[^"\\]|\\.)*"|\S+)', stripped):
            key = match.group(1)
            if not _ENV_KEY_RE.match(key):
                raise ValueError(f"Invalid ENV key: {key}")
            val = match.group(2)
            # Strip surrounding quotes
            if val.startswith('"') and val.endswith('"'):
                val = val[1:-1]
            env_vars[key] = val
    else:
        # Space form: ENV KEY VALUE
        parts = stripped.split(None, 1)
        if len(parts) == 2:
            if not _ENV_KEY_RE.match(parts[0]):
                raise ValueError(f"Invalid ENV key: {parts[0]}")
            env_vars[parts[0]] = parts[1]


def _resolve_entrypoint(
    entrypoint: list[str] | None,
    cmd: list[str] | None,
    *,
    require: bool = True,
) -> list[str]:
    """Resolve the effective entrypoint command.

    - If ENTRYPOINT is set, use it (ignore CMD)
    - If only CMD is set, use CMD as entrypoint
    - If neither and require=True → raise ValueError
    - If neither and require=False → return [] (caller provides external entrypoint)
    """
    if entrypoint:
        return entrypoint
    if cmd:
        return cmd
    if require:
        raise ValueError("Dockerfile must specify ENTRYPOINT or CMD")
    return []
