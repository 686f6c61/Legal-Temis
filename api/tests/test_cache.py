import pytest
import redis.asyncio as redis_async

from legislacion.cache import Cache


class RedisFalso:
    def __init__(self) -> None:
        self.datos: dict[str, str] = {}
        self.cerrado = False

    async def ping(self) -> None:
        pass

    async def get(self, clave: str) -> str | None:
        return self.datos.get(clave)

    async def set(self, clave: str, valor: str, ex: int | None = None) -> None:
        self.datos[clave] = valor

    async def aclose(self) -> None:
        self.cerrado = True


class RedisRoto(RedisFalso):
    async def get(self, clave: str) -> str | None:
        raise redis_async.RedisError

    async def set(self, clave: str, valor: str, ex: int | None = None) -> None:
        raise redis_async.RedisError


def _cache_con(monkeypatch, falso: RedisFalso) -> Cache:
    monkeypatch.setattr("legislacion.cache.redis_async.from_url", lambda *_a, **_k: falso)
    return Cache("redis://da-igual:6379/0", ttl_segundos=60)


@pytest.mark.asyncio
async def test_guardar_y_obtener(monkeypatch):
    cache = _cache_con(monkeypatch, RedisFalso())
    await cache.guardar("clave", {"a": 1})
    assert await cache.obtener("clave") == {"a": 1}


@pytest.mark.asyncio
async def test_obtener_inexistente_devuelve_none(monkeypatch):
    cache = _cache_con(monkeypatch, RedisFalso())
    assert await cache.obtener("no-existe") is None


@pytest.mark.asyncio
async def test_errores_de_redis_no_rompen(monkeypatch):
    cache = _cache_con(monkeypatch, RedisRoto())
    await cache.guardar("clave", {"a": 1})
    assert await cache.obtener("clave") is None


@pytest.mark.asyncio
async def test_cerrar_libera_la_conexion(monkeypatch):
    falso = RedisFalso()
    cache = _cache_con(monkeypatch, falso)
    await cache.guardar("clave", 1)
    await cache.cerrar()
    assert falso.cerrado is True
    await cache.cerrar()


@pytest.mark.asyncio
async def test_sin_redis_degrada_a_no_cachear():
    cache = Cache("redis://inexistente:1/0", ttl_segundos=60)
    await cache.guardar("clave", 1)
    assert await cache.obtener("clave") is None
    await cache.cerrar()


class RedisContadores(RedisFalso):
    def __init__(self) -> None:
        super().__init__()
        self.hash: dict[str, int] = {}

    async def hincrby(self, clave: str, campo: str, cantidad: int) -> None:
        self.hash[campo] = self.hash.get(campo, 0) + cantidad

    async def hgetall(self, clave: str) -> dict[str, str]:
        return {k: str(v) for k, v in self.hash.items()}


class RedisContadoresRoto(RedisContadores):
    async def hincrby(self, clave: str, campo: str, cantidad: int) -> None:
        raise redis_async.RedisError

    async def hgetall(self, clave: str) -> dict[str, str]:
        raise redis_async.RedisError


@pytest.mark.asyncio
async def test_contador_de_derivaciones(monkeypatch):
    cache = _cache_con(monkeypatch, RedisContadores())
    await cache.incrementar("madrid:reglamento")
    await cache.incrementar("madrid:reglamento")
    await cache.incrementar("galicia:reglamento")
    assert await cache.contadores() == {"madrid:reglamento": 2, "galicia:reglamento": 1}


@pytest.mark.asyncio
async def test_contadores_con_redis_roto_no_rompen(monkeypatch):
    cache = _cache_con(monkeypatch, RedisContadoresRoto())
    await cache.incrementar("x")
    assert await cache.contadores() == {}


@pytest.mark.asyncio
async def test_contadores_sin_redis():
    cache = Cache("redis://inexistente:1/0", ttl_segundos=60)
    await cache.incrementar("x")
    assert await cache.contadores() == {}


class RedisVentana(RedisFalso):
    def __init__(self) -> None:
        super().__init__()
        self.contadores: dict[str, int] = {}
        self.expiraciones: list[tuple[str, int]] = []

    async def incr(self, clave: str) -> int:
        self.contadores[clave] = self.contadores.get(clave, 0) + 1
        return self.contadores[clave]

    async def expire(self, clave: str, segundos: int) -> None:
        self.expiraciones.append((clave, segundos))


class RedisVentanaRoto(RedisVentana):
    async def incr(self, clave: str) -> int:
        raise redis_async.RedisError


@pytest.mark.asyncio
async def test_contar_en_ventana_incrementa_y_expira_la_primera_vez(monkeypatch):
    falso = RedisVentana()
    cache = _cache_con(monkeypatch, falso)
    assert await cache.contar_en_ventana("k", 60) == 1
    assert await cache.contar_en_ventana("k", 60) == 2
    assert falso.expiraciones == [("k", 60)]


@pytest.mark.asyncio
async def test_contar_en_ventana_con_redis_roto_devuelve_cero(monkeypatch):
    cache = _cache_con(monkeypatch, RedisVentanaRoto())
    assert await cache.contar_en_ventana("k", 60) == 0


@pytest.mark.asyncio
async def test_contar_en_ventana_sin_redis_devuelve_cero():
    cache = Cache("redis://inexistente:1/0", ttl_segundos=60)
    assert await cache.contar_en_ventana("k", 60) == 0
