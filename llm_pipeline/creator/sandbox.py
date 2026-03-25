"""
Docker-based sandbox for validating LLM-generated step code.

Defense-in-depth: Layer 1 is an AST-based denylist scan (fast, no Docker),
Layer 2 is import-check in an isolated container (network=none, read-only FS,
512MB, no caps). Gracefully degrades when Docker is unavailable.
"""
import ast
import json
import logging
import re
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
    module_name = "pkg." + module_file.replace(".py", "")
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

    On first use, auto-builds a sandbox image with deps derived from the
    installed llm-pipeline package metadata (no hardcoded dep list).
    """

    SANDBOX_IMAGE = "llm-pipeline-sandbox"

    def __init__(self, base_image: str = "python:3.11-slim", timeout: int = 60) -> None:
        self.base_image = base_image
        self.timeout = timeout

    def _get_client(self):
        """Return docker client or None if unavailable."""
        try:
            import docker
        except ImportError:
            warnings.warn(
                "docker package not installed; sandbox container execution skipped. "
                "Install with: pip install llm-pipeline[sandbox]",
                category=UserWarning,
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
                category=UserWarning,
                stacklevel=2,
            )
            return None

    @staticmethod
    def _find_project_root() -> Path | None:
        """Find llm-pipeline project root (dir containing pyproject.toml)."""
        import importlib.util
        spec = importlib.util.find_spec("llm_pipeline")
        if spec is None or not spec.submodule_search_locations:
            return None
        pkg_dir = Path(spec.submodule_search_locations[0])
        root = pkg_dir.parent
        if (root / "pyproject.toml").exists():
            return root
        return None

    @staticmethod
    def _source_hash(project_root: Path) -> str:
        """Hash of pyproject.toml + package source for cache invalidation."""
        import hashlib
        h = hashlib.sha256()
        # Hash pyproject.toml for dep changes
        h.update((project_root / "pyproject.toml").read_bytes())
        # Hash all .py files in llm_pipeline/ for code changes
        pkg_dir = project_root / "llm_pipeline"
        for py in sorted(pkg_dir.rglob("*.py")):
            h.update(py.read_bytes())
        return h.hexdigest()[:12]

    def _ensure_image(self, client) -> str:
        """Build sandbox image from local source. Returns image tag."""
        project_root = self._find_project_root()
        if project_root is None:
            raise RuntimeError("Cannot find llm-pipeline project root")

        tag = f"{self.SANDBOX_IMAGE}:{self._source_hash(project_root)}"

        try:
            client.images.get(tag)
            logger.debug("Sandbox image %s already exists", tag)
            return tag
        except Exception:
            pass

        # Build from project root: install core deps then copy source
        # (avoids hatch-vcs needing .git and build hook needing npm)
        from importlib.metadata import requires
        reqs = requires("llm-pipeline") or []
        core_deps = [r.split(";")[0].strip() for r in reqs if "; extra ==" not in r]
        pip_line = " ".join(f'"{d}"' for d in sorted(core_deps))

        dockerfile_content = (
            f"FROM {self.base_image}\n"
            f"RUN pip install --no-cache-dir {pip_line}\n"
            "COPY llm_pipeline/ /usr/local/lib/python3.11/site-packages/llm_pipeline/\n"
        )
        # Write temp Dockerfile into project root for build context
        dockerfile_path = project_root / ".sandbox.Dockerfile"
        try:
            dockerfile_path.write_text(dockerfile_content)
            logger.info("Building sandbox image %s from local source ...", tag)
            client.images.build(
                path=str(project_root),
                dockerfile=".sandbox.Dockerfile",
                tag=tag,
                rm=True,
                quiet=True,
            )
            logger.info("Sandbox image %s built successfully", tag)
        finally:
            dockerfile_path.unlink(missing_ok=True)

        return tag

    def _write_files(
        self,
        tmpdir: Path,
        artifacts: dict[str, str],
        sample_data: dict | None,
    ) -> list[str]:
        """
        Write artifacts into a proper Python package (pkg/) under tmpdir.

        Layout:
            tmpdir/
              run_test.py
              sample_data.json        (if provided)
              pkg/
                __init__.py           (empty)
                {step}_step.py        (artifact)
                {step}_instructions.py(artifact)
                schemas.py            (alias re-exporting from _instructions)
                models.py             (stub classes for .models imports)

        Returns list of Python module filenames to import-check
        (excludes non-.py and YAML prompt files).
        """
        pkg_dir = tmpdir / "pkg"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("", encoding="utf-8")

        module_files: list[str] = []
        instructions_module: str | None = None

        for filename in artifacts:
            if filename.endswith("_instructions.py"):
                instructions_module = filename.replace(".py", "")

        # -- Build schemas.py: re-export from _instructions + stub Context --

        # 1. Find class names defined in the instructions artifact
        instructions_classes: set[str] = set()
        if instructions_module:
            instr_content = artifacts.get(f"{instructions_module}.py", "")
            for m in re.finditer(r"^class\s+(\w+)", instr_content, re.MULTILINE):
                instructions_classes.add(m.group(1))

        # 2. Collect all names artifacts import from .schemas
        schema_names: set[str] = set()
        for content in artifacts.values():
            for m in re.finditer(r"from\s+\.schemas\s+import\s+(.+)", content):
                for name in m.group(1).split(","):
                    name = name.strip()
                    if name and name != "*":
                        schema_names.add(name)

        # 3. All names schemas.py will export
        all_schema_exports = instructions_classes | schema_names

        # 4. Write schemas.py
        schema_lines: list[str] = []
        if instructions_module and instructions_classes:
            names_csv = ", ".join(sorted(instructions_classes))
            schema_lines.append(f"from .{instructions_module} import {names_csv}")
        stub_names = schema_names - instructions_classes
        if stub_names:
            schema_lines.append("from llm_pipeline.context import PipelineContext")
            for name in sorted(stub_names):
                schema_lines.append(f"class {name}(PipelineContext): pass")
        (pkg_dir / "schemas.py").write_text(
            "\n".join(schema_lines) + "\n", encoding="utf-8"
        )

        # -- Write artifacts into pkg/, patching missing schema imports --
        for filename, content in artifacts.items():
            if filename.endswith(".py") and not filename.endswith("_prompts.py"):
                # Find names used as bare identifiers that schemas.py exports
                # but the file doesn't import from .schemas
                already_imported: set[str] = set()
                for m in re.finditer(r"from\s+\.schemas\s+import\s+(.+)", content):
                    for name in m.group(1).split(","):
                        name = name.strip()
                        if name == "*":
                            already_imported = all_schema_exports
                        elif name:
                            already_imported.add(name)
                # Names this file defines itself (don't inject imports for those)
                locally_defined: set[str] = set()
                for m in re.finditer(r"^class\s+(\w+)", content, re.MULTILINE):
                    locally_defined.add(m.group(1))
                missing = {
                    n for n in all_schema_exports - already_imported - locally_defined
                    if re.search(r"\b" + re.escape(n) + r"\b", content)
                }
                if missing:
                    inject = "from .schemas import " + ", ".join(sorted(missing))
                    content = inject + "\n" + content

            (pkg_dir / filename).write_text(content, encoding="utf-8")
            if filename.endswith(".py") and not filename.endswith("_prompts.py"):
                module_files.append(filename)

        # Stub: models.py -> generate BaseModel stubs for any `from .models import X`
        model_names: set[str] = set()
        for content in artifacts.values():
            for m in re.finditer(r"from\s+\.models\s+import\s+(.+)", content):
                for name in m.group(1).split(","):
                    name = name.strip()
                    if name and name != "*":
                        model_names.add(name)
        if model_names:
            lines = ["from pydantic import BaseModel\n"]
            for name in sorted(model_names):
                lines.append(f"class {name}(BaseModel): pass\n")
            (pkg_dir / "models.py").write_text("\n".join(lines), encoding="utf-8")
        else:
            (pkg_dir / "models.py").write_text("", encoding="utf-8")

        # Write test harness at tmpdir root (outside pkg/)
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

        try:
            from docker.types import Mount
        except ImportError:
            return SandboxResult(
                import_ok=True,
                security_issues=[],
                sandbox_skipped=True,
                output="docker import failed after client init",
                errors=[],
                modules_found=[],
            )

        # Build sandbox image with deps (cached after first build)
        try:
            image_tag = self._ensure_image(client)
        except Exception as exc:
            logger.warning("Failed to build sandbox image: %s", exc)
            return SandboxResult(
                import_ok=True,
                security_issues=[],
                sandbox_skipped=True,
                output=f"Sandbox image build failed: {exc}",
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

                environment = {"PYTHONPATH": "/code"}
                command = ["python", "/code/run_test.py"] + module_files

                container = client.containers.create(
                    image_tag,
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
                parsed = False
                results = {"import_ok": False, "errors": [], "modules_found": []}
                stdout_logs = container.logs(stdout=True, stderr=False).decode(
                    "utf-8", errors="replace"
                )
                for line in reversed(stdout_logs.strip().splitlines()):
                    line = line.strip()
                    if line.startswith("{"):
                        try:
                            results = json.loads(line)
                            parsed = True
                            break
                        except json.JSONDecodeError:
                            continue

                errors = results.get("errors", [])
                if not parsed:
                    errors.append("Could not parse container output")

                return SandboxResult(
                    import_ok=results.get("import_ok", False),
                    security_issues=[],
                    sandbox_skipped=False,
                    output=logs,
                    errors=errors,
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
