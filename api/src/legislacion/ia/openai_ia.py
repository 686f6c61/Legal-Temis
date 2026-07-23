import json

from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel, ValidationError


class OpenAICompatibleIA:
    """Proveedor para la API de OpenAI y para OpenRouter (compatible OpenAI).

    Si el modelo no soporta salidas estructuradas nativas (caso frecuente en
    OpenRouter según el modelo elegido), degrada a modo JSON con validación
    Pydantic local."""

    def __init__(
        self,
        nombre: str,
        api_key: str,
        modelo: str,
        base_url: str | None = None,
        timeout: float = 90.0,
    ) -> None:
        self.nombre = nombre
        self.modelo = modelo
        self._cliente = AsyncOpenAI(
            api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0
        )

    async def estructurar[T: BaseModel](
        self, sistema: str, usuario: str, esquema: type[T]
    ) -> T | None:
        try:
            respuesta = await self._cliente.chat.completions.parse(
                model=self.modelo,
                messages=[
                    {"role": "system", "content": sistema},
                    {"role": "user", "content": usuario},
                ],
                response_format=esquema,
            )
            return respuesta.choices[0].message.parsed
        except OpenAIError:
            return await self._estructurar_via_json(sistema, usuario, esquema)

    async def _estructurar_via_json[T: BaseModel](
        self, sistema: str, usuario: str, esquema: type[T]
    ) -> T | None:
        instrucciones = (
            f"{sistema}\n\nResponde únicamente con un objeto JSON válido conforme a este "
            f"esquema, sin texto adicional:\n{json.dumps(esquema.model_json_schema())}"
        )
        texto = await self.generar(instrucciones, usuario)
        if texto is None:
            return None
        try:
            return esquema.model_validate_json(texto.strip().strip("`").removeprefix("json"))
        except ValidationError:
            return None

    async def generar(self, sistema: str, usuario: str) -> str | None:
        try:
            respuesta = await self._cliente.chat.completions.create(
                model=self.modelo,
                messages=[
                    {"role": "system", "content": sistema},
                    {"role": "user", "content": usuario},
                ],
            )
        except OpenAIError:
            return None
        return respuesta.choices[0].message.content
