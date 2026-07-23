"""Adaptador de EUR-Lex vía el punto SPARQL de CELLAR (Oficina de
Publicaciones de la UE). Busca reglamentos y directivas por título en
castellano; los identificadores son números CELEX con URL oficial estable."""

import re
from typing import Any

import httpx

from legislacion.cache import Cache
from legislacion.modelos import ConsultaEstructurada, Norma

_MIN_LETRAS = 3

_TIPOS = ", ".join(
    f"<http://publications.europa.eu/resource/authority/resource-type/{t}>"
    for t in ("REG", "DIR", "REG_DEL", "REG_IMPL", "DIR_DEL", "DIR_IMPL")
)

_PLANTILLA = """PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?celex ?titulo ?envigor ?fecha ?eli WHERE {{
  ?exp cdm:expression_belongs_to_work ?work ;
       cdm:expression_uses_language
         <http://publications.europa.eu/resource/authority/language/SPA> ;
       cdm:expression_title ?titulo .
  ?titulo bif:contains "{busqueda}" .
  ?work cdm:resource_legal_id_celex ?celex .
  ?work cdm:work_has_resource-type ?tipo .
  FILTER(?tipo IN ({tipos}))
  FILTER(!STRSTARTS(?titulo, "Corrección de errores"))
  BIND(IF(
    ?tipo = <http://publications.europa.eu/resource/authority/resource-type/REG>
      || ?tipo = <http://publications.europa.eu/resource/authority/resource-type/DIR>,
    0, 1) AS ?prioridad)
  OPTIONAL {{ ?work cdm:resource_legal_in-force ?envigor }}
  OPTIONAL {{ ?work cdm:work_date_document ?fecha }}
  OPTIONAL {{ ?work cdm:resource_legal_eli ?eli }}
}} ORDER BY ?prioridad DESC(?fecha) LIMIT {limite}"""

_RANGOS_UE = ("Reglamento Delegado", "Reglamento de Ejecución", "Reglamento", "Directiva")


def _expresion_busqueda(terminos: list[str]) -> str:
    palabras: list[str] = []
    for termino in terminos:
        for palabra in termino.split():
            limpio = re.sub(r"[^\wáéíóúüñÁÉÍÓÚÜÑ]", "", palabra)
            if len(limpio) >= _MIN_LETRAS:
                palabras.append(f"'{limpio}*'")
    return " AND ".join(palabras)


def _rango_ue(titulo: str) -> str:
    for rango in _RANGOS_UE:
        if titulo.startswith(rango):
            return rango
    return "Norma UE"


def _a_norma(fila: dict[str, Any]) -> Norma:
    celex = fila["celex"]["value"]
    titulo = fila["titulo"]["value"]
    envigor = fila.get("envigor", {}).get("value")
    fecha = (fila.get("fecha", {}).get("value") or "").replace("-", "") or None
    return Norma(
        identificador=celex,
        titulo=titulo,
        comunidad="union-europea",
        rango=_rango_ue(titulo),
        fecha_disposicion=fecha,
        vigente=None if envigor is None else envigor in ("1", "true"),
        url_oficial=f"https://eur-lex.europa.eu/legal-content/ES/TXT/?uri=CELEX:{celex}",
        url_eli=fila.get("eli", {}).get("value"),
        fuente="eurlex",
    )


class AdaptadorEURLex:
    def __init__(self, endpoint: str, cache: Cache, timeout: float, max_resultados: int) -> None:
        self._endpoint = endpoint
        self._cache = cache
        self._timeout = timeout
        self._max = max_resultados

    async def buscar(self, consulta: ConsultaEstructurada) -> tuple[list[Norma], dict[str, str]]:
        """Prueba los términos y, si no hay resultados, cada sinónimo."""
        grupos: list[list[str]] = []
        if consulta.terminos:
            grupos.append(consulta.terminos)
        grupos.extend([sinonimo] for sinonimo in consulta.sinonimos)

        filas: list[dict[str, Any]] = []
        busqueda = ""
        for grupo in grupos:
            busqueda = _expresion_busqueda(grupo)
            if not busqueda:
                continue
            filas = await self._ejecutar(busqueda)
            if filas:
                break
        parametros = {"endpoint": self._endpoint, "busqueda": busqueda}
        return [_a_norma(f) for f in filas], parametros

    async def _ejecutar(self, busqueda: str) -> list[dict[str, Any]]:
        clave = f"eurlex:{busqueda}"
        filas = await self._cache.obtener(clave)
        if filas is None:
            query = _PLANTILLA.format(busqueda=busqueda, tipos=_TIPOS, limite=self._max)
            async with httpx.AsyncClient(timeout=self._timeout) as cliente:
                respuesta = await cliente.get(
                    self._endpoint,
                    params={"query": query, "format": "application/sparql-results+json"},
                )
                respuesta.raise_for_status()
                cuerpo = respuesta.json()
            filas = cuerpo.get("results", {}).get("bindings", [])
            await self._cache.guardar(clave, filas)
        return filas
