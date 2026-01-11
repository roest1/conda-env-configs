#!/usr/bin/env python3
"""
Dependency Visualizer

Scans all environment.yml files in the repo, resolves referenced
requirements.txt files, and produces:

1. Mermaid graph of package → environment relationships
2. Cluster report showing shared package groupings across environments

Features:
- Ignores template / placeholder environments
- Resolves pip -r requirements.txt references
- Normalizes package names
- Detects version drift across environments
- Detects shared dependency clusters

Usage:
    python tools/generate_graph.py

Outputs:
    diagrams/dependency-graph.mmd
    diagrams/dependency-clusters.txt
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List, Set

try:
    import yaml
except Exception:
    print("❌ Missing dependency: PyYAML")
    print("   Install once in base env:  pip install PyYAML")
    raise

REPO_ROOT = Path(__file__).resolve().parents[1]
DIAGRAMS_DIR = REPO_ROOT / "diagrams"
GRAPH_FILE = DIAGRAMS_DIR / "dependency-graph.mmd"
CLUSTER_FILE = DIAGRAMS_DIR / "dependency-clusters.txt"
README_FILE = REPO_ROOT / "README.md"
README_START = "<!-- DEP_GRAPH_START -->"
README_END = "<!-- DEP_GRAPH_END -->"

# Ignore scaffolding folders
IGNORE_DIRS = {"template", ".git", ".github"}

ENV_DIRS = [
    p
    for p in REPO_ROOT.iterdir()
    if p.is_dir()
    and p.name not in IGNORE_DIRS
    and (p / "environment.yml").exists()
]

REQ_LINE_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)(?:==([^\s]+))?")


# -----------------------------
# Parsing
# -----------------------------

def normalize_pkg(name: str) -> str:
    return name.lower().replace("-", "_")


def parse_requirements(req_path: Path) -> Dict[str, str | None]:
    """Parse requirements.txt into {package: version|None}."""
    pkgs: Dict[str, str | None] = {}

    if not req_path.exists():
        # Ignore placeholder paths quietly
        if "<" in str(req_path) or "path" in str(req_path):
            return pkgs
        print(f"⚠️  requirements file not found: {req_path}")
        return pkgs

    for line in req_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        m = REQ_LINE_RE.match(line)
        if not m:
            continue

        name, version = m.groups()
        pkgs[normalize_pkg(name)] = version

    return pkgs


def load_envs() -> Dict[str, Dict[str, str | None]]:
    """Return {env_name: {package: version|None}}."""
    envs: Dict[str, Dict[str, str | None]] = {}

    for env_dir in ENV_DIRS:
        env_file = env_dir / "environment.yml"
        data = yaml.safe_load(env_file.read_text()) or {}
        env_name = data.get("name", env_dir.name)

        # Skip placeholder template envs
        if env_name.lower() in {"envname", "template"}:
            continue

        pkgs: Dict[str, str | None] = {}

        deps = data.get("dependencies", [])
        for dep in deps:
            if isinstance(dep, dict) and "pip" in dep:
                for entry in dep["pip"]:
                    if isinstance(entry, str) and entry.startswith("-r"):
                        rel_path = entry.split(maxsplit=1)[1]
                        req_path = (env_dir / rel_path).resolve()
                        pkgs.update(parse_requirements(req_path))

        envs[env_name] = pkgs

    return envs


# -----------------------------
# Analysis
# -----------------------------

def collect_versions(envs: Dict[str, Dict[str, str | None]]) -> Dict[str, Set[str]]:
    versions: Dict[str, Set[str]] = {}
    for pkgs in envs.values():
        for pkg, version in pkgs.items():
            versions.setdefault(pkg, set()).add(version or "*")
    return versions


def compute_clusters(envs: Dict[str, Dict[str, str | None]]) -> Dict[frozenset[str], Set[str]]:
    """
    Returns:
        { frozenset(env_names) : {package, ...} }
    """
    pkg_to_envs: Dict[str, Set[str]] = {}

    for env, pkgs in envs.items():
        for pkg in pkgs:
            pkg_to_envs.setdefault(pkg, set()).add(env)

    clusters: Dict[frozenset[str], Set[str]] = {}

    for pkg, env_set in pkg_to_envs.items():
        key = frozenset(sorted(env_set))
        clusters.setdefault(key, set()).add(pkg)

    return clusters


# -----------------------------
# Rendering
# -----------------------------

def build_mermaid(envs: Dict[str, Dict[str, str | None]]) -> str:
    """
    Render Mermaid graph using cluster subgraphs.

    Each cluster represents a set of environments that share packages.
    """
    drift_nodes: List[str] = []
    lines: List[str] = []
    lines.append("graph TD\n")

    clusters = compute_clusters(envs)
    versions = collect_versions(envs)

    def node_id(name: str) -> str:
        return re.sub(r"[^A-Za-z0-9_]", "_", name)

    # Sort clusters by size, then name
    def cluster_sort_key(item):
        env_set, _ = item
        return (len(env_set), sorted(env_set))

    for env_set, pkgs in sorted(clusters.items(), key=cluster_sort_key):
        env_label = " + ".join(sorted(env_set))
        cluster_name = "cluster_" + "_".join(sorted(env_set))
        cluster_id = node_id(cluster_name)

        lines.append(f'  subgraph {cluster_id}["{env_label}"]')

        for pkg in sorted(pkgs):
            version_set = versions.get(pkg, set())
            drift = len(version_set) > 1

            label = pkg
            versions_str = sorted(v for v in version_set if v != "*")
            if versions_str:
                label = f"{pkg}=={versions_str[0]}"
            if drift:
                label += " ⚠️"

            pkg_node = node_id(label)
            lines.append(f"    {pkg_node}[{label}]")

            if drift:
                drift_nodes.append(pkg_node)


        lines.append("  end\n")
    
    lines.append("") # append blank line before sytles
    for node in drift_nodes:
        lines.append(f"  style {node} fill:#ffe6e6,stroke:#ff0000,stroke-width:2px")

    return "\n".join(lines)

def build_cluster_report(clusters: Dict[frozenset[str], Set[str]]) -> str:
    lines: List[str] = []
    lines.append("📦 Dependency Clusters\n")

    for env_set in sorted(clusters.keys(), key=lambda s: (len(s), sorted(s))):
        pkgs = sorted(clusters[env_set])
        env_label = ", ".join(env_set)

        lines.append(f"[{env_label}]")
        for pkg in pkgs:
            lines.append(f"  - {pkg}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# -----------------------------
# Writing to README.md
# -----------------------------

def inject_graph_into_readme(mermaid: str) -> None:
    if not README_FILE.exists():
        print("⚠️ README.md not found — skipping injection")
        return

    text = README_FILE.read_text()

    if README_START not in text or README_END not in text:
        print("⚠️ README markers not found — skipping injection")
        return

    before, rest = text.split(README_START, 1)
    _, after = rest.split(README_END, 1)

    injected = (
        f"{before}{README_START}\n\n"
        f"```mermaid\n{mermaid}```\n\n"
        f"{README_END}{after}"
    )

    README_FILE.write_text(injected)


# -----------------------------
# Main
# -----------------------------

def main() -> int:
    DIAGRAMS_DIR.mkdir(exist_ok=True)

    envs = load_envs()
    if not envs:
        print("❌ No environments found")
        return 1

    # Graph
    mermaid = build_mermaid(envs)
    GRAPH_FILE.write_text(mermaid)
    inject_graph_into_readme(mermaid)

    # Clusters
    clusters = compute_clusters(envs)
    cluster_text = build_cluster_report(clusters)
    CLUSTER_FILE.write_text(cluster_text)

    print(f"✅ Wrote {GRAPH_FILE.relative_to(REPO_ROOT)}")
    print("✅ Updated README.md")
    print(f"✅ Wrote {CLUSTER_FILE.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
