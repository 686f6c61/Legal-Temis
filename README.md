# Temis

API de consulta de normativa autonómica, estatal y europea en lenguaje natural,
con IA y trazabilidad completa sobre fuentes oficiales.

Haces una pregunta en lenguaje natural y la API responde qué norma aplica, la cita
artículo a artículo y enlaza siempre a la fuente oficial. Nada sale de la memoria
del modelo: toda norma citada se recupera en vivo de fuentes oficiales.

## Qué hace

- **Leyes autonómicas de las 17 comunidades**: búsqueda, texto consolidado y
  vigencia vía la API de legislación consolidada del BOE.
- **Rango reglamentario**: derivación honesta al buscador oficial de cada
  comunidad cuando no existe fuente programática (`redirect_oficial`).
- **Derecho de la Unión Europea**: cuando ninguna norma española vigente responde,
  se añaden los reglamentos y directivas aplicables desde EUR-Lex (SPARQL de
  CELLAR, identificadores CELEX con URL oficial en castellano).
- **IA**: transforma la pregunta en una consulta estructurada validada y redacta
  la respuesta citando exclusivamente normas recuperadas de fuentes oficiales.

## Puesta en marcha

Requiere Docker. Configura al menos un proveedor de IA con clave.

```bash
cp .env.example .env   # y rellena la clave del proveedor que uses
docker compose up --build -d
```

- API: http://localhost:4000
- Documentación interactiva (Swagger): http://localhost:4000/docs — y `/redoc`
- Esquema OpenAPI: http://localhost:4000/openapi.json

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/consulta` | Pregunta en lenguaje natural → `resultados`, `redirect_oficial` o `error_consulta` |
| POST | `/comparar` | La misma materia contra las 17 comunidades en paralelo |
| GET | `/cobertura` | Tabla comunidad × rango con el nivel de soporte real y enlace al portal oficial |
| GET | `/norma/{identificador}` | Norma con texto consolidado y artículos con ancla; `?fecha=AAAA-MM-DD` devuelve la versión vigente en esa fecha |
| GET | `/proveedores` | Proveedores y modelos de IA disponibles |
| GET | `/derivaciones` | Contador de derivaciones al buscador oficial por comunidad y rango |
| GET | `/salud` | Comprobación de vida |

## Configuración (variables de entorno)

Todas con prefijo `LEGISLACION_`, en `.env` (véase `.env.example`). Solo se
activan los proveedores de IA con clave configurada.

| Variable | Por defecto | Descripción |
|---|---|---|
| `NAN_API_KEY` | — | Clave de un servidor compatible (modelos servidos por tu propio endpoint) |
| `MODELOS_NAN` | lista integrada | Modelos a exponer, separados por comas; vacío = lista por defecto |
| `OPENROUTER_API_KEY` | — | Clave de OpenRouter (opcional; expone un modelo por entrada de su lista) |
| `MODELOS_OPENROUTER` | lista integrada | Modelos OpenRouter, separados por comas |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | — | Acceso directo a Anthropic u OpenAI (opcional) |
| `MODELO_ANTHROPIC` / `MODELO_OPENAI` | — | Modelo para el acceso directo |
| `PROVEEDOR_DEFECTO` | `anthropic` | Proveedor si la petición no indica uno |
| `REDIS_URL` | `redis://redis:6379/0` | Cache de fuentes y contador de derivaciones |
| `CACHE_TTL_SEGUNDOS` | `21600` | Caducidad de la caché de fuentes (6 horas) |
| `BOE_BASE_URL` | API oficial del BOE | Punto de la legislación consolidada |
| `EURLEX_SPARQL_URL` | SPARQL de CELLAR | Punto oficial de EUR-Lex |
| `TIMEOUT_FUENTES_SEGUNDOS` | `20` | Timeout por petición a las fuentes |
| `TIMEOUT_IA_SEGUNDOS` | `45` | Timeout por llamada de IA (al vencer, degradación automática a modo JSON) |
| `MAX_RESULTADOS` | `10` | Máximo de normas por búsqueda |
| `CORS_ORIGENES` | `*` | Orígenes CORS permitidos, separados por comas |
| `LIMITE_CONSULTA_POR_MINUTO` | `20` | Límite de `/consulta` por IP (0 = sin tope) |
| `LIMITE_COMPARAR_POR_MINUTO` | `5` | Límite de `/comparar` por IP (0 = sin tope) |

## Seguridad

- **Las claves de IA no se exponen:** no están en el código ni en config versionada
  (`.env` está en `.gitignore`); la trazabilidad de las respuestas solo devuelve el
  nombre del proveedor y del modelo, nunca la clave; no se registran en logs ni en
  los cuerpos de error (un 500 devuelve un mensaje genérico).
- **Rate limiting por IP:** `/consulta` (20/min) y `/comparar` (5/min) por defecto,
  sobre Redis. Al superarlo se devuelve `429` con `Retry-After`.
- **Errores de proveedor controlados:** una caída o saturación del proveedor de IA
  degrada a una respuesta controlada, no a un 500 con traza.
- **Redis** no publica puertos (solo red interna); la **API** corre como usuario
  no-root en el contenedor.

Antes de exponerla a producción:

1. **Restringe CORS:** pon tu dominio real en `CORS_ORIGENES` en lugar del `*`.
2. **Sirve tras HTTPS** con un proxy inverso (Caddy, Traefik, nginx). El limitador
   respeta `X-Forwarded-For`, así que el proxy debe fijar esa cabecera.
3. **Ajusta los límites** por minuto al tráfico esperado y a la cuota del proveedor.
4. **Gestiona las claves** de IA como secretos del entorno de despliegue.
5. Considera autenticación por clave si vas a exponer la API a terceros.

## Desarrollo

Requiere [uv](https://docs.astral.sh/uv/).

```bash
cd api
uv sync --all-groups
uv run pytest              # tests
uv run ruff check .        # linter
uv run ty check src/       # tipos
uv run uvicorn legislacion.app:app --reload --port 4000
```

## Licencia

[PolyForm Noncommercial License 1.0.0](LICENSE.md). Uso permitido para fines no
comerciales (personal, académico, investigación, ONG y organismos públicos).
Cualquier uso comercial requiere una licencia aparte del autor.
