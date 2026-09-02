import httpx

from .config import Settings


class OdooError(Exception):
    """Error amigable de Odoo, pensado para mostrarse al LLM."""


class OdooClient:
    """Cliente JSON-RPC de Odoo, SOLO métodos de lectura.

    No expone create/write/unlink: la integridad de los datos queda intacta.
    """

    def __init__(self, settings: Settings):
        self.base = settings.odoo_url
        self.db = settings.odoo_db
        self.user = settings.odoo_user
        self.pwd = settings.odoo_password
        self._uid = None
        self._http = httpx.AsyncClient(timeout=90)

    @staticmethod
    def _payload(service: str, method: str, args: list) -> dict:
        return {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {"service": service, "method": method, "args": args},
            "id": None,
        }

    async def _call(self, service: str, method: str, *args):
        try:
            resp = await self._http.post(
                f"{self.base}/jsonrpc", json=self._payload(service, method, list(args))
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise OdooError(f"No se pudo conectar con Odoo ({exc.__class__.__name__}).") from exc
        body = resp.json()
        if "error" in body:
            err = body["error"]
            name = err.get("data", {}).get("name", "OdooError")
            message = err.get("data", {}).get("message", err.get("message", "error"))
            raise OdooError(f"{name}: {message}")
        return body.get("result")

    async def authenticate(self) -> int:
        if self._uid:
            return self._uid
        uid = await self._call("common", "authenticate", self.db, self.user, self.pwd, {})
        if not uid:
            raise OdooError(
                "No se pudo autenticar contra Odoo. Revisa ODOO_DB, ODOO_USER y ODOO_PASSWORD."
            )
        self._uid = uid
        return uid

    async def _execute(self, model: str, method: str, args: list | None = None, kwargs: dict | None = None):
        await self.authenticate()
        return await self._call(
            "object",
            "execute_kw",
            self.db,
            self._uid,
            self.pwd,
            model,
            method,
            args or [],
            kwargs or {},
        )

    # ---- Métodos de lectura ---- #

    async def fields_get(self, model: str, attributes: list[str] | None = None) -> dict:
        attrs = attributes or ["string", "type", "required", "readonly", "selection", "relation"]
        return await self._execute(model, "fields_get", kwargs={"attributes": attrs})

    async def search(self, model: str, domain: list | None = None, limit: int | None = None) -> list[int]:
        kwargs: dict = {}
        if limit:
            kwargs["limit"] = limit
        return await self._execute(model, "search", [domain or []], kwargs)

    async def read(self, model: str, ids: list[int], fields: list[str] | None = None) -> list[dict]:
        kwargs = {"fields": fields} if fields else {}
        return await self._execute(model, "read", [ids], kwargs)

    async def search_read(
        self,
        model: str,
        domain: list | None = None,
        fields: list[str] | None = None,
        limit: int | None = None,
        offset: int = 0,
        order: str | None = None,
    ) -> list[dict]:
        kwargs: dict = {"fields": fields or []}
        if limit:
            kwargs["limit"] = limit
        if offset:
            kwargs["offset"] = offset
        if order:
            kwargs["order"] = order
        return await self._execute(model, "search_read", [domain or []], kwargs)

    async def read_group(
        self,
        model: str,
        domain: list,
        fields: list[str],
        groupby: list[str],
        limit: int | None = None,
        offset: int = 0,
        orderby: str | None = None,
    ) -> list[dict]:
        kwargs: dict = {}
        if limit:
            kwargs["limit"] = limit
        if offset:
            kwargs["offset"] = offset
        if orderby:
            kwargs["orderby"] = orderby
        return await self._execute(model, "read_group", [domain, fields, groupby], kwargs)

    async def name_search(
        self, model: str, name: str = "", domain: list | None = None, limit: int | None = None
    ) -> list[list]:
        kwargs = {"limit": limit} if limit else {}
        return await self._execute(model, "name_search", [name, domain or []], kwargs)

    async def aclose(self) -> None:
        await self._http.aclose()
