from legislacion.cobertura import COMUNIDADES
from legislacion.ia.base import ClienteIA
from legislacion.modelos import ConsultaEstructurada, Rango

_SLUGS = ", ".join(COMUNIDADES.keys())

_SISTEMA = f"""Eres el analizador de consultas de un sistema de búsqueda de normativa \
autonómica española. Tu única tarea es transformar la pregunta del usuario en una \
consulta estructurada. No respondes la pregunta: solo la analizas.

Reglas:
- es_consulta_normativa: true si la pregunta busca normativa española (leyes, \
decretos, órdenes, regulación), sea estatal o autonómica. Preguntas de otro tipo \
(conversación general, opiniones, otros países) → false, con motivo_error explicando \
por qué en una frase.
- comunidad: exactamente uno de estos identificadores, o null: {_SLUGS}. Si la \
pregunta menciona un municipio, ciudad, provincia o isla de España, asigna la \
comunidad autónoma a la que pertenece (Sevilla → andalucia, Bilbao → pais-vasco, \
Gijón → asturias, León → castilla-y-leon, Ibiza → baleares). Si no menciona \
comunidad ni lugar que permita deducirla, déjala en null: la búsqueda se hará sobre \
la normativa estatal.
- rango: "ley" si pregunta por una ley, decreto-ley, decreto legislativo o ley foral; \
"reglamento" si pregunta por un decreto ordinario, orden de consejería, resolución o \
instrucción; "desconocido" si no se distingue.
- terminos: entre 1 y 4 palabras clave de la materia, en singular y sin artículos \
(por ejemplo: vivienda, turismo, juego). Sin la comunidad ni el rango.
- sinonimos: de 0 a 3 términos alternativos con los que la legislación española \
suele denominar esa misma materia (por ejemplo criptomoneda → criptoactivo, \
moneda virtual; alquiler → arrendamiento). Vacío si no hay alternativa clara.
- numero_oficial: solo si el usuario cita un número de norma tipo "5/2025"."""


class Comprension:
    def __init__(self, cliente: ClienteIA) -> None:
        self._cliente = cliente

    async def analizar(
        self,
        pregunta: str,
        comunidad_fijada: str | None = None,
        rango_fijado: Rango | None = None,
    ) -> ConsultaEstructurada:
        consulta = await self._cliente.estructurar(_SISTEMA, pregunta, ConsultaEstructurada)
        if consulta is None:
            return ConsultaEstructurada(
                es_consulta_normativa=False,
                motivo_error="No se pudo analizar la consulta.",
            )
        if comunidad_fijada:
            consulta = consulta.model_copy(update={"comunidad": comunidad_fijada})
        if rango_fijado:
            consulta = consulta.model_copy(update={"rango": rango_fijado})
        return consulta
