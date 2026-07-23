"""Limitador de tasa por IP sobre Redis (ventana fija de un minuto).

Evita el abuso por volumen: cada IP tiene un cupo de peticiones por minuto y
endpoint. Sin dependencias externas; usa el mismo Redis que la cache. Si Redis
no está disponible, no bloquea (fail-open), para no denegar el servicio ante
una caída de la cache."""

import time

from fastapi import Request  # noqa: TC002
from starlette.responses import JSONResponse

from legislacion.cache import Cache

_VENTANA_SEGUNDOS = 60


def _ip_cliente(request: Request) -> str:
    """IP del cliente, respetando X-Forwarded-For si hay un proxy delante (el
    primero de la lista es el cliente original)."""
    reenviada = request.headers.get("x-forwarded-for")
    if reenviada:
        return reenviada.split(",")[0].strip()
    return request.client.host if request.client else "desconocida"


async def _permitido(cache: Cache, ruta: str, ip: str, limite: int) -> bool:
    if limite <= 0:
        return True
    minuto = int(time.time() // _VENTANA_SEGUNDOS)
    clave = f"legislacion:rl:{ruta}:{ip}:{minuto}"
    usados = await cache.contar_en_ventana(clave, _VENTANA_SEGUNDOS)
    return usados <= limite


def limite_middleware(limites: dict[str, int]):  # noqa: ANN201
    """Middleware que limita las rutas de `limites` (ruta → peticiones/minuto).
    Lee la cache de `app.state.cache`, compartida con el resto del sistema."""

    async def middleware(request: Request, call_next):  # noqa: ANN001, ANN202
        limite = limites.get(request.url.path)
        if limite is not None:
            cache: Cache = request.app.state.cache
            ip = _ip_cliente(request)
            if not await _permitido(cache, request.url.path, ip, limite):
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": (
                            f"Límite de {limite} peticiones por minuto superado. "
                            "Espera un momento antes de volver a consultar."
                        )
                    },
                    headers={"Retry-After": str(_VENTANA_SEGUNDOS)},
                )
        return await call_next(request)

    return middleware
