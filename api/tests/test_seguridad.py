import pytest
from starlette.requests import Request

from legislacion.seguridad import _ip_cliente, _permitido, limite_middleware


class CacheFalsa:
    def __init__(self, valores: list[int]) -> None:
        self._valores = valores
        self.llamadas: list[tuple[str, int]] = []

    async def contar_en_ventana(self, clave: str, ventana: int) -> int:
        self.llamadas.append((clave, ventana))
        return self._valores.pop(0)


def _request(path: str, host: str = "1.2.3.4", xff: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": headers,
        "client": (host, 12345),
        "app": None,
    }
    return Request(scope)


def test_ip_directa():
    assert _ip_cliente(_request("/consulta")) == "1.2.3.4"


def test_ip_desde_x_forwarded_for():
    assert _ip_cliente(_request("/consulta", xff="9.9.9.9, 10.0.0.1")) == "9.9.9.9"


def test_ip_sin_cliente():
    scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "client": None}
    assert _ip_cliente(Request(scope)) == "desconocida"


@pytest.mark.asyncio
async def test_permitido_dentro_del_limite():
    cache = CacheFalsa([1])
    assert await _permitido(cache, "/consulta", "1.2.3.4", 20) is True


@pytest.mark.asyncio
async def test_permitido_al_superar_el_limite():
    cache = CacheFalsa([21])
    assert await _permitido(cache, "/consulta", "1.2.3.4", 20) is False


@pytest.mark.asyncio
async def test_limite_cero_no_bloquea_ni_consulta_redis():
    cache = CacheFalsa([])
    assert await _permitido(cache, "/consulta", "1.2.3.4", 0) is True
    assert cache.llamadas == []


@pytest.mark.asyncio
async def test_middleware_deja_pasar_dentro_del_limite():
    class App:
        class state:  # noqa: N801
            cache = CacheFalsa([5])

    async def siguiente(_request):
        return "respuesta-ok"

    mw = limite_middleware({"/consulta": 20})
    req = _request("/consulta")
    req.scope["app"] = App()
    assert await mw(req, siguiente) == "respuesta-ok"


@pytest.mark.asyncio
async def test_middleware_bloquea_con_429_al_superar():
    class App:
        class state:  # noqa: N801
            cache = CacheFalsa([21])

    async def siguiente(_request):
        return "no-deberia-llegar"

    mw = limite_middleware({"/consulta": 20})
    req = _request("/consulta")
    req.scope["app"] = App()
    respuesta = await mw(req, siguiente)
    assert respuesta.status_code == 429
    assert respuesta.headers["Retry-After"] == "60"


@pytest.mark.asyncio
async def test_middleware_ignora_rutas_no_limitadas():
    async def siguiente(_request):
        return "libre"

    mw = limite_middleware({"/consulta": 20})
    req = _request("/salud")
    assert await mw(req, siguiente) == "libre"
