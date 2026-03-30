"""
Prompt service for retrieving LLM prompts from database.
"""
from typing import Optional, Any
from sqlmodel import Session, select
from llm_pipeline.db.prompt import Prompt
from llm_pipeline.prompts.utils import extract_variables_from_content


class PromptService:
    """Service for retrieving prompts from database."""

    def __init__(self, session: Session):
        self.session = session

    def get_prompt(
        self,
        prompt_key: str,
        prompt_type: str = 'system',
        context: Optional[dict] = None,
        fallback: Optional[str] = None
    ) -> str:
        """Get a prompt by key and type, optionally filtered by context."""
        stmt = select(Prompt).where(
            Prompt.prompt_key == prompt_key,
            Prompt.prompt_type == prompt_type,
            Prompt.is_active == True
        )

        if context:
            context_match = self.session.exec(
                stmt.where(Prompt.context.contains(context))
            ).first()
            if context_match:
                return context_match.content

        base_prompt = self.session.exec(stmt).first()
        if base_prompt:
            return base_prompt.content

        if fallback is not None:
            return fallback

        raise ValueError(
            f"Prompt not found: {prompt_key}"
            + (f" with context {context}" if context else "")
        )

    def get_system_instruction(
        self,
        step_name: str,
        fallback: Optional[str] = None
    ) -> str:
        """Get system instruction for a pipeline step."""
        prompt_key = f"{step_name}.system_instruction"
        return self.get_prompt(prompt_key=prompt_key, fallback=fallback)

    def get_guidance(
        self,
        step_name: str,
        table_type: Optional[str] = None,
        fallback: str = ""
    ) -> str:
        """Get guidance text for a step, filtered by table type."""
        if table_type:
            prompt_key = f"{step_name}.guidance.{table_type}"
            context = {"table_type": table_type}
        else:
            prompt_key = f"{step_name}.guidance"
            context = None
        return self.get_prompt(
            prompt_key=prompt_key,
            context=context,
            fallback=fallback
        )

    def prompt_exists(self, prompt_key: str) -> bool:
        """Check if a prompt exists in the database."""
        return self.session.exec(
            select(Prompt).where(
                Prompt.prompt_key == prompt_key,
                Prompt.is_active == True
            )
        ).first() is not None

    def get_system_prompt(
        self,
        prompt_key: str,
        variables: dict,
        variable_instance: Optional[Any] = None,
        context: Optional[dict] = None,
        fallback: Optional[str] = None
    ) -> str:
        """Get system prompt template and format with variables."""
        template = self.get_prompt(
            prompt_key=prompt_key,
            prompt_type='system',
            context=context,
            fallback=fallback
        )
        try:
            return template.format(**variables)
        except KeyError as e:
            template_requires = extract_variables_from_content(template)
            class_defines = None
            if variable_instance is not None and hasattr(variable_instance, 'model_fields'):
                class_defines = list(type(variable_instance).model_fields.keys())

            error_parts = [
                f"System prompt template variable {e} not provided.",
                "",
                f"Template requires:  {template_requires}",
            ]
            if class_defines is not None:
                error_parts.append(f"Class defines:      {class_defines}")
            error_parts.append(f"Runtime provided:   {list(variables.keys())}")

            if class_defines is not None:
                missing_from_class = [v for v in template_requires if v not in class_defines]
                if missing_from_class:
                    error_parts.extend([
                        "",
                        f"Missing from class: {missing_from_class}",
                        f"ACTION: Add missing variables to prompts/{prompt_key.split('.')[0]}/system_prompt.yaml and regenerate"
                    ])
            raise ValueError("\n".join(error_parts))

    def get_user_prompt(
        self,
        prompt_key: str,
        variables: dict,
        variable_instance: Optional[Any] = None,
        context: Optional[dict] = None,
        fallback: Optional[str] = None
    ) -> str:
        """Get user prompt template and format with variables."""
        template = self.get_prompt(
            prompt_key=prompt_key,
            prompt_type='user',
            context=context,
            fallback=fallback
        )
        try:
            return template.format(**variables)
        except KeyError as e:
            template_requires = extract_variables_from_content(template)
            class_defines = None
            if variable_instance is not None and hasattr(variable_instance, 'model_fields'):
                class_defines = list(type(variable_instance).model_fields.keys())

            error_parts = [
                f"User prompt template variable {e} not provided.",
                "",
                f"Template requires:  {template_requires}",
            ]
            if class_defines is not None:
                error_parts.append(f"Class defines:      {class_defines}")
            error_parts.append(f"Runtime provided:   {list(variables.keys())}")

            if class_defines is not None:
                missing_from_class = [v for v in template_requires if v not in class_defines]
                if missing_from_class:
                    error_parts.extend([
                        "",
                        f"Missing from class: {missing_from_class}",
                        f"ACTION: Add missing variables to prompts/{prompt_key.split('.')[0]}/user_prompt.yaml and regenerate"
                    ])
            raise ValueError("\n".join(error_parts))


__all__ = ["PromptService"]
