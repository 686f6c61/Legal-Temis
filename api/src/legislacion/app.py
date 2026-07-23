import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from legislacion.adaptadores.boe import AdaptadorBOE
from legislacion.adaptadores.eurlex import AdaptadorEURLex
from legislacion.cache import Cache
from legislacion.cobertura import tabla_cobertura
from legislacion.config import ajustes
from legislacion.enrutador import Enrutador
from legislacion.ia.fabrica import crear_clientes
from legislacion.modelos import (
    NormaDetalle,
    PeticionComparacion,
    PeticionConsulta,
    RespuestaComparar,
    RespuestaConsulta,
)
from legislacion.seguridad import limite_middleware

_FORMATO_FECHA = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")

_DESCRIPCION = """API de consulta de normativa española y europea en lenguaje natural.

Fuentes oficiales consultadas en vivo, sin memoria de modelo: legislación
consolidada del BOE (leyes de las 17 comunidades autónomas y normativa estatal,
con vigencia y modificaciones) y EUR-Lex vía CELLAR para reglamentos y
directivas de la Unión Europea. Toda norma citada existe en la fuente y enlaza
a ella; los enlaces los construye el sistema de forma determinista, nunca el
modelo de IA.

Flujo de una consulta: comprensión (pregunta → consulta estructurada validada),
recuperación con recurso automático autonómico → estatal → Unión Europea,
cribado de pertinencia, orden jurídico determinista (vigentes primero, leyes
antes que reglamentos, recientes antes) y redacción con citas por artículo.
"""

_ETIQUETAS = [
    {
        "name": "consultas",
        "description": "Consulta en lenguaje natural y comparado entre comunidades.",
    },
    {
        "name": "normas",
        "description": "Acceso directo a una norma con su texto consolidado por artículos.",
    },
    {
        "name": "sistema",
        "description": "Cobertura, proveedores de IA, métricas de derivación y salud.",
    },
]


@asynccontextmanager
async def _ciclo_vida(app: FastAPI) -> AsyncIterator[None]:
    config = ajustes()
    cache = Cache(config.redis_url, config.cache_ttl_segundos)
    boe = AdaptadorBOE(
        config.boe_base_url, cache, config.timeout_fuentes_segundos, config.max_resultados
    )
    eurlex = AdaptadorEURLex(
        config.eurlex_sparql_url, cache, config.timeout_fuentes_segundos, config.max_resultados
    )
    app.state.cache = cache
    app.state.boe = boe
    app.state.enrutador = Enrutador(
        crear_clientes(config), config.proveedor_defecto, boe, cache=cache, eurlex=eurlex
    )
    yield
    await cache.cerrar()


app = FastAPI(
    title="Temis",
    summary="Normativa autonómica, estatal y europea en lenguaje natural, con trazabilidad.",
    description=_DESCRIPCION,
    version="0.1.0",
    openapi_tags=_ETIQUETAS,
    lifespan=_ciclo_vida,
)

_config_inicial = ajustes()
_origenes = [o.strip() for o in _config_inicial.cors_origenes.split(",") if o.strip()]
# El limitador se registra ANTES que CORS para que CORS quede como middleware más
# externo: así toda respuesta —incluidos el 429 del límite y los errores— lleva las
# cabeceras CORS y el navegador la recibe en vez de bloquearla.
app.middleware("http")(
    limite_middleware(
        {
            "/consulta": _config_inicial.limite_consulta_por_minuto,
            "/comparar": _config_inicial.limite_comparar_por_minuto,
        }
    )
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origenes or ["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.post(
    "/consulta",
    tags=["consultas"],
    summary="Consulta en lenguaje natural",
    response_description=(
        "Resultados con normas y respuesta redactada, derivación oficial o error controlado."
    ),
)
async def consulta(peticion: PeticionConsulta) -> RespuestaConsulta:
    """Transforma la pregunta en una búsqueda estructurada y devuelve uno de
    tres tipos de respuesta, siempre con trazabilidad (fuente, parámetros,
    proveedor y modelo de IA):

    - `resultados`: normas recuperadas de la fuente oficial, ordenadas y
      cribadas, con la respuesta redactada por la IA citando artículo a
      artículo (`redactar_respuesta: false` la omite).
    - `redirect_oficial`: la comunidad no ofrece acceso programático a ese
      rango; se devuelve el enlace preparado a su buscador oficial.
    - `error_consulta`: la pregunta no es normativa o le falta información;
      `motivo` explica qué.

    `comunidad` y `rango` fijan valores en lugar de deducirlos; `proveedor`
    elige el modelo de IA (véase `GET /proveedores`), admitiendo el prefijo
    `openrouter` para el primer modelo de su lista.
    """
    enrutador: Enrutador = app.state.enrutador
    return await enrutador.consultar(peticion)


@app.post(
    "/comparar",
    tags=["consultas"],
    summary="Comparado entre las 17 comunidades",
    response_description=(
        "Normas de cada comunidad sobre la misma materia, ordenadas jurídicamente."
    ),
)
async def comparar(peticion: PeticionComparacion) -> RespuestaComparar:
    """Lanza la misma materia contra las 17 comunidades autónomas en paralelo
    y devuelve las normas de cada una (hasta `max_por_comunidad`, por defecto
    3). Sin redacción de IA: es una comparación determinista de fuentes.
    """
    enrutador: Enrutador = app.state.enrutador
    return await enrutador.comparar(peticion)


@app.get(
    "/cobertura",
    tags=["sistema"],
    summary="Mapa de cobertura",
    response_description="Una fila por comunidad y rango, más la Unión Europea.",
)
async def cobertura() -> list[dict[str, str | bool]]:
    """Qué fuente atiende cada combinación comunidad × rango, si está
    soportada con datos o deriva al buscador oficial, y el enlace verificado
    a cada portal.
    """
    return tabla_cobertura()


@app.get(
    "/proveedores",
    tags=["sistema"],
    summary="Proveedores de IA disponibles",
    response_description="Proveedores configurados con su modelo, y el usado por defecto.",
)
async def proveedores() -> dict[str, str | dict[str, str]]:
    """Solo aparecen los proveedores con clave configurada. Las claves de la
    lista son los valores válidos para el campo `proveedor` de las consultas.
    """
    enrutador: Enrutador = app.state.enrutador
    return enrutador.proveedores()


@app.get(
    "/derivaciones",
    tags=["sistema"],
    summary="Contador de derivaciones",
    response_description="Número de derivaciones al buscador oficial por comunidad y rango.",
)
async def derivaciones() -> dict[str, int]:
    """Cada `redirect_oficial` servido incrementa el contador de su combinación
    `comunidad:rango`. Es la medida objetiva de qué adaptador autonómico
    conviene construir a continuación.
    """
    cache: Cache = app.state.cache
    return await cache.contadores()


@app.get(
    "/norma/{identificador}",
    tags=["normas"],
    summary="Norma con texto consolidado por artículos",
    response_description="Metadatos oficiales, texto completo y artículos con enlace de ancla.",
)
async def norma(identificador: str, fecha: str | None = None) -> NormaDetalle:
    """Recupera una norma del BOE por su identificador (por ejemplo
    `BOE-A-2015-4747`). Cada artículo llega con su texto, su fecha de vigencia
    y un enlace con ancla directa al texto oficial consolidado.

    Con `?fecha=AAAA-MM-DD` se reconstruye el texto tal como estaba vigente en
    esa fecha, eligiendo por bloque la versión aplicable del consolidado
    oficial.
    """
    fecha_compacta: str | None = None
    if fecha is not None:
        coincidencia = _FORMATO_FECHA.match(fecha)
        if coincidencia is None:
            raise HTTPException(
                status_code=400, detail="Formato de fecha no válido; usa AAAA-MM-DD."
            )
        fecha_compacta = "".join(coincidencia.groups())
    boe: AdaptadorBOE = app.state.boe
    detalle = await boe.obtener_norma(identificador, fecha_compacta)
    if detalle is None:
        raise HTTPException(status_code=404, detail=f"Norma no encontrada: {identificador}")
    return detalle


@app.get("/salud", tags=["sistema"], summary="Comprobación de vida")
async def salud() -> dict[str, str]:
    return {"estado": "ok"}
