# Otto — Asistente de Odoo con lenguaje natural

Chat agente (LLM + tool calling) que responde en lenguaje natural preguntas sobre tu
instancia de Odoo, **solo lectura**. Si la pregunta no está definida de antemano, el
agente descubre el esquema en vivo (modelos y campos) y responde igual.

## Arquitectura

- **Backend**: Python + FastAPI. Expone un endpoint SSE `/api/chat` y `/api/health`.
- **Agente**: SDK de OpenAI (compatible con ModelArts MaaS / glm) con tool calling.
- **Conexión a Odoo**: JSON-RPC directo (`/jsonrpc`), únicamente métodos de lectura
  (`search`, `read`, `search_read`, `fields_get`, `read_group`, `name_search`).
- **Frontend**: HTML/CSS/JS estáticos servidos por FastAPI.

## Herramientas del agente (read-only)

| Herramienta | Qué hace |
|---|---|
| `list_models` | Modelos disponibles (curados) |
| `get_fields(model)` | Campos/esquema de un modelo |
| `search_records(model, domain, limit, ...)` | Buscar registros |
| `get_record(model, id)` | Leer un registro por id |
| `aggregate_records(model, groupby, ...)` | Agrupaciones / totales (`read_group`) |
| `get_context` | Usuario, empresa y timezone de la sesión |

## Configuración

Copia `.env.example` a `.env` y completa:

```
ODOO_URL=http://localhost:8069
ODOO_DB=
ODOO_USER=
ODOO_PASSWORD=
AI_API_ENDPOINT=https://api-ap-southeast-1.modelarts-maas.com/openai/v1
AI_API_KEY=
AI_MODEL=glm-5.2
```

## Ejecutar local

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows  (Linux: source .venv/bin/activate)
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Abrir http://localhost:8000

## Docker (para Coolify luego)

```bash
cd backend
docker compose up --build
```

## Seguridad

- El cliente de Odoo solo llama métodos de lectura; no hay `create/write/unlink`.
- Las credenciales viven en `.env` (ignorado por git).
- Los errores de Odoo se convierten en respuestas amables del asistente, no en
  stacktraces hacia el usuario.
