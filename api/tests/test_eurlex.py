import httpx
import pytest
import respx

from legislacion.adaptadores.eurlex import AdaptadorEURLex, _expresion_busqueda, _rango_ue
from legislacion.cache import Cache
from legislacion.modelos import ConsultaEstructurada

ENDPOINT = "https://sparql.test/endpoint"


def _adaptador() -> AdaptadorEURLex:
    cache = Cache("redis://inexistente:1/0", ttl_segundos=60)
    return AdaptadorEURLex(ENDPOINT, cache, timeout=5.0, max_resultados=10)


def _consulta(**kwargs) -> ConsultaEstructurada:
    valores = {"es_consulta_normativa": True, "terminos": ["criptomoneda"]}
    valores.update(kwargs)
    return ConsultaEstructurada(**valores)


FILA_MICA = {
    "celex": {"value": "32023R1114"},
    "titulo": {"value": "Reglamento (UE) 2023/1114 del Parlamento Europeo y del Consejo"},
    "envigor": {"value": "1"},
    "fecha": {"value": "2023-05-31"},
    "eli": {"value": "http://data.europa.eu/eli/reg/2023/1114/oj"},
}


def _respuesta_sparql(filas):
    return httpx.Response(200, json={"results": {"bindings": filas}})


def test_expresion_de_busqueda_con_comodines_y_saneado():
    expresion = _expresion_busqueda(["protección de datos", 'x") OR *'])
    assert expresion == "'protección*' AND 'datos*'"


def test_rango_ue_desde_el_titulo():
    assert _rango_ue("Reglamento Delegado (UE) 2025/414") == "Reglamento Delegado"
    assert _rango_ue("Directiva (UE) 2019/1024") == "Directiva"
    assert _rango_ue("Decisión (UE) 2020/1") == "Norma UE"


@pytest.mark.asyncio
@respx.mock
async def test_buscar_normaliza_resultados():
    respx.get(ENDPOINT).mock(return_value=_respuesta_sparql([FILA_MICA]))
    normas, parametros = await _adaptador().buscar(_consulta())
    assert len(normas) == 1
    norma = normas[0]
    assert norma.identificador == "32023R1114"
    assert norma.comunidad == "union-europea"
    assert norma.rango == "Reglamento"
    assert norma.vigente is True
    assert norma.fecha_disposicion == "20230531"
    assert norma.url_oficial.endswith("uri=CELEX:32023R1114")
    assert norma.url_eli == "http://data.europa.eu/eli/reg/2023/1114/oj"
    assert norma.fuente == "eurlex"
    assert parametros["busqueda"] == "'criptomoneda*'"


@pytest.mark.asyncio
@respx.mock
async def test_buscar_prueba_sinonimos_si_los_terminos_no_dan():
    respx.get(ENDPOINT).mock(side_effect=[_respuesta_sparql([]), _respuesta_sparql([FILA_MICA])])
    consulta = _consulta(terminos=["criptomoneda"], sinonimos=["criptoactivo"])
    normas, parametros = await _adaptador().buscar(consulta)
    assert len(normas) == 1
    assert parametros["busqueda"] == "'criptoactivo*'"


@pytest.mark.asyncio
@respx.mock
async def test_buscar_sin_resultados():
    respx.get(ENDPOINT).mock(return_value=_respuesta_sparql([]))
    normas, _ = await _adaptador().buscar(_consulta())
    assert normas == []


@pytest.mark.asyncio
async def test_sin_terminos_utilizables_no_llama_a_la_red():
    normas, parametros = await _adaptador().buscar(_consulta(terminos=["de"]))
    assert normas == []
    assert parametros["busqueda"] == ""


@pytest.mark.asyncio
@respx.mock
async def test_fila_sin_vigencia_ni_fecha():
    fila = {"celex": {"value": "32020L0001"}, "titulo": {"value": "Directiva (UE) 2020/1"}}
    respx.get(ENDPOINT).mock(return_value=_respuesta_sparql([fila]))
    normas, _ = await _adaptador().buscar(_consulta())
    assert normas[0].vigente is None
    assert normas[0].fecha_disposicion is None
