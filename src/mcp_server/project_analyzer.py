"""
Universal Project Structure Analyzer for Diagram Generation.

Analyzes any project type (Python, Node.js, etc.) and generates
appropriate architecture diagrams dynamically.
"""

import json
from pathlib import Path
from typing import Any


def analyze_project_structure(project_path: Path) -> dict[str, Any]:
    """Analyze project to determine type, structure, and key components.

    Args:
        project_path: Path to project root

    Returns:
        Dictionary with project metadata:
        - project_type: python, nodejs, rust, go, etc.
        - entry_points: main files
        - structure: directories and key files
        - dependencies: from package managers
        - components: detected logical components
    """
    analysis = {
        "project_type": "unknown",
        "entry_points": [],
        "directories": {},
        "key_files": [],
        "dependencies": {},
        "components": [],
        "git_initialized": False,
    }

    # Check git
    if (project_path / ".git").exists():
        analysis["git_initialized"] = True

    # Detect AtlasTrinity (Internal)
    if project_path.name == "atlastrinity" or (project_path / "src" / "brain").exists():
        analysis["project_type"] = "atlastrinity"
        analysis.update(_analyze_atlastrinity_project(project_path))

    # Detect Python project
    elif (project_path / "requirements.txt").exists() or (project_path / "pyproject.toml").exists():
        analysis["project_type"] = "python"
        analysis.update(_analyze_python_project(project_path))

    # Detect Node.js project
    elif (project_path / "package.json").exists():
        analysis["project_type"] = "nodejs"
        analysis.update(_analyze_nodejs_project(project_path))

    # Detect Rust project
    elif (project_path / "Cargo.toml").exists():
        analysis["project_type"] = "rust"
        analysis.update(_analyze_rust_project(project_path))

    # Detect Go project
    elif (project_path / "go.mod").exists():
        analysis["project_type"] = "go"
        analysis.update(_analyze_go_project(project_path))

    # Generic fallback
    else:
        analysis.update(_analyze_generic_project(project_path))

    return analysis


def _analyze_python_project(project_path: Path) -> dict[str, Any]:
    """Analyze Python project structure."""
    info: dict[str, Any] = {
        "entry_points": [],
        "key_files": [],
        "components": [],
        "directories": {},
    }

    # Find entry points
    for pattern in ["main.py", "app.py", "__main__.py", "run.py", "start.py"]:
        if (project_path / pattern).exists():
            info["entry_points"].append(pattern)

    # Find src/ or package directories
    src_dirs = ["src", "app", project_path.name]
    for src_dir in src_dirs:
        src_path = project_path / src_dir
        if src_path.exists() and src_path.is_dir():
            info["directories"][src_dir] = list(src_path.glob("*.py"))
            # Detect components
            for py_file in src_path.rglob("*.py"):
                if py_file.stem not in ["__init__", "__pycache__"]:
                    info["components"].append(py_file.stem.replace("_", " ").title())

    # Parse requirements
    req_file = project_path / "requirements.txt"
    if req_file.exists():
        deps = req_file.read_text().strip().split("\n")
        info["dependencies"] = {dep.split("==")[0]: dep for dep in deps if dep.strip()}

    # Parse pyproject.toml
    pyproject = project_path / "pyproject.toml"
    if pyproject.exists():
        info["key_files"].append("pyproject.toml")

    return info


def _analyze_nodejs_project(project_path: Path) -> dict[str, Any]:
    """Analyze Node.js project structure."""
    info: dict[str, Any] = {
        "entry_points": [],
        "key_files": [],
        "components": [],
        "directories": {},
    }

    # Parse package.json
    pkg_json = project_path / "package.json"
    if pkg_json.exists():
        try:
            pkg_data = json.loads(pkg_json.read_text())
            info["key_files"].append("package.json")

            # Get main entry point
            if "main" in pkg_data:
                info["entry_points"].append(pkg_data["main"])

            # Get dependencies
            info["dependencies"] = pkg_data.get("dependencies", {})
        except Exception:
            pass

    # Find common entry points
    for pattern in ["index.js", "index.ts", "app.js", "app.ts", "server.js", "main.js"]:
        if (project_path / pattern).exists() and pattern not in info["entry_points"]:
            info["entry_points"].append(pattern)

    # Analyze src/ structure
    src_path = project_path / "src"
    if src_path.exists():
        info["directories"]["src"] = []
        for item in src_path.iterdir():
            if item.is_dir():
                info["components"].append(item.name.replace("-", " ").title())
            elif item.suffix in [".js", ".ts", ".tsx"]:
                info["directories"]["src"].append(item.name)

    return info


def _analyze_rust_project(project_path: Path) -> dict[str, Any]:
    """Analyze Rust project structure."""
    info: dict[str, Any] = {
        "entry_points": ["src/main.rs"],
        "key_files": ["Cargo.toml"],
        "components": [],
        "dependencies": {},
    }

    # Parse Cargo.toml for dependencies
    cargo_toml = project_path / "Cargo.toml"
    if cargo_toml.exists():
        # Simple parsing - could use toml library
        content = cargo_toml.read_text()
        if "[dependencies]" in content:
            info["dependencies"] = {}  # type: ignore[typeddict-item]  # Would parse here

    # Analyze src/
    src_path = project_path / "src"
    if src_path.exists():
        for rs_file in src_path.glob("*.rs"):
            if rs_file.stem != "main":
                info["components"].append(rs_file.stem.replace("_", " ").title())

    return info


def _analyze_go_project(project_path: Path) -> dict[str, Any]:
    """Analyze Go project structure."""
    info = {"entry_points": [], "key_files": ["go.mod"], "components": []}

    # Find main.go
    for main_file in project_path.rglob("main.go"):
        info["entry_points"].append(str(main_file.relative_to(project_path)))

    # Analyze cmd/ and pkg/ structure
    for dir_name in ["cmd", "pkg", "internal"]:
        dir_path = project_path / dir_name
        if dir_path.exists():
            for item in dir_path.iterdir():
                if item.is_dir():
                    info["components"].append(item.name.title())

    return info


def _analyze_generic_project(project_path: Path) -> dict[str, Any]:
    """Analyze unknown project type."""
    info: dict[str, Any] = {"entry_points": [], "key_files": [], "components": []}

    # Find common files
    for pattern in [
        "README.md",
        "README.txt",
        "Makefile",
        "CMakeLists.txt",
        ".gitignore",
    ]:
        if (project_path / pattern).exists():
            info["key_files"].append(pattern)

    # List top-level directories
    for item in project_path.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            info["components"].append(item.name.title())

    return info


def _analyze_atlastrinity_project(project_path: Path) -> dict[str, Any]:
    """Analyze AtlasTrinity specific structure."""
    info: dict[str, Any] = {
        "entry_points": ["src/main/main.ts", "src/brain/server.py"],
        "key_files": ["package.json", "pyproject.toml", "config/config.yaml.template"],
        "components": [],
        "directories": {},
    }

    # Detect Brain components (Core Logic)
    brain_path = project_path / "src" / "brain"
    if brain_path.exists():
        info["directories"]["brain"] = []
        # Core submodules
        for item in brain_path.iterdir():
            if item.is_dir() and item.name not in ["__pycache__", "data", "tests", "mcp"]:
                component_name = f"Brain.{item.name.title()}"
                info["components"].append(component_name)
                info["directories"]["brain"].append(item.name)

    # Detect MCP Servers
    mcp_path = project_path / "src" / "mcp_server"
    if mcp_path.exists():
        info["directories"]["mcp_server"] = []
        for item in mcp_path.iterdir():
            # Check for _server.py files or directories like "golden_fund"
            valid_server = False
            server_name = ""
            if item.suffix == ".py" and item.stem.endswith("_server"):
                server_name = item.stem.replace("_server", "").title()
                valid_server = True
            elif item.is_dir() and (item / "server.py").exists():
                server_name = item.name.title()
                valid_server = True

            if valid_server:
                info["components"].append(f"MCP.{server_name}")
                info["directories"]["mcp_server"].append(item.name)

    # Detect Frontend
    renderer_path = project_path / "src" / "renderer"
    if renderer_path.exists():
        info["directories"]["renderer"] = ["components", "hooks", "pages"]
        info["components"].append("Frontend.React")

    return info


def detect_changed_components(
    project_analysis: dict[str, Any], git_diff: str, modified_files: list[str]
) -> list[str]:
    """Detect which components were affected by changes.

    This is universal - works for any project type.

    Args:
        project_analysis: Result from analyze_project_structure
        git_diff: Git diff output
        modified_files: List of modified file paths

    Returns:
        List of affected component names
    """
    affected = set()

    # Map files to components dynamically
    for file_path in modified_files:
        # Check if file is an entry point
        for entry_point in project_analysis.get("entry_points", []):
            if entry_point in file_path:
                affected.add("Main Entry Point")

        # Check directory mapping
        for dir_name in project_analysis.get("directories", {}):
            if dir_name in file_path:
                affected.add(f"{dir_name.title()} Module")

        # Check components
        for component in project_analysis.get("components", []):
            component_slug = component.lower().replace(" ", "_")
            if component_slug in file_path.lower():
                affected.add(component)

    return list(affected)
