from fastapi.testclient import TestClient

from legislacion.app import app
from legislacion.modelos import NormaDetalle


def test_salud_y_cobertura():
    with TestClient(app) as cliente:
        assert cliente.get("/salud").json() == {"estado": "ok"}
        filas = cliente.get("/cobertura").json()
        assert len(filas) == 39
        assert any(f["slug"] == "andalucia" and f["soportado"] for f in filas)


def test_norma_con_identificador_invalido_da_404():
    with TestClient(app) as cliente:
        assert cliente.get("/norma/no-es-un-id").status_code == 404


def test_proveedores_sin_claves():
    with TestClient(app) as cliente:
        info = cliente.get("/proveedores").json()
        assert info["disponibles"] == {}
        assert info["defecto"] == ""


def test_consulta_sin_proveedor_configurado_devuelve_error():
    with TestClient(app) as cliente:
        respuesta = cliente.post("/consulta", json={"pregunta": "ley de caza de Galicia"}).json()
        assert respuesta["tipo"] == "error_consulta"
        assert "Proveedores configurados: ninguno" in respuesta["motivo"]


def test_norma_existente_se_sirve():

    class BoeFalso:
        async def obtener_norma(self, identificador, fecha=None):
            return NormaDetalle(
                identificador=identificador,
                titulo="Ley de prueba",
                comunidad="andalucia",
                rango="Ley",
                url_oficial="https://www.boe.es/buscar/act.php?id=X",
                fuente="boe",
                texto="Artículo único.",
            )

    with TestClient(app) as cliente:
        app.state.boe = BoeFalso()
        cuerpo = cliente.get("/norma/BOE-A-2026-423").json()
        assert cuerpo["titulo"] == "Ley de prueba"
        assert cuerpo["texto"] == "Artículo único."


def test_norma_con_fecha_invalida_da_400():
    with TestClient(app) as cliente:
        respuesta = cliente.get("/norma/BOE-A-2026-423?fecha=23-07-2026")
        assert respuesta.status_code == 400


def test_norma_con_fecha_valida_la_convierte_a_formato_compacto():
    fechas = []

    class BoeFalso:
        async def obtener_norma(self, identificador, fecha=None):
            fechas.append(fecha)
            return NormaDetalle(
                identificador=identificador,
                titulo="Ley de prueba",
                comunidad="andalucia",
                rango="Ley",
                url_oficial="https://www.boe.es/buscar/act.php?id=X",
                fuente="boe",
            )

    with TestClient(app) as cliente:
        app.state.boe = BoeFalso()
        assert cliente.get("/norma/BOE-A-2026-423?fecha=2023-05-10").status_code == 200
        assert fechas == ["20230510"]


def test_comparar_sin_proveedor_configurado():
    with TestClient(app) as cliente:
        respuesta = cliente.post(
            "/comparar", json={"pregunta": "vivienda en cada comunidad"}
        ).json()
        assert respuesta["tipo"] == "error_consulta"


def test_derivaciones_sin_redis_devuelve_vacio():
    with TestClient(app) as cliente:
        assert cliente.get("/derivaciones").json() == {}
