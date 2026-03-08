"""Dockerfile parser for compute environments.

Parses a subset of Dockerfile syntax relevant to HPC compute jobs.
The entrypoint is extracted separately and passed to the Docker wrapper script.

Supported: FROM, RUN, ENV, WORKDIR, ENTRYPOINT, CMD, COPY, ADD, ARG, LABEL, SHELL, EXPOSE.
Rejected with clear errors: USER, VOLUME, HEALTHCHECK, STOPSIGNAL, ONBUILD.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

_DOCKER_IMAGE_RE = re.compile(
    r"^[a-zA-Z0-9]([a-zA-Z0-9._/-]*[a-zA-Z0-9])?"
    r"(:[a-zA-Z0-9][a-zA-Z0-9._-]*)?"
    r"(@sha256:[a-f0-9]{64})?$"
)
_WORKDIR_RE = re.compile(r"^/[a-zA-Z0-9._/-]+$")
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# Safe characters for COPY/ADD source paths (no glob, no traversal tricks)
_COPY_SRC_RE = re.compile(r"^[a-zA-Z0-9._/\- ]+$")

DOCKER_IMAGES: dict[str, str] = {
    "ouro-ubuntu": "ubuntu:22.04",
    "ouro-python": "python:3.12-slim",
    "ouro-nodejs": "node:20-slim",
}
PREBUILT_ALIASES = DOCKER_IMAGES  # backward compat — parse_dockerfile checks membership

# Instructions rejected with clear error messages
_REJECTED: dict[str, str] = {
    "USER": "USER is not supported; containers run as non-root with --no-new-privileges",
    "VOLUME": "VOLUME is not supported; use workspace files at /workspace",
    "HEALTHCHECK": "HEALTHCHECK is not supported for batch jobs",
    "STOPSIGNAL": "STOPSIGNAL is not supported for batch jobs",
    "ONBUILD": "ONBUILD is not supported",
}

# Instructions we handle
_HANDLED = {"FROM", "RUN", "ENV", "WORKDIR", "ENTRYPOINT", "CMD", "COPY", "ADD", "ARG", "LABEL", "SHELL", "EXPOSE"}


@dataclass
class DockerfileParsed:
    from_image: str  # "ouro-python" or "python:3.12-slim"
    run_commands: list[str] = field(default_factory=list)
    env_vars: dict[str, str] = field(default_factory=dict)
    workdir: str | None = None
    entrypoint_cmd: list[str] = field(default_factory=list)
    needs_build: bool = False
    needs_docker_build: bool = False
    arg_vars: dict[str, str | None] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    shell: list[str] | None = None
    copy_instructions: list[tuple[str, str]] = field(default_factory=list)
    is_external_image: bool = False


def parse_dockerfile(content: str, *, require_entrypoint: bool = True) -> DockerfileParsed:
    """Parse Dockerfile content into a structured representation.

    Supports: FROM, RUN, ENV, WORKDIR, ENTRYPOINT, CMD, COPY, ADD, ARG, LABEL, SHELL, EXPOSE.
    Rejects with clear errors: USER, VOLUME, HEALTHCHECK, STOPSIGNAL, ONBUILD.
    Multi-stage builds (multiple FROM) are rejected for security reasons.
    """
    # Reject BuildKit syntax directives (before any processing)
    for raw_line in content.splitlines():
        stripped_raw = raw_line.strip()
        if stripped_raw.lower().startswith("# syntax=") or stripped_raw.lower().startswith("#syntax="):
            raise ValueError("# syntax= directive is not supported for security reasons")

    # Join backslash-continuation lines
    lines = _join_continuations(content)

    # Reject multi-stage builds (multiple FROM instructions)
    from_count = sum(
        1 for line in lines
        if line.strip() and not line.strip().startswith("#")
        and line.strip().split()[0].upper() == "FROM"
    )
    if from_count > 1:
        raise ValueError("Multi-stage builds (multiple FROM) are not supported")

    from_image: str | None = None
    run_commands: list[str] = []
    env_vars: dict[str, str] = {}
    workdir: str | None = None
    entrypoint: list[str] | None = None
    cmd: list[str] | None = None
    arg_vars: dict[str, str | None] = {}
    labels: dict[str, str] = {}
    shell: list[str] | None = None
    copy_instructions: list[tuple[str, str]] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Split instruction from arguments
        parts = stripped.split(None, 1)
        instruction = parts[0].upper()
        args = parts[1] if len(parts) > 1 else ""

        if instruction == "FROM":
            # Strip "AS <name>" suffix.
            from_image = re.split(r"\s+[Aa][Ss]\s+", args)[0].strip()
            if from_image not in PREBUILT_ALIASES and not _DOCKER_IMAGE_RE.match(from_image):
                raise ValueError(f"Invalid FROM image: {from_image}")

        elif instruction == "ARG":
            _parse_arg(args, arg_vars)

        elif instruction == "RUN":
            if args:
                substituted = _substitute_args(args, arg_vars)
                if re.search(r"--mount[\s=]", substituted):
                    raise ValueError("RUN --mount is not supported for security reasons")
                run_commands.append(substituted)

        elif instruction == "ENV":
            _parse_env(_substitute_args(args, arg_vars), env_vars)

        elif instruction == "WORKDIR":
            wd = _substitute_args(args.strip(), arg_vars)
            if not _WORKDIR_RE.match(wd):
                raise ValueError(f"Invalid WORKDIR: must be absolute path with safe characters")
            workdir = wd

        elif instruction == "ENTRYPOINT":
            entrypoint = _parse_cmd_or_entrypoint(args)

        elif instruction == "CMD":
            cmd = _parse_cmd_or_entrypoint(args)

        elif instruction == "COPY":
            _parse_copy_add(_substitute_args(args, arg_vars), copy_instructions, workdir, is_add=False)

        elif instruction == "ADD":
            _parse_copy_add(_substitute_args(args, arg_vars), copy_instructions, workdir, is_add=True)

        elif instruction == "LABEL":
            _parse_label(_substitute_args(args, arg_vars), labels)

        elif instruction == "SHELL":
            shell = _parse_shell(args)

        elif instruction == "EXPOSE":
            _parse_expose(args, labels)

        elif instruction in _REJECTED:
            raise ValueError(_REJECTED[instruction])

        # Unknown instructions silently ignored (forward compatibility)

    if not from_image:
        raise ValueError("Dockerfile must have a FROM instruction")

    # Resolve entrypoint (skip if caller provides external entrypoint)
    resolved_entrypoint = _resolve_entrypoint(entrypoint, cmd, require=require_entrypoint)

    # External images (not prebuilt aliases) must specify ENTRYPOINT/CMD
    # so the proxy knows which interpreter to use. Prebuilt images are fine
    # without it because the proxy's extension-based executor map handles them.
    is_alias = from_image in PREBUILT_ALIASES
    if not is_alias and not resolved_entrypoint:
        raise ValueError(
            f"External image '{from_image}' requires ENTRYPOINT or CMD in the Dockerfile "
            f"to specify how to run the entrypoint file (e.g., ENTRYPOINT [\"ruby\", \"hello.rb\"])"
        )

    # Determine needs_build
    needs_build = (
        not is_alias
        or len(run_commands) > 0
        or len(env_vars) > 0
        or workdir is not None
        or len(copy_instructions) > 0
    )

    # Does it actually need `docker build` vs just `docker pull`?
    needs_docker_build = (
        len(run_commands) > 0
        or len(env_vars) > 0
        or workdir is not None
        or len(copy_instructions) > 0
    )

    return DockerfileParsed(
        from_image=from_image,
        run_commands=run_commands,
        env_vars=env_vars,
        workdir=workdir,
        entrypoint_cmd=resolved_entrypoint,
        needs_build=needs_build,
        needs_docker_build=needs_docker_build,
        is_external_image=not is_alias,
        arg_vars=arg_vars,
        labels=labels,
        shell=shell,
        copy_instructions=copy_instructions,
    )


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


def _parse_arg(args: str, arg_vars: dict[str, str | None]) -> None:
    """Parse ARG instruction: ARG NAME or ARG NAME=default."""
    stripped = args.strip()
    if "=" in stripped:
        key, _, val = stripped.partition("=")
        key = key.strip()
        val = val.strip()
        # Strip surrounding quotes from value
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
            val = val[1:-1]
    else:
        key = stripped
        val = None
    if not _ENV_KEY_RE.match(key):
        raise ValueError(f"Invalid ARG name: {key}")
    arg_vars[key] = val


def _substitute_args(text: str, arg_vars: dict[str, str | None]) -> str:
    """Replace $VAR and ${VAR} references with ARG values.

    Variables with no value set (None) are left as-is.
    """
    def _replace(m: re.Match) -> str:
        name = m.group(1) or m.group(2)
        val = arg_vars.get(name)
        if val is not None:
            return val
        return m.group(0)  # leave unsubstituted

    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)", _replace, text)


def _validate_copy_src(src: str) -> None:
    """Validate a COPY/ADD source path. Raises ValueError on unsafe paths."""
    if "\x00" in src:
        raise ValueError(f"Null bytes in COPY source path: {src!r}")
    # Reject glob characters
    if any(c in src for c in ("*", "?")):
        raise ValueError(f"Glob patterns in COPY are not supported; list files explicitly: {src}")
    # Reject absolute paths
    if src.startswith("/"):
        raise ValueError(f"Absolute paths in COPY source are not allowed: {src}")
    # Normalize and check for traversal
    normalized = os.path.normpath(src)
    if normalized.startswith(".."):
        raise ValueError(f"Path traversal in COPY source: {src}")
    # Check for safe characters
    if not _COPY_SRC_RE.match(src):
        raise ValueError(f"Unsafe characters in COPY source path: {src}")


def _resolve_copy_dest(dest: str, workdir: str | None) -> str:
    """Resolve COPY dest against the current WORKDIR.

    - Absolute dest: returned as-is
    - Relative dest (like '.' or 'subdir/'): resolved against workdir (default '/')
    """
    if dest.startswith("/"):
        return dest
    base = workdir or "/"
    # Join and normalize to handle '.' and redundant separators
    joined = os.path.join(base, dest)
    normalized = os.path.normpath(joined)
    # Preserve trailing slash if original dest had one (indicates directory)
    if dest.endswith("/"):
        normalized += "/"
    return normalized


def _parse_copy_add(
    args: str,
    copy_instructions: list[tuple[str, str]],
    workdir: str | None,
    *,
    is_add: bool,
) -> None:
    """Parse COPY or ADD instruction arguments."""
    stripped = args.strip()

    # Reject COPY --from=... (multi-stage COPY)
    if not is_add and stripped.startswith("--from"):
        raise ValueError("COPY --from is not supported (multi-stage COPY)")

    # Strip --chown and --chmod flags (not used in our container execution)
    stripped = re.sub(r"--(?:chown|chmod)=\S+\s*", "", stripped).strip()

    # JSON form: COPY ["src", "dest"]
    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list) and len(parsed) >= 2:
                srcs = [str(s) for s in parsed[:-1]]
                dest = str(parsed[-1])
            else:
                raise ValueError(f"COPY/ADD JSON form requires at least 2 elements")
        except json.JSONDecodeError:
            raise ValueError(f"Invalid COPY/ADD JSON syntax: {stripped}")
    else:
        # Space-separated form
        parts = shlex.split(stripped)
        if len(parts) < 2:
            raise ValueError(f"COPY/ADD requires at least source and destination")
        srcs = parts[:-1]
        dest = parts[-1]

    # Multiple sources require dest to end with /
    if len(srcs) > 1 and not dest.endswith("/"):
        raise ValueError(f"COPY/ADD with multiple sources requires destination ending with '/': {dest}")

    # Determine if dest is a directory reference (ends with /, is '.', or has multiple srcs)
    dest_is_dir = dest.endswith("/") or dest == "." or len(srcs) > 1

    for src in srcs:
        # ADD: reject URLs
        if is_add and re.match(r"https?://", src, re.IGNORECASE):
            raise ValueError("ADD with URLs is not supported for security reasons; use RUN curl/wget instead")
        _validate_copy_src(src)
        resolved_dest = _resolve_copy_dest(dest, workdir)
        # For directory destinations, append the source filename
        if dest_is_dir:
            if resolved_dest.endswith("/"):
                resolved_dest = resolved_dest + os.path.basename(src)
            else:
                resolved_dest = resolved_dest + "/" + os.path.basename(src)
        copy_instructions.append((src, resolved_dest))


def _parse_label(args: str, labels: dict[str, str]) -> None:
    """Parse LABEL instruction.

    Supports: LABEL key=value [key2=value2 ...] and LABEL key value.
    Security: strips newlines and rejects values where any line starts with '%'.
    """
    stripped = args.strip()
    if "=" in stripped:
        # Equals form: LABEL key=value key2="val 2"
        for match in re.finditer(r'([\w.\-]+)=("(?:[^"\\]|\\.)*"|\S+)', stripped):
            key = match.group(1)
            val = match.group(2)
            if val.startswith('"') and val.endswith('"'):
                val = val[1:-1]
            labels[key] = _sanitize_label_value(val)
    else:
        # Space form: LABEL key value
        parts = stripped.split(None, 1)
        if len(parts) == 2:
            labels[parts[0]] = _sanitize_label_value(parts[1])


def _sanitize_label_value(val: str) -> str:
    """Strip newlines from label values."""
    return val.replace("\n", " ").replace("\r", " ")


def _parse_shell(args: str) -> list[str]:
    """Parse SHELL instruction. Must be JSON exec form: SHELL ["executable", "param"]."""
    stripped = args.strip()
    if not stripped.startswith("["):
        raise ValueError("SHELL must use JSON exec form: SHELL [\"executable\", \"param\"]")
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        raise ValueError(f"Invalid SHELL JSON syntax: {stripped}")
    if not isinstance(parsed, list) or not all(isinstance(s, str) for s in parsed):
        raise ValueError("SHELL must be a JSON array of strings")
    if len(parsed) < 1:
        raise ValueError("SHELL must have at least one element")
    return parsed


def _parse_expose(args: str, labels: dict[str, str]) -> None:
    """Parse EXPOSE instruction. Stores as metadata label; no runtime effect."""
    ports = args.strip().split()
    existing = labels.get("ouro.exposed_ports", "")
    all_ports = ([existing] if existing else []) + ports
    labels["ouro.exposed_ports"] = ",".join(all_ports)


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


# ---------------------------------------------------------------------------
# Docker Hub image validation
# ---------------------------------------------------------------------------

# Registries that are actually Docker Hub (strip prefix and validate normally)
_DOCKER_HUB_HOSTS = {"docker.io", "index.docker.io", "registry-1.docker.io"}


async def validate_docker_image(image: str) -> None:
    """Check that an external Docker Hub image exists. Raises ValueError if not found.

    Fails open on timeout/5xx/network errors — Docker Hub outages must not block submissions.
    Skips validation for prebuilt aliases and digest references (@sha256:...).
    Non-Docker-Hub registries (ghcr.io, quay.io, etc.) are also skipped.
    """

    # Skip prebuilt aliases
    if image in PREBUILT_ALIASES:
        return

    # Skip digest references
    if "@sha256:" in image:
        return

    # Parse registry prefix: if first component contains '.', it's a registry host
    parts = image.split("/", 1)
    if len(parts) == 2 and "." in parts[0]:
        host = parts[0]
        if host not in _DOCKER_HUB_HOSTS:
            # Non-Docker-Hub registry — can't validate, skip
            return
        # Strip Docker Hub prefix and continue
        image = parts[1]

    # Parse namespace/repo:tag
    if ":" in image:
        name, tag = image.rsplit(":", 1)
    else:
        name = image
        tag = "latest"

    if "/" in name:
        namespace, repo = name.split("/", 1)
    else:
        namespace = "library"
        repo = name

    url = f"https://hub.docker.com/v2/namespaces/{namespace}/repositories/{repo}/tags/{tag}"

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
    except (httpx.TimeoutException, httpx.ConnectError, OSError) as e:
        logger.warning("Docker Hub validation timeout/error for %s: %s", image, e)
        return  # fail open

    if resp.status_code == 200:
        return
    if resp.status_code == 404:
        raise ValueError(
            f"Docker image '{image}' not found on Docker Hub. "
            "Check the image name and tag."
        )
    if resp.status_code in (429, 500, 502, 503, 504):
        logger.warning("Docker Hub returned %d for %s, failing open", resp.status_code, image)
        return  # fail open

    # Unexpected status — fail open
    logger.warning("Docker Hub returned unexpected %d for %s", resp.status_code, image)
    return
