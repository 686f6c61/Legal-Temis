from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Rango(StrEnum):
    LEY = "ley"
    REGLAMENTO = "reglamento"
    DESCONOCIDO = "desconocido"


class ConsultaEstructurada(BaseModel):
    es_consulta_normativa: bool
    comunidad: str | None = None
    rango: Rango = Rango.DESCONOCIDO
    terminos: list[str] = Field(default_factory=list)
    sinonimos: list[str] = Field(default_factory=list)
    numero_oficial: str | None = None
    motivo_error: str | None = None


class Norma(BaseModel):
    identificador: str
    titulo: str
    comunidad: str
    rango: str
    fecha_disposicion: str | None = None
    numero_oficial: str | None = None
    vigente: bool | None = None
    estado_consolidacion: str | None = None
    url_oficial: str
    url_eli: str | None = None
    fuente: str


class Trazabilidad(BaseModel):
    fuente: str
    parametros: dict[str, str]
    proveedor_ia: str | None = None
    modelo_ia: str | None = None
    momento: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RespuestaResultados(BaseModel):
    tipo: Literal["resultados"] = "resultados"
    consulta: ConsultaEstructurada
    normas: list[Norma]
    respuesta_ia: str | None = None
    nota: str | None = None
    trazabilidad: Trazabilidad


class RespuestaRedirect(BaseModel):
    tipo: Literal["redirect_oficial"] = "redirect_oficial"
    consulta: ConsultaEstructurada
    motivo: str
    enlace_oficial: str
    nombre_fuente: str
    trazabilidad: Trazabilidad


class RespuestaError(BaseModel):
    tipo: Literal["error_consulta"] = "error_consulta"
    motivo: str
    consulta: ConsultaEstructurada | None = None


RespuestaConsulta = RespuestaResultados | RespuestaRedirect | RespuestaError


class PeticionConsulta(BaseModel):
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "pregunta": (
                        "¿Qué dice la ley de vivienda de Andalucía sobre la vivienda protegida?"
                    ),
                    "redactar_respuesta": True,
                },
                {
                    "pregunta": "¿Sigue vigente la ley del juego?",
                    "comunidad": "madrid",
                    "rango": "ley",
                    "proveedor": "nan:qwen3.6",
                },
            ]
        }
    }

    pregunta: str = Field(min_length=3, max_length=2000)
    comunidad: str | None = None
    rango: Rango | None = None
    redactar_respuesta: bool = True
    proveedor: str | None = None


class Articulo(BaseModel):
    id: str
    titulo: str
    texto: str
    url: str
    vigente_desde: str | None = None


class NormaDetalle(Norma):
    texto: str | None = None
    articulos: list[Articulo] = Field(default_factory=list)
    fecha_texto: str | None = None
    fecha_actualizacion: str | None = None


class PeticionComparacion(BaseModel):
    model_config = {
        "json_schema_extra": {
            "examples": [
                {"pregunta": "regulación de las viviendas de uso turístico", "max_por_comunidad": 2}
            ]
        }
    }

    pregunta: str = Field(min_length=3, max_length=2000)
    proveedor: str | None = None
    max_por_comunidad: int = Field(default=3, ge=1, le=10)


class ComparacionComunidad(BaseModel):
    comunidad: str
    nombre: str
    normas: list[Norma]


class RespuestaComparacion(BaseModel):
    tipo: Literal["comparacion"] = "comparacion"
    consulta: ConsultaEstructurada
    resultados: list[ComparacionComunidad]
    trazabilidad: Trazabilidad


RespuestaComparar = RespuestaComparacion | RespuestaError
