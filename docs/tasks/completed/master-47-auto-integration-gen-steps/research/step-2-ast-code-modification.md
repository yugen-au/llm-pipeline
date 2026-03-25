# Research: AST Code Modification for StepIntegrator

## Scope
How to safely modify existing pipeline Python files to:
1. Add a step to a strategy's `get_steps()` return list
2. Add a model to a registry's `models=[...]` class keyword

---

## Target Code Structures

### Strategy File (get_steps method)

Concrete pattern found in `llm_pipeline/demo/pipeline.py` and `llm_pipeline/creator/pipeline.py`:

```python
class DefaultStrategy(PipelineStrategy):
    def can_handle(self, context: dict[str, Any]) -> bool:
        return True

    def get_steps(self):
        return [
            SentimentAnalysisStep.create_definition(),
            TopicExtractionStep.create_definition(),
            SummaryStep.create_definition(),
        ]
```

To integrate a new step: append `NewStep.create_definition()` to the return list.

The `get_steps` method ALWAYS returns a list literal directly (no intermediate variable). This is consistent across all 10+ strategy implementations in the codebase.

### Registry File (class definition keyword)

```python
class TextAnalyzerRegistry(PipelineDatabaseRegistry, models=[Topic]):
    pass
```

The `models=[...]` list is a **class keyword argument** in the `ClassDef` node's `keywords` list - NOT a `MODELS = [...]` assignment. Adding a model requires modifying the class definition line itself.

Pattern is consistent: every concrete registry in the codebase uses `models=[...]` keyword, never `MODELS = [...]` assignment.

---

## AST Node Locations

### Strategy: get_steps return list

AST path:
```
Module.body -> ClassDef (name matches strategy class)
  -> FunctionDef (name == 'get_steps')
    -> Return
      -> List (the list of StepDefinition calls)
```

The `ast.List` node has `.elts` (elements) and the last element's `end_lineno`/`end_col_offset` tells us where to insert.

### Registry: models keyword

AST path:
```
Module.body -> ClassDef (name matches registry class)
  -> keywords[i] where keyword.arg == 'models'
    -> keyword.value (ast.List)
```

The `ast.List.end_lineno`/`end_col_offset` give the position of `]`.

---

## Recommended Approach: Hybrid AST-locate + String-replace

### Why not full AST round-trip?
`ast.unparse()` (Python 3.9+) strips all comments and reformats whitespace. Since pipeline files like `demo/pipeline.py` contain docstrings and inline comments, this is unacceptable.

### Why not libcst?
Would require adding `libcst` as a dependency. Overkill for two targeted append operations. The codebase has no existing libcst usage.

### Why not raw regex?
Fragile against code style variation (trailing commas, multiline vs single-line lists, whitespace).

### Recommended: AST-locate + targeted string splice

Two-phase approach:
1. **Locate phase**: Use `ast.parse()` to find precise line/column positions of the insertion point
2. **Splice phase**: Read file as lines, splice new element text at the located position

This:
- Preserves all comments, docstrings, formatting outside the modified area
- Uses reliable AST for location (not regex)
- Only touches the specific list being modified

---

## Implementation Details

### Phase 1: Locate insertion point

```python
import ast

def _find_list_end(source: str, class_name: str, list_type: str) -> tuple[int, int, str]:
    """
    Returns (line_number_0indexed, col_offset, indent_str) for insert point.
    list_type: 'get_steps' or 'models_keyword'
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            if list_type == 'get_steps':
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == 'get_steps':
                        for stmt in item.body:
                            if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.List):
                                lst = stmt.value
                                return (lst.end_lineno - 1, lst.end_col_offset - 1)
            elif list_type == 'models_keyword':
                for kw in node.keywords:
                    if kw.arg == 'models' and isinstance(kw.value, ast.List):
                        lst = kw.value
                        return (lst.end_lineno - 1, lst.end_col_offset - 1)
    raise ValueError(f"Could not find {list_type} in class {class_name}")
```

### Phase 2: String splice

```python
def _insert_before_closing_bracket(
    source: str,
    line_idx: int,
    col_idx: int,
    new_element: str,
    indent: str = "            ",
) -> str:
    lines = source.splitlines(keepends=True)
    line = lines[line_idx]

    # Determine if list has trailing comma
    preceding = line[:col_idx].rstrip()
    has_trailing_comma = preceding.endswith(',')

    if has_trailing_comma:
        # Insert new element on new line before ]
        insert = f"{indent}{new_element},\n"
        lines[line_idx] = line[:col_idx] + "\n" + insert + line[col_idx:]
    else:
        # Add comma to last element, then new element
        # Find end of last element in preceding text
        insert = f",\n{indent}{new_element},\n"
        lines[line_idx] = line[:col_idx] + insert + line[col_idx:]

    return "".join(lines)
```

### Single-line list edge case

If the list is on one line (`models=[Topic]`), the splice must expand it to multiline or insert inline. Detection:
```python
# If list start line == list end line, it's single-line
if lst.lineno == lst.end_lineno:
    # inline insert: models=[Topic, NewModel]
```

---

## New Text to Insert

### For get_steps (strategy file)
New element text: `NewStep.create_definition()`

Also requires an import at the top of the file:
```python
from .steps import NewStep  # or from llm_pipeline.some_module import NewStep
```

### For registry (models keyword)
New element text: `NewModel`

Also requires an import at the top of the file:
```python
from .models import NewModel  # or appropriate import path
```

**Import injection** is a separate concern - can use the same AST-locate + string-splice approach targeting the last import block, or simply append to the import section.

---

## Safety Pattern

```python
import shutil
import ast
from pathlib import Path

def safe_modify_file(file_path: Path, modify_fn) -> None:
    """Backup, modify, validate, or restore."""
    backup = file_path.with_suffix('.py.bak')
    shutil.copy2(file_path, backup)
    try:
        source = file_path.read_text(encoding='utf-8')
        new_source = modify_fn(source)
        # Validate syntax before writing
        ast.parse(new_source)
        # Atomic write via temp file
        tmp = file_path.with_suffix('.py.tmp')
        tmp.write_text(new_source, encoding='utf-8')
        tmp.replace(file_path)
        backup.unlink()  # clean up backup on success
    except Exception:
        shutil.copy2(backup, file_path)  # restore
        backup.unlink()
        raise
```

---

## Unresolved Questions for CEO

### Q1: How does StepIntegrator locate the file to modify?

The task 47 description passes `target_strategy: str` and `target_pipeline: str` as string names, but the integrator needs a file PATH to open and modify. No existing code shows how these names map to file paths.

Options:
- A) Pass explicit `strategy_file: Path` and `registry_file: Path` parameters
- B) Scan `target_dir` for Python files containing a class with the matching name (risky - slow, could find wrong file)
- C) `target_pipeline` is a dotted module path (e.g. `"myproject.pipeline"`) resolved via `importlib.util.find_spec`
- D) The integrator only generates files and AST modification is a separate manual step

**Recommendation**: Option A (explicit file paths). The caller (StepIntegrator.integrate) should receive `strategy_file: Path | None` and `registry_file: Path | None` directly.

### Q2: Should import statements also be injected?

When adding `NewStep.create_definition()` to a strategy, the file also needs `from ... import NewStep`. Similarly for registry models. Should `_update_strategy` and `_update_registry` also inject the import? Or is that out of scope for AST manipulation?

### Q3: Single-line vs multiline list handling

The demo registry is `models=[Topic]` (single-line). The strategy `get_steps()` is multiline. Should both cases be handled, or can we require/enforce multiline format first?

---

## Summary of Findings

| Target | AST Node Type | Modification | Approach |
|--------|---------------|--------------|----------|
| `get_steps()` return list | `ast.FunctionDef` > `ast.Return` > `ast.List` | Append `NewStep.create_definition()` | Hybrid: AST locate + string splice |
| `models=[...]` class keyword | `ast.ClassDef.keywords` where `arg='models'` | Append model class name | Hybrid: AST locate + string splice |

Both targets exist in a SINGLE file per pipeline (e.g., `demo/pipeline.py` contains both the registry class and strategy class). This means both modifications can be done in one file read/write cycle.

The stdlib `ast` module is sufficient for location; no external dependencies needed. `libcst` would be ideal but is not warranted given scope.
