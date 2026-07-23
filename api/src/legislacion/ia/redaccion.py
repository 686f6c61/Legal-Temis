from legislacion.ia.base import ClienteIA
from legislacion.modelos import Norma, NormaDetalle

_SISTEMA = """Eres el redactor de un sistema de consulta de normativa autonómica \
española dirigido a profesionales del derecho. Recibes la pregunta del usuario y las \
normas recuperadas de fuentes oficiales.

Reglas inquebrantables:
- Solo puedes citar normas que aparezcan en la lista recuperada. Nunca menciones \
normas que no estén en ella, aunque las conozcas.
- Cada afirmación relevante debe ir acompañada de la cita de la norma de la que \
procede: título abreviado más el identificador oficial escrito exactamente como \
aparece en la lista (por ejemplo BOE-A-2026-423), sin alterarlo.
- Cuando la afirmación proceda de un artículo concreto de la norma principal, cita \
el artículo (por ejemplo: artículo 4, Ley 6/2015, BOE-A-2015-4747). Usa solo los \
artículos que se te facilitan.
- Nunca escribas URLs en el texto: el sistema convierte los identificadores en \
enlaces oficiales automáticamente.
- Si el estado de vigencia de una norma no está garantizado por la fuente, dilo.
- Si las normas recuperadas no permiten responder la pregunta, di exactamente eso y \
no rellenes con conocimiento propio.
- Responde en castellano, en tono profesional y conciso: primero la respuesta, \
después el detalle.
- Responde en texto plano, sin ningún formato Markdown: nada de asteriscos, \
almohadillas, guiones de lista, tablas ni separadores. Estructura con párrafos y, \
si necesitas enumerar, usa numeración simple (1., 2., 3.) al inicio de línea."""


def _formatear_normas(
    normas: list[Norma], detalle: NormaDetalle | None, max_caracteres: int
) -> str:
    lineas = ["NORMAS RECUPERADAS DE FUENTES OFICIALES:"]
    for n in normas:
        vigencia = {True: "vigente", False: "no vigente"}.get(n.vigente, "vigencia no verificada")
        lineas.append(
            f"- [{n.identificador}] {n.titulo} ({n.rango}, {n.comunidad}, {vigencia}) "
            f"— {n.url_oficial}"
        )
    if detalle is None:
        return "\n".join(lineas)
    if detalle.articulos:
        lineas.append(f"\nARTÍCULOS DE LA NORMA PRINCIPAL [{detalle.identificador}]:")
        restante = max_caracteres
        for articulo in detalle.articulos:
            fragmento = f"[{articulo.titulo}] {articulo.texto}"
            if len(fragmento) > restante:
                break
            lineas.append(fragmento)
            restante -= len(fragmento)
    elif detalle.texto:
        lineas.append("\nTEXTO CONSOLIDADO DE LA NORMA PRINCIPAL (extracto):")
        lineas.append(detalle.texto[:max_caracteres])
    return "\n".join(lineas)


class Redaccion:
    def __init__(self, cliente: ClienteIA, max_caracteres_texto: int = 40000) -> None:
        self._cliente = cliente
        self._max_texto = max_caracteres_texto

    async def redactar(
        self, pregunta: str, normas: list[Norma], detalle: NormaDetalle | None = None
    ) -> str | None:
        if not normas:
            return None
        contenido = (
            f"{_formatear_normas(normas, detalle, self._max_texto)}"
            f"\n\nPREGUNTA DEL USUARIO:\n{pregunta}"
        )
        return await self._cliente.generar(_SISTEMA, contenido)
