"""Herramientas (tool schemas) del agente + ejecución read-only sobre Odoo."""

import re
from datetime import datetime, timezone

from .odoo_client import OdooClient

MAX_LIMIT = 100

# Modelos comúnmente útiles para responder preguntas de negocio.
CURATED_MODELS = {
    "res.partner": "Contactos / clientes",
    "product.product": "Variantes de producto (stocks, precios)",
    "product.template": "Productos (plantillas)",
    "product.category": "Categorías de producto",
    "sale.order": "Órdenes de venta (pedidos)",
    "sale.order.line": "Líneas de órdenes de venta",
    "account.move": "Facturas / asientos",
    "account.move.line": "Líneas de factura",
    "stock.quant": "Quants de inventario",
    "stock.picking": "Transferencias (albaranes)",
    "stock.move": "Movimientos de stock",
    "uom.uom": "Unidades de medida",
    "res.company": "Empresas",
}

# Campos preferidos para mostrar en búsquedas genéricas.
DISPLAY_PREF = [
    "name",
    "display_name",
    "state",
    "date_order",
    "amount_total",
    "amount_untaxed",
    "quantity",
    "qty_available",
    "virtual_available",
    "product_uom_qty",
    "partner_id",
    "product_id",
    "location_id",
    "date",
    "invoice_date",
    "create_date",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _pick_fields(client: OdooClient, model: str, max_n: int = 8) -> list[str]:
    """Elige campos display seguros para un modelo (existen en su esquema)."""
    fg = await client.fields_get(model)
    selected = [f for f in DISPLAY_PREF if f in fg][:max_n]
    if not selected:
        simple = [
            n
            for n, m in fg.items()
            if n != "id"
            and m.get("type") in ("char", "text", "many2one", "selection", "integer", "float", "monetary")
        ]
        selected = simple[:max_n]
    return selected


# ---------------------------- Implementaciones ---------------------------- #

async def impl_list_models(client: OdooClient, args: dict) -> dict:
    return {
        "modelos": [
            {"model": m, "descripcion": d, "operaciones": "solo lectura"}
            for m, d in CURATED_MODELS.items()
        ]
    }


async def impl_get_fields(client: OdooClient, args: dict) -> dict:
    model = str(args.get("model") or "").strip()
    if not model:
        return {"error": "Falta el parámetro 'model'."}
    fg = await client.fields_get(model)
    simplified = {
        name: {
            "tipo": meta.get("type"),
            "etiqueta": meta.get("string"),
            "requerido": meta.get("required", False),
            "relacion": meta.get("relation"),
            "opciones": meta.get("selection"),
        }
        for name, meta in sorted(fg.items())
    }
    return {"model": model, "num_campos": len(simplified), "campos": simplified}


async def impl_search_records(client: OdooClient, args: dict) -> dict:
    model = str(args.get("model") or "").strip()
    if not model:
        return {"error": "Falta el parámetro 'model'."}
    domain = args.get("domain") or []
    limit = min(int(args.get("limit") or 20), MAX_LIMIT)
    offset = int(args.get("offset") or 0)
    order = args.get("order")
    fields = await _pick_fields(client, model)
    records = await client.search_read(model, domain, fields, limit=limit, offset=offset, order=order)
    return {
        "model": model,
        "total_devuelto": len(records),
        "registros": records,
        "sugerencia": "Si necesitas otros campos, usa get_fields para ver el esquema completo.",
    }


async def impl_get_record(client: OdooClient, args: dict) -> dict:
    model = str(args.get("model") or "").strip()
    record_id = args.get("record_id")
    if not model or record_id is None:
        return {"error": "Faltan parámetros 'model' y/o 'record_id'."}
    try:
        record_id = int(record_id)
    except (TypeError, ValueError):
        return {"error": "'record_id' debe ser un entero."}
    fields = args.get("fields")
    if fields:
        fields = [str(f) for f in fields]
    else:
        fields = await _pick_fields(client, model)
    records = await client.read(model, [record_id], fields)
    if not records:
        return {"error": f"No existe el registro {record_id} en {model}."}
    return {"model": model, "id": record_id, "registro": records[0]}


async def impl_aggregate_records(client: OdooClient, args: dict) -> dict:
    model = str(args.get("model") or "").strip()
    if not model:
        return {"error": "Falta el parámetro 'model'."}
    groupby = args.get("groupby") or ["__count"]
    groupby = [str(g) for g in groupby]
    groupby = [g for g in groupby if g not in ("__count", "count")]
    if not groupby:
        return {"error": "El 'groupby' no puede quedar vacío. Indica un campo de agrupación."}
    domain = args.get("domain") or []
    limit = min(int(args.get("limit") or 50), MAX_LIMIT)
    offset = int(args.get("offset") or 0)

    measures = args.get("aggregates") or []
    read_group_fields: list[str] = []
    for m in measures:
        s = str(m)
        if s == "__count":
            continue
        read_group_fields.append(s)

    try:
        groups = await client.read_group(model, domain, read_group_fields, groupby, limit=limit, offset=offset)
    except Exception as exc:
        return {
            "error": f"No se pudo agrupar en {model}. Revisa que 'groupby' y 'aggregates' sean válidos: {exc}"
        }

    clean = []
    for g in groups:
        row = {}
        for k, v in g.items():
            if k.endswith("_count") and k[: -len("_count")] in groupby or k == "__count":
                row[k] = v
            else:
                row[k] = v
        clean.append(row)

    return {
        "model": model,
        "groupby": groupby,
        "medidas": measures,
        "num_grupos": len(clean),
        "grupos": clean,
    }


CHART_TYPES = ("bar", "line", "pie", "doughnut", "polarArea", "radar")


async def impl_generate_chart(client: OdooClient, args: dict) -> dict:
    tipo = str(args.get("tipo") or "bar").lower()
    if tipo not in CHART_TYPES:
        return {
            "error": (
                f"Tipo de gráfico no soportado: {tipo}. "
                f"Usa uno de: {', '.join(CHART_TYPES)}."
            )
        }
    titulo = str(args.get("titulo") or "").strip()
    etiquetas = [str(e) for e in (args.get("etiquetas") or [])]
    series = args.get("series")
    if series is None and isinstance(args.get("datos"), list):
        series = [{"nombre": str(args.get("nombre_serie") or "serie"), "datos": args["datos"]}]
    if not isinstance(series, list) or not series:
        return {"error": "Falta 'series' (lista de {nombre, datos})."}
    for s in series:
        datos = s.get("datos") if isinstance(s, dict) else None
        if not isinstance(datos, list) or not all(isinstance(v, (int, float)) for v in datos):
            return {"error": f"Cada serie debe tener 'datos' con números. Serie inválida: {s}"}
        if etiquetas and len(datos) != len(etiquetas):
            return {
                "error": f"La serie '{s.get('nombre')}' tiene {len(datos)} datos pero hay {len(etiquetas)} etiquetas."
            }
    if not etiquetas and series:
        etiquetas = [str(i + 1) for i in range(len(series[0]["datos"]))]
    return {
        "ok": True,
        "mensaje": f"Gráfico de tipo {tipo} generado.",
        "chart": {"tipo": tipo, "titulo": titulo, "etiquetas": etiquetas, "series": series},
    }


async def impl_get_context(client: OdooClient, args: dict) -> dict:
    ctx = {"generado_utc": _now_iso()}
    try:
        user_id = await client.authenticate()
        user = await client.read("res.users", [user_id], ["name", "tz", "company_id"])
        ctx["usuario"] = user[0] if user else {"name": "?"}
    except Exception as exc:
        ctx["usuario"] = {"error": str(exc)}
    try:
        companies = await client.search_read("res.company", [], ["name"], limit=20)
        ctx["empresas"] = companies
    except Exception as exc:
        ctx["empresas"] = {"error": str(exc)}
    return ctx


# ---------------------------- Schemas OpenAI ---------------------------- #

def _model_param(desc: str = "Nombre técnico del modelo, p. ej. 'sale.order'.") -> dict:
    return {"type": "string", "description": desc}


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_models",
            "description": (
                "Lista los modelos de Odoo disponibles para consulta. "
                "Úsala si no sabes qué modelo usar o si un modelo no funciona."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_fields",
            "description": (
                "Obtiene el esquema (campos, tipos, opciones) de un modelo de Odoo. "
                "Úsala para saber con qué campos filtrar o qué pedir cuando no estés seguro."
            ),
            "parameters": {
                "type": "object",
                "properties": {"model": _model_param()},
                "required": ["model"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_records",
            "description": (
                "Busca registros de un modelo de Odoo. 'domain' es una lista estilo Odoo, "
                "ej. [['state','=','sale'],['date_order','>=','2026-08-01']]. "
                "Para fechas usa formato 'YYYY-MM-DD' o 'YYYY-MM-DD HH:MM:SS' (UTC). "
                "Úsala para listados y conteos cuando no necesites agrupar."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "model": _model_param(),
                    "domain": {"type": "array", "items": {"type": "array"}, "description": "Dominio Odoo."},
                    "limit": {"type": "integer", "description": "Máximo de registros (default 20, máx 100)."},
                    "offset": {"type": "integer", "description": "Desplazamiento para paginar."},
                    "order": {"type": "string", "description": "Orden, ej. 'name asc'."},
                },
                "required": ["model"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_record",
            "description": "Lee un registro concreto de Odoo por su id numérico.",
            "parameters": {
                "type": "object",
                "properties": {
                    "model": _model_param(),
                    "record_id": {"type": "integer", "description": "ID del registro."},
                    "fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Campos opcionales; si se omite se eligen los relevantes.",
                    },
                },
                "required": ["model", "record_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "aggregate_records",
            "description": (
                "Agrega registros de Odoo en grupos (equivale a read_group / GROUP BY). "
                "'groupby' acepta nombres de campo, opcionalmente con granularidad de fecha "
                "('date_order:month', ':day', ':year'). 'aggregates' acepta expresiones "
                "'campo:operador' (sum, count, avg, min, max) y/o '__count'. "
                "Úsala para totales, top-N por grupo, ventas por mes, etc. "
                "Para stock usa stock.quant filtrando por location_id.usage='internal' "
                "y company_id (obtenlo de get_context)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "model": _model_param(),
                    "groupby": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Campos de agrupación, ej. ['product_id'] o ['date_order:month'].",
                    },
                    "aggregates": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Expresiones 'campo:op', ej. ['amount_total:sum']. Vacío = solo conteo.",
                    },
                    "domain": {"type": "array", "items": {"type": "array"}, "description": "Dominio Odoo."},
                    "limit": {"type": "integer", "description": "Máximo de grupos (default 50)."},
                },
                "required": ["model", "groupby"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_chart",
            "description": (
                "Genera un gráfico que el usuario verá renderizado. NO dibuja en Odoo; solo prepara "
                "la especificación. Usa tipos: 'bar' (barras), 'line' (líneas), 'pie' (pastel), "
                "'doughnut' (donut), 'polarArea' o 'radar'. Para pie/doughnut/polarArea usa UNA serie "
                "con las etiquetas. Combínala con aggregate_records o search_records para obtener datos reales."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tipo": {
                        "type": "string",
                        "enum": ["bar", "line", "pie", "doughnut", "polarArea", "radar"],
                        "description": "Tipo de gráfico.",
                    },
                    "titulo": {"type": "string", "description": "Título del gráfico."},
                    "etiquetas": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Categorías del eje X (o nombres de las porciones).",
                    },
                    "series": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "nombre": {"type": "string"},
                                "datos": {"type": "array", "items": {"type": "number"}},
                            },
                        },
                        "description": "Una o más series de datos.",
                    },
                },
                "required": ["tipo", "etiquetas", "series"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_context",
            "description": (
                "Devuelve el contexto de la sesión: usuario conectado, empresa(s) y zona horaria. "
                "Úsala para contextualizar respuestas sobre 'mi empresa' o 'mi usuario'."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _as_int(v, default):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


IMPL = {
    "list_models": impl_list_models,
    "get_fields": impl_get_fields,
    "search_records": impl_search_records,
    "get_record": impl_get_record,
    "aggregate_records": impl_aggregate_records,
    "get_context": impl_get_context,
    "generate_chart": impl_generate_chart,
}


async def execute_tool(client: OdooClient, name: str, args: dict) -> dict:
    if name not in IMPL:
        return {"error": f"Herramienta desconocida: {name}"}
    return await IMPL[name](client, args or {})
