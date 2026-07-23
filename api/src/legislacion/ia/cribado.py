from pydantic import BaseModel, Field

from legislacion.ia.base import ClienteIA
from legislacion.modelos import Norma

_SISTEMA = """Eres el filtro de pertinencia de un sistema de consulta de normativa \
española. Recibes la pregunta del usuario y una lista de normas candidatas \
recuperadas de fuentes oficiales (identificador, rango y título).

Reglas:
- Devuelve en identificadores_relevantes solo los identificadores de las normas que \
de verdad regulan o tratan la materia por la que se pregunta.
- Descarta las normas que solo mencionan la materia de forma incidental (por \
ejemplo, un currículo educativo o una estrategia sectorial que la cita de pasada).
- Usa exclusivamente identificadores de la lista recibida, escritos tal cual.
- Si ninguna candidata es pertinente, devuelve la lista vacía.
- Conserva el orden de mayor a menor pertinencia."""


class Seleccion(BaseModel):
    identificadores_relevantes: list[str] = Field(default_factory=list)


class Cribado:
    def __init__(self, cliente: ClienteIA) -> None:
        self._cliente = cliente

    async def filtrar(self, pregunta: str, normas: list[Norma]) -> list[Norma]:
        if len(normas) <= 1:
            return normas
        lineas = [f"- {n.identificador} | {n.rango} | {n.titulo}" for n in normas]
        contenido = f"PREGUNTA:\n{pregunta}\n\nNORMAS CANDIDATAS:\n" + "\n".join(lineas)
        seleccion = await self._cliente.estructurar(_SISTEMA, contenido, Seleccion)
        if seleccion is None:
            return normas
        por_id = {n.identificador: n for n in normas}
        vistos: set[str] = set()
        filtradas: list[Norma] = []
        for identificador in seleccion.identificadores_relevantes:
            norma = por_id.get(identificador)
            if norma is not None and identificador not in vistos:
                vistos.add(identificador)
                filtradas.append(norma)
        return filtradas
