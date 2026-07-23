import pytest
from pydantic import BaseModel

from legislacion.enrutador import Enrutador
from legislacion.ia.cribado import Seleccion
from legislacion.modelos import (
    ConsultaEstructurada,
    Norma,
    NormaDetalle,
    PeticionConsulta,
    Rango,
)

NORMA = Norma(
    identificador="BOE-A-2026-423",
    titulo="Ley 5/2025, de Vivienda de Andalucía.",
    comunidad="andalucia",
    rango="Ley",
    vigente=True,
    url_oficial="https://www.boe.es/buscar/act.php?id=BOE-A-2026-423",
    fuente="boe",
)


class ClienteIAFalso:
    nombre = "falso"
    modelo = "modelo-falso"

    def __init__(self, consulta: ConsultaEstructurada) -> None:
        self._consulta = consulta

    async def estructurar(self, sistema: str, usuario: str, esquema: type[BaseModel]):
        if esquema is Seleccion:
            return None
        return self._consulta

    async def generar(self, sistema: str, usuario: str) -> str:
        return "Respuesta redactada por la IA falsa."


class BoeFalso:
    def __init__(self) -> None:
        self.codigos_recibidos: list[str] | None = None

    async def buscar(self, consulta, codigos):
        self.codigos_recibidos = codigos
        return [NORMA], {"query": "..."}

    async def obtener_norma(self, identificador):
        return None


def _enrutador(consulta: ConsultaEstructurada) -> tuple[Enrutador, BoeFalso]:
    boe = BoeFalso()
    clientes = {"falso": ClienteIAFalso(consulta)}
    return Enrutador(clientes, "falso", boe), boe


@pytest.mark.asyncio
async def test_pregunta_no_normativa_devuelve_error():
    enrutador, _ = _enrutador(
        ConsultaEstructurada(es_consulta_normativa=False, motivo_error="No es normativa.")
    )
    respuesta = await enrutador.consultar(PeticionConsulta(pregunta="hola, ¿qué tal?"))
    assert respuesta.tipo == "error_consulta"
    assert respuesta.motivo == "No es normativa."


@pytest.mark.asyncio
async def test_sin_comunidad_busca_normativa_estatal():
    enrutador, boe = _enrutador(
        ConsultaEstructurada(es_consulta_normativa=True, terminos=["vivienda"])
    )
    respuesta = await enrutador.consultar(PeticionConsulta(pregunta="ley de vivienda"))
    assert respuesta.tipo == "resultados"
    assert boe.codigos_recibidos == []
    assert respuesta.nota == "Consulta sin comunidad autónoma: se muestra normativa estatal."


@pytest.mark.asyncio
async def test_ley_va_por_boe_con_los_codigos_de_la_comunidad():
    enrutador, boe = _enrutador(
        ConsultaEstructurada(
            es_consulta_normativa=True,
            comunidad="valencia",
            rango=Rango.LEY,
            terminos=["vivienda"],
        )
    )
    respuesta = await enrutador.consultar(
        PeticionConsulta(pregunta="ley de vivienda de la Comunitat Valenciana")
    )
    assert respuesta.tipo == "resultados"
    assert boe.codigos_recibidos == ["8161", "8162"]
    assert respuesta.respuesta_ia == "Respuesta redactada por la IA falsa."
    assert respuesta.trazabilidad.fuente == "boe"
    assert respuesta.trazabilidad.proveedor_ia == "falso"
    assert respuesta.trazabilidad.modelo_ia == "modelo-falso"


@pytest.mark.asyncio
async def test_reglamento_devuelve_redirect_oficial():
    enrutador, _ = _enrutador(
        ConsultaEstructurada(
            es_consulta_normativa=True,
            comunidad="madrid",
            rango=Rango.REGLAMENTO,
            terminos=["taxi"],
        )
    )
    respuesta = await enrutador.consultar(PeticionConsulta(pregunta="decreto del taxi de Madrid"))
    assert respuesta.tipo == "redirect_oficial"
    assert respuesta.enlace_oficial == "https://gestiona.comunidad.madrid/wleg_pub"


@pytest.mark.asyncio
async def test_sin_redaccion_no_llama_a_la_ia():
    enrutador, _ = _enrutador(
        ConsultaEstructurada(
            es_consulta_normativa=True,
            comunidad="andalucia",
            rango=Rango.LEY,
            terminos=["vivienda"],
        )
    )
    respuesta = await enrutador.consultar(
        PeticionConsulta(pregunta="ley de vivienda de Andalucía", redactar_respuesta=False)
    )
    assert respuesta.tipo == "resultados"
    assert respuesta.respuesta_ia is None


@pytest.mark.asyncio
async def test_proveedor_no_configurado_devuelve_error():
    enrutador, _ = _enrutador(
        ConsultaEstructurada(es_consulta_normativa=True, comunidad="andalucia", terminos=["x"])
    )
    respuesta = await enrutador.consultar(
        PeticionConsulta(pregunta="ley de x de Andalucía", proveedor="openai")
    )
    assert respuesta.tipo == "error_consulta"
    assert "openai" in respuesta.motivo


def test_proveedores_expone_disponibles_y_defecto():
    enrutador, _ = _enrutador(
        ConsultaEstructurada(es_consulta_normativa=True, comunidad="andalucia", terminos=["x"])
    )
    info = enrutador.proveedores()
    assert info["defecto"] == "falso"
    assert info["disponibles"] == {"falso": "modelo-falso"}


@pytest.mark.asyncio
async def test_comunidad_desconocida_devuelve_error():
    enrutador, _ = _enrutador(
        ConsultaEstructurada(es_consulta_normativa=True, comunidad="gotham", terminos=["x"])
    )
    respuesta = await enrutador.consultar(PeticionConsulta(pregunta="ley de x de Gotham"))
    assert respuesta.tipo == "error_consulta"
    assert "gotham" in respuesta.motivo


@pytest.mark.asyncio
async def test_redaccion_recibe_el_texto_de_la_norma_principal():

    class BoeConDetalle(BoeFalso):
        async def obtener_norma(self, identificador):
            return NormaDetalle(**NORMA.model_dump(), texto="Texto consolidado completo.")

    boe = BoeConDetalle()
    consulta = ConsultaEstructurada(
        es_consulta_normativa=True, comunidad="andalucia", rango=Rango.LEY, terminos=["vivienda"]
    )
    enrutador = Enrutador({"falso": ClienteIAFalso(consulta)}, "falso", boe)
    respuesta = await enrutador.consultar(PeticionConsulta(pregunta="ley de vivienda de Andalucía"))
    assert respuesta.tipo == "resultados"
    assert respuesta.respuesta_ia == "Respuesta redactada por la IA falsa."


@pytest.mark.asyncio
async def test_sin_terminos_ni_numero_devuelve_error():
    enrutador, _ = _enrutador(
        ConsultaEstructurada(es_consulta_normativa=True, comunidad="andalucia")
    )
    respuesta = await enrutador.consultar(PeticionConsulta(pregunta="normativa de Andalucía"))
    assert respuesta.tipo == "error_consulta"
    assert "materia" in respuesta.motivo


def _enrutador_multimodelo() -> Enrutador:
    consulta = ConsultaEstructurada(
        es_consulta_normativa=True, comunidad="andalucia", terminos=["x"]
    )
    clientes = {
        "openrouter:modelo-a": ClienteIAFalso(consulta),
        "openrouter:modelo-b": ClienteIAFalso(consulta),
    }
    return Enrutador(clientes, "openrouter", BoeFalso())


@pytest.mark.asyncio
async def test_prefijo_de_proveedor_resuelve_al_primer_modelo():
    enrutador = _enrutador_multimodelo()
    respuesta = await enrutador.consultar(
        PeticionConsulta(pregunta="ley de x de Andalucía", proveedor="openrouter")
    )
    assert respuesta.tipo == "resultados"


def test_defecto_por_prefijo_y_defecto_ausente():
    enrutador = _enrutador_multimodelo()
    assert enrutador.proveedores()["defecto"] == "openrouter:modelo-a"
    consulta = ConsultaEstructurada(
        es_consulta_normativa=True, comunidad="andalucia", terminos=["x"]
    )
    sin_coincidencia = Enrutador({"falso": ClienteIAFalso(consulta)}, "openai", BoeFalso())
    assert sin_coincidencia.proveedores()["defecto"] == "falso"


class BoeSoloEstatal(BoeFalso):
    """Devuelve resultados solo cuando la búsqueda es estatal (sin códigos)."""

    def __init__(self) -> None:
        super().__init__()
        self.llamadas: list[list[str]] = []

    async def buscar(self, consulta, codigos):
        self.llamadas.append(codigos)
        return ([NORMA], {"query": "..."}) if codigos == [] else ([], {"query": "..."})


@pytest.mark.asyncio
async def test_sin_resultados_autonomicos_recurre_a_estatal():
    consulta = ConsultaEstructurada(
        es_consulta_normativa=True, comunidad="andalucia", terminos=["criptomoneda"]
    )
    boe = BoeSoloEstatal()
    enrutador = Enrutador({"falso": ClienteIAFalso(consulta)}, "falso", boe)
    respuesta = await enrutador.consultar(
        PeticionConsulta(pregunta="leyes sobre criptomonedas en Andalucía")
    )
    assert respuesta.tipo == "resultados"
    assert boe.llamadas == [["8010"], []]
    assert respuesta.nota is not None
    assert "estatal" in respuesta.nota


class BoeSinResultados(BoeFalso):
    async def buscar(self, consulta, codigos):
        return [], {"query": "..."}


@pytest.mark.asyncio
async def test_sin_resultados_en_ningun_ambito_no_lleva_nota():
    consulta = ConsultaEstructurada(
        es_consulta_normativa=True, comunidad="andalucia", terminos=["inexistente"]
    )
    enrutador = Enrutador({"falso": ClienteIAFalso(consulta)}, "falso", BoeSinResultados())
    respuesta = await enrutador.consultar(PeticionConsulta(pregunta="ley inexistente de Andalucía"))
    assert respuesta.tipo == "resultados"
    assert respuesta.normas == []
    assert respuesta.nota is None


NORMA_B = NORMA.model_copy(update={"identificador": "BOE-A-2020-1", "titulo": "Otra."})


class ClienteQueDescartaTodo(ClienteIAFalso):
    async def estructurar(self, sistema: str, usuario: str, esquema: type[BaseModel]):
        if esquema is Seleccion:
            return Seleccion()
        return self._consulta


class BoeDosNormas(BoeFalso):
    async def buscar(self, consulta, codigos):
        return [NORMA, NORMA_B], {"query": "..."}


@pytest.mark.asyncio
async def test_cribado_que_descarta_todo_deja_nota_de_menciones_incidentales():
    consulta = ConsultaEstructurada(
        es_consulta_normativa=True, comunidad="andalucia", terminos=["criptomoneda"]
    )
    enrutador = Enrutador({"falso": ClienteQueDescartaTodo(consulta)}, "falso", BoeDosNormas())
    respuesta = await enrutador.consultar(
        PeticionConsulta(pregunta="criptomonedas en Andalucía", redactar_respuesta=False)
    )
    assert respuesta.tipo == "resultados"
    assert respuesta.normas == []
    assert "incidentales" in respuesta.nota


from legislacion.modelos import PeticionComparacion  # noqa: E402


class CacheContadorFalso:
    def __init__(self) -> None:
        self.incrementos: list[str] = []

    async def incrementar(self, campo: str) -> None:
        self.incrementos.append(campo)


@pytest.mark.asyncio
async def test_redirect_incrementa_el_contador_de_derivaciones():
    consulta = ConsultaEstructurada(
        es_consulta_normativa=True, comunidad="madrid", rango=Rango.REGLAMENTO, terminos=["taxi"]
    )
    contador = CacheContadorFalso()
    enrutador = Enrutador({"falso": ClienteIAFalso(consulta)}, "falso", BoeFalso(), cache=contador)
    respuesta = await enrutador.consultar(PeticionConsulta(pregunta="decreto del taxi de Madrid"))
    assert respuesta.tipo == "redirect_oficial"
    assert contador.incrementos == ["madrid:reglamento"]


class BoeComparador(BoeFalso):
    def __init__(self) -> None:
        super().__init__()
        self.consultados: list[str] = []

    async def buscar(self, consulta, codigos):
        self.consultados.append(consulta.comunidad)
        norma = NORMA.model_copy(update={"comunidad": consulta.comunidad})
        return [norma], {"query": "..."}


@pytest.mark.asyncio
async def test_comparar_recorre_las_17_comunidades():
    consulta = ConsultaEstructurada(es_consulta_normativa=True, terminos=["vivienda"])
    boe = BoeComparador()
    enrutador = Enrutador({"falso": ClienteIAFalso(consulta)}, "falso", boe)
    respuesta = await enrutador.comparar(PeticionComparacion(pregunta="vivienda en cada comunidad"))
    assert respuesta.tipo == "comparacion"
    assert len(respuesta.resultados) == 17
    assert sorted(boe.consultados) == sorted(r.comunidad for r in respuesta.resultados)
    assert all(len(r.normas) == 1 for r in respuesta.resultados)
    assert "ceuta" not in boe.consultados


@pytest.mark.asyncio
async def test_comparar_valida_la_consulta():
    consulta = ConsultaEstructurada(es_consulta_normativa=False, motivo_error="No aplica.")
    enrutador = Enrutador({"falso": ClienteIAFalso(consulta)}, "falso", BoeFalso())
    respuesta = await enrutador.comparar(PeticionComparacion(pregunta="hola"))
    assert respuesta.tipo == "error_consulta"


@pytest.mark.asyncio
async def test_comparar_sin_proveedor_devuelve_error():
    enrutador = Enrutador({}, "anthropic", BoeFalso())
    respuesta = await enrutador.comparar(PeticionComparacion(pregunta="vivienda"))
    assert respuesta.tipo == "error_consulta"


NORMA_UE = NORMA.model_copy(
    update={"identificador": "32023R1114", "comunidad": "union-europea", "fuente": "eurlex"}
)


class EurlexFalso:
    def __init__(self, normas) -> None:
        self._normas = normas
        self.llamado = False

    async def buscar(self, consulta):
        self.llamado = True
        return self._normas, {"endpoint": "sparql", "busqueda": "'x*'"}


@pytest.mark.asyncio
async def test_sin_normativa_espanola_recurre_a_eurlex():
    consulta = ConsultaEstructurada(
        es_consulta_normativa=True, comunidad="andalucia", terminos=["criptomoneda"]
    )
    eurlex = EurlexFalso([NORMA_UE])
    enrutador = Enrutador(
        {"falso": ClienteIAFalso(consulta)}, "falso", BoeSinResultados(), eurlex=eurlex
    )
    respuesta = await enrutador.consultar(
        PeticionConsulta(pregunta="criptomonedas en Andalucía", redactar_respuesta=False)
    )
    assert respuesta.tipo == "resultados"
    assert eurlex.llamado is True
    assert respuesta.normas[0].fuente == "eurlex"
    assert "Unión Europea" in respuesta.nota


@pytest.mark.asyncio
async def test_eurlex_sin_resultados_mantiene_la_respuesta_vacia():
    consulta = ConsultaEstructurada(
        es_consulta_normativa=True, comunidad="andalucia", terminos=["inexistente"]
    )
    eurlex = EurlexFalso([])
    enrutador = Enrutador(
        {"falso": ClienteIAFalso(consulta)}, "falso", BoeSinResultados(), eurlex=eurlex
    )
    respuesta = await enrutador.consultar(
        PeticionConsulta(pregunta="materia inexistente de Andalucía", redactar_respuesta=False)
    )
    assert respuesta.tipo == "resultados"
    assert respuesta.normas == []
    assert respuesta.nota is None


@pytest.mark.asyncio
async def test_con_resultados_espanoles_no_se_consulta_eurlex():
    consulta = ConsultaEstructurada(
        es_consulta_normativa=True, comunidad="andalucia", rango=Rango.LEY, terminos=["vivienda"]
    )
    eurlex = EurlexFalso([NORMA_UE])
    enrutador = Enrutador({"falso": ClienteIAFalso(consulta)}, "falso", BoeFalso(), eurlex=eurlex)
    respuesta = await enrutador.consultar(
        PeticionConsulta(pregunta="ley de vivienda de Andalucía", redactar_respuesta=False)
    )
    assert respuesta.tipo == "resultados"
    assert eurlex.llamado is False


@pytest.mark.asyncio
async def test_normas_espanolas_derogadas_se_completan_con_la_ue():
    consulta = ConsultaEstructurada(
        es_consulta_normativa=True, comunidad="andalucia", terminos=["criptomoneda"]
    )

    class BoeDerogada(BoeFalso):
        async def buscar(self, consulta, codigos):
            return [NORMA.model_copy(update={"vigente": False})], {"query": "..."}

    eurlex = EurlexFalso([NORMA_UE.model_copy(update={"vigente": True})])
    enrutador = Enrutador(
        {"falso": ClienteIAFalso(consulta)}, "falso", BoeDerogada(), eurlex=eurlex
    )
    respuesta = await enrutador.consultar(
        PeticionConsulta(pregunta="criptomonedas en Andalucía", redactar_respuesta=False)
    )
    assert respuesta.tipo == "resultados"
    assert [n.fuente for n in respuesta.normas] == ["eurlex", "boe"]
    assert "Unión Europea" in respuesta.nota
    assert "eurlex_busqueda" in respuesta.trazabilidad.parametros
