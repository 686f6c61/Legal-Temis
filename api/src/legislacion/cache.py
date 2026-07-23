import json
from typing import Any

import redis.asyncio as redis_async


class Cache:
    """Cache de respuestas de fuentes oficiales. Si Redis no está disponible,
    degrada a no cachear: el sistema sigue funcionando, solo más lento."""

    def __init__(self, url: str, ttl_segundos: int) -> None:
        self._ttl = ttl_segundos
        self._cliente: redis_async.Redis | None = None
        self._url = url

    async def _conexion(self) -> redis_async.Redis | None:
        if self._cliente is None:
            try:
                self._cliente = redis_async.from_url(
                    self._url, socket_connect_timeout=2, decode_responses=True
                )
                await self._cliente.ping()
            except redis_async.RedisError, OSError:
                self._cliente = None
        return self._cliente

    async def obtener(self, clave: str) -> Any | None:  # noqa: ANN401
        cliente = await self._conexion()
        if cliente is None:
            return None
        try:
            valor = await cliente.get(clave)
        except redis_async.RedisError, OSError:
            return None
        return json.loads(valor) if valor else None

    async def guardar(self, clave: str, valor: Any) -> None:  # noqa: ANN401
        cliente = await self._conexion()
        if cliente is None:
            return
        try:
            await cliente.set(clave, json.dumps(valor), ex=self._ttl)
        except redis_async.RedisError, OSError:
            return

    async def incrementar(self, campo: str) -> None:
        cliente = await self._conexion()
        if cliente is None:
            return
        try:
            await cliente.hincrby("legislacion:derivaciones", campo, 1)
        except redis_async.RedisError, OSError:
            return

    async def contadores(self) -> dict[str, int]:
        cliente = await self._conexion()
        if cliente is None:
            return {}
        try:
            datos = await cliente.hgetall("legislacion:derivaciones")
        except redis_async.RedisError, OSError:
            return {}
        return {
            (campo if isinstance(campo, str) else campo.decode()): int(valor)
            for campo, valor in datos.items()
        }

    async def contar_en_ventana(self, clave: str, ventana_segundos: int) -> int:
        """Incrementa un contador de ventana fija y devuelve su valor. La primera
        vez fija la caducidad. Si Redis no está disponible, devuelve 0 (fail-open:
        el rate limiter no bloquea si la cache cae)."""
        cliente = await self._conexion()
        if cliente is None:
            return 0
        try:
            valor = await cliente.incr(clave)  # ty: ignore[invalid-await]
            if valor == 1:
                await cliente.expire(clave, ventana_segundos)
        except redis_async.RedisError, OSError:
            return 0
        return int(valor)

    async def cerrar(self) -> None:
        if self._cliente is not None:
            await self._cliente.aclose()
            self._cliente = None
