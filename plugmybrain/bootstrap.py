# Wires this machine's agents to the server: registers it with Claude Code and Codex, and
# installs the /pmb-* commands. Standard library only, so any Python on the host runs it.
#
#   python -m plugmybrain.bootstrap
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from plugmybrain import config

SERVER = "plugmybrain"
COMMANDS = config.REPO_ROOT / "commands"


@dataclass
class SetupReport:
    wired: list[str] = field(default_factory=list)
    installed: list[Path] = field(default_factory=list)
    removed: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def mcp_url() -> str:
    """Where the server listens; the publish port is a variable, so it is read, not assumed."""
    return f"http://127.0.0.1:{os.getenv('MCP_PUBLISH_PORT', '9000')}/mcp"


def _wire_claude(report: SetupReport) -> None:
    """Register the server through Claude Code's own CLI, so its config format stays its own."""
    claude = shutil.which("claude")
    command = ["mcp", "add", "--transport", "http", SERVER, mcp_url(), "--scope", "user"]
    if claude is None:
        report.warnings.append(f"claude is not on PATH. Run: claude {' '.join(command)}")
        return
    result = subprocess.run([claude, *command], capture_output=True, text=True)
    # Already registered is success for a setup that is safe to re-run
    if result.returncode and "already exists" not in (result.stdout + result.stderr).lower():
        report.warnings.append(f"claude mcp add failed: {result.stderr.strip()[:200]}")
        return
    report.wired.append(f"Claude Code > {mcp_url()}")


def _wire_codex(report: SetupReport, home: Path) -> None:
    """Append the server to Codex's config.toml; `codex mcp add` takes stdio servers only."""
    path = home / ".codex" / "config.toml"
    block = (
        f'\n[mcp_servers.{SERVER}]\nurl = "{mcp_url()}"\n'
        "startup_timeout_sec = 60\ntool_timeout_sec = 120\n"
    )
    if path.is_file():
        if f"[mcp_servers.{SERVER}]" in path.read_text(encoding="utf-8"):
            report.wired.append(f"Codex > {mcp_url()} (already present)")
            return
        with path.open("a", encoding="utf-8") as handle:
            handle.write(block)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(block.lstrip("\n"), encoding="utf-8")
    report.wired.append(f"Codex > {mcp_url()}")


def stale_commands(directory: Path, keep: set[str]) -> list[Path]:
    """Commands this project installed once and no longer ships. The pmb prefix is ours alone."""
    if not directory.is_dir():
        return []
    return [path for path in sorted(directory.glob("pmb*.md")) if path.name not in keep]


def install_commands(report: SetupReport, home: Path) -> None:
    """Copy every /pmb-* command into both agents, and remove the ones no longer shipped."""
    templates = sorted(COMMANDS.glob("pmb*.md"))
    if not templates:
        report.warnings.append(f"no commands in {COMMANDS}, so nothing was installed")
        return
    keep = {template.name for template in templates}
    for directory in (home / ".claude" / "commands", home / ".codex" / "prompts"):
        directory.mkdir(parents=True, exist_ok=True)
        for template in templates:
            target = directory / template.name
            shutil.copyfile(template, target)
            report.installed.append(target)
        for stale in stale_commands(directory, keep):
            stale.unlink()
            report.removed.append(stale)


def setup(home: Path | None = None, wire: bool = True) -> SetupReport:
    """Safe to re-run: config files are appended to, and only our own commands are replaced."""
    home = Path.home() if home is None else home
    report = SetupReport()
    if wire:
        _wire_claude(report)
        _wire_codex(report, home)
    install_commands(report, home)
    return report


def main() -> int:
    report = setup()
    for line in report.wired:
        print(f"wired:     {line}")
    commands = sorted({path.stem for path in report.installed})
    print(f"installed: {', '.join('/' + name for name in commands)}")
    for path in report.removed:
        print(f"removed:   {path}, no longer shipped")
    for warning in report.warnings:
        print(f"WARNING:   {warning}")
    print("\nRestart Claude Code and Codex: both load commands and servers at start.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
