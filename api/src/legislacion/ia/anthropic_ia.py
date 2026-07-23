from anthropic import AnthropicError, AsyncAnthropic
from pydantic import BaseModel


class AnthropicIA:
    nombre = "anthropic"

    def __init__(self, api_key: str, modelo: str, timeout: float = 90.0) -> None:
        self._cliente = AsyncAnthropic(api_key=api_key, timeout=timeout)
        self.modelo = modelo

    async def estructurar[T: BaseModel](
        self, sistema: str, usuario: str, esquema: type[T]
    ) -> T | None:
        try:
            respuesta = await self._cliente.messages.parse(
                model=self.modelo,
                max_tokens=1024,
                system=[{"type": "text", "text": sistema, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": usuario}],
                output_format=esquema,
            )
        except AnthropicError:
            return None
        if respuesta.stop_reason == "refusal":
            return None
        return respuesta.parsed_output

    async def generar(self, sistema: str, usuario: str) -> str | None:
        try:
            respuesta = await self._cliente.messages.create(
                model=self.modelo,
                max_tokens=2048,
                system=[{"type": "text", "text": sistema, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": usuario}],
            )
        except AnthropicError:
            return None
        if respuesta.stop_reason == "refusal":
            return None
        return next((b.text for b in respuesta.content if b.type == "text"), None)
