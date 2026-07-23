import asyncio

from legislacion.adaptadores.boe import AdaptadorBOE, ordenar_normas
from legislacion.adaptadores.eurlex import AdaptadorEURLex
from legislacion.cache import Cache
from legislacion.cobertura import COMUNIDADES, resolver_soporte
from legislacion.ia.base import ClienteIA
from legislacion.ia.comprension import Comprension
from legislacion.ia.cribado import Cribado
from legislacion.ia.redaccion import Redaccion
from legislacion.modelos import (
    ComparacionComunidad,
    ConsultaEstructurada,
    PeticionComparacion,
    PeticionConsulta,
    RespuestaComparacion,
    RespuestaComparar,
    RespuestaConsulta,
    RespuestaError,
    RespuestaRedirect,
    RespuestaResultados,
    Trazabilidad,
)

_CONCURRENCIA_COMPARACION = 6


class Enrutador:
    def __init__(
        self,
        clientes_ia: dict[str, ClienteIA],
        proveedor_defecto: str,
        boe: AdaptadorBOE,
        cache: Cache | None = None,
        eurlex: AdaptadorEURLex | None = None,
    ) -> None:
        self._clientes = clientes_ia
        self._defecto = proveedor_defecto
        self._boe = boe
        self._cache = cache
        self._eurlex = eurlex

    def proveedores(self) -> dict[str, str | dict[str, str]]:
        return {
            "defecto": self._resolver(self._defecto) or "",
            "disponibles": {n: c.modelo for n, c in self._clientes.items()},
        }

    def _resolver(self, nombre: str) -> str | None:
        """Resuelve un identificador a una clave de cliente: coincidencia exacta,
        prefijo (`openrouter` → primer modelo de OpenRouter) o, para el proveedor
        por defecto ausente, el primero configurado."""
        if nombre in self._clientes:
            return nombre
        for clave in self._clientes:
            if clave.startswith(f"{nombre}:"):
                return clave
        if nombre == self._defecto:
            return next(iter(self._clientes), None)
        return None

    def _cliente(self, proveedor: str | None) -> ClienteIA | RespuestaError:
        nombre = proveedor or self._defecto
        clave = self._resolver(nombre)
        if clave is None:
            configurados = ", ".join(self._clientes) or "ninguno"
            return RespuestaError(
                motivo=(
                    f"Proveedor de IA no disponible: {nombre}. "
                    f"Proveedores configurados: {configurados}."
                )
            )
        return self._clientes[clave]

    async def consultar(self, peticion: PeticionConsulta) -> RespuestaConsulta:
        cliente = self._cliente(peticion.proveedor)
        if isinstance(cliente, RespuestaError):
            return cliente

        consulta = await Comprension(cliente).analizar(
            peticion.pregunta, peticion.comunidad, peticion.rango
        )
        error = _validar(consulta)
        if error is not None:
            return error

        resultado = await self._recuperar(consulta, cliente)
        if isinstance(resultado, RespuestaError | RespuestaRedirect):
            return resultado
        normas, parametros, nota = resultado
        normas = ordenar_normas(normas)

        recuperadas = len(normas)
        normas = ordenar_normas(await Cribado(cliente).filtrar(peticion.pregunta, normas))
        if recuperadas and not normas:
            nota = (
                "La fuente oficial solo devolvió normas con menciones incidentales a la "
                "materia; ninguna la regula directamente."
            )

        if self._eurlex is not None and not any(n.vigente for n in normas):
            normas_ue, parametros_ue = await self._eurlex.buscar(consulta)
            if normas_ue:
                normas_ue = await Cribado(cliente).filtrar(peticion.pregunta, normas_ue)
            if normas_ue:
                normas = ordenar_normas(normas + normas_ue)
                parametros = parametros | {f"eurlex_{k}": v for k, v in parametros_ue.items()}
                aviso_ue = "Se añade la normativa de la Unión Europea aplicable (EUR-Lex)."
                nota = f"{nota} {aviso_ue}" if nota else aviso_ue

        respuesta_ia: str | None = None
        if peticion.redactar_respuesta and normas:
            detalle = await self._boe.obtener_norma(normas[0].identificador)
            respuesta_ia = await Redaccion(cliente).redactar(peticion.pregunta, normas, detalle)
        return RespuestaResultados(
            consulta=consulta,
            normas=normas,
            respuesta_ia=respuesta_ia,
            nota=nota,
            trazabilidad=Trazabilidad(
                fuente="boe",
                parametros=parametros,
                proveedor_ia=cliente.nombre,
                modelo_ia=cliente.modelo,
            ),
        )

    async def comparar(self, peticion: PeticionComparacion) -> RespuestaComparar:
        """Lanza la misma materia contra las 17 comunidades con potestad
        legislativa y devuelve las normas de cada una, ordenadas."""
        cliente = self._cliente(peticion.proveedor)
        if isinstance(cliente, RespuestaError):
            return cliente

        consulta = await Comprension(cliente).analizar(peticion.pregunta)
        error = _validar(consulta)
        if error is not None:
            return error

        limite = asyncio.Semaphore(_CONCURRENCIA_COMPARACION)

        async def por_comunidad(slug: str) -> ComparacionComunidad:
            comunidad = COMUNIDADES[slug]
            async with limite:
                normas, _ = await self._boe.buscar(
                    consulta.model_copy(update={"comunidad": slug}), comunidad.codigos_boe
                )
            return ComparacionComunidad(
                comunidad=slug,
                nombre=comunidad.nombre,
                normas=ordenar_normas(normas)[: peticion.max_por_comunidad],
            )

        resultados = await asyncio.gather(
            *(
                por_comunidad(slug)
                for slug, comunidad in COMUNIDADES.items()
                if comunidad.tiene_potestad_legislativa
            )
        )
        return RespuestaComparacion(
            consulta=consulta,
            resultados=list(resultados),
            trazabilidad=Trazabilidad(
                fuente="boe",
                parametros={"comunidades": str(len(resultados))},
                proveedor_ia=cliente.nombre,
                modelo_ia=cliente.modelo,
            ),
        )

    async def _recuperar(
        self, consulta: ConsultaEstructurada, cliente: ClienteIA
    ) -> tuple[list, dict[str, str], str | None] | RespuestaError | RespuestaRedirect:
        """Resuelve la fuente y recupera las normas: autonómico con recurso a
        estatal, estatal directo, derivación oficial o error."""
        if not consulta.comunidad:
            normas, parametros = await self._boe.buscar(consulta, [])
            nota = "Consulta sin comunidad autónoma: se muestra normativa estatal."
            return normas, parametros, nota

        soporte = resolver_soporte(consulta.comunidad, consulta.rango)
        if soporte is None:
            return RespuestaError(
                motivo=f"Comunidad no reconocida: {consulta.comunidad}", consulta=consulta
            )
        if soporte.fuente != "boe":
            comunidad = COMUNIDADES[consulta.comunidad]
            if self._cache is not None:
                await self._cache.incrementar(f"{consulta.comunidad}:{consulta.rango.value}")
            return RespuestaRedirect(
                consulta=consulta,
                motivo=(
                    f"{comunidad.nombre} no ofrece acceso programático a la normativa de "
                    "rango reglamentario. La consulta debe completarse en su buscador oficial."
                ),
                enlace_oficial=soporte.enlace_oficial,
                nombre_fuente=soporte.nombre_fuente,
                trazabilidad=Trazabilidad(
                    fuente=soporte.nombre_fuente,
                    parametros={},
                    proveedor_ia=cliente.nombre,
                    modelo_ia=cliente.modelo,
                ),
            )

        codigos = COMUNIDADES[consulta.comunidad].codigos_boe
        normas, parametros = await self._boe.buscar(consulta, codigos)
        nota: str | None = None
        if not normas:
            normas, parametros = await self._boe.buscar(consulta, [])
            if normas:
                nombre = COMUNIDADES[consulta.comunidad].nombre
                nota = (
                    f"No hay normativa autonómica de {nombre} sobre esta materia; "
                    "se muestra la normativa estatal aplicable."
                )
        return normas, parametros, nota


def _validar(consulta: ConsultaEstructurada) -> RespuestaError | None:
    if not consulta.es_consulta_normativa:
        return RespuestaError(
            motivo=consulta.motivo_error
            or "La pregunta no parece una consulta de normativa española.",
            consulta=consulta,
        )
    if not consulta.terminos and not consulta.numero_oficial:
        return RespuestaError(
            motivo="No se ha podido extraer una materia o número de norma de la pregunta.",
            consulta=consulta,
        )
    return None
