from legislacion.config import Ajustes
from legislacion.ia.anthropic_ia import AnthropicIA
from legislacion.ia.base import ClienteIA
from legislacion.ia.openai_ia import OpenAICompatibleIA

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
NAN_BASE_URL = "https://api.nan.builders/v1"

MODELOS_OPENROUTER_DEFECTO = (
    "openai/gpt-5.5,anthropic/claude-opus-4.8,anthropic/claude-sonnet-5,"
    "google/gemini-3.6-flash,x-ai/grok-4.5,deepseek/deepseek-v4-pro,"
    "mistralai/mistral-large-2512"
)

MODELOS_NAN_DEFECTO = "qwen3.6,deepseek-v4-flash,mimo-v2.5,gemma4"


def crear_clientes(config: Ajustes) -> dict[str, ClienteIA]:
    """Un cliente por proveedor con clave configurada. OpenRouter genera una
    entrada por cada modelo de su lista, con clave `openrouter:<modelo>`."""
    clientes: dict[str, ClienteIA] = {}
    if config.anthropic_api_key:
        clientes["anthropic"] = AnthropicIA(
            config.anthropic_api_key, config.modelo_anthropic, timeout=config.timeout_ia_segundos
        )
    if config.openai_api_key:
        clientes["openai"] = OpenAICompatibleIA(
            "openai",
            config.openai_api_key,
            config.modelo_openai,
            timeout=config.timeout_ia_segundos,
        )
    if config.openrouter_api_key:
        lista = config.modelos_openrouter or MODELOS_OPENROUTER_DEFECTO
        for modelo in [m.strip() for m in lista.split(",") if m.strip()]:
            clientes[f"openrouter:{modelo}"] = OpenAICompatibleIA(
                "openrouter",
                config.openrouter_api_key,
                modelo,
                base_url=OPENROUTER_BASE_URL,
                timeout=config.timeout_ia_segundos,
            )
    if config.nan_api_key:
        lista = config.modelos_nan or MODELOS_NAN_DEFECTO
        for modelo in [m.strip() for m in lista.split(",") if m.strip()]:
            clientes[f"nan:{modelo}"] = OpenAICompatibleIA(
                "nan",
                config.nan_api_key,
                modelo,
                base_url=NAN_BASE_URL,
                timeout=config.timeout_ia_segundos,
            )
    return clientes
