from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Ajustes(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LEGISLACION_", env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    openrouter_api_key: str = ""
    nan_api_key: str = ""
    proveedor_defecto: str = "anthropic"
    modelo_anthropic: str = "claude-opus-4-8"
    modelo_openai: str = "gpt-5"
    modelos_openrouter: str = ""
    modelos_nan: str = ""
    redis_url: str = "redis://legislacion-redis:6379/0"
    cache_ttl_segundos: int = 6 * 3600
    boe_base_url: str = "https://www.boe.es/datosabiertos/api/legislacion-consolidada"
    eurlex_sparql_url: str = "https://publications.europa.eu/webapi/rdf/sparql"
    timeout_fuentes_segundos: float = 20.0
    timeout_ia_segundos: float = 90.0
    max_resultados: int = 10
    limite_consulta_por_minuto: int = 20
    limite_comparar_por_minuto: int = 5
    cors_origenes: str = "*"


@lru_cache
def ajustes() -> Ajustes:
    return Ajustes()
