"""GigaChat provider — direct integration via gigachat SDK."""

from __future__ import annotations

import json
import uuid
from typing import Any

import json_repair
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole, Function
from loguru import logger

from gigabot.providers.base import LLMProvider, LLMResponse, ToolCallRequest


def _openai_tools_to_gigachat_functions(tools: list[dict[str, Any]]) -> list[Function]:
    """Convert OpenAI-format tool definitions to GigaChat Function objects."""
    functions = []
    for tool in tools:
        func = tool.get("function", tool)
        functions.append(Function(
            name=func["name"],
            description=func.get("description", ""),
            parameters=func.get("parameters", {}),
        ))
    return functions


def _convert_messages_to_gigachat(messages: list[dict[str, Any]]) -> list[Messages]:
    """Convert OpenAI-format messages to GigaChat Messages."""
    result = []
    for msg in messages:
        role_str = msg.get("role", "user")
        content = msg.get("content") or ""

        if role_str == "system":
            result.append(Messages(role=MessagesRole.SYSTEM, content=content))

        elif role_str == "user":
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text_parts.append(part["text"])
                result.append(Messages(role=MessagesRole.USER, content="\n".join(text_parts) or ""))
            else:
                result.append(Messages(role=MessagesRole.USER, content=content))

        elif role_str == "assistant":
            giga_msg = Messages(role=MessagesRole.ASSISTANT, content=content or "")
            if msg.get("tool_calls"):
                tc = msg["tool_calls"][0]
                func = tc.get("function", {})
                args_raw = func.get("arguments", "{}")
                if isinstance(args_raw, str):
                    try:
                        args_raw = json.loads(args_raw)
                    except (json.JSONDecodeError, TypeError):
                        args_raw = {}
                from gigachat.models import FunctionCall
                giga_msg.function_call = FunctionCall(
                    name=func.get("name", ""),
                    arguments=args_raw,
                )
            if msg.get("functions_state_id"):
                giga_msg.functions_state_id = msg["functions_state_id"]
            result.append(giga_msg)

        elif role_str == "tool":
            # GigaChat requires function results to be valid JSON
            try:
                json.loads(content)
                json_content = content
            except (json.JSONDecodeError, TypeError):
                json_content = json.dumps({"result": content}, ensure_ascii=False)
            result.append(Messages(
                role=MessagesRole.FUNCTION,
                content=json_content,
            ))

    return result


class GigaChatProvider(LLMProvider):
    """LLM provider using GigaChat SDK directly.

    Supports chat completions with function calling, streaming,
    embeddings, and file operations via the official gigachat package.
    """

    def __init__(
        self,
        credentials: str,
        scope: str = "GIGACHAT_API_PERS",
        model: str = "GigaChat-2-Max",
        verify_ssl_certs: bool = False,
        timeout: float = 120.0,
    ):
        self.default_model = model
        self._credentials = credentials
        self._scope = scope
        self._verify_ssl = verify_ssl_certs
        self._timeout = timeout

        self._client = GigaChat(
            credentials=credentials,
            scope=scope,
            model=model,
            verify_ssl_certs=verify_ssl_certs,
            timeout=timeout,
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        model = model or self.default_model
        giga_messages = _convert_messages_to_gigachat(messages)

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": giga_messages,
            "max_tokens": max(1, max_tokens),
            "temperature": temperature,
        }

        if tools:
            kwargs["functions"] = _openai_tools_to_gigachat_functions(tools)
            kwargs["function_call"] = "auto"

        try:
            chat_request = Chat(**kwargs)
            response = self._client.chat(chat_request)
            return self._parse_response(response)
        except Exception as e:
            logger.error("GigaChat API error: {}", e)
            return LLMResponse(
                content=f"Error calling GigaChat: {str(e)}",
                finish_reason="error",
            )

    def _parse_response(self, response: Any) -> LLMResponse:
        """Parse GigaChat response into standard LLMResponse."""
        choice = response.choices[0]
        message = choice.message

        tool_calls = []
        if message.function_call:
            fc = message.function_call
            args = fc.arguments if isinstance(fc.arguments, dict) else {}
            if isinstance(fc.arguments, str):
                try:
                    args = json_repair.loads(fc.arguments)
                except Exception:
                    args = {}

            tool_calls.append(ToolCallRequest(
                id=str(uuid.uuid4())[:8],
                name=fc.name,
                arguments=args,
            ))

        usage = {}
        if hasattr(response, "usage") and response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        content = message.content
        if tool_calls and not content:
            content = ""

        functions_state_id = getattr(message, "functions_state_id", None)

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
            functions_state_id=functions_state_id,
        )

    def get_embeddings(self, texts: list[str], model: str = "Embeddings") -> list[list[float]]:
        """Get embeddings for RAG via GigaChat Embeddings API."""
        response = self._client.embeddings(texts=texts, model=model)
        return [item.embedding for item in response.data]

    def get_image(self, file_id: str) -> bytes:
        """Retrieve a generated image by file_id."""
        response = self._client.get_image(file_id)
        import base64
        return base64.b64decode(response.content)

    def get_default_model(self) -> str:
        return self.default_model
