from legislacion.cobertura import COMUNIDADES, resolver_soporte, tabla_cobertura
from legislacion.modelos import Rango


def test_hay_19_territorios():
    assert len(COMUNIDADES) == 19


def test_ley_se_resuelve_por_boe():
    soporte = resolver_soporte("andalucia", Rango.LEY)
    assert soporte is not None
    assert soporte.fuente == "boe"


def test_rango_desconocido_se_resuelve_por_boe():
    soporte = resolver_soporte("galicia", Rango.DESCONOCIDO)
    assert soporte is not None
    assert soporte.fuente == "boe"


def test_reglamento_deriva_al_buscador_oficial():
    soporte = resolver_soporte("madrid", Rango.REGLAMENTO)
    assert soporte is not None
    assert soporte.fuente is None
    assert soporte.enlace_oficial == "https://gestiona.comunidad.madrid/wleg_pub"


def test_ceuta_sin_potestad_legislativa_deriva_siempre():
    soporte = resolver_soporte("ceuta", Rango.LEY)
    assert soporte is not None
    assert soporte.fuente is None


def test_comunidad_desconocida_devuelve_none():
    assert resolver_soporte("gotham", Rango.LEY) is None


def test_valencia_y_baleares_tienen_doble_codigo():
    assert COMUNIDADES["valencia"].codigos_boe == ["8161", "8162"]
    assert COMUNIDADES["baleares"].codigos_boe == ["8120", "8121"]


def test_tabla_cobertura_cubre_todo():
    filas = tabla_cobertura()
    assert len(filas) == 19 * 2 + 1
    soportadas = [f for f in filas if f["soportado"]]
    assert len(soportadas) == 18
