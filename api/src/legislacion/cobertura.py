"""Registro de cobertura: qué fuente atiende cada combinación comunidad × rango.

Los códigos de departamento proceden de la API de legislación consolidada del BOE
(consulta en vivo sobre las 3.610 normas con ambito@codigo:2). Baleares y la
Comunitat Valenciana conservan dos códigos por renombrado histórico: las búsquedas
deben incluir ambos.
"""

from pydantic import BaseModel

from legislacion.modelos import Rango


class Comunidad(BaseModel):
    slug: str
    nombre: str
    codigos_boe: list[str]
    boletin: str
    buscador_oficial: str
    consolidado_oficial: str | None = None
    tiene_potestad_legislativa: bool = True


COMUNIDADES: dict[str, Comunidad] = {
    c.slug: c
    for c in [
        Comunidad(
            slug="andalucia",
            nombre="Andalucía",
            codigos_boe=["8010"],
            boletin="BOJA",
            buscador_oficial="https://www.juntadeandalucia.es/buscar.html",
        ),
        Comunidad(
            slug="aragon",
            nombre="Aragón",
            codigos_boe=["8020"],
            boletin="BOA",
            buscador_oficial="https://www.boa.aragon.es",
        ),
        Comunidad(
            slug="asturias",
            nombre="Principado de Asturias",
            codigos_boe=["8150"],
            boletin="BOPA",
            buscador_oficial="https://miprincipado.asturias.es/bopa",
        ),
        Comunidad(
            slug="baleares",
            nombre="Illes Balears",
            codigos_boe=["8120", "8121"],
            boletin="BOIB",
            buscador_oficial="https://www.caib.es/eboibfront",
        ),
        Comunidad(
            slug="canarias",
            nombre="Canarias",
            codigos_boe=["8030"],
            boletin="BOC",
            buscador_oficial="https://www.gobiernodecanarias.org/boc/busqueda.html",
            consolidado_oficial="https://www3.gobiernodecanarias.org/libroazul",
        ),
        Comunidad(
            slug="cantabria",
            nombre="Cantabria",
            codigos_boe=["8040"],
            boletin="BOC de Cantabria",
            buscador_oficial="https://boc.cantabria.es/boces/",
        ),
        Comunidad(
            slug="castilla-la-mancha",
            nombre="Castilla-La Mancha",
            codigos_boe=["8060"],
            boletin="DOCM",
            buscador_oficial="https://docm.jccm.es/docm/busquedaAvanzada.do",
        ),
        Comunidad(
            slug="castilla-y-leon",
            nombre="Castilla y León",
            codigos_boe=["9531"],
            boletin="BOCYL",
            buscador_oficial="https://bocyl.jcyl.es",
        ),
        Comunidad(
            slug="cataluna",
            nombre="Cataluña",
            codigos_boe=["8070"],
            boletin="DOGC",
            buscador_oficial="https://portaljuridic.gencat.cat",
            consolidado_oficial="https://portaljuridic.gencat.cat",
        ),
        Comunidad(
            slug="extremadura",
            nombre="Extremadura",
            codigos_boe=["8080"],
            boletin="DOE",
            buscador_oficial="https://doe.juntaex.es/busquedas/bus_avanzada.php",
            consolidado_oficial="https://doe.juntaex.es/consolidada/consolidadas.php",
        ),
        Comunidad(
            slug="galicia",
            nombre="Galicia",
            codigos_boe=["8090"],
            boletin="DOG",
            buscador_oficial="https://www.xunta.gal/diario-oficial-galicia/portalPublicoBusqueda.do",
            consolidado_oficial="https://transparencia.xunta.gal/tema/informacion-de-relevancia-xuridica/normativa-consolidada",
        ),
        Comunidad(
            slug="la-rioja",
            nombre="La Rioja",
            codigos_boe=["8110"],
            boletin="BOR",
            buscador_oficial="https://web.larioja.org/bor-portada",
        ),
        Comunidad(
            slug="madrid",
            nombre="Comunidad de Madrid",
            codigos_boe=["8131"],
            boletin="BOCM",
            buscador_oficial="https://www.bocm.es",
            consolidado_oficial="https://gestiona.comunidad.madrid/wleg_pub",
        ),
        Comunidad(
            slug="murcia",
            nombre="Región de Murcia",
            codigos_boe=["8100"],
            boletin="BORM",
            buscador_oficial="https://www.borm.es",
        ),
        Comunidad(
            slug="navarra",
            nombre="Comunidad Foral de Navarra",
            codigos_boe=["8170"],
            boletin="BON",
            buscador_oficial="https://bon.navarra.es",
            consolidado_oficial="http://www.lexnavarra.navarra.es",
        ),
        Comunidad(
            slug="pais-vasco",
            nombre="País Vasco",
            codigos_boe=["8140"],
            boletin="BOPV",
            buscador_oficial="https://www.euskadi.eus/web01-bopv/es/",
        ),
        Comunidad(
            slug="valencia",
            nombre="Comunitat Valenciana",
            codigos_boe=["8161", "8162"],
            boletin="DOGV",
            buscador_oficial="https://dogv.gva.es/es",
        ),
        Comunidad(
            slug="ceuta",
            nombre="Ceuta",
            codigos_boe=[],
            boletin="BOCCE",
            buscador_oficial="https://www.ceuta.es/ceuta/bocce",
            tiene_potestad_legislativa=False,
        ),
        Comunidad(
            slug="melilla",
            nombre="Melilla",
            codigos_boe=[],
            boletin="BOME",
            buscador_oficial="https://bomemelilla.es/buscar",
            tiene_potestad_legislativa=False,
        ),
    ]
}


class Soporte(BaseModel):
    comunidad: str
    rango: Rango
    fuente: str | None
    nivel: str
    enlace_oficial: str
    nombre_fuente: str


def _soporte(comunidad: Comunidad, rango: Rango) -> Soporte:
    if rango in (Rango.LEY, Rango.DESCONOCIDO) and comunidad.tiene_potestad_legislativa:
        return Soporte(
            comunidad=comunidad.slug,
            rango=rango,
            fuente="boe",
            nivel="api_consolidada",
            enlace_oficial="https://www.boe.es/buscar/legislacion.php",
            nombre_fuente="BOE - Legislación consolidada",
        )
    return Soporte(
        comunidad=comunidad.slug,
        rango=rango,
        fuente=None,
        nivel="redirect_oficial",
        enlace_oficial=comunidad.consolidado_oficial or comunidad.buscador_oficial,
        nombre_fuente=comunidad.boletin,
    )


def resolver_soporte(slug: str, rango: Rango) -> Soporte | None:
    comunidad = COMUNIDADES.get(slug)
    return None if comunidad is None else _soporte(comunidad, rango)


def tabla_cobertura() -> list[dict[str, str | bool]]:
    filas: list[dict[str, str | bool]] = []
    for slug, comunidad in COMUNIDADES.items():
        for rango in (Rango.LEY, Rango.REGLAMENTO):
            soporte = _soporte(comunidad, rango)
            filas.append(
                {
                    "comunidad": comunidad.nombre,
                    "slug": slug,
                    "rango": rango.value,
                    "soportado": soporte.fuente is not None,
                    "fuente": soporte.fuente.upper() if soporte.fuente else soporte.nombre_fuente,
                    "nivel": soporte.nivel,
                    "enlace": soporte.enlace_oficial,
                }
            )
    filas.append(
        {
            "comunidad": "Unión Europea",
            "slug": "union-europea",
            "rango": "reglamentos y directivas",
            "soportado": True,
            "fuente": "EUR-LEX",
            "nivel": "sparql_cellar",
            "enlace": "https://eur-lex.europa.eu",
        }
    )
    return filas
