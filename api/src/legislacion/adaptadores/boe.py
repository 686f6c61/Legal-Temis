"""Adaptador de la API de legislación consolidada del BOE.

Cubre todas las normas con rango de ley de las 17 comunidades autónomas.
La búsqueda y los metadatos se sirven en JSON; el texto consolidado solo
existe en XML y se parsea con lxml.
"""

import json
import re
from typing import Any

import httpx
from lxml import etree

from legislacion.cache import Cache
from legislacion.modelos import Articulo, ConsultaEstructurada, Norma, NormaDetalle

_FORMATO_ID = re.compile(r"^[A-Z]+-[a-z]-\d{4}-\d+$", re.IGNORECASE)
_MIN_LETRAS = 3
_MIN_LETRAS_COMODIN = 4


def _query_string(
    consulta: ConsultaEstructurada,
    codigos_departamento: list[str],
    campo: str = "titulo",
    terminos: list[str] | None = None,
) -> str:
    """Sin códigos de departamento, la búsqueda se acota al ámbito estatal."""
    partes: list[str] = []
    if codigos_departamento:
        codigos = " OR ".join(f"departamento@codigo:{c}" for c in codigos_departamento)
        partes.append(f"({codigos})")
    else:
        partes.append("ambito@codigo:1")
    if consulta.numero_oficial:
        partes.append(f'numero_oficial:"{consulta.numero_oficial}"')
    for termino in consulta.terminos if terminos is None else terminos:
        for palabra in termino.split():
            limpio = re.sub(r"[^\wáéíóúüñÁÉÍÓÚÜÑ]", "", palabra)
            if len(limpio) < _MIN_LETRAS:
                continue
            sufijo = "*" if len(limpio) >= _MIN_LETRAS_COMODIN else ""
            partes.append(f"{campo}:{limpio}{sufijo}")
    return " AND ".join(partes)


def _a_norma(dato: dict[str, Any], comunidad: str) -> Norma:
    identificador = dato["identificador"]
    vigencia = dato.get("vigencia_agotada")
    derogada = dato.get("estatus_derogacion")
    vigente: bool | None = None
    if vigencia is not None or derogada is not None:
        vigente = vigencia != "S" and derogada != "S"
    return Norma(
        identificador=identificador,
        titulo=dato.get("titulo", ""),
        comunidad=comunidad,
        rango=dato.get("rango", {}).get("texto", ""),
        fecha_disposicion=dato.get("fecha_disposicion"),
        numero_oficial=dato.get("numero_oficial"),
        vigente=vigente,
        estado_consolidacion=dato.get("estado_consolidacion", {}).get("texto"),
        url_oficial=dato.get(
            "url_html_consolidada", f"https://www.boe.es/buscar/act.php?id={identificador}"
        ),
        url_eli=dato.get("url_eli"),
        fuente="boe",
    )


class AdaptadorBOE:
    def __init__(self, base_url: str, cache: Cache, timeout: float, max_resultados: int) -> None:
        self._base = base_url.rstrip("/")
        self._cache = cache
        self._timeout = timeout
        self._max = max_resultados

    async def buscar(
        self, consulta: ConsultaEstructurada, codigos_departamento: list[str]
    ) -> tuple[list[Norma], dict[str, str]]:
        """Cadena de búsqueda: título con los términos, título con los sinónimos
        y, como último recurso, texto completo fusionando los resultados de
        términos y sinónimos."""
        datos, parametros = await self._ejecutar(
            _query_string(consulta, codigos_departamento, "titulo")
        )
        for sinonimo in consulta.sinonimos:
            if datos:
                break
            datos, parametros = await self._ejecutar(
                _query_string(consulta, codigos_departamento, "titulo", [sinonimo])
            )
        if not datos and (consulta.terminos or consulta.sinonimos):
            datos, parametros = await self._buscar_en_texto(consulta, codigos_departamento)
        comunidad = (consulta.comunidad if codigos_departamento else None) or "estado"
        return [_a_norma(d, comunidad) for d in datos], parametros

    async def _buscar_en_texto(
        self, consulta: ConsultaEstructurada, codigos_departamento: list[str]
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        grupos: list[list[str]] = []
        if consulta.terminos:
            grupos.append(consulta.terminos)
        grupos.extend([sinonimo] for sinonimo in consulta.sinonimos)
        unicos: dict[str, dict[str, Any]] = {}
        consultas: list[str] = []
        for grupo in grupos:
            qs = _query_string(consulta, codigos_departamento, "texto", grupo)
            datos, _ = await self._ejecutar(qs)
            consultas.append(qs)
            for dato in datos:
                unicos.setdefault(dato["identificador"], dato)
        parametros = {"query": " || ".join(consultas), "limit": str(self._max)}
        return list(unicos.values())[: self._max], parametros

    async def _ejecutar(self, qs: str) -> tuple[list[dict[str, Any]], dict[str, str]]:
        parametros = {
            "query": json.dumps({"query": {"query_string": {"query": qs}}}, ensure_ascii=False),
            "limit": str(self._max),
        }
        clave = f"boe:buscar:{qs}"
        datos = await self._cache.obtener(clave)
        if datos is None:
            async with httpx.AsyncClient(timeout=self._timeout) as cliente:
                respuesta = await cliente.get(
                    self._base, params=parametros, headers={"Accept": "application/json"}
                )
                respuesta.raise_for_status()
                cuerpo = respuesta.json()
            if cuerpo.get("status", {}).get("code") not in ("200", 200):
                msg = f"API BOE: {cuerpo.get('status', {}).get('text', 'error desconocido')}"
                raise RuntimeError(msg)
            datos = cuerpo.get("data", [])
            await self._cache.guardar(clave, datos)
        return datos, parametros

    async def obtener_norma(
        self, identificador: str, fecha: str | None = None
    ) -> NormaDetalle | None:
        """`fecha` en formato YYYYMMDD: devuelve el texto consolidado tal como
        estaba vigente en esa fecha; sin fecha, la versión vigente actual."""
        if not _FORMATO_ID.match(identificador):
            return None
        clave = f"boe:norma:{identificador}:{fecha or 'vigente'}"
        datos = await self._cache.obtener(clave)
        metadatos: dict[str, Any]
        texto: str | None
        articulos: list[dict[str, str | None]]
        if datos is None:
            async with httpx.AsyncClient(timeout=self._timeout) as cliente:
                meta = await cliente.get(
                    f"{self._base}/id/{identificador}/metadatos",
                    headers={"Accept": "application/json"},
                )
                if meta.status_code == httpx.codes.NOT_FOUND:
                    return None
                meta.raise_for_status()
                cuerpo = meta.json()
                lista = cuerpo.get("data", [])
                if not lista:
                    return None
                metadatos = lista[0]
                texto_xml = await cliente.get(
                    f"{self._base}/id/{identificador}/texto",
                    headers={"Accept": "application/xml"},
                )
                url_oficial = metadatos.get(
                    "url_html_consolidada", f"https://www.boe.es/buscar/act.php?id={identificador}"
                )
                texto, articulos = None, []
                if texto_xml.is_success:
                    texto, articulos = _extraer_bloques(texto_xml.content, url_oficial, fecha)
            await self._cache.guardar(
                clave, {"metadatos": metadatos, "texto": texto, "articulos": articulos}
            )
        else:
            metadatos = datos["metadatos"]
            texto = datos.get("texto")
            articulos = datos.get("articulos") or []
        norma = _a_norma(metadatos, metadatos.get("departamento", {}).get("texto", ""))
        return NormaDetalle(
            **norma.model_dump(),
            texto=texto,
            articulos=[Articulo.model_validate(a) for a in articulos],
            fecha_texto=fecha,
            fecha_actualizacion=metadatos.get("fecha_actualizacion"),
        )


def _texto_plano(elemento: etree._Element) -> str:
    fragmentos: list[str] = []
    for fragmento in elemento.itertext():
        texto = fragmento if isinstance(fragmento, str) else fragmento.decode("utf-8", "replace")
        if texto.strip():
            fragmentos.append(texto.strip())
    return "\n".join(fragmentos)


def _version_aplicable(
    bloque: etree._Element, fecha: str | None
) -> tuple[etree._Element | None, str | None]:
    """Entre las versiones del bloque, la última cuya fecha de vigencia no sea
    posterior a la fecha pedida; sin fecha, la de vigencia más reciente."""
    candidatas: list[tuple[str, etree._Element]] = []
    for version in bloque.iter("version"):
        vigencia = version.get("fecha_vigencia") or version.get("fecha_publicacion") or ""
        if fecha and vigencia > fecha:
            continue
        candidatas.append((vigencia, version))
    if not candidatas:
        return None, None
    vigencia, version = max(candidatas, key=lambda c: c[0])
    return version, vigencia or None


def _extraer_bloques(
    contenido_xml: bytes, url_oficial: str, fecha: str | None
) -> tuple[str | None, list[dict[str, str | None]]]:
    try:
        raiz = etree.fromstring(contenido_xml)
    except etree.XMLSyntaxError:
        return None, []
    bloques = list(raiz.iter("bloque"))
    if not bloques:
        texto = _texto_plano(raiz)
        return texto or None, []
    partes: list[str] = []
    articulos: list[dict[str, str | None]] = []
    for bloque in bloques:
        version, vigencia = _version_aplicable(bloque, fecha)
        if version is None:
            continue
        texto = _texto_plano(version)
        if not texto:
            continue
        partes.append(texto)
        if bloque.get("tipo") == "precepto":
            identificador = bloque.get("id") or ""
            articulos.append(
                {
                    "id": identificador,
                    "titulo": bloque.get("titulo") or identificador,
                    "texto": texto,
                    "url": f"{url_oficial}#{identificador}",
                    "vigente_desde": vigencia,
                }
            )
    return ("\n".join(partes) or None), articulos


_ORDEN_RANGOS = [
    ("ley orgánica", 0),
    ("decreto-ley", 2),
    ("decreto ley", 2),
    ("legislativo", 3),
    ("ley", 1),
    ("reglamento delegado", 5),
    ("reglamento de ejecución", 5),
    ("reglamento", 4),
    ("directiva", 4),
    ("real decreto", 4),
    ("decreto", 4),
    ("orden", 5),
]


def _peso_rango(rango: str) -> int:
    nombre = rango.lower()
    for fragmento, peso in _ORDEN_RANGOS:
        if fragmento in nombre:
            return peso
    return 6


def ordenar_normas(normas: list[Norma]) -> list[Norma]:
    """Orden jurídico determinista: vigentes primero, después por rango
    (ley antes que reglamento, reglamento antes que resolución) y, a igualdad,
    la más reciente."""

    def _clave(n: Norma) -> tuple[int, int, int]:
        fecha = n.fecha_disposicion or ""
        return (
            1 if n.vigente is False else 0,
            _peso_rango(n.rango),
            -(int(fecha) if fecha.isdigit() else 0),
        )

    return sorted(normas, key=_clave)
