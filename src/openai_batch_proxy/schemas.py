from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    """A single message in a chat conversation."""

    role: str  # "system", "user", "assistant"
    content: str


class ChatCompletionRequest(BaseModel):
    """Request body for chat completion endpoint."""

    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[ChatMessage] = Field(min_length=1)
    # Optional fields (accepted but may be ignored by workflow)
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    n: int | None = None
    stop: str | list[str] | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    user: str | None = None


class Usage(BaseModel):
    """Token usage statistics."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class Choice(BaseModel):
    """A single completion choice."""

    index: int
    message: ChatMessage
    finish_reason: str  # "stop", "length", etc.


class ChatCompletionResponse(BaseModel):
    """Response body for chat completion endpoint."""

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: Usage = Field(default_factory=Usage)


class ModelInfo(BaseModel):
    """Information about a single model."""

    id: str
    object: str = "model"
    created: int
    owned_by: str = "custom"


class ModelsListResponse(BaseModel):
    """Response body for models list endpoint."""

    object: str = "list"
    data: list[ModelInfo]


class HealthResponse(BaseModel):
    """Response body for health check endpoint."""

    status: str = "healthy"
