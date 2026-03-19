"""
Docker-based sandbox for validating LLM-generated step code.

Defense-in-depth: Layer 1 is an AST-based denylist scan (fast, no Docker),
Layer 2 is import-check in an isolated container (network=none, read-only FS,
512MB, no caps). Gracefully degrades when Docker is unavailable.
"""
import ast
import importlib.util
import json
import logging
import tempfile
import warnings
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result model (transient, NOT SQLModel)
# ---------------------------------------------------------------------------


class SandboxResult(BaseModel):
    """Result of a sandbox validation run."""

    import_ok: bool = False
    security_issues: list[str] = []
    sandbox_skipped: bool = True
    output: str = ""
    errors: list[str] = []
    modules_found: list[str] = []


# ---------------------------------------------------------------------------
# AST-based security validator
# ---------------------------------------------------------------------------


class _SecurityVisitor(ast.NodeVisitor):
    """AST visitor that collects security issues from blocked patterns."""

    BLOCKED_MODULES: frozenset[str] = frozenset({
        "os", "subprocess", "sys", "socket", "ctypes", "importlib",
        "builtins", "pickle", "marshal", "shelve", "pty", "tty",
        "signal", "resource", "mmap", "multiprocessing", "threading",
        "concurrent", "asyncio", "shutil", "tempfile", "pathlib",
        "glob", "fnmatch", "linecache", "tokenize", "code", "codeop",
        "compileall", "py_compile", "dis", "inspect", "gc",
        "tracemalloc", "faulthandler", "_thread",
    })

    BLOCKED_BUILTINS: frozenset[str] = frozenset({
        "eval", "exec", "compile", "open", "__import__", "breakpoint",
    })

    BLOCKED_ATTRIBUTES: frozenset[str] = frozenset({
        "system", "popen", "call", "Popen", "run",
        "check_output", "spawn", "execv", "execve", "fork",
    })

    def __init__(self) -> None:
        self.issues: list[str] = []

    # -- visitors --

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            top = alias.name.split(".")[0]
            if top in self.BLOCKED_MODULES:
                self.issues.append(
                    f"Blocked module import: {alias.name} (line {node.lineno})"
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            top = node.module.split(".")[0]
            if top in self.BLOCKED_MODULES:
                self.issues.append(
                    f"Blocked module import: {node.module} (line {node.lineno})"
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Direct builtin calls: eval(...), exec(...), __import__(...)
        if isinstance(node.func, ast.Name):
            if node.func.id in self.BLOCKED_BUILTINS:
                self.issues.append(
                    f"Blocked builtin call: {node.func.id}() (line {node.lineno})"
                )

        # Dotted attribute calls: os.system(...), subprocess.Popen(...)
        if isinstance(node.func, ast.Attribute):
            chain = self._resolve_attribute_chain(node.func)
            if chain:
                parts = chain.split(".")
                # Check if the attribute (last part) is blocked
                if parts[-1] in self.BLOCKED_ATTRIBUTES:
                    self.issues.append(
                        f"Blocked attribute call: {chain}() (line {node.lineno})"
                    )

        self.generic_visit(node)

    # -- helpers --

    @staticmethod
    def _resolve_attribute_chain(node: ast.expr) -> str | None:
        """Recursively build 'a.b.c' from nested ast.Attribute nodes."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = _SecurityVisitor._resolve_attribute_chain(node.value)
            if parent is not None:
                return f"{parent}.{node.attr}"
        return None


class CodeSecurityValidator:
    """Validates Python source code against a security denylist using AST analysis."""

    def validate(self, code: str) -> list[str]:
        """Return list of security issues found in code, empty if clean."""
        if not code or not code.strip():
            return []
        try:
            tree = ast.parse(code, mode="exec")
        except SyntaxError:
            # Syntax errors are handled elsewhere; security scan skips unparseable code
            return []
        visitor = _SecurityVisitor()
        visitor.visit(tree)
        return visitor.issues


# ---------------------------------------------------------------------------
# Docker sandbox executor
# ---------------------------------------------------------------------------

# run_test.py harness template -- injected into container at runtime
_RUN_TEST_PY = """\
import sys
import json

results = {"import_ok": False, "errors": [], "modules_found": []}
for module_file in sys.argv[1:]:
    module_name = module_file.replace(".py", "")
    try:
        __import__(module_name)
        results["modules_found"].append(module_name)
    except Exception as e:
        results["errors"].append(f"{module_name}: {type(e).__name__}: {e}")
results["import_ok"] = len(results["errors"]) == 0
print(json.dumps(results))
sys.exit(0 if results["import_ok"] else 1)
"""


class StepSandbox:
    """
    Docker-based sandbox for import-checking generated step code.

    Creates a locked-down container (no network, read-only FS, limited resources)
    and runs import checks on generated Python modules. Gracefully skips container
    execution when Docker is unavailable, but always performs AST security scan.
    """

    def __init__(self, image: str = "python:3.11-slim", timeout: int = 60) -> None:
        self.image = image
        self.timeout = timeout

    def _get_client(self):
        """Return docker client or None if unavailable."""
        try:
            import docker
        except ImportError:
            warnings.warn(
                "docker package not installed; sandbox container execution skipped. "
                "Install with: pip install llm-pipeline[sandbox]",
                stacklevel=2,
            )
            return None
        try:
            client = docker.from_env()
            client.ping()
            return client
        except Exception:
            warnings.warn(
                "Docker daemon not available; sandbox container execution skipped.",
                stacklevel=2,
            )
            return None

    def _discover_framework_path(self) -> str | None:
        """Auto-discover llm_pipeline package location for container mount."""
        spec = importlib.util.find_spec("llm_pipeline")
        if spec is None or not spec.submodule_search_locations:
            return None
        try:
            loc = spec.submodule_search_locations[0]
            # Parent is site-packages or source root
            return str(Path(loc).parent)
        except (IndexError, TypeError):
            return None

    def _write_files(
        self,
        tmpdir: Path,
        artifacts: dict[str, str],
        sample_data: dict | None,
    ) -> list[str]:
        """
        Write artifacts and test harness to tmpdir.

        Returns list of Python module filenames to import-check
        (excludes non-.py and YAML prompt files).
        """
        module_files: list[str] = []

        for filename, content in artifacts.items():
            filepath = tmpdir / filename
            filepath.write_text(content, encoding="utf-8")
            # Only include actual Python code files for import checking.
            # Files like {step}_prompts.py contain YAML, not Python -- skip them.
            if filename.endswith(".py") and not filename.endswith("_prompts.py"):
                module_files.append(filename)

        # Write test harness
        (tmpdir / "run_test.py").write_text(_RUN_TEST_PY, encoding="utf-8")

        # Write sample data if provided
        if sample_data is not None:
            (tmpdir / "sample_data.json").write_text(
                json.dumps(sample_data, default=str), encoding="utf-8"
            )

        return module_files

    def validate_code(self, code: str) -> list[str]:
        """Thin wrapper around CodeSecurityValidator.validate()."""
        return CodeSecurityValidator().validate(code)

    def run(
        self,
        artifacts: dict[str, str],
        sample_data: dict | None = None,
    ) -> SandboxResult:
        """
        Validate artifacts via AST scan + Docker container import check.

        1. AST security scan on all artifacts (always runs)
        2. Docker container import check (skipped if Docker unavailable)
        """
        # Layer 1: AST security scan
        all_issues: list[str] = []
        for filename, code in artifacts.items():
            if filename.endswith(".py") and not filename.endswith("_prompts.py"):
                issues = self.validate_code(code)
                all_issues.extend(issues)

        if all_issues:
            return SandboxResult(
                import_ok=False,
                security_issues=all_issues,
                sandbox_skipped=True,
                output="",
                errors=all_issues,
                modules_found=[],
            )

        # Layer 2: Docker container import check
        client = self._get_client()
        if client is None:
            return SandboxResult(
                import_ok=True,
                security_issues=[],
                sandbox_skipped=True,
                output="Docker unavailable; AST scan passed",
                errors=[],
                modules_found=[],
            )

        framework_path = self._discover_framework_path()
        if framework_path is None:
            warnings.warn(
                "Could not discover llm_pipeline package path; "
                "framework will not be available in sandbox.",
                stacklevel=2,
            )

        try:
            import docker
            from docker.types import Mount
        except ImportError:
            # Shouldn't happen since _get_client succeeded, but defensive
            return SandboxResult(
                import_ok=True,
                security_issues=[],
                sandbox_skipped=True,
                output="docker import failed after client init",
                errors=[],
                modules_found=[],
            )

        container = None
        try:
            with tempfile.TemporaryDirectory() as tmpdir_str:
                tmpdir = Path(tmpdir_str)
                module_files = self._write_files(tmpdir, artifacts, sample_data)

                if not module_files:
                    return SandboxResult(
                        import_ok=True,
                        security_issues=[],
                        sandbox_skipped=True,
                        output="No Python modules to import-check",
                        errors=[],
                        modules_found=[],
                    )

                # Build mounts
                mounts = [
                    Mount(
                        target="/code",
                        source=str(tmpdir),
                        type="bind",
                        read_only=False,
                    ),
                    Mount(
                        target="/workspace",
                        source="",
                        type="tmpfs",
                        tmpfs_size=67108864,  # 64MB
                    ),
                ]

                python_path_parts = ["/code"]

                if framework_path:
                    mounts.append(
                        Mount(
                            target="/mounted-site-packages",
                            source=framework_path,
                            type="bind",
                            read_only=True,
                        )
                    )
                    python_path_parts.append("/mounted-site-packages")

                environment = {
                    "PYTHONPATH": ":".join(python_path_parts),
                }

                command = ["python", "/code/run_test.py"] + module_files

                container = client.containers.create(
                    self.image,
                    command=command,
                    mounts=mounts,
                    network_mode="none",
                    read_only=True,
                    mem_limit="512m",
                    memswap_limit="512m",
                    cpu_period=100000,
                    cpu_quota=100000,
                    cap_drop=["ALL"],
                    security_opt=["no-new-privileges"],
                    pids_limit=50,
                    environment=environment,
                    auto_remove=False,
                )

                container.start()

                try:
                    from requests.exceptions import ReadTimeout
                    container.wait(timeout=self.timeout)
                except ReadTimeout:
                    container.kill()
                    logs = container.logs(stdout=True, stderr=True).decode(
                        "utf-8", errors="replace"
                    )
                    return SandboxResult(
                        import_ok=False,
                        security_issues=[],
                        sandbox_skipped=False,
                        output=logs,
                        errors=["Container timed out"],
                        modules_found=[],
                    )

                logs = container.logs(stdout=True, stderr=True).decode(
                    "utf-8", errors="replace"
                )

                # Parse last JSON line from stdout
                results = {"import_ok": False, "errors": [], "modules_found": []}
                stdout_logs = container.logs(stdout=True, stderr=False).decode(
                    "utf-8", errors="replace"
                )
                for line in reversed(stdout_logs.strip().splitlines()):
                    line = line.strip()
                    if line.startswith("{"):
                        try:
                            results = json.loads(line)
                            break
                        except json.JSONDecodeError:
                            continue

                return SandboxResult(
                    import_ok=results.get("import_ok", False),
                    security_issues=[],
                    sandbox_skipped=False,
                    output=logs,
                    errors=results.get("errors", []),
                    modules_found=results.get("modules_found", []),
                )

        except Exception as exc:
            # Catch docker.errors.DockerException and anything else
            logger.warning("Sandbox container error: %s", exc)
            return SandboxResult(
                import_ok=False,
                security_issues=[],
                sandbox_skipped=False,
                output=str(exc),
                errors=[f"Container error: {type(exc).__name__}: {exc}"],
                modules_found=[],
            )
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass


__all__ = ["SandboxResult", "CodeSecurityValidator", "StepSandbox"]
