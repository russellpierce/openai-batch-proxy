from skeleton_open_ai.schemas import ChatMessage
from skeleton_open_ai.workflow import run_workflow


def test_workflow_returns_string() -> None:
    """Test that workflow returns a string response."""
    messages = [ChatMessage(role="user", content="Hello!")]
    result = run_workflow(messages=messages, model="test-model")

    assert isinstance(result, str)
    assert len(result) > 0


def test_workflow_receives_messages() -> None:
    """Test that workflow receives the messages list."""
    messages = [
        ChatMessage(role="system", content="You are helpful."),
        ChatMessage(role="user", content="Test message content"),
    ]
    result = run_workflow(messages=messages, model="test-model")

    # Placeholder includes last message content
    assert "Test message content" in result


def test_workflow_receives_model_name() -> None:
    """Test that workflow receives the model name."""
    messages = [ChatMessage(role="user", content="Hi")]
    result = run_workflow(messages=messages, model="custom-model-name")

    # Placeholder includes model name
    assert "custom-model-name" in result
