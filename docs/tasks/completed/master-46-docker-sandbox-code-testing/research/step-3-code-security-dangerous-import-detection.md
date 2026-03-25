# Research: Code Security & Dangerous Import Detection

## Scope
Security patterns for validating LLM-generated Python code before execution in Docker sandbox. Focuses on pre-scan layer (AST-based analysis) as first line of defense, with Docker isolation (network=none, resource limits) as second layer.

## Context
- LLM-generated code = non-adversarial but potentially incorrect/unsafe
- Generated code is pipeline step scaffolding: `LLMStep` subclasses, `PipelineContext`, `LLMResultMixin`
- Existing `_syntax_check` in `steps.py` already uses `ast.parse` for syntax validation
- `validate_code` in `sandbox.py` returns list of security warnings/errors
- Target: `llm_pipeline/creator/sandbox.py`, Python 3.11+, Pydantic v2

---

## 1. Dangerous Python Pattern Taxonomy

### Category A: System/Process Access (Critical)
| Pattern | Risk | Detection Method |
|---------|------|-----------------|
| `os.system(cmd)` | Arbitrary command execution | AST: Call node with `os.system` attribute |
| `os.popen(cmd)` | Command execution with pipe | AST: Call node with `os.popen` attribute |
| `os.exec*()` | Process replacement | AST: Call node with `os.exec*` attribute |
| `subprocess.*` | Full subprocess control | AST: Import/ImportFrom node for `subprocess` |
| `shutil.rmtree()` | Recursive directory deletion | AST: Import + Call detection |

### Category B: Dynamic Code Execution (Critical)
| Pattern | Risk | Detection Method |
|---------|------|-----------------|
| `eval(expr)` | Arbitrary expression evaluation | AST: Call node with Name `eval` |
| `exec(code)` | Arbitrary code execution | AST: Call node with Name `exec` |
| `compile(code)` | Code compilation for later exec | AST: Call node with Name `compile` |
| `code.interact()` | Interactive interpreter | AST: Import of `code` module |

### Category C: Dynamic Import Mechanisms (High)
| Pattern | Risk | Detection Method |
|---------|------|-----------------|
| `__import__(name)` | Dynamic module loading | AST: Call node with Name `__import__` |
| `importlib.import_module()` | Programmatic import | AST: Import of `importlib` |
| `importlib.util.spec_from_file_location()` | Load from arbitrary path | AST: Import of `importlib.util` |

### Category D: Builtin/Metaclass Manipulation (High)
| Pattern | Risk | Detection Method |
|---------|------|-----------------|
| `builtins.__import__` | Override import mechanism | AST: Import of `builtins` or attribute access |
| `__builtins__` | Direct builtins dict access | AST: Name node `__builtins__` |
| `type()` with 3 args | Dynamic class creation | AST: Call to `type` with 3+ args (tricky) |

### Category E: Low-Level / FFI Access (High)
| Pattern | Risk | Detection Method |
|---------|------|-----------------|
| `ctypes.*` | C function calls, memory access | AST: Import of `ctypes` |
| `cffi.*` | C Foreign Function Interface | AST: Import of `cffi` |
| `ctypes.cdll.LoadLibrary()` | Load arbitrary shared libs | AST: Import of `ctypes` (caught by above) |

### Category F: Network Access (Medium -- Docker network=none is backstop)
| Pattern | Risk | Detection Method |
|---------|------|-----------------|
| `socket.*` | Raw socket access | AST: Import of `socket` |
| `requests.*` | HTTP client | AST: Import of `requests` |
| `urllib.*` | URL handling | AST: Import of `urllib` |
| `http.client.*` | Low-level HTTP | AST: Import of `http.client` or `http` |
| `httpx.*` | Async HTTP client | AST: Import of `httpx` |
| `aiohttp.*` | Async HTTP client | AST: Import of `aiohttp` |

### Category G: Resource Exhaustion (Low -- Docker limits are backstop)
| Pattern | Risk | Detection Method |
|---------|------|-----------------|
| `multiprocessing.*` | Fork bomb potential | AST: Import of `multiprocessing` |
| `threading.*` | Thread exhaustion | AST: Import of `threading` |
| `signal.*` | Signal handler manipulation | AST: Import of `signal` |

---

## 2. AST-Based Analysis vs String Matching

### String Matching
```python
# Naive approach from task 46 spec
DANGEROUS_IMPORTS = ['os.system', 'subprocess', 'eval', 'exec', ...]
def validate_code(self, code: str) -> list[str]:
    errors = []
    for pattern in DANGEROUS_IMPORTS:
        if pattern in code:
            errors.append(f'Dangerous pattern detected: {pattern}')
    return errors
```

**Pros:**
- Trivial to implement (5 lines)
- Zero parsing overhead
- Works on syntactically invalid code
- Catches patterns in comments/strings (sometimes desired)

**Cons:**
- False positives: `my_subprocess_handler`, `# don't use eval`, `"eval"` in string literals, docstrings
- False negatives: `getattr(os, 'system')`, `globals()['eval']`, base64-encoded payloads
- Cannot distinguish `import subprocess` from `# import subprocess`
- Cannot detect aliased imports: `import subprocess as sp; sp.run()`
- Cannot detect `from os import system` separately from `import os`
- Brittle: adding a variable named `exec_mode` triggers false positive

### AST-Based Analysis
```python
import ast

class DangerousPatternVisitor(ast.NodeVisitor):
    def __init__(self):
        self.issues: list[str] = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            if alias.name in BLOCKED_MODULES:
                self.issues.append(
                    f"line {node.lineno}: blocked import '{alias.name}'"
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module and node.module.split('.')[0] in BLOCKED_MODULES:
            self.issues.append(
                f"line {node.lineno}: blocked import from '{node.module}'"
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # Detect eval(), exec(), __import__(), compile()
        if isinstance(node.func, ast.Name):
            if node.func.id in BLOCKED_BUILTINS:
                self.issues.append(
                    f"line {node.lineno}: blocked call to '{node.func.id}()'"
                )
        # Detect os.system(), subprocess.run(), etc.
        if isinstance(node.func, ast.Attribute):
            full_name = _resolve_attribute(node.func)
            if full_name and any(full_name.startswith(p) for p in BLOCKED_ATTRIBUTES):
                self.issues.append(
                    f"line {node.lineno}: blocked call to '{full_name}()'"
                )
        self.generic_visit(node)
```

**Pros:**
- Semantic accuracy: understands code structure, not just text
- No false positives from comments, strings, variable names
- Catches `import X`, `from X import Y`, `from X.Y import Z` precisely
- Detects specific function calls with attribute chain resolution
- Handles aliased imports (can track alias -> real name if needed)
- Line numbers for precise error reporting
- Already compatible with codebase (`steps.py` uses `ast.parse`)
- Can extend to detect patterns like attribute access chains

**Cons:**
- Requires syntactically valid Python (but `_syntax_check` runs first anyway)
- Cannot detect runtime-constructed patterns: `getattr(os, 'sys'+'tem')(...)`
- Cannot detect encoded payloads: `exec(base64.b64decode(...))`
- Slightly more complex implementation (~50-80 lines vs ~5 lines)
- Cannot detect patterns in `exec()`/`eval()` string arguments

### Recommendation: AST-Primary with String Fallback

Use AST analysis as primary detection mechanism. Supplement with targeted string checks for edge cases AST cannot catch (see Section 5). This aligns with existing codebase patterns (`ast.parse` already used in `_syntax_check`).

---

## 3. Python `ast` Module Implementation Patterns

### 3.1 Parsing
```python
tree = ast.parse(code, mode="exec")  # Parse full module
# mode="exec" = module level (imports, classes, functions)
# mode="eval" = single expression
# mode="single" = single interactive statement
```

### 3.2 Walking the Tree

Two approaches:

**`ast.walk(tree)` -- flat iteration (simpler, sufficient for import/call detection)**
```python
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        # handle import
    elif isinstance(node, ast.ImportFrom):
        # handle from-import
    elif isinstance(node, ast.Call):
        # handle function call
```

**`ast.NodeVisitor` -- visitor pattern (better for complex analysis)**
```python
class SecurityVisitor(ast.NodeVisitor):
    def visit_Import(self, node): ...
    def visit_ImportFrom(self, node): ...
    def visit_Call(self, node): ...
    def visit_Name(self, node): ...
    def visit_Attribute(self, node): ...
```

### 3.3 Key AST Node Types for Security Scanning

```python
# Import statement: import os, subprocess
ast.Import(names=[ast.alias(name='os'), ast.alias(name='subprocess')])

# From-import: from os import system
ast.ImportFrom(module='os', names=[ast.alias(name='system')])

# Function call: eval(code)
ast.Call(func=ast.Name(id='eval'), args=[...])

# Attribute call: os.system(cmd)
ast.Call(func=ast.Attribute(
    value=ast.Name(id='os'),
    attr='system'
))

# Nested attribute: urllib.request.urlopen(url)
ast.Call(func=ast.Attribute(
    value=ast.Attribute(
        value=ast.Name(id='urllib'),
        attr='request'
    ),
    attr='urlopen'
))
```

### 3.4 Attribute Chain Resolution Helper
```python
def _resolve_attribute_chain(node: ast.expr) -> str | None:
    """Resolve dotted attribute access to full name string.

    os.system -> 'os.system'
    urllib.request.urlopen -> 'urllib.request.urlopen'
    variable.method -> 'variable.method'
    complex[0].attr -> None (unresolvable)
    """
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return '.'.join(reversed(parts))
    return None  # Cannot resolve (subscript, call result, etc.)
```

### 3.5 Detecting `__import__` Calls
```python
# __import__('os') appears as:
ast.Call(func=ast.Name(id='__import__'), args=[ast.Constant(value='os')])

# Detection:
if isinstance(node.func, ast.Name) and node.func.id == '__import__':
    # Can also inspect args[0] if it's a Constant to get module name
    if node.args and isinstance(node.args[0], ast.Constant):
        module_name = node.args[0].value  # 'os'
```

---

## 4. Allowlist vs Denylist Approaches

### Denylist (Block known dangerous patterns)
```python
BLOCKED_MODULES = {
    'os', 'subprocess', 'importlib', 'builtins', 'ctypes', 'cffi',
    'socket', 'requests', 'urllib', 'http', 'httpx', 'aiohttp',
    'multiprocessing', 'threading', 'signal', 'shutil', 'code',
    'pty', 'commands', 'pdb', 'cProfile', 'profile', 'trace',
    'webbrowser', 'antigravity', 'turtle',
}
BLOCKED_BUILTINS = {'eval', 'exec', 'compile', '__import__', 'breakpoint'}
```

**Pros:** Permissive -- anything not blocked is allowed. Easier for LLM-generated code that may use unexpected-but-safe modules.
**Cons:** Must maintain list. New dangerous modules/patterns can slip through. Cat-and-mouse game.

### Allowlist (Only permit known safe patterns)
```python
ALLOWED_MODULES = {
    # Framework
    'llm_pipeline', 'pydantic', 'sqlmodel', 'sqlalchemy',
    # Standard lib (safe subset)
    'typing', 'typing_extensions', 'dataclasses', 'enum', 'abc',
    'collections', 'functools', 'itertools', 'operator',
    'datetime', 'decimal', 'fractions', 'math', 'statistics',
    'json', 'csv', 're', 'string', 'textwrap',
    'pathlib', 'copy', 'uuid', 'hashlib', 'hmac',
    'logging', 'warnings',
    # Common safe third-party
    'jinja2', 'yaml', 'pyyaml',
}
```

**Pros:** Explicit security boundary. Unknown = blocked by default (fail-secure). No cat-and-mouse.
**Cons:** Restrictive -- legitimate imports may be blocked. Requires updating allowlist when new safe imports are needed. May frustrate LLM code generation if it picks an unlisted-but-safe module.

### Recommendation: Allowlist with Override

For LLM-generated pipeline step code, the **allowlist approach is strongly recommended** because:

1. Generated step code has a well-defined scope: it only needs `llm_pipeline.*`, `pydantic`, `typing`, and select stdlib modules
2. The code template (`step.py.j2`) constrains what generated code looks like
3. Fail-secure: any unknown module triggers a clear error rather than silently allowing dangerous code
4. The LLM prompt (in `prompts.py`) can be updated to instruct the LLM to only use allowed modules

The allowlist should be:
- A module-level constant in `sandbox.py` (or imported from a config)
- Checked at the top-level module name: `import foo.bar` checks `foo`
- Overridable via constructor parameter for special cases

**Hybrid approach:** Use allowlist as primary, denylist as documentation/secondary signal for clear error messages when known-dangerous patterns are detected specifically.

---

## 5. Edge Cases and Evasion Patterns

### 5.1 Patterns AST Analysis Catches
| Pattern | AST Detection |
|---------|--------------|
| `import os` | `ast.Import` node, `alias.name == 'os'` |
| `from os import system` | `ast.ImportFrom` node, `module == 'os'` |
| `import subprocess as sp` | `ast.Import` node, `alias.name == 'subprocess'` |
| `eval("1+1")` | `ast.Call` node, `func.id == 'eval'` |
| `__import__('os')` | `ast.Call` node, `func.id == '__import__'` |
| `os.system('ls')` | `ast.Call` node, attribute chain resolution |

### 5.2 Patterns AST Analysis Misses (Docker Handles)
| Pattern | Why AST Misses | Docker Mitigation |
|---------|---------------|-------------------|
| `getattr(os, 'sys'+'tem')()` | String concatenation in runtime | network=none, read-only mounts |
| `globals()['__builtins__']['eval']` | Runtime dict lookup | Container isolation |
| `exec(base64.b64decode('aW1wb3J0IG9z'))` | Encoded payload in exec arg | exec itself is caught; if somehow bypassed, Docker contains |
| `type('X', (), {'__init__': lambda s: ...})` | Dynamic class creation | Resource limits, timeout |
| `sys.modules['os'].system('cmd')` | Module cache access | network=none blocks most damage |
| Pickle deserialization exploit | Not code pattern | No pickle in generated code context |

### 5.3 LLM-Specific Edge Cases
Since the code is LLM-generated (not adversarial), these are the realistic edge cases:
1. **LLM imports `os` for `os.path.join`**: Common LLM mistake. Pre-scan should flag `os` import but suggest `pathlib` alternative in error message. Or allowlist `os.path` specifically.
2. **LLM uses `open()` for file I/O**: `open` is a builtin, not an import. AST can detect `ast.Call` with `func.id == 'open'`. Decision: allow or block? Docker has read-only code mount + writable workspace, so risk is contained. Recommend: allow with warning.
3. **LLM generates `typing.TYPE_CHECKING` guarded imports**: These never execute. AST would still flag them. Consider: skip import checks inside `if TYPE_CHECKING:` blocks.
4. **LLM generates `try/except ImportError` blocks**: Common pattern for optional deps. AST still flags the import. Acceptable behavior -- the import is still present in source.

### 5.4 String-Based Supplementary Checks
For patterns AST cannot detect, add lightweight string checks:
```python
SUSPICIOUS_STRINGS = [
    r'base64\.b64decode',   # Encoded payloads
    r'codecs\.decode',      # Alternative encoding
    r'\\x[0-9a-f]{2}',     # Hex escape sequences in strings
    r'getattr\s*\(',        # Dynamic attribute access
    r'globals\s*\(\)',      # Global scope access
    r'locals\s*\(\)',       # Local scope access
    r'__dict__',            # Direct dict access
    r'__class__',           # Class manipulation
    r'__subclasses__',      # Subclass enumeration (sandbox escape)
]
```
These produce **warnings** (non-blocking) rather than errors, since they may have legitimate uses. Docker isolation handles the actual containment.

---

## 6. Defense-in-Depth: Pre-Scan vs Docker Isolation

### Layer 1: Pre-Scan (validate_code)
**Purpose:** Fast-fail with clear, actionable error messages before container overhead.

**Catches:**
- Explicit dangerous imports (blocked modules)
- Dangerous builtin calls (eval, exec, compile, __import__)
- Dangerous attribute calls (os.system, subprocess.run)
- Syntax errors (via ast.parse, already done in _syntax_check)
- Unknown/unallowed imports (via allowlist)

**Behavior:**
- Returns immediately with specific error messages including line numbers
- No container startup overhead (~10ms vs ~2-5s for Docker)
- Errors are developer-facing: "line 3: import 'subprocess' is not in the allowed modules list"
- Warnings are informational: "line 7: 'getattr()' detected -- dynamic attribute access may bypass security checks"

### Layer 2: Docker Container Isolation
**Purpose:** Contain any damage from patterns that bypass pre-scan or from legitimate-but-dangerous runtime behavior.

**Handles:**
- network=none: blocks all network access (exfiltration, C2, downloads)
- mem_limit=512m: prevents memory exhaustion attacks
- cpu_count=1: prevents CPU exhaustion
- timeout=60s: prevents infinite loops / long-running processes
- read-only code mount: prevents code self-modification
- No host filesystem access beyond mounted volumes
- No privileged operations (default unprivileged container)
- Process isolation: can't affect host processes

**What Docker catches that pre-scan misses:**
- Runtime-constructed imports/calls (getattr, globals, etc.)
- Resource exhaustion (while True, fork bombs via multiprocessing if somehow imported)
- Network access attempts (even if socket somehow loaded)
- File system damage (read-only mounts)

### Layer Interaction
```
LLM generates code
        |
        v
  [Pre-Scan Layer]
  ast.parse() -> syntax check
  AST walk -> import/call check
  Allowlist -> module check
  String scan -> suspicious patterns
        |
   pass/fail?
        |
  fail -> Return errors immediately (fast, descriptive)
  pass -> Continue to Docker
        |
        v
  [Docker Layer]
  network=none
  mem_limit=512m
  cpu_count=1
  timeout=60s
  read-only mounts
        |
        v
  Execute code safely
  Capture stdout/stderr
  Return SandboxResult
```

---

## 7. Recommended Implementation Structure

### 7.1 Constants
```python
# In sandbox.py or a dedicated security_constants.py

ALLOWED_MODULES: frozenset[str] = frozenset({
    # Framework
    'llm_pipeline', 'pydantic', 'sqlmodel', 'sqlalchemy',
    # Typing/ABC
    'typing', 'typing_extensions', 'dataclasses', 'enum', 'abc',
    # Collections/Functional
    'collections', 'functools', 'itertools', 'operator',
    # Data types
    'datetime', 'decimal', 'fractions', 'math', 'statistics',
    # Serialization/Text
    'json', 'csv', 're', 'string', 'textwrap',
    # Utilities
    'pathlib', 'copy', 'uuid', 'hashlib', 'hmac',
    # Logging
    'logging', 'warnings',
    # Third-party (safe)
    'jinja2', 'yaml',
})

BLOCKED_BUILTINS: frozenset[str] = frozenset({
    'eval', 'exec', 'compile', '__import__', 'breakpoint',
})

BLOCKED_ATTRIBUTES: frozenset[str] = frozenset({
    'os.system', 'os.popen', 'os.execl', 'os.execle', 'os.execlp',
    'os.execlpe', 'os.execv', 'os.execve', 'os.execvp', 'os.execvpe',
    'os.spawn', 'os.spawnl', 'os.spawnle',
    'subprocess.run', 'subprocess.call', 'subprocess.Popen',
    'subprocess.check_output', 'subprocess.check_call',
    'shutil.rmtree',
})
```

### 7.2 Validator Class Shape
```python
@dataclass
class SecurityIssue:
    line: int
    severity: str  # 'error' | 'warning'
    message: str
    pattern: str  # What was detected

class CodeSecurityValidator:
    """AST-based security validator for LLM-generated code."""

    def __init__(self, allowed_modules: frozenset[str] | None = None):
        self.allowed_modules = allowed_modules or ALLOWED_MODULES

    def validate(self, code: str) -> list[SecurityIssue]:
        """Full validation: syntax + AST security scan + string patterns."""
        issues = []

        # 1. Syntax check (ast.parse)
        try:
            tree = ast.parse(code, mode="exec")
        except SyntaxError as e:
            return [SecurityIssue(line=e.lineno or 0, severity='error',
                                  message=f'Syntax error: {e.msg}', pattern='syntax')]

        # 2. AST security walk
        issues.extend(self._check_imports(tree))
        issues.extend(self._check_calls(tree))

        # 3. Supplementary string checks (warnings only)
        issues.extend(self._check_suspicious_strings(code))

        return issues

    def has_errors(self, issues: list[SecurityIssue]) -> bool:
        return any(i.severity == 'error' for i in issues)
```

### 7.3 Integration with StepSandbox
The `validate_code` method on `StepSandbox` should delegate to `CodeSecurityValidator`:
```python
class StepSandbox:
    def __init__(self):
        self.validator = CodeSecurityValidator()
        self.client = docker.from_env()

    def validate_code(self, code: str) -> list[str]:
        """Pre-scan for dangerous imports. Returns error strings."""
        issues = self.validator.validate(code)
        return [f"{i.severity}: line {i.line}: {i.message}" for i in issues
                if i.severity == 'error']
```

This keeps the `validate_code` return type as `list[str]` per the task 46 spec while using structured `SecurityIssue` internally.

---

## 8. Existing Codebase Integration Points

### 8.1 `_syntax_check` in steps.py (line 234)
Already uses `ast.parse(code, mode="exec")`. The security validator should reuse the same parse call and extend it with security checks. Consider: refactor `_syntax_check` to use the new validator, or have the validator include syntax checking.

### 8.2 `CodeValidationStep` in steps.py (line 252)
Currently validates syntax only. After sandbox implementation, this step could optionally invoke `CodeSecurityValidator` to add security validation to the LLM validation pipeline itself.

### 8.3 `CodeGenerationInstructions.imports` field
The imports list from code generation is a natural integration point. The security validator could also validate these before they're rendered into templates.

---

## 9. Summary of Recommendations

1. **Use AST-based analysis as primary detection** -- aligns with existing `ast` usage in `steps.py`
2. **Use allowlist approach for imports** -- generated step code has well-defined, narrow scope
3. **Supplement with string-based checks for edge cases** -- produce warnings, not errors
4. **Structured `SecurityIssue` internally, `list[str]` at API boundary** -- matches task spec while enabling future severity filtering
5. **Pre-scan catches obvious patterns fast; Docker contains everything else** -- defense-in-depth
6. **Include line numbers in all error messages** -- AST nodes carry `lineno` attribute
7. **Make allowlist configurable via constructor** -- extensible for different pipeline contexts
8. **Do not block `open()`** -- Docker read-only mounts handle file safety; blocking `open` would break legitimate patterns
9. **Consider `TYPE_CHECKING` guard awareness** -- imports inside `if TYPE_CHECKING:` blocks never execute at runtime; could skip or downgrade to warning
10. **Keep validator as separate class from StepSandbox** -- single responsibility, independently testable
