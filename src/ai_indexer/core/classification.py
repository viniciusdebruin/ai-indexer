"""File classification and semantic hint helpers."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
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
    ("api", "api"), ("apis", "api"),
    ("graphql", "graphql"), ("resolvers", "resolver"),
    ("schemas", "schema"), ("schema", "schema"),
    ("dtos", "dto"), ("dto", "dto"),
    ("types", "types"), ("interfaces", "types"),
    ("utils", "util"), ("helpers", "util"), ("lib", "util"),
    ("config", "config"), ("settings", "config"),
    ("db", "database"), ("database", "database"),
    ("migrations", "migration"), ("migration", "migration"),
    ("tests", "test"), ("test", "test"), ("specs", "test"),
]
_TYPE_NAME_RULES: list[tuple[str, str]] = [
    ("server", "entrypoint"), ("app", "entrypoint"), ("main", "entrypoint"),
    ("index", "barrel"), ("mod", "barrel"), ("lib", "barrel"),
    ("config", "config"), ("settings", "config"), ("env", "config"),
    ("middleware", "middleware"), ("worker", "worker"),
    ("route", "route"), ("router", "route"),
    ("controller", "controller"), ("handler", "handler"),
    ("service", "service"), ("usecase", "usecase"),
    ("model", "model"), ("entity", "entity"),
    ("repository", "repository"), ("repo", "repository"),
    ("adapter", "adapter"), ("gateway", "gateway"),
    ("client", "client"), ("provider", "provider"),
    ("validator", "validator"), ("serializer", "serializer"),
    ("presenter", "presenter"), ("view", "view"),
    ("component", "component"), ("page", "page"), ("layout", "layout"),
    ("resolver", "resolver"), ("schema", "schema"),
    ("dto", "types"), ("types", "types"), ("interface", "types"),
    ("util", "util"), ("helper", "util"),
    ("auth", "auth"), ("cache", "cache"),
    ("queue", "queue"), ("event", "event"),
    ("job", "job"), ("task", "job"),
    ("migration", "migration"), ("seed", "seed"),
    ("test", "test"), ("spec", "test"),
]

_DOMAIN_KEYWORDS: dict[str, str] = {
    "auth": "auth", "login": "auth", "logout": "auth", "oauth": "auth",
    "jwt": "auth", "session": "auth", "permission": "auth", "role": "auth",
    "mfa": "auth", "2fa": "auth",
    "user": "users", "users": "users", "profile": "users", "account": "users",
    "team": "teams", "organization": "teams",
    "billing": "billing", "payment": "billing", "invoice": "billing",
    "stripe": "billing", "paypal": "billing", "subscription": "billing",
    "checkout": "billing", "cart": "billing",
    "lead": "leads", "crm": "crm", "customer": "crm", "client": "crm",
    "product": "catalog", "catalog": "catalog", "inventory": "inventory",
    "order": "orders", "shipping": "shipping", "shipment": "shipping",
    "email": "email", "sms": "sms", "notification": "notification",
    "webhook": "webhooks", "slack": "messaging", "discord": "messaging",
    "llm": "ai", "openai": "ai", "anthropic": "ai", "embedding": "ai", "rag": "ai",
    "database": "database", "db": "database", "sql": "database",
    "postgres": "database", "mysql": "database", "mongodb": "database",
    "redis": "cache", "cache": "cache",
    "elasticsearch": "search", "search": "search",
    "storage": "storage", "upload": "storage", "download": "storage",
    "security": "security", "crypto": "security", "encrypt": "security",
    "audit": "audit", "compliance": "compliance",
    "monitoring": "monitoring", "metric": "monitoring",
    "logging": "logging", "log": "logging", "trace": "tracing", "tracing": "tracing",
    "deploy": "deployment", "ci": "ci", "cd": "cd",
    "docker": "container", "kubernetes": "orchestration",
    "scheduler": "scheduler", "cron": "scheduler", "job": "jobs", "worker": "workers",
    "config": "config", "settings": "config", "env": "config",
    "shared": "shared", "common": "shared", "utils": "util", "helpers": "util",
    "dashboard": "dashboard", "analytics": "analytics", "report": "analytics",
}
_LAYER_MAP: dict[str, str] = {
    "route": "presentation", "router": "presentation",
    "controller": "presentation", "handler": "presentation",
    "view": "presentation", "template": "presentation",
    "component": "presentation", "page": "presentation", "layout": "presentation",
    "service": "application", "usecase": "application", "interactor": "application",
    "job": "application", "command": "application", "query": "application",
    "worker": "application",
    "model": "domain", "entity": "domain", "domain": "domain", "repository": "domain",
    "policy": "domain", "validator": "domain",
    "infra": "infrastructure", "middleware": "infrastructure", "cache": "infrastructure",
    "queue": "infrastructure", "database": "infrastructure", "adapter": "infrastructure",
    "gateway": "infrastructure", "client": "infrastructure", "provider": "infrastructure",
    "logging": "infrastructure", "monitoring": "infrastructure", "tracing": "infrastructure",
}
_AUTO_ENTRYPOINT_DIRS: frozenset[str] = frozenset({
    "routes", "views", "pages", "app", "controllers",
    "handlers", "endpoints", "api", "graphql", "resolvers",
    "lambda", "functions", "jobs", "workers", "commands",
})
_ENTRYPOINT_NAMES: frozenset[str] = frozenset({
    "server.ts", "server.js", "app.ts", "app.js", "main.ts", "main.js", "index.ts", "index.js",
    "server.py", "app.py", "main.py", "run.py", "manage.py", "wsgi.py", "asgi.py", "__main__.py",
    "main.go", "main.rs", "application.java", "main.java", "program.cs",
    "index.php", "server.php", "start.sh", "run.sh", "deploy.sh",
})
_RE_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_RE_TOKEN = re.compile(r"[^a-zA-Z0-9]+")
_HINT_PROBES = [
    (r"Bun\.sql|\.query\(|SELECT |INSERT |UPDATE |DELETE ", "database"),
    (r"fetch\(|axios\.|requests\.get|\.listen\(", "http"),
    (r"redis|cache", "cache"),
    (r"password|argon|bcrypt|jwt|token|session|csrf", "auth"),
    (r"stripe|invoice|billing|subscription", "billing"),
]
_HINT_PROBES_COMPILED = [(re.compile(p, re.IGNORECASE), label) for p, label in _HINT_PROBES]

_CRITICAL_DOMAINS = {"auth", "billing", "security", "database"}
_CRITICAL_DEP_HINTS = {"auth", "jwt", "bcrypt", "crypto", "database", "postgres", "mysql", "mongo", "redis"}


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


def detect_domain(
    rel: Path,
    src: str,
    config: IndexerConfig,
    dependencies: list[str] | None = None,
    symbols: list[str] | None = None,
    module_doc: str | None = None,
) -> tuple[ConfidenceValue, str | None]:
    for prefix, dom in config.domain_overrides.items():
        if rel.as_posix().startswith(prefix.lstrip("/")):
            return ConfidenceValue(dom, 1.0), None

    scores = domain_evidence(rel, src, dependencies=dependencies, symbols=symbols, module_doc=module_doc)
    if not scores:
        return ConfidenceValue("core", 0.4), None
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    primary, primary_score = ranked[0]
    secondary = ranked[1][0] if len(ranked) > 1 and ranked[1][1] > 0.0 else None
    total = sum(max(value, 0.0) for _, value in ranked)
    confidence = min(0.95, 0.5 + (primary_score / max(1.0, total)) * 0.45)
    return ConfidenceValue(primary, round(confidence, 3)), secondary


def domain_evidence(
    rel: Path,
    src: str,
    dependencies: list[str] | None = None,
    symbols: list[str] | None = None,
    module_doc: str | None = None,
) -> dict[str, float]:
    evidence: defaultdict[str, float] = defaultdict(float)
    for token in _tokenize_path(rel):
        mapped = _DOMAIN_KEYWORDS.get(token)
        if mapped:
            evidence[mapped] += 2.0

    if src:
        lower = src.lower()
        for key, mapped in _DOMAIN_KEYWORDS.items():
            if key in lower:
                evidence[mapped] += 1.0

    for dep in dependencies or []:
        dep_tokens = _tokenize_string(dep)
        for token in dep_tokens:
            mapped = _DOMAIN_KEYWORDS.get(token)
            if mapped:
                evidence[mapped] += 2.5

    for symbol in symbols or []:
        for token in _tokenize_string(symbol):
            mapped = _DOMAIN_KEYWORDS.get(token)
            if mapped:
                evidence[mapped] += 1.5

    if module_doc:
        for token in _tokenize_string(module_doc):
            mapped = _DOMAIN_KEYWORDS.get(token)
            if mapped:
                evidence[mapped] += 1.2

    return dict(evidence)


def detect_layer(ftype: str, rel: Path | None, src: str) -> str:  # noqa: ARG001
    if ftype in {"docs", "config", "asset", "template"}:
        return "infrastructure" if ftype == "config" else "unknown"
    mapped = _LAYER_MAP.get(ftype)
    if mapped:
        return mapped
    if rel is not None:
        tokens = set(_tokenize_string(rel.as_posix()))
        for ftype_token, layer in _LAYER_MAP.items():
            if ftype_token in tokens:
                return layer
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


def get_criticality(
    rel: Path,
    ftype: str,
    config: IndexerConfig,
    *,
    domain: str | None = None,
    entrypoint: bool = False,
    dependencies: list[str] | None = None,
    warnings: list[str] | None = None,
) -> str:
    for prefix, crit in config.criticality_overrides.items():
        if rel.as_posix().startswith(prefix.lstrip("/")):
            return crit
    score = 0.0
    reasons = criticality_signals(
        rel,
        ftype,
        domain=domain,
        entrypoint=entrypoint,
        dependencies=dependencies,
        warnings=warnings,
    )
    for value in reasons.values():
        score += value
    if score >= 70:
        return "critical"
    if score >= 45:
        return "infra"
    if ftype in {"config", "barrel", "types", "schema", "dto", "interface", "shared"}:
        return "config"
    return "supporting"


def criticality_signals(
    rel: Path,
    ftype: str,
    *,
    domain: str | None = None,
    entrypoint: bool = False,
    dependencies: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, float]:
    baseline = {
        "entrypoint": 28.0, "core": 24.0, "service": 22.0, "usecase": 22.0,
        "auth": 24.0, "database": 24.0, "query": 22.0, "model": 20.0,
        "entity": 20.0, "repository": 22.0, "validator": 18.0,
    }
    signals: dict[str, float] = {"type_baseline": baseline.get(ftype, 10.0)}
    if entrypoint:
        signals["entrypoint_boost"] = 30.0
    if domain in _CRITICAL_DOMAINS:
        signals["critical_domain_boost"] = 20.0
    path_tokens = set(_tokenize_path(rel))
    if {"auth", "billing", "payment", "security"} & path_tokens:
        signals["path_risk_boost"] = 14.0
    dependency_tokens: set[str] = set()
    for dep in dependencies or []:
        dependency_tokens.update(_tokenize_string(dep))
    if _CRITICAL_DEP_HINTS & dependency_tokens:
        signals["dependency_risk_boost"] = 12.0
    if any("secret" in warning.lower() for warning in warnings or []):
        signals["secret_warning_boost"] = 10.0
    return signals


def complexity(
    lines: int,
    funcs: list[str],
    classes: list[str],
    internal: list[str],
    src: str,
) -> tuple[int, str]:
    details = complexity_signals(lines, funcs, classes, internal, src)
    score = int(round(sum(details.values())))
    if score > 1300:
        return score, "extreme"
    if score > 700:
        return score, "high"
    if score > 280:
        return score, "medium"
    return score, "low"


def complexity_signals(
    lines: int,
    funcs: list[str],
    classes: list[str],
    internal: list[str],
    src: str,
) -> dict[str, float]:
    branch_points = len(re.findall(r"\b(if|elif|for|while|case|switch|catch|except)\b", src))
    logical_ops = len(re.findall(r"&&|\|\|", src))
    nesting = _nesting_depth(src)
    long_lines = sum(1 for line in src.splitlines() if len(line) > 120)
    fanout = len(internal)
    responsibilities = len(funcs) + (len(classes) * 2)
    entropy = _import_entropy(internal)
    return {
        "size": float(lines),
        "responsibilities": float(responsibilities * 12),
        "fanout": float(fanout * 8),
        "branches": float(branch_points * 11),
        "logical_ops": float(logical_ops * 4),
        "nesting": float(nesting * 18),
        "long_lines": float(long_lines * 2),
        "entropy": float(entropy * 10),
    }


def extract_hints(
    rel: Path,
    src: str,
    ftype: str,
    domain: str,
    funcs: list[str],
    classes: list[str],
    deps: list[str],
    module_doc: str | None,
    *,
    domain_scores: dict[str, float] | None = None,
    criticality_scores: dict[str, float] | None = None,
    complexity_scores: dict[str, float] | None = None,
    complexity_label: str | None = None,
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
    for dep in deps[:12]:
        head = dep.lstrip("@").split("/")[0].split(".")[0]
        if head and len(head) > 1:
            keywords.add(head.lower())

    for sym in list(funcs[:8]) + list(classes[:5]):
        for word in _RE_CAMEL.sub("_", sym).lower().split("_"):
            if len(word) > 3:
                keywords.add(word)

    for part in rel.parts[:-1]:
        token = part.strip("./")
        if token and len(token) > 2 and token not in {"src", "lib", "app"}:
            keywords.add(token.lower())

    if src:
        lower_src = src.lower()
        for pattern, label in _HINT_PROBES_COMPILED:
            if pattern.search(lower_src):
                keywords.add(label)

    classification_explanation = {
        "file_type": ftype,
        "domain": domain,
        "domain_evidence": _sorted_top(domain_scores or {}, limit=5),
        "criticality_signals": _sorted_top(criticality_scores or {}, limit=6),
        "complexity_signals": _sorted_top(complexity_scores or {}, limit=6),
        "complexity_label": complexity_label or "low",
    }
    return {
        "description": description,
        "keywords": sorted(keywords),
        "classification": classification_explanation,
    }


def _tokenize_path(rel: Path) -> list[str]:
    tokens: list[str] = []
    for part in rel.parts:
        tokens.extend(_tokenize_string(part))
    return tokens


def _tokenize_string(value: str) -> list[str]:
    tokens = [token for token in _RE_TOKEN.split(value.lower()) if token]
    return tokens


def _nesting_depth(src: str) -> int:
    max_depth = 0
    for line in src.splitlines():
        stripped = line.lstrip(" ")
        if not stripped:
            continue
        indent = len(line) - len(stripped)
        if stripped.startswith(("#", "//", "/*", "*")):
            continue
        depth = int(math.floor(indent / 4))
        max_depth = max(max_depth, depth)
    return max_depth


def _import_entropy(imports: list[str]) -> float:
    if not imports:
        return 0.0
    counter = Counter(imp.split("/")[0] for imp in imports if imp)
    total = sum(counter.values())
    entropy = 0.0
    for count in counter.values():
        prob = count / max(1, total)
        entropy -= prob * math.log2(prob)
    return entropy


def _sorted_top(raw: dict[str, float], limit: int) -> dict[str, float]:
    return dict(sorted(raw.items(), key=lambda item: item[1], reverse=True)[:limit])
