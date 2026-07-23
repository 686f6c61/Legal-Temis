from legislacion.config import Ajustes
from legislacion.ia.fabrica import OPENROUTER_BASE_URL, crear_clientes


def _config(**kwargs) -> Ajustes:
    valores = {"anthropic_api_key": "", "openai_api_key": "", "openrouter_api_key": ""}
    valores.update(kwargs)
    return Ajustes(_env_file=None, **valores)


def test_sin_claves_no_hay_proveedores():
    assert crear_clientes(_config()) == {}


def test_openrouter_crea_una_entrada_por_modelo():
    clientes = crear_clientes(
        _config(openrouter_api_key="clave", modelos_openrouter="openai/gpt-5.5, x-ai/grok-4.5,")
    )
    assert sorted(clientes) == ["openrouter:openai/gpt-5.5", "openrouter:x-ai/grok-4.5"]
    cliente = clientes["openrouter:x-ai/grok-4.5"]
    assert cliente.nombre == "openrouter"
    assert cliente.modelo == "x-ai/grok-4.5"
    assert cliente._cliente.base_url.host == "openrouter.ai"


def test_lista_de_modelos_por_defecto():
    clientes = crear_clientes(_config(openrouter_api_key="clave"))
    assert len(clientes) == 7
    assert all(clave.startswith("openrouter:") for clave in clientes)


def test_todos_los_proveedores():
    clientes = crear_clientes(
        _config(
            anthropic_api_key="a",
            openai_api_key="b",
            openrouter_api_key="c",
            modelos_openrouter="openai/gpt-5.5",
        )
    )
    assert sorted(clientes) == ["anthropic", "openai", "openrouter:openai/gpt-5.5"]


def test_base_url_de_openrouter():
    assert OPENROUTER_BASE_URL == "https://openrouter.ai/api/v1"


def test_nan_crea_una_entrada_por_modelo():
    clientes = crear_clientes(_config(nan_api_key="clave", modelos_nan="qwen3.6, gemma4"))
    assert sorted(clientes) == ["nan:gemma4", "nan:qwen3.6"]
    cliente = clientes["nan:qwen3.6"]
    assert cliente.nombre == "nan"
    assert cliente._cliente.base_url.host == "api.nan.builders"


def test_lista_nan_por_defecto():
    clientes = crear_clientes(_config(nan_api_key="clave"))
    assert sorted(clientes) == [
        "nan:deepseek-v4-flash",
        "nan:gemma4",
        "nan:mimo-v2.5",
        "nan:qwen3.6",
    ]
