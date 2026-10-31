"""OpenRouter Chat Completions with lossless provider reasoning fields."""

from copy import deepcopy
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

FIELDS = ("reasoning", "reasoning_content", "reasoning_details")


class OpenRouterChatModel(ChatOpenAI):
    def with_structured_output(self, schema=None, *, method=None, **kwargs):
        # Routed providers (e.g. DeepSeek) reject the json_schema response_format
        # ChatOpenAI defaults to ("This response_format type is unavailable now").
        # Tool calling carries the same schema, but structured output forces the
        # tool, and thinking mode refuses a forced tool_choice; so the formatting
        # call runs with reasoning off. Earlier turns keep their own setting.
        if method:
            return super().with_structured_output(schema, method=method, **kwargs)
        formatter = self.model_copy(
            update={"extra_body": {**(self.extra_body or {}), "reasoning": {"enabled": False}}}
        )
        return ChatOpenAI.with_structured_output(
            formatter, schema, method="function_calling", **kwargs
        )

    def _create_chat_result(self, response, generation_info=None):
        result = super()._create_chat_result(response, generation_info)
        raw = response if isinstance(response, dict) else response.model_dump()
        for generation, choice in zip(result.generations, raw.get("choices", [])):
            message = choice.get("message", {})
            if raw.get("provider"):
                generation.message.response_metadata["inference_provider"] = raw["provider"]
            for field in FIELDS:
                if field in message:
                    generation.message.additional_kwargs[field] = deepcopy(message[field])
        return result

    def _convert_chunk_to_generation_chunk(self, chunk, default_chunk_class, base_generation_info):
        result = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        choices = chunk.get("choices", []) or chunk.get("chunk", {}).get("choices", [])
        if result is not None and choices:
            delta = choices[0].get("delta") or {}
            for field in FIELDS:
                if field in delta:
                    result.message.additional_kwargs[field] = deepcopy(delta[field])
        return result

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        messages = self._convert_input(input_).to_messages()
        for source, target in zip(messages, payload.get("messages", [])):
            if isinstance(source, AIMessage):
                for field in FIELDS:
                    if field in source.additional_kwargs:
                        target[field] = deepcopy(source.additional_kwargs[field])
        return payload
