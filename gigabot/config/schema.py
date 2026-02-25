"""Configuration schema for GigaBot."""

from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from pydantic.alias_generators import to_camel
from pydantic_settings import BaseSettings


class Base(BaseModel):
    """Base model: accepts both camelCase and snake_case keys."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class GigaChatConfig(Base):
    """GigaChat API configuration."""
    credentials: str = ""
    scope: str = "GIGACHAT_API_PERS"
    model: str = "GigaChat-2-Max"
    verify_ssl_certs: bool = False
    max_tokens: int = 8192
    temperature: float = 0.7
    timeout: float = 120.0


class SaluteSpeechConfig(Base):
    """SaluteSpeech API configuration."""
    credentials: str = ""  # base64(client_id:client_secret)
    scope: str = "SALUTE_SPEECH_PERS"
    stt_model: str = "general"
    tts_voice: str = "Nec_24000"


class TelegramConfig(Base):
    """Telegram channel configuration."""
    enabled: bool = False
    token: str = ""
    allow_from: list[str] = Field(default_factory=list)
    proxy: str | None = None
    reply_to_message: bool = False


class RAGConfig(Base):
    """RAG configuration."""
    chroma_dir: str = "~/.gigabot/rag_db"
    embed_model: str = "EmbeddingsGigaR"
    chunk_size: int = 3500
    chunk_overlap: int = 400
    top_k: int = 5


class WebSearchConfig(Base):
    """Web search tool configuration."""
    api_key: str = ""
    max_results: int = 5


class ExecToolConfig(Base):
    """Shell exec tool configuration."""
    timeout: int = 60


class ToolsConfig(Base):
    """Tools configuration."""
    web: WebSearchConfig = Field(default_factory=WebSearchConfig)
    exec: ExecToolConfig = Field(default_factory=ExecToolConfig)
    restrict_to_workspace: bool = False


class AgentConfig(Base):
    """Agent behavior configuration."""
    workspace: str = "~/.gigabot/workspace"
    max_tool_iterations: int = 20
    memory_window: int = 50


class GatewayConfig(Base):
    """Gateway/server configuration."""
    host: str = "0.0.0.0"
    port: int = 18800


class Config(BaseSettings):
    """Root configuration for GigaBot."""
    gigachat: GigaChatConfig = Field(default_factory=GigaChatConfig)
    salute_speech: SaluteSpeechConfig = Field(default_factory=SaluteSpeechConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)

    @property
    def workspace_path(self) -> Path:
        return Path(self.agent.workspace).expanduser()

    model_config = ConfigDict(env_prefix="GIGABOT_", env_nested_delimiter="__")
