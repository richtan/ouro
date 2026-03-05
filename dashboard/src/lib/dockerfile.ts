/**
 * Lightweight Dockerfile parser for UI display and validation.
 * The backend is the authority — this is only for showing info in the submit bar
 * and gating the submit button.
 */

export interface DockerfileInfo {
  fromImage: string | null;
  entrypoint: string | null; // Human-readable, e.g. "python main.py"
  hasRunCommands: boolean;
  isValid: boolean;
  errors: string[];
}

const PREBUILT_ALIASES = new Set([
  "base",
  "python312",
  "node20",
  "pytorch",
  "r-base",
]);

export function parseDockerfile(content: string): DockerfileInfo {
  const errors: string[] = [];
  let fromImage: string | null = null;
  let entrypoint: string | null = null;
  let cmd: string | null = null;
  let hasRunCommands = false;

  // Join backslash continuations
  const joined = content.replace(/\\\s*\n/g, " ");
  const lines = joined.split("\n");

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;

    const spaceIdx = trimmed.indexOf(" ");
    if (spaceIdx === -1) continue;

    const instruction = trimmed.slice(0, spaceIdx).toUpperCase();
    const args = trimmed.slice(spaceIdx + 1).trim();

    switch (instruction) {
      case "FROM":
        // Strip "AS <name>" suffix
        fromImage = args.split(/\s+[Aa][Ss]\s+/)[0].trim();
        break;
      case "RUN":
        hasRunCommands = true;
        break;
      case "ENTRYPOINT":
        entrypoint = parseEntrypointDisplay(args);
        break;
      case "CMD":
        cmd = parseEntrypointDisplay(args);
        break;
    }
  }

  if (!fromImage) {
    errors.push("Missing FROM instruction");
  }

  const resolvedEntrypoint = entrypoint ?? cmd;
  if (!resolvedEntrypoint) {
    errors.push("Missing ENTRYPOINT or CMD");
  }

  return {
    fromImage,
    entrypoint: resolvedEntrypoint,
    hasRunCommands,
    isValid: errors.length === 0,
    errors,
  };
}

/**
 * Check if a FROM image is a prebuilt alias (instant, no build needed).
 */
export function isPrebuiltAlias(image: string): boolean {
  return PREBUILT_ALIASES.has(image);
}

/**
 * Human-readable display of entrypoint args.
 * ["python", "main.py"] → "python main.py"
 * python main.py → "python main.py"
 */
function parseEntrypointDisplay(args: string): string {
  const trimmed = args.trim();
  if (trimmed.startsWith("[")) {
    try {
      const parsed = JSON.parse(trimmed);
      if (Array.isArray(parsed)) {
        return parsed.join(" ");
      }
    } catch {
      // Fall through to raw display
    }
  }
  return trimmed;
}
