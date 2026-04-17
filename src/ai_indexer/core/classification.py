"""File classification and semantic hint helpers."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from ai_indexer.core.models import ConfidenceValue
from ai_indexer.utils.config import IndexerConfig

_TYPE_SEGMENT_RULES: list[tuple[str, str]] = [
    ("services", "service"), ("service", "service"),
    ("controllers", "controller"), ("controller", "controller"),
    ("routes", "route"), ("route", "route"),
    ("models", "model"), ("model", "model"),
    ("entities", "entity"), ("entity", "entity"),
    ("repositories", "repository"), ("repository", "repository"),
    ("middlewares", "middleware"), ("middleware", "middleware"),
    ("handlers", "handler"), ("handler", "handler"),
    ("usecases", "usecase"), ("usecase", "usecase"),
    ("interactors", "interactor"), ("interactor", "interactor"),
    ("jobs", "job"), ("job", "job"),
    ("workers", "worker"), ("worker", "worker"),
    ("consumers", "consumer"), ("consumer", "consumer"),
    ("producers", "producer"), ("producer", "producer"),
    ("listeners", "listener"), ("listener", "listener"),
    ("subscribers", "subscriber"), ("subscriber", "subscriber"),
    ("observers", "observer"), ("observer", "observer"),
    ("policies", "policy"), ("policy", "policy"),
    ("validators", "validator"), ("validator", "validator"),
    ("serializers", "serializer"), ("serializer", "serializer"),
    ("presenters", "presenter"), ("presenter", "presenter"),
    ("views", "view"), ("view", "view"),
    ("templates", "template"), ("template", "template"),
    ("layouts", "layout"), ("layout", "layout"),
    ("pages", "page"), ("page", "page"),
    ("components", "component"), ("component", "component"),
    ("hooks", "hook"), ("hook", "hook"),
    ("composables", "composable"), ("composable", "composable"),
    ("stores", "store"), ("store", "store"),
    ("contexts", "context"), ("context", "context"),
    ("reducers", "reducer"), ("reducer", "reducer"),
    ("actions", "action"), ("action", "action"),
    ("mutations", "mutation"), ("mutation", "mutation"),
    ("getters", "getter"), ("getter", "getter"),
    ("api", "api"), ("apis", "api"),
    ("graphql", "graphql"), ("resolvers", "resolver"), ("resolver", "resolver"),
    ("schemas", "schema"), ("schema", "schema"),
    ("dtos", "dto"), ("dto", "dto"),
    ("types", "types"), ("interfaces", "types"),
    ("utils", "util"), ("helpers", "util"), ("lib", "util"),
    ("config", "config"), ("settings", "config"),
    ("db", "database"), ("database", "database"),
    ("queries", "query"), ("query", "query"),
    ("mutations", "mutation"), ("mutation", "mutation"),
    ("migrations", "migration"), ("migration", "migration"),
    ("seeds", "seed"), ("seed", "seed"),
    ("factories", "factory"), ("factory", "factory"),
    ("fixtures", "fixture"), ("fixture", "fixture"),
    ("tests", "test"), ("test", "test"), ("specs", "test"),
    ("infra", "infra"), ("core", "core"), ("shared", "shared"),
    ("adapters", "adapter"), ("adapter", "adapter"),
    ("ports", "port"), ("port", "port"),
    ("gateways", "gateway"), ("gateway", "gateway"),
    ("clients", "client"), ("client", "client"),
    ("providers", "provider"), ("provider", "provider"),
    ("commands", "command"), ("command", "command"),
    ("events", "event"), ("event", "event"),
    ("queues", "queue"), ("queue", "queue"),
    ("mailers", "mailer"), ("mailer", "mailer"),
    ("notifications", "notification"), ("notification", "notification"),
    ("channels", "channel"), ("channel", "channel"),
    ("exceptions", "exception"), ("exception", "exception"),
    ("errors", "error"), ("error", "error"),
    ("logging", "logging"), ("logger", "logging"),
    ("metrics", "metrics"), ("monitoring", "monitoring"),
    ("ui", "ui"), ("styles", "style"), ("assets", "asset"),
]
_TYPE_NAME_RULES: list[tuple[str, str]] = [
    ("server", "entrypoint"), ("app", "entrypoint"), ("main", "entrypoint"),
    ("index", "barrel"), ("mod", "barrel"), ("lib", "barrel"),
    ("config", "config"), ("settings", "config"), ("env", "config"),
    ("middleware", "middleware"), ("worker", "worker"),
    ("cron", "scheduler"), ("scheduler", "scheduler"),
    ("route", "route"), ("router", "route"),
    ("controller", "controller"), ("handler", "handler"),
    ("service", "service"), ("usecase", "usecase"),
    ("model", "model"), ("entity", "entity"),
    ("repository", "repository"), ("repo", "repository"),
    ("dao", "repository"), ("dal", "repository"),
    ("adapter", "adapter"), ("gateway", "gateway"),
    ("port", "port"), ("client", "client"),
    ("provider", "provider"), ("factory", "factory"),
    ("builder", "builder"), ("mapper", "mapper"),
    ("validator", "validator"), ("serializer", "serializer"),
    ("presenter", "presenter"), ("view", "view"),
    ("component", "component"), ("page", "page"), ("layout", "layout"),
    ("hook", "hook"), ("composable", "composable"),
    ("store", "store"), ("context", "context"),
    ("reducer", "reducer"), ("action", "action"),
    ("resolver", "resolver"), ("schema", "schema"),
    ("dto", "types"), ("types", "types"), ("interface", "types"),
    ("util", "util"), ("helper", "util"),
    ("auth", "auth"), ("cache", "cache"),
    ("queue", "queue"), ("event", "event"),
    ("job", "job"), ("task", "job"),
    ("migration", "migration"), ("seed", "seed"),
    ("test", "test"), ("spec", "test"),
    ("fixture", "fixture"), ("mock", "test"),
    ("logger", "observability"), ("metric", "observability"),
    ("tracer", "observability"), ("span", "observability"),
    ("exception", "exception"), ("error", "error"),
    ("command", "command"), ("cli", "cli"),
]

_DOMAIN_KEYWORDS: dict[str, str] = {
    "auth": "auth", "login": "auth", "logout": "auth", "oauth": "auth",
    "jwt": "auth", "session": "auth", "permission": "auth", "role": "auth",
    "rbac": "auth", "abac": "auth", "sso": "auth", "mfa": "auth", "2fa": "auth",
    "user": "users", "users": "users", "profile": "users", "account": "users",
    "member": "users", "team": "teams", "teams": "teams", "organization": "teams",
    "billing": "billing", "payment": "billing", "invoice": "billing",
    "stripe": "billing", "paypal": "billing", "asaas": "billing",
    "pagar": "billing", "mercado pago": "billing", "subscription": "billing",
    "plan": "billing", "price": "billing", "checkout": "billing", "cart": "billing",
    "lead": "leads", "leads": "leads", "crm": "crm", "customer": "crm",
    "client": "crm", "contact": "crm", "deal": "crm", "pipeline": "crm",
    "product": "catalog", "catalog": "catalog", "inventory": "inventory",
    "stock": "inventory", "order": "orders", "orders": "orders",
    "shipment": "shipping", "shipping": "shipping", "fulfillment": "shipping",
    "tax": "tax", "vat": "tax", "coupon": "promotion", "promotion": "promotion",
    "email": "email", "smtp": "email", "mail": "email",
    "sms": "sms", "twilio": "sms", "push": "push", "notification": "notification",
    "whatsapp": "whatsapp", "telegram": "messaging", "slack": "messaging",
    "discord": "messaging", "webhook": "webhooks", "webhooks": "webhooks",
    "llm": "ai", "ai": "ai", "openai": "ai", "anthropic": "ai",
    "chatgpt": "ai", "claude": "ai", "embedding": "ai", "vector": "ai",
    "rag": "ai", "prompt": "ai", "completion": "ai",
    "database": "database", "db": "database", "sql": "database",
    "nosql": "database", "mongodb": "database", "postgres": "database",
    "mysql": "database", "sqlite": "database", "redis": "cache", "cache": "cache",
    "memcached": "cache", "elasticsearch": "search", "search": "search",
    "s3": "storage", "storage": "storage", "blob": "storage", "file": "storage",
    "upload": "storage", "download": "storage",
    "crypto": "security", "security": "security", "encrypt": "security",
    "decrypt": "security", "hash": "security", "csrf": "security",
    "xss": "security", "sql injection": "security", "audit": "audit",
    "compliance": "compliance", "gdpr": "compliance", "lgpd": "compliance",
    "health": "infra", "status": "infra", "metric": "monitoring",
    "monitoring": "monitoring", "logging": "logging", "log": "logging",
    "trace": "tracing", "tracing": "tracing", "alert": "alerting",
    "alerting": "alerting", "deploy": "deployment", "ci": "ci",
    "cd": "cd", "docker": "container", "kubernetes": "orchestration",
    "ws": "realtime", "socket": "realtime", "websocket": "realtime",
    "sse": "realtime", "pubsub": "realtime", "realtime": "realtime",
    "scheduler": "scheduler", "cron": "scheduler", "schedule": "scheduler",
    "job": "jobs", "jobs": "jobs", "task": "jobs", "worker": "workers",
    "blog": "cms", "cms": "cms", "post": "cms", "article": "cms",
    "media": "media", "image": "media", "video": "media", "audio": "media",
    "config": "config", "settings": "config", "env": "config",
    "shared": "shared", "common": "shared", "utils": "util", "helpers": "util",
    "admin": "admin", "dashboard": "dashboard", "report": "analytics",
    "analytics": "analytics", "export": "export", "import": "import",
    "backup": "backup", "restore": "backup", "feature": "feature-flag",
    "toggle": "feature-flag", "abtest": "experiment", "experiment": "experiment",
}
_CRITICALITY_MAP: dict[str, str] = {
    "entrypoint": "critical", "core": "critical", "service": "critical",
    "usecase": "critical", "interactor": "critical",
    "auth": "critical", "database": "critical", "query": "critical",
    "model": "critical", "entity": "critical", "repository": "critical",
    "domain": "critical", "policy": "critical", "validator": "critical",
    "handler": "critical", "controller": "critical",
    "worker": "supporting", "job": "supporting", "scheduler": "supporting",
    "route": "supporting", "middleware": "supporting", "adapter": "supporting",
    "gateway": "supporting", "client": "supporting", "provider": "supporting",
    "serializer": "supporting", "presenter": "supporting", "view": "supporting",
    "component": "supporting", "page": "supporting", "hook": "supporting",
    "composable": "supporting", "store": "supporting", "reducer": "supporting",
    "util": "supporting", "helper": "supporting",
    "migration": "supporting", "seed": "supporting", "test": "supporting",
    "fixture": "supporting",
    "infra": "infra", "cache": "infra", "queue": "infra", "event": "infra",
    "logging": "infra", "monitoring": "infra", "tracing": "infra",
    "observability": "infra", "exception": "infra",
    "config": "config", "barrel": "config", "types": "config",
    "schema": "config", "dto": "config", "interface": "config",
    "shared": "config", "constant": "config", "enum": "config",
}
_LAYER_MAP: dict[str, str] = {
    "route": "presentation", "router": "presentation",
    "controller": "presentation", "handler": "presentation",
    "view": "presentation", "template": "presentation",
    "component": "presentation", "page": "presentation",
    "layout": "presentation", "presenter": "presentation",
    "service": "application", "usecase": "application",
    "interactor": "application", "job": "application",
    "command": "application", "query": "application",
    "mutation": "application", "resolver": "application",
    "worker": "application", "consumer": "application",
    "model": "domain", "entity": "domain", "domain": "domain",
    "repository": "domain", "policy": "domain",
    "validator": "domain", "valueobject": "domain",
    "infra": "infrastructure", "middleware": "infrastructure",
    "cache": "infrastructure", "queue": "infrastructure",
    "database": "infrastructure", "adapter": "infrastructure",
    "gateway": "infrastructure", "client": "infrastructure",
    "provider": "infrastructure", "logging": "infrastructure",
    "monitoring": "infrastructure", "tracing": "infrastructure",
}
_AUTO_ENTRYPOINT_DIRS: frozenset[str] = frozenset({
    "routes", "views", "pages", "screens", "app", "controllers",
    "handlers", "endpoints", "api", "graphql", "resolvers",
    "lambda", "functions", "jobs", "workers", "commands",
})
_ENTRYPOINT_NAMES: frozenset[str] = frozenset({
    "server.ts", "server.js", "server.mjs", "server.cjs", "server.mts", "server.cts",
    "app.ts", "app.js", "app.mjs", "app.cjs",
    "main.ts", "main.js", "main.mjs", "main.cjs",
    "index.ts", "index.js", "index.mjs", "index.cjs",
    "cli.ts", "cli.js", "cli.mjs",
    "server.py", "app.py", "main.py", "run.py", "manage.py", "wsgi.py", "asgi.py",
    "cli.py", "__main__.py",
    "main.go", "server.go",
    "main.rs", "lib.rs",
    "Application.java", "Main.java", "App.java", "Server.java",
    "Application.kt", "Main.kt", "App.kt",
    "Program.cs", "Startup.cs",
    "config.ru", "app.rb", "main.rb",
    "index.php", "server.php", "artisan",
    "start.sh", "run.sh", "deploy.sh",
})
_RE_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_HINT_PROBES = [
    (r"Bun\.sql|\.query\(|SELECT |INSERT |UPDATE |DELETE ", "database"),
    (r"fetch\(|axios\.|requests\.get|\.listen\(", "http"),
    (r"redis|\.set\(.*ex=|cache", "cache"),
    (r"password|argon|bcrypt|jwt|token|session|csrf", "auth"),
    (r"stripe|asaas|invoice|billing|subscription", "billing"),
]
_HINT_PROBES_COMPILED = [(re.compile(p, re.IGNORECASE), label) for p, label in _HINT_PROBES]


def detect_type(rel: Path, src: str, config: IndexerConfig) -> ConfidenceValue:
    segs = [p.lower() for p in rel.parts]
    stem = rel.stem.lower()
    suffix = rel.suffix.lower()
    exact_name = rel.name

    combined_segment_rules = config.type_segment_rules + _TYPE_SEGMENT_RULES
    for seg_kw, result, *rest in combined_segment_rules:
        conf = rest[0] if rest else 0.9
        if seg_kw in segs[:-1]:
            return ConfidenceValue(result, conf)

    combined_name_rules = config.type_name_rules + [(n, t, 0.75) for n, t in _TYPE_NAME_RULES]
    for name_kw, result, *rest in combined_name_rules:
        conf = rest[0] if rest else 0.75
        if name_kw in stem:
            return ConfidenceValue(result, conf)

    user_suffix = config.type_suffix_rules.get(suffix)
    if user_suffix:
        return ConfidenceValue(user_suffix[0], user_suffix[1])

    if suffix == ".sql":
        return ConfidenceValue("migration", 0.85)
    if suffix in {".css", ".scss", ".tsx", ".jsx", ".html", ".vue"}:
        return ConfidenceValue("ui", 0.9)
    if suffix in {".md", ".rst"}:
        return ConfidenceValue("docs", 0.95)
    if suffix in {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf"}:
        return ConfidenceValue("config", 0.95)
    if suffix == ".sh":
        return ConfidenceValue("script", 0.85)

    user_exact = config.type_exact_name_rules.get(exact_name)
    if user_exact:
        return ConfidenceValue(user_exact[0], user_exact[1])

    if exact_name in {"Dockerfile", "dockerfile"}:
        return ConfidenceValue("config", 0.9)
    if exact_name in {"Makefile", "Procfile"}:
        return ConfidenceValue("build", 0.85)

    if suffix in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py"}:
        if is_entrypoint(rel, src):
            return ConfidenceValue("entrypoint", 0.8)
        return ConfidenceValue("module", 0.55)

    return ConfidenceValue("module", 0.5)


def detect_domain(rel: Path, src: str, config: IndexerConfig) -> tuple[ConfidenceValue, str | None]:
    tokens: list[str] = []
    for part in rel.parts:
        for tok in re.split(r"[^a-zA-Z0-9]+", part.lower()):
            if tok:
                tokens.append(tok)
    matches: list[str] = []
    for tok in tokens:
        mapped = _DOMAIN_KEYWORDS.get(tok)
        if mapped:
            matches.append(mapped)
    if src:
        lower = src.lower()
        for key, dom in _DOMAIN_KEYWORDS.items():
            if key in lower:
                matches.append(dom)
    for prefix, dom in config.domain_overrides.items():
        if rel.as_posix().startswith(prefix.lstrip("/")):
            return ConfidenceValue(dom, 1.0), None
    if not matches:
        return ConfidenceValue("core", 0.4), None
    counter = Counter(matches)
    primary = counter.most_common(1)[0][0]
    total = sum(counter.values())
    conf = min(0.95, 0.5 + (counter[primary] / max(1, total)) * 0.45)
    secondary = next((d for d, _ in counter.most_common() if d != primary), None)
    return ConfidenceValue(primary, conf), secondary


def detect_layer(ftype: str, rel: Path | None, src: str) -> str:
    if ftype in {"docs", "config", "asset", "template"}:
        return "infrastructure" if ftype == "config" else "unknown"
    mapped = _LAYER_MAP.get(ftype)
    if mapped:
        return mapped
    if rel is not None:
        tokens = set(re.split(r"[^a-zA-Z0-9]+", rel.as_posix().lower()))
        for ft, lyr in _LAYER_MAP.items():
            if ft in tokens:
                return lyr
    return "unknown"


def is_entrypoint(rel: Path, src: str) -> bool:
    name = rel.name.lower()
    dirs = {p.lower() for p in rel.parts[:-1]}
    if name in _ENTRYPOINT_NAMES:
        return True
    if dirs & _AUTO_ENTRYPOINT_DIRS:
        return True
    if rel.suffix.lower() == ".py" and re.search(r"if\s+__name__\s*==\s*['\"]__main__['\"]", src):
        return True
    if rel.suffix.lower() in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"} and re.search(r"\.listen\s*\(", src):
        return True
    return False


def get_criticality(rel: Path, ftype: str, config: IndexerConfig) -> str:
    for prefix, crit in config.criticality_overrides.items():
        if rel.as_posix().startswith(prefix.lstrip("/")):
            return crit
    return _CRITICALITY_MAP.get(ftype, "supporting")


def complexity(lines: int, funcs: list[str], classes: list[str], internal: list[str], src: str) -> tuple[int, str]:
    score = lines + len(funcs) * 12 + len(classes) * 25 + len(internal) * 8
    score += src.count("\n") // 20
    if score > 1200:
        return score, "extreme"
    if score > 600:
        return score, "high"
    if score > 200:
        return score, "medium"
    return score, "low"


def extract_hints(
    rel: Path,
    src: str,
    ftype: str,
    domain: str,
    funcs: list[str],
    classes: list[str],
    deps: list[str],
    module_doc: str | None,
) -> dict[str, Any]:
    if module_doc:
        description = module_doc.strip().split("\n")[0][:120]
    else:
        dir_name = rel.parent.name
        parts_desc = [f"{ftype} for {domain} domain"]
        if dir_name and dir_name not in {"src", ".", ""}:
            parts_desc.append(f"in {dir_name}/")
        description = " ".join(parts_desc)

    keywords: set[str] = {domain, ftype}
    for dep in deps[:8]:
        head = dep.lstrip("@").split("/")[0].split(".")[0]
        if head and len(head) > 1:
            keywords.add(head.lower())

    for sym in list(funcs[:6]) + list(classes[:4]):
        for word in _RE_CAMEL.sub("_", sym).lower().split("_"):
            if len(word) > 3:
                keywords.add(word)

    for part in rel.parts[:-1]:
        tok = part.strip("./")
        if tok and len(tok) > 2 and tok not in {"src", "lib", "app"}:
            keywords.add(tok.lower())

    if src:
        lower_src = src.lower()
        for pattern, label in _HINT_PROBES_COMPILED:
            if pattern.search(lower_src):
                keywords.add(label)

    return {"description": description, "keywords": sorted(keywords)}

