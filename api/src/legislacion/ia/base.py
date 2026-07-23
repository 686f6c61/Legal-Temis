from typing import Protocol

from pydantic import BaseModel


class ClienteIA(Protocol):
    """Interfaz común de los proveedores de IA. `estructurar` devuelve el esquema
    validado o None si el proveedor no pudo producirlo; `generar` devuelve texto
    libre o None ante un rechazo."""

    nombre: str
    modelo: str

    async def estructurar[T: BaseModel](
        self, sistema: str, usuario: str, esquema: type[T]
    ) -> T | None: ...

    async def generar(self, sistema: str, usuario: str) -> str | None: ...
