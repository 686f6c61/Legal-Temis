import json
from types import SimpleNamespace

import pytest
from openai import OpenAIError
from pydantic import BaseModel

from legislacion.ia.anthropic_ia import AnthropicIA
from legislacion.ia.comprension import Comprension
from legislacion.ia.openai_ia import OpenAICompatibleIA
from legislacion.ia.redaccion import Redaccion
from legislacion.modelos import Articulo, ConsultaEstructurada, Norma, NormaDetalle, Rango


class Dato(BaseModel):
    x: int


NORMA = Norma(
    identificador="BOE-A-2026-423",
    titulo="Ley 5/2025, de Vivienda de Andalucía.",
    comunidad="andalucia",
    rango="Ley",
    vigente=True,
    url_oficial="https://www.boe.es/buscar/act.php?id=BOE-A-2026-423",
    fuente="boe",
)


def _async(valor):
    async def _fn(*_args, **_kwargs):
        return valor

    return _fn


def _async_error(excepcion):
    async def _fn(*_args, **_kwargs):
        raise excepcion

    return _fn


# --- AnthropicIA ---


def _anthropic_con(parse=None, create=None) -> AnthropicIA:
    ia = AnthropicIA("clave", "modelo-test")
    ia._cliente = SimpleNamespace(messages=SimpleNamespace(parse=parse, create=create))
    return ia


@pytest.mark.asyncio
async def test_anthropic_estructurar():
    respuesta = SimpleNamespace(stop_reason="end_turn", parsed_output=Dato(x=1))
    ia = _anthropic_con(parse=_async(respuesta))
    assert await ia.estructurar("s", "u", Dato) == Dato(x=1)


@pytest.mark.asyncio
async def test_anthropic_estructurar_rechazo_devuelve_none():
    respuesta = SimpleNamespace(stop_reason="refusal", parsed_output=None)
    ia = _anthropic_con(parse=_async(respuesta))
    assert await ia.estructurar("s", "u", Dato) is None


@pytest.mark.asyncio
async def test_anthropic_generar():
    bloques = [SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text="hola")]
    respuesta = SimpleNamespace(stop_reason="end_turn", content=bloques)
    ia = _anthropic_con(create=_async(respuesta))
    assert await ia.generar("s", "u") == "hola"


@pytest.mark.asyncio
async def test_anthropic_generar_rechazo_devuelve_none():
    respuesta = SimpleNamespace(stop_reason="refusal", content=[])
    ia = _anthropic_con(create=_async(respuesta))
    assert await ia.generar("s", "u") is None


# --- OpenAICompatibleIA ---


def _respuesta_chat(**message) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(**message))])


def _openai_con(parse=None, create=None) -> OpenAICompatibleIA:
    ia = OpenAICompatibleIA("openrouter", "clave", "modelo-test")
    ia._cliente = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(parse=parse, create=create))
    )
    return ia


@pytest.mark.asyncio
async def test_openai_estructurar_nativo():
    ia = _openai_con(parse=_async(_respuesta_chat(parsed=Dato(x=2))))
    assert await ia.estructurar("s", "u", Dato) == Dato(x=2)


@pytest.mark.asyncio
async def test_openai_estructurar_degrada_a_json():
    ia = _openai_con(
        parse=_async_error(OpenAIError("sin structured outputs")),
        create=_async(_respuesta_chat(content=json.dumps({"x": 3}))),
    )
    assert await ia.estructurar("s", "u", Dato) == Dato(x=3)


@pytest.mark.asyncio
async def test_openai_json_invalido_devuelve_none():
    ia = _openai_con(
        parse=_async_error(OpenAIError("sin structured outputs")),
        create=_async(_respuesta_chat(content="esto no es JSON")),
    )
    assert await ia.estructurar("s", "u", Dato) is None


@pytest.mark.asyncio
async def test_openai_sin_contenido_devuelve_none():
    ia = _openai_con(
        parse=_async_error(OpenAIError("sin structured outputs")),
        create=_async(_respuesta_chat(content=None)),
    )
    assert await ia.estructurar("s", "u", Dato) is None


@pytest.mark.asyncio
async def test_openai_generar():
    ia = _openai_con(create=_async(_respuesta_chat(content="texto")))
    assert await ia.generar("s", "u") == "texto"


# --- Comprension ---


class ClienteEstructura:
    nombre = "falso"
    modelo = "m"

    def __init__(self, resultado) -> None:
        self._resultado = resultado

    async def estructurar(self, sistema, usuario, esquema):
        return self._resultado

    async def generar(self, sistema, usuario):
        return None


@pytest.mark.asyncio
async def test_comprension_sin_respuesta_del_proveedor():
    consulta = await Comprension(ClienteEstructura(None)).analizar("pregunta")
    assert consulta.es_consulta_normativa is False
    assert consulta.motivo_error == "No se pudo analizar la consulta."


@pytest.mark.asyncio
async def test_comprension_fija_comunidad_y_rango():
    base = ConsultaEstructurada(es_consulta_normativa=True, comunidad="madrid", terminos=["caza"])
    consulta = await Comprension(ClienteEstructura(base)).analizar(
        "pregunta", comunidad_fijada="galicia", rango_fijado=Rango.LEY
    )
    assert consulta.comunidad == "galicia"
    assert consulta.rango == Rango.LEY


# --- Redaccion ---


class ClienteGenera:
    nombre = "falso"
    modelo = "m"

    def __init__(self) -> None:
        self.contenido: str | None = None

    async def estructurar(self, sistema, usuario, esquema):
        return None

    async def generar(self, sistema, usuario):
        self.contenido = usuario
        return "redactado"


@pytest.mark.asyncio
async def test_redaccion_sin_normas_devuelve_none():
    assert await Redaccion(ClienteGenera()).redactar("pregunta", []) is None


@pytest.mark.asyncio
async def test_redaccion_incluye_texto_truncado_si_no_hay_articulos():
    cliente = ClienteGenera()
    detalle = NormaDetalle(**NORMA.model_dump(), texto="x" * 100)
    resultado = await Redaccion(cliente, max_caracteres_texto=10).redactar(
        "pregunta", [NORMA], detalle
    )
    assert resultado == "redactado"
    assert cliente.contenido is not None
    assert "BOE-A-2026-423" in cliente.contenido
    assert "TEXTO CONSOLIDADO" in cliente.contenido
    assert "x" * 11 not in cliente.contenido


@pytest.mark.asyncio
async def test_redaccion_prefiere_articulos_y_respeta_el_limite():
    cliente = ClienteGenera()
    articulos = [
        Articulo(id="a1", titulo="Artículo 1", texto="Objeto de la ley.", url="u#a1"),
        Articulo(id="a2", titulo="Artículo 2", texto="y" * 200, url="u#a2"),
    ]
    detalle = NormaDetalle(**NORMA.model_dump(), texto="todo", articulos=articulos)
    await Redaccion(cliente, max_caracteres_texto=60).redactar("pregunta", [NORMA], detalle)
    assert cliente.contenido is not None
    assert "ARTÍCULOS DE LA NORMA PRINCIPAL" in cliente.contenido
    assert "[Artículo 1] Objeto de la ley." in cliente.contenido
    assert "y" * 200 not in cliente.contenido


@pytest.mark.asyncio
async def test_redaccion_sin_texto_principal():
    cliente = ClienteGenera()
    await Redaccion(cliente).redactar("pregunta", [NORMA])
    assert cliente.contenido is not None
    assert "TEXTO CONSOLIDADO" not in cliente.contenido


# --- Cribado ---

from legislacion.ia.cribado import Cribado, Seleccion  # noqa: E402

NORMA_B = NORMA.model_copy(update={"identificador": "BOE-A-2020-1", "titulo": "Otra norma."})
NORMA_C = NORMA.model_copy(update={"identificador": "BOE-A-2021-2", "titulo": "Tercera norma."})


class ClienteCriba:
    nombre = "falso"
    modelo = "m"

    def __init__(self, seleccion) -> None:
        self._seleccion = seleccion
        self.llamado = False

    async def estructurar(self, sistema, usuario, esquema):
        self.llamado = True
        return self._seleccion

    async def generar(self, sistema, usuario):
        return None


@pytest.mark.asyncio
async def test_cribado_con_una_norma_no_llama_a_la_ia():
    cliente = ClienteCriba(Seleccion())
    resultado = await Cribado(cliente).filtrar("pregunta", [NORMA])
    assert resultado == [NORMA]
    assert cliente.llamado is False


@pytest.mark.asyncio
async def test_cribado_filtra_ordena_y_descarta_identificadores_inventados():
    seleccion = Seleccion(
        identificadores_relevantes=[
            "BOE-A-2021-2",
            "BOE-A-9999-9",
            NORMA.identificador,
            "BOE-A-2021-2",
        ]
    )
    resultado = await Cribado(ClienteCriba(seleccion)).filtrar(
        "pregunta", [NORMA, NORMA_B, NORMA_C]
    )
    assert [n.identificador for n in resultado] == ["BOE-A-2021-2", NORMA.identificador]


@pytest.mark.asyncio
async def test_cribado_sin_respuesta_no_filtra():
    resultado = await Cribado(ClienteCriba(None)).filtrar("pregunta", [NORMA, NORMA_B])
    assert resultado == [NORMA, NORMA_B]


# --- Resiliencia ante errores del proveedor ---

from anthropic import APIConnectionError as AnthropicConnError  # noqa: E402
from httpx import Request as HttpxRequest  # noqa: E402
from openai import APIError as OpenAIAPIError  # noqa: E402


def _openai_error():
    return OpenAIAPIError("caído", request=HttpxRequest("POST", "http://x"), body=None)


@pytest.mark.asyncio
async def test_openai_generar_ante_error_del_proveedor_devuelve_none():
    ia = _openai_con(create=_async_error(_openai_error()))
    assert await ia.generar("s", "u") is None


@pytest.mark.asyncio
async def test_openai_estructurar_degrada_y_si_falla_todo_devuelve_none():
    ia = _openai_con(
        parse=_async_error(_openai_error()),
        create=_async_error(_openai_error()),
    )
    assert await ia.estructurar("s", "u", Dato) is None


@pytest.mark.asyncio
async def test_anthropic_estructurar_ante_error_devuelve_none():
    ia = _anthropic_con(
        parse=_async_error(AnthropicConnError(request=HttpxRequest("POST", "http://x")))
    )
    assert await ia.estructurar("s", "u", Dato) is None


@pytest.mark.asyncio
async def test_anthropic_generar_ante_error_devuelve_none():
    ia = _anthropic_con(
        create=_async_error(AnthropicConnError(request=HttpxRequest("POST", "http://x")))
    )
    assert await ia.generar("s", "u") is None
