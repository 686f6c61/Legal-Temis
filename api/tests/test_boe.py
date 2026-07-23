import httpx
import pytest
import respx

from legislacion.adaptadores.boe import AdaptadorBOE, _query_string
from legislacion.cache import Cache
from legislacion.modelos import ConsultaEstructurada, Rango

BASE = "https://boe.test/api"


def _cache_sin_redis() -> Cache:
    return Cache("redis://inexistente:1/0", ttl_segundos=60)


def _adaptador() -> AdaptadorBOE:
    return AdaptadorBOE(BASE, _cache_sin_redis(), timeout=5.0, max_resultados=10)


def _consulta(**kwargs) -> ConsultaEstructurada:
    valores = {
        "es_consulta_normativa": True,
        "comunidad": "andalucia",
        "rango": Rango.LEY,
        "terminos": ["vivienda"],
    }
    valores.update(kwargs)
    return ConsultaEstructurada(**valores)


DATO_BOE = {
    "identificador": "BOE-A-2026-423",
    "titulo": "Ley 5/2025, de 16 de diciembre, de Vivienda de Andalucía.",
    "rango": {"codigo": "1300", "texto": "Ley"},
    "departamento": {"codigo": "8010", "texto": "Comunidad Autónoma de Andalucía"},
    "fecha_disposicion": "20251216",
    "numero_oficial": "5/2025",
    "vigencia_agotada": "N",
    "estatus_derogacion": "N",
    "estado_consolidacion": {"codigo": "3", "texto": "Finalizado"},
    "url_eli": "https://www.boe.es/eli/es-an/l/2025/12/16/5",
    "url_html_consolidada": "https://www.boe.es/buscar/act.php?id=BOE-A-2026-423",
}


def test_query_string_con_terminos_y_departamentos():
    qs = _query_string(_consulta(), ["8010"])
    assert qs == "(departamento@codigo:8010) AND titulo:vivienda*"


def test_query_string_con_doble_codigo():
    qs = _query_string(_consulta(comunidad="valencia"), ["8161", "8162"])
    assert qs.startswith("(departamento@codigo:8161 OR departamento@codigo:8162)")


def test_query_string_sanea_caracteres_de_control():
    qs = _query_string(_consulta(terminos=['vivienda") OR *:*']), ["8010"])
    assert qs == "(departamento@codigo:8010) AND titulo:vivienda*"


def test_query_string_con_numero_oficial():
    qs = _query_string(_consulta(terminos=[], numero_oficial="5/2025"), ["8010"])
    assert 'numero_oficial:"5/2025"' in qs


@pytest.mark.asyncio
@respx.mock
async def test_buscar_normaliza_resultados():
    respx.get(BASE).mock(
        return_value=httpx.Response(
            200, json={"status": {"code": "200", "text": "ok"}, "data": [DATO_BOE]}
        )
    )
    normas, parametros = await _adaptador().buscar(_consulta(), ["8010"])
    assert len(normas) == 1
    norma = normas[0]
    assert norma.identificador == "BOE-A-2026-423"
    assert norma.vigente is True
    assert norma.url_eli == "https://www.boe.es/eli/es-an/l/2025/12/16/5"
    assert norma.fuente == "boe"
    assert "query" in parametros


@pytest.mark.asyncio
@respx.mock
async def test_buscar_marca_no_vigente_si_derogada():
    dato = {**DATO_BOE, "estatus_derogacion": "S"}
    respx.get(BASE).mock(
        return_value=httpx.Response(
            200, json={"status": {"code": "200", "text": "ok"}, "data": [dato]}
        )
    )
    normas, _ = await _adaptador().buscar(_consulta(), ["8010"])
    assert normas[0].vigente is False


@pytest.mark.asyncio
@respx.mock
async def test_buscar_error_de_api_lanza_excepcion():
    respx.get(BASE).mock(
        return_value=httpx.Response(
            200, json={"status": {"code": "500", "text": "Server error"}, "data": ""}
        )
    )
    with pytest.raises(RuntimeError, match="API BOE"):
        await _adaptador().buscar(_consulta(), ["8010"])


@pytest.mark.asyncio
async def test_obtener_norma_rechaza_identificador_invalido():
    assert await _adaptador().obtener_norma("../../etc/passwd") is None


@pytest.mark.asyncio
@respx.mock
async def test_obtener_norma_compone_metadatos_y_texto():
    respx.get(f"{BASE}/id/BOE-A-2026-423/metadatos").mock(
        return_value=httpx.Response(
            200, json={"status": {"code": "200", "text": "ok"}, "data": [DATO_BOE]}
        )
    )
    respx.get(f"{BASE}/id/BOE-A-2026-423/texto").mock(
        return_value=httpx.Response(
            200,
            content=b"<texto><p>Art\xc3\xadculo 1. Objeto.</p><p>Esta ley regula.</p></texto>",
        )
    )
    detalle = await _adaptador().obtener_norma("BOE-A-2026-423")
    assert detalle is not None
    assert "Artículo 1" in (detalle.texto or "")
    assert detalle.comunidad == "Comunidad Autónoma de Andalucía"


class CacheConDatos:
    def __init__(self, valor) -> None:
        self._valor = valor

    async def obtener(self, clave):
        return self._valor

    async def guardar(self, clave, valor):
        pass


@pytest.mark.asyncio
@respx.mock
async def test_obtener_norma_inexistente_devuelve_none():
    respx.get(f"{BASE}/id/BOE-A-1999-1/metadatos").mock(return_value=httpx.Response(404))
    assert await _adaptador().obtener_norma("BOE-A-1999-1") is None


@pytest.mark.asyncio
@respx.mock
async def test_obtener_norma_con_datos_vacios_devuelve_none():
    respx.get(f"{BASE}/id/BOE-A-1999-1/metadatos").mock(
        return_value=httpx.Response(200, json={"status": {"code": "200"}, "data": []})
    )
    assert await _adaptador().obtener_norma("BOE-A-1999-1") is None


@pytest.mark.asyncio
@respx.mock
async def test_obtener_norma_con_xml_invalido_deja_texto_vacio():
    respx.get(f"{BASE}/id/BOE-A-2026-423/metadatos").mock(
        return_value=httpx.Response(200, json={"status": {"code": "200"}, "data": [DATO_BOE]})
    )
    respx.get(f"{BASE}/id/BOE-A-2026-423/texto").mock(
        return_value=httpx.Response(200, content=b"esto no es xml <")
    )
    detalle = await _adaptador().obtener_norma("BOE-A-2026-423")
    assert detalle is not None
    assert detalle.texto is None


@pytest.mark.asyncio
async def test_obtener_norma_desde_cache_no_llama_a_la_red():
    cache = CacheConDatos({"metadatos": DATO_BOE, "texto": "Texto cacheado."})
    adaptador = AdaptadorBOE(BASE, cache, timeout=5.0, max_resultados=10)
    detalle = await adaptador.obtener_norma("BOE-A-2026-423")
    assert detalle is not None
    assert detalle.texto == "Texto cacheado."


def test_query_string_sin_codigos_acota_a_ambito_estatal():
    qs = _query_string(_consulta(comunidad=None), [])
    assert qs == "ambito@codigo:1 AND titulo:vivienda*"


def test_query_string_trocea_terminos_con_espacios():
    qs = _query_string(_consulta(terminos=["protección de datos"]), [])
    assert qs == "ambito@codigo:1 AND titulo:protección* AND titulo:datos*"


def test_query_string_por_texto_completo():
    qs = _query_string(_consulta(), ["8010"], campo="texto")
    assert qs == "(departamento@codigo:8010) AND texto:vivienda*"


@pytest.mark.asyncio
@respx.mock
async def test_buscar_recurre_al_texto_completo_si_el_titulo_no_da_resultados():
    respx.get(BASE).mock(
        side_effect=[
            httpx.Response(200, json={"status": {"code": "200"}, "data": []}),
            httpx.Response(200, json={"status": {"code": "200"}, "data": [DATO_BOE]}),
        ]
    )
    normas, parametros = await _adaptador().buscar(_consulta(terminos=["criptomoneda"]), ["8010"])
    assert len(normas) == 1
    assert "texto:criptomoneda" in parametros["query"]


@pytest.mark.asyncio
@respx.mock
async def test_buscar_sin_terminos_no_repite_la_busqueda():
    ruta = respx.get(BASE).mock(
        return_value=httpx.Response(200, json={"status": {"code": "200"}, "data": []})
    )
    normas, _ = await _adaptador().buscar(_consulta(terminos=[], numero_oficial="5/2025"), ["8010"])
    assert normas == []
    assert ruta.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_buscar_prueba_sinonimos_antes_que_texto_completo():
    respx.get(BASE).mock(
        side_effect=[
            httpx.Response(200, json={"status": {"code": "200"}, "data": []}),
            httpx.Response(200, json={"status": {"code": "200"}, "data": [DATO_BOE]}),
        ]
    )
    consulta = _consulta(terminos=["criptomoneda"], sinonimos=["criptoactivo"])
    normas, parametros = await _adaptador().buscar(consulta, ["8010"])
    assert len(normas) == 1
    assert "titulo:criptoactivo*" in parametros["query"]


@pytest.mark.asyncio
@respx.mock
async def test_texto_completo_fusiona_terminos_y_sinonimos_sin_duplicados():
    dato_b = {**DATO_BOE, "identificador": "BOE-A-2023-1"}
    dato_c = {**DATO_BOE, "identificador": "BOE-A-2023-2"}
    respx.get(BASE).mock(
        side_effect=[
            httpx.Response(200, json={"status": {"code": "200"}, "data": []}),
            httpx.Response(200, json={"status": {"code": "200"}, "data": []}),
            httpx.Response(200, json={"status": {"code": "200"}, "data": [DATO_BOE, dato_b]}),
            httpx.Response(200, json={"status": {"code": "200"}, "data": [dato_b, dato_c]}),
        ]
    )
    consulta = _consulta(terminos=["criptomoneda"], sinonimos=["criptoactivo"])
    normas, parametros = await _adaptador().buscar(consulta, [])
    assert [n.identificador for n in normas] == ["BOE-A-2026-423", "BOE-A-2023-1", "BOE-A-2023-2"]
    assert " || " in parametros["query"]
    assert "texto:criptoactivo*" in parametros["query"]


@pytest.mark.asyncio
@respx.mock
async def test_cada_sinonimo_se_prueba_por_separado_en_titulo():
    respx.get(BASE).mock(
        side_effect=[
            httpx.Response(200, json={"status": {"code": "200"}, "data": []}),
            httpx.Response(200, json={"status": {"code": "200"}, "data": []}),
            httpx.Response(200, json={"status": {"code": "200"}, "data": [DATO_BOE]}),
        ]
    )
    consulta = _consulta(terminos=["criptomoneda"], sinonimos=["moneda virtual", "criptoactivo"])
    normas, parametros = await _adaptador().buscar(consulta, ["8010"])
    assert len(normas) == 1
    assert parametros["query"].count("titulo:criptoactivo*") == 1
    assert "moneda" not in parametros["query"]


@pytest.mark.asyncio
@respx.mock
async def test_el_primer_sinonimo_con_resultados_detiene_la_cadena():
    ruta = respx.get(BASE).mock(
        side_effect=[
            httpx.Response(200, json={"status": {"code": "200"}, "data": []}),
            httpx.Response(200, json={"status": {"code": "200"}, "data": [DATO_BOE]}),
        ]
    )
    consulta = _consulta(terminos=["criptomoneda"], sinonimos=["criptoactivo", "moneda virtual"])
    normas, _ = await _adaptador().buscar(consulta, ["8010"])
    assert len(normas) == 1
    assert ruta.call_count == 2


XML_BLOQUES = b"""<response>
<bloque id="a1" tipo="precepto" titulo="Art\xc3\xadculo 1">
  <version id_norma="BOE-A-2015-1" fecha_publicacion="20150101"
    fecha_vigencia="20150102"><p>Texto original del art\xc3\xadculo 1.</p></version>
  <version id_norma="BOE-A-2020-2" fecha_publicacion="20200101"
    fecha_vigencia="20200102"><p>Texto reformado del art\xc3\xadculo 1.</p></version>
</bloque>
<bloque id="pre" tipo="preambulo">
  <version id_norma="BOE-A-2015-1" fecha_publicacion="20150101"
    fecha_vigencia="20150102"><p>Pre\xc3\xa1mbulo.</p></version>
</bloque>
<bloque id="vacio" tipo="precepto" titulo="Art\xc3\xadculo 2">
  <version id_norma="BOE-A-2015-1" fecha_publicacion="20150101"
    fecha_vigencia="20150102"></version>
</bloque>
</response>"""


def _mock_norma_con_bloques():
    respx.get(f"{BASE}/id/BOE-A-2026-423/metadatos").mock(
        return_value=httpx.Response(200, json={"status": {"code": "200"}, "data": [DATO_BOE]})
    )
    respx.get(f"{BASE}/id/BOE-A-2026-423/texto").mock(
        return_value=httpx.Response(200, content=XML_BLOQUES)
    )


@pytest.mark.asyncio
@respx.mock
async def test_obtener_norma_extrae_articulos_con_ancla():
    _mock_norma_con_bloques()
    detalle = await _adaptador().obtener_norma("BOE-A-2026-423")
    assert detalle is not None
    assert len(detalle.articulos) == 1
    articulo = detalle.articulos[0]
    assert articulo.titulo == "Artículo 1"
    assert articulo.texto == "Texto reformado del artículo 1."
    assert articulo.url.endswith("act.php?id=BOE-A-2026-423#a1")
    assert articulo.vigente_desde == "20200102"
    assert "Preámbulo." in (detalle.texto or "")


@pytest.mark.asyncio
@respx.mock
async def test_obtener_norma_a_fecha_pasada_da_la_version_de_entonces():
    _mock_norma_con_bloques()
    detalle = await _adaptador().obtener_norma("BOE-A-2026-423", fecha="20180101")
    assert detalle is not None
    assert detalle.articulos[0].texto == "Texto original del artículo 1."
    assert detalle.fecha_texto == "20180101"


@pytest.mark.asyncio
@respx.mock
async def test_obtener_norma_a_fecha_anterior_a_la_norma_no_tiene_bloques():
    _mock_norma_con_bloques()
    detalle = await _adaptador().obtener_norma("BOE-A-2026-423", fecha="20100101")
    assert detalle is not None
    assert detalle.articulos == []
    assert detalle.texto is None


def _norma_orden(identificador, rango, vigente, fecha):
    return NORMA_ORDEN.model_copy(
        update={
            "identificador": identificador,
            "rango": rango,
            "vigente": vigente,
            "fecha_disposicion": fecha,
        }
    )


from legislacion.adaptadores.boe import ordenar_normas  # noqa: E402
from legislacion.modelos import Norma  # noqa: E402

NORMA_ORDEN = Norma(
    identificador="X",
    titulo="t",
    comunidad="c",
    rango="Ley",
    url_oficial="https://www.boe.es",
    fuente="boe",
)


def test_ordenar_normas_vigencia_rango_y_fecha():
    normas = [
        _norma_orden("derogada", "Ley", False, "20240101"),
        _norma_orden("orden", "Orden TMA/1/2020", True, "20200101"),
        _norma_orden("ley-vieja", "Ley", True, "20050101"),
        _norma_orden("ley-nueva", "Ley", True, "20250101"),
        _norma_orden("decreto-ley", "Decreto-ley", True, "20230101"),
        _norma_orden("resolucion", "Resolución", None, "20260101"),
        _norma_orden("organica", "Ley Orgánica", True, "19990101"),
    ]
    orden = [n.identificador for n in ordenar_normas(normas)]
    assert orden == [
        "organica",
        "ley-nueva",
        "ley-vieja",
        "decreto-ley",
        "orden",
        "resolucion",
        "derogada",
    ]


def test_ordenar_sin_fecha_valida_no_rompe():
    normas = [_norma_orden("a", "Ley", True, None), _norma_orden("b", "Ley", True, "20200101")]
    assert [n.identificador for n in ordenar_normas(normas)] == ["b", "a"]
