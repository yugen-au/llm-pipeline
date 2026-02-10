"""
Prompt synchronization from YAML files to database.

Prompts are stored in YAML files organized by step/context, and synced
to the database via migrations or standalone script.
"""
import os
import re
import yaml
import logging
from pathlib import Path
from sqlmodel import select
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


def extract_variables_from_content(content: str) -> List[str]:
    """
    Extract variable names from prompt content.

    Finds all {variable_name} patterns and returns unique variable names.
    """
    pattern = r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}'
    variables = re.findall(pattern, content)
    seen = set()
    unique_vars = []
    for var in variables:
        if var not in seen:
            seen.add(var)
            unique_vars.append(var)
    return unique_vars


def get_prompts_dir() -> Path:
    """
    Get prompts directory from environment or use default.

    Environment variable: PROMPTS_DIR
    Default: ./prompts (relative to current working directory)
    """
    prompts_dir = os.getenv('PROMPTS_DIR')
    if prompts_dir:
        return Path(prompts_dir)
    # Default: cwd/prompts (generic, not hardcoded to any project structure)
    return Path.cwd() / 'prompts'


def load_prompt(yaml_path: Path) -> Dict[str, Any]:
    """Load a single prompt from YAML file."""
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    required = ['prompt_key', 'name', 'type', 'category', 'step', 'version', 'content']
    for field in required:
        if field not in data:
            raise ValueError(f"Missing required field '{field}' in {yaml_path}")
    return data


def load_all_prompts(prompts_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load all prompts from YAML files in prompts directory."""
    if prompts_dir is None:
        prompts_dir = get_prompts_dir()
    if not prompts_dir.exists():
        raise FileNotFoundError(f"Prompts directory not found: {prompts_dir}")

    prompts = []
    for yaml_file in prompts_dir.rglob('*.yaml'):
        try:
            prompt = load_prompt(yaml_file)
            prompts.append(prompt)
        except Exception as e:
            logger.warning(f"  Warning: Failed to load {yaml_file}: {e}")
    for yml_file in prompts_dir.rglob('*.yml'):
        try:
            prompt = load_prompt(yml_file)
            prompts.append(prompt)
        except Exception as e:
            logger.warning(f"  Warning: Failed to load {yml_file}: {e}")
    return prompts


def sync_prompts(bind, prompts_dir: Optional[Path] = None, force: bool = False) -> Dict[str, int]:
    """
    Sync prompts from YAML files to database.

    Behavior:
    - Inserts new prompts (new prompt_key)
    - Updates existing prompts if version number increased
    - Skips if version unchanged (idempotent)
    - Force flag updates all prompts regardless of version
    - Automatically extracts required_variables from content
    """
    from llm_pipeline.db.prompt import Prompt

    session = Session(bind=bind)
    inserted = 0
    updated = 0
    skipped = 0

    try:
        prompts = load_all_prompts(prompts_dir)
        logger.info(f"\nSyncing {len(prompts)} prompts from YAML files...")

        for prompt_data in prompts:
            required_vars = extract_variables_from_content(prompt_data['content'])
            existing = session.exec(select(Prompt).where(
                Prompt.prompt_key == prompt_data['prompt_key'],
                Prompt.prompt_type == prompt_data['type']
            )).first()

            if existing:
                new_version = prompt_data.get('version', '1.0')
                current_version = existing.version or '1.0'

                if force or _version_greater(new_version, current_version):
                    existing.prompt_name = prompt_data['name']
                    existing.prompt_type = prompt_data['type']
                    existing.category = prompt_data['category']
                    existing.step_name = prompt_data['step']
                    existing.content = prompt_data['content']
                    existing.required_variables = required_vars if required_vars else None
                    existing.description = prompt_data.get('description')
                    existing.version = new_version
                    existing.is_active = prompt_data.get('is_active', True)
                    updated += 1
                    logger.info(f"  [UPDATE] {prompt_data['prompt_key']} (v{current_version} -> v{new_version})")
                else:
                    skipped += 1
            else:
                prompt = Prompt(
                    prompt_key=prompt_data['prompt_key'],
                    prompt_name=prompt_data['name'],
                    prompt_type=prompt_data['type'],
                    category=prompt_data['category'],
                    step_name=prompt_data['step'],
                    content=prompt_data['content'],
                    required_variables=required_vars if required_vars else None,
                    description=prompt_data.get('description'),
                    version=prompt_data.get('version', '1.0'),
                    is_active=prompt_data.get('is_active', True),
                )
                session.add(prompt)
                inserted += 1
                vars_str = f" [{', '.join(required_vars)}]" if required_vars else ""
                logger.info(f"  + Inserted: {prompt_data['prompt_key']} (v{prompt_data.get('version', '1.0')}){vars_str}")

        session.commit()
        logger.info(f"\nPrompt sync complete: {inserted} inserted, {updated} updated, {skipped} skipped")
        return {'inserted': inserted, 'updated': updated, 'skipped': skipped}

    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def _version_greater(new: str, current: str) -> bool:
    """Compare semantic versions."""
    try:
        new_parts = [int(x) for x in new.split('.')]
        current_parts = [int(x) for x in current.split('.')]
        max_len = max(len(new_parts), len(current_parts))
        new_parts += [0] * (max_len - len(new_parts))
        current_parts += [0] * (max_len - len(current_parts))
        return new_parts > current_parts
    except Exception:
        return True


__all__ = ['sync_prompts', 'load_all_prompts', 'get_prompts_dir', 'extract_variables_from_content']
