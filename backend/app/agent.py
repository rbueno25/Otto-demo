"""Agente LLM: convierta la pregunta en lenguaje natural en llamadas a herramientas de Odoo."""

import json
from typing import AsyncGenerator

from openai import AsyncOpenAI

from .config import Settings
from .odoo_client import OdooClient
from .tools import TOOLS, execute_tool

SYSTEM_PROMPT = """Eres Otto, un asistente que responde en ESPAÑOL preguntas sobre la instancia
de Odoo de la empresa. Hablas de forma natural y concisa, con datos reales.

REGLAS:
1. Para responder usa SIEMPRE las herramientas disponibles (solo lectura). Nunca inventes
   datos, cifras, nombres o IDs: si no hay herramienta que lo confirme, di que no puedes
   acceder a esa información.
2. Si no sabes qué modelo usar, llama a list_models. Si un modelo o campo falla, usa
   get_fields para descubrir el esquema correcto e inténtalo de nuevo.
3. Cuando una herramienta devuelva un ERROR, tradúcelo a lenguaje amable: no muestres
   stacktraces. Si falta contexto, haz UNA pregunta aclaratoria breve.
4. Domains de Odoo: usa listas, ej. [["state","=","sale"]]. Fechas en formato
   "YYYY-MM-DD HH:MM:SS" en UTC. Para "último mes", "este mes", etc., calcula el rango
   de fechas tú mismo y úsalo en el domain.
5. Para totales, top-N o agrupaciones usa aggregate_records.
6. Si el usuario pide un GRÁFICO (grafica, gráfico, chart, top visual, etc.), obtén los datos con
   aggregate_records/search_records y luego llama a generate_chart con el tipo adecuado
   (bar, line, pie, doughnut, polarArea, radar). El gráfico se renderiza automáticamente.
7. Responde en la misma moneda/formato que devuelve Odoo, y sé claro con las unidades.
8. No hagas nada que modifique datos: solo lectura.

REGLA DE STOCK (importante, evita errores):
- Para reportar stock usa SIEMPRE el modelo stock.quant.
- Filtra por ubicaciones internas añadiendo al domain: ["location_id", "usage", "=", "internal"].
- Filtra SOLO por la empresa del usuario: llama a get_context, toma su company_id y añade
  ["company_id", "=", company_id] al domain.
- Suma el campo quantity (en mano). Para "disponible" resta reserved_quantity.
- NO sumes quants de ubicaciones virtuales como "Inventory adjustment" (tienen cantidades
  negativas y distorsionan el total).
- Si la empresa del usuario no tiene stock registrado, dilo claramente ("la empresa X no tiene
  stock registrado") en lugar de mezclar datos de otras empresas.
"""

MAX_TOOL_RESULT_CHARS = 12000


def _truncate(text: str) -> str:
    if len(text) <= MAX_TOOL_RESULT_CHARS:
        return text
    return text[:MAX_TOOL_RESULT_CHARS] + "... [resultado truncado]"


async def run_agent(
    odoo: OdooClient,
    settings: Settings,
    history: list[dict],
) -> AsyncGenerator[dict, None]:
    """Ejecuta el ciclo de tool calling y emite eventos SSE:

    {"type": "delta", "text": ...}   fragmento de la respuesta final
    {"type": "tool", "name": ..., "result": ...}  herramienta ejecutada
    {"type": "done"}
    {"type": "error", "message": ...}
    """
    client = AsyncOpenAI(base_url=settings.ai_api_endpoint, api_key=settings.ai_api_key)

    # Contexto de sesión inyectado para que Otto siempre sepa la empresa del usuario.
    session_note = ""
    try:
        uid = await odoo.authenticate()
        user = await odoo.read("res.users", [uid], ["name", "company_id", "tz", "login"])
        if user:
            comp = user[0].get("company_id") or [None, "?"]
            session_note = (
                "\nCONTEXTO DE SESIÓN (dato real, no lo pidas): "
                f"usuario={user[0].get('name')} ({user[0].get('login')}), "
                f"company_id={comp[0] if isinstance(comp, list) else comp} "
                f"({comp[1] if isinstance(comp, list) and len(comp) > 1 else '?'}), tz={user[0].get('tz')}.\n"
                "Cuando reportes stock, filtra por company_id={comp[0] if isinstance(comp, list) else comp}.\n"
            )
    except Exception:
        pass

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT + session_note}]
    for m in history:
        role = m.get("role")
        content = m.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    for _ in range(settings.max_iterations):
        try:
            stream = await client.chat.completions.create(
                model=settings.ai_model,
                messages=messages,
                tools=TOOLS,
                stream=True,
            )
        except Exception as exc:
            yield {
                "type": "error",
                "message": f"No se pudo contactar al modelo de IA: {exc.__class__.__name__}: {exc}",
            }
            return

        assistant: dict = {"role": "assistant", "content": ""}
        tool_calls: dict[int, dict] = {}

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                assistant["content"] += delta.content
                yield {"type": "delta", "text": delta.content}
            if delta and delta.tool_calls:
                for tc in delta.tool_calls:
                    entry = tool_calls.setdefault(tc.index, {"id": "", "function": {"name": "", "arguments": ""}})
                    if tc.id:
                        entry["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            entry["function"]["name"] = tc.function.name
                        if tc.function.arguments:
                            entry["function"]["arguments"] += tc.function.arguments

        if tool_calls:
            ordered = [tool_calls[i] for i in sorted(tool_calls)]
            assistant["tool_calls"] = [
                {
                    "id": t["id"],
                    "type": "function",
                    "function": {"name": t["function"]["name"], "arguments": t["function"]["arguments"]},
                }
                for t in ordered
            ]
            messages.append(assistant)
            for t in ordered:
                name = t["function"]["name"]
                raw_args = t["function"]["arguments"]
                try:
                    args = json.loads(raw_args) if raw_args.strip() else {}
                    if not isinstance(args, dict):
                        args = {"valor": args}
                except json.JSONDecodeError:
                    args = {}
                try:
                    result = await execute_tool(odoo, name, args)
                    result_text = _truncate(json.dumps(result, ensure_ascii=False, default=str))
                except Exception as exc:  # noqa: BLE001 - se devuelve al LLM para que lo explique
                    result_text = f"ERROR: {exc.__class__.__name__}: {exc}"
                messages.append({"role": "tool", "tool_call_id": t["id"], "content": result_text})
                yield {"type": "tool", "name": name, "result": result_text[:500]}
                if name == "generate_chart" and isinstance(result, dict) and result.get("chart"):
                    yield {"type": "chart", "spec": result["chart"]}
            continue

        # Respuesta final sin tool calls: ya se transmitió el contenido.
        if not assistant["content"]:
            assistant["content"] = "No pude generar una respuesta. Intenta reformular la pregunta."
        messages.append(assistant)
        break

    yield {"type": "done"}
    await client.close()
