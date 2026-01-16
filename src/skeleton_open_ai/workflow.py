import logging
from typing import Final

from skeleton_open_ai.schemas import ChatMessage

logger: Final = logging.getLogger(__name__)


def run_workflow(messages: list[ChatMessage], model: str) -> str:
    """
    Execute the AI workflow and return a response.

    This is a placeholder - implement your actual AI workflow here.

    Args:
        messages: The conversation history from the request
        model: The model name requested by the client

    Returns:
        The assistant's response as a string

    Raises:
        Any exception will crash the request (fail-fast principle).
        Do not catch exceptions here unless you can actually handle them.
    """
    logger.info(f"Workflow called: model='{model}', message_count={len(messages)}")

    # TODO: Implement actual AI workflow here
    # For now, return a placeholder response

    last_message = messages[-1].content if messages else "No messages provided"

    return (
        f"This is a placeholder response from model '{model}'. "
        f"Your message was: '{last_message}'. "
        f"Implement your workflow in workflow.py"
    )
