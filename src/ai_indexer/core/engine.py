"""Analysis engine — orchestrates parsing, graph building, metric enrichment,
and output generation for a single project root."""

from __future__ import annotations

import fnmatch
import logging
import re
import sys
import time
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from collections.abc import Callable
from typing import Any, TypedDict

from ai_indexer.core.cache import AnalysisCache
from ai_indexer.core.classification import (
    complexity as classify_complexity,
    detect_domain as classify_domain,
    detect_layer as classify_layer,
    detect_type as classify_type,
    extract_hints as classify_hints,
    get_criticality as classify_criticality,
    is_entrypoint as classify_entrypoint,
)
from ai_indexer.core.models import (
    AnalysisRecord,
    ConfidenceValue,
    FileMetadata,
)
from ai_indexer.core.graph import build_graph, compute_v8_metrics, enrich_graph_metrics
from ai_indexer.core.pipeline import AnalysisPipeline
from ai_indexer.parsers.base import ParserRegistry
from ai_indexer.parsers.python import PythonParser
from ai_indexer.parsers.typescript import TypeScriptParser
from ai_indexer.utils.config import IndexerConfig
from ai_indexer.utils.io import (
    GitignoreFilter,
    ImportResolver,
    safe_read_text,
)
from ai_indexer.version import __version__

log = logging.getLogger("ai-indexer.engine")

# Aumenta recursionlimit para grafos grandes
sys.setrecursionlimit(10000)

# ── Default ignore sets (expanded for polyglot ecosystems) ────────────────────
_IGNORE_DIRS: frozenset[str] = frozenset[str]({
    # VCS e ferramentas
    ".git", ".hg", ".svn",
    # Dependências
    "node_modules", "vendor", "bower_components", "jspm_packages",
    # Build / output
    "dist", "build", "out", "target", "bin", "obj", "Debug", "Release",
    "x64", "x86", "generated", ".output", ".nuxt", ".next", ".turbo",
    # Python
    "__pycache__", ".venv", "venv", "env", ".env", "virtualenv",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", "*.egg-info",
    # Java / Kotlin
    ".gradle", ".idea", ".settings", "classes", ".classpath", ".project",
    # .NET
    "packages", ".vs",
    # Ruby
    ".bundle", "log", "tmp", "coverage",
    # PHP
    "storage", "bootstrap/cache",
    # IDEs e editores
    ".vscode", ".cursor", ".claude", ".fleet", ".idea", ".eclipse",
    # Testes e relatórios
    "coverage", ".nyc_output", "test-results", "reports",
    # Ferramentas específicas
    ".terraform", ".serverless", "cdk.out", ".amplify",
    # Documentação gerada
    "docs/_build", "site", ".docusaurus",
    # Dados e mídia (grandes volumes)
    "data", "dataset", "models", "uploads", "static",
})
_IGNORE_PATTERNS: tuple[str, ...] = (
    # Sistema
    ".DS_Store", "Thumbs.db", "desktop.ini", "ehthumbs.db",
    # Ambiente
    ".env*", "*.local", "*.secret",
    # Git
    ".git*", "*.patch",
    # Dependências travadas
    "*.lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "Pipfile.lock", "Gemfile.lock", "Cargo.lock",
    "composer.lock", "mix.lock", "pubspec.lock",
    # Compilados / minificados
    "*.min.js", "*.min.css", "*.min.js.map", "*.min.css.map",
    "*.pyc", "*.pyo", "*.pyd", "*.so", "*.dll", "*.exe", "*.o", "*.a",
    "*.class", "*.jar", "*.war", "*.ear",
    # Mídia e binários
    "*.png", "*.jpg", "*.jpeg", "*.gif", "*.ico", "*.svg", "*.webp",
    "*.woff", "*.woff2", "*.ttf", "*.eot", "*.otf",
    "*.mp3", "*.mp4", "*.wav", "*.avi", "*.mov", "*.webm",
    "*.zip", "*.tar", "*.gz", "*.bz2", "*.7z", "*.rar",
    "*.pdf", "*.doc", "*.docx", "*.xls", "*.xlsx", "*.ppt", "*.pptx",
    # Certificados e chaves
    "*.pem", "*.crt", "*.key", "*.p12", "*.pfx",
    # Outros
    "*.log", "*.bak", "*.tmp", "*.swp", "*.swo",
)
_GENERATED_FILES: frozenset[str] = frozenset[str]({
    "estrutura_projeto.json", "estrutura_projeto.toon",
    "estrutura_projeto.html", "estrutura_projeto.md",
    ".aicontext_cache_v6.json", ".aicontext_cache_v8.json",
    "package-lock.json", "yarn.lock", "Cargo.lock", "go.sum",
})
_TEXT_SUFFIXES: frozenset[str] = frozenset[str]({
    # JavaScript / TypeScript
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts",
    # Python
    ".py", ".pyi", ".pyx", ".pxd", ".pxi",
    # Web (templates e estilos)
    ".html", ".htm", ".xhtml", ".vue", ".svelte", ".astro",
    ".css", ".scss", ".sass", ".less", ".styl",
    # Ruby
    ".rb", ".erb", ".rake", ".gemspec",
    # PHP
    ".php", ".phtml", ".php3", ".php4", ".php5", ".phps",
    # Java / Kotlin / Scala
    ".java", ".kt", ".kts", ".scala", ".groovy",
    # C / C++ / Rust / Zig
    ".c", ".h", ".cpp", ".hpp", ".cc", ".hh", ".cxx", ".hxx",
    ".rs", ".zig",
    # C# / F#
    ".cs", ".fs", ".vb",
    # Go
    ".go",
    # Shell
    ".sh", ".bash", ".zsh", ".fish", ".ps1", ".psm1", ".psd1",
    # Dados / Configuração
    ".json", ".jsonc", ".json5", ".yml", ".yaml", ".toml", ".ini",
    ".cfg", ".conf", ".config", ".properties", ".env", ".env.example",
    # Documentação
    ".md", ".markdown", ".rst", ".adoc", ".tex", ".txt", "",
    # Query / Schema
    ".sql", ".graphql", ".gql", ".prisma", ".proto", ".thrift",
    # Outras linguagens
    ".dart", ".ex", ".exs", ".elm", ".purs", ".hs", ".lhs",
    ".clj", ".cljs", ".edn", ".rkt", ".lisp", ".lsp",
    ".swift", ".m", ".mm",
})
_SPECIAL_TEXT_FILENAMES: frozenset[str] = frozenset[str]({
    "Dockerfile", "Makefile", "Procfile", "Gemfile", "Rakefile",
    "Vagrantfile", "Berksfile", "Cheffile", "Puppetfile",
    "Jenkinsfile", "Brewfile", "Fastfile", "Podfile",
    "Cargo.toml", "Cargo.lock", "go.mod", "go.sum",
    "CMakeLists.txt", "BUILD", "WORKSPACE", "BUCK",
    "requirements.txt", "Pipfile", "pyproject.toml",
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "tsconfig.json", "jsconfig.json", "babel.config.js", "webpack.config.js",
    ".eslintrc", ".prettierrc", ".stylelintrc", ".editorconfig",
    ".gitignore", ".dockerignore", ".npmignore", ".eslintignore",
    "README", "LICENSE", "CHANGELOG", "CONTRIBUTING", "CODE_OF_CONDUCT",
})
_TYPE_SEGMENT_RULES: list[tuple[str, str]] = [
    # Backend
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
    # Autenticação e Autorização
    "auth": "auth", "login": "auth", "logout": "auth", "oauth": "auth",
    "jwt": "auth", "session": "auth", "permission": "auth", "role": "auth",
    "rbac": "auth", "abac": "auth", "sso": "auth", "mfa": "auth", "2fa": "auth",

    # Usuários e Perfis
    "user": "users", "users": "users", "profile": "users", "account": "users",
    "member": "users", "team": "teams", "teams": "teams", "organization": "teams",

    # Pagamentos e Faturamento
    "billing": "billing", "payment": "billing", "invoice": "billing",
    "stripe": "billing", "paypal": "billing", "asaas": "billing",
    "pagar": "billing", "mercado pago": "billing", "subscription": "billing",
    "plan": "billing", "price": "billing", "checkout": "billing", "cart": "billing",

    # Leads e CRM
    "lead": "leads", "leads": "leads", "crm": "crm", "customer": "crm",
    "client": "crm", "contact": "crm", "deal": "crm", "pipeline": "crm",

    # E‑commerce
    "product": "catalog", "catalog": "catalog", "inventory": "inventory",
    "stock": "inventory", "order": "orders", "orders": "orders",
    "shipment": "shipping", "shipping": "shipping", "fulfillment": "shipping",
    "tax": "tax", "vat": "tax", "coupon": "promotion", "promotion": "promotion",

    # Comunicação
    "email": "email", "smtp": "email", "mail": "email",
    "sms": "sms", "twilio": "sms", "push": "push", "notification": "notification",
    "whatsapp": "whatsapp", "telegram": "messaging", "slack": "messaging",
    "discord": "messaging", "webhook": "webhooks", "webhooks": "webhooks",

    # IA / LLM
    "llm": "ai", "ai": "ai", "openai": "ai", "anthropic": "ai",
    "chatgpt": "ai", "claude": "ai", "embedding": "ai", "vector": "ai",
    "rag": "ai", "prompt": "ai", "completion": "ai",

    # Dados e Armazenamento
    "database": "database", "db": "database", "sql": "database",
    "nosql": "database", "mongodb": "database", "postgres": "database",
    "mysql": "database", "sqlite": "database", "redis": "cache", "cache": "cache",
    "memcached": "cache", "elasticsearch": "search", "search": "search",
    "s3": "storage", "storage": "storage", "blob": "storage", "file": "storage",
    "upload": "storage", "download": "storage",

    # Segurança
    "crypto": "security", "security": "security", "encrypt": "security",
    "decrypt": "security", "hash": "security", "csrf": "security",
    "xss": "security", "sql injection": "security", "audit": "audit",
    "compliance": "compliance", "gdpr": "compliance", "lgpd": "compliance",

    # Infraestrutura e DevOps
    "health": "infra", "status": "infra", "metric": "monitoring",
    "monitoring": "monitoring", "logging": "logging", "log": "logging",
    "trace": "tracing", "tracing": "tracing", "alert": "alerting",
    "alerting": "alerting", "deploy": "deployment", "ci": "ci",
    "cd": "cd", "docker": "container", "kubernetes": "orchestration",

    # Realtime
    "ws": "realtime", "socket": "realtime", "websocket": "realtime",
    "sse": "realtime", "pubsub": "realtime", "realtime": "realtime",

    # Agendamento
    "scheduler": "scheduler", "cron": "scheduler", "schedule": "scheduler",
    "job": "jobs", "jobs": "jobs", "task": "jobs", "worker": "workers",

    # Conteúdo e Mídia
    "blog": "cms", "cms": "cms", "post": "cms", "article": "cms",
    "media": "media", "image": "media", "video": "media", "audio": "media",

    # Configuração e Utilidades
    "config": "config", "settings": "config", "env": "config",
    "shared": "shared", "common": "shared", "utils": "util", "helpers": "util",

    # Outros
    "admin": "admin", "dashboard": "dashboard", "report": "analytics",
    "analytics": "analytics", "export": "export", "import": "import",
    "backup": "backup", "restore": "backup", "feature": "feature-flag",
    "toggle": "feature-flag", "abtest": "experiment", "experiment": "experiment",
}
_CRITICALITY_MAP: dict[str, str] = {
    # Críticos
    "entrypoint": "critical", "core": "critical", "service": "critical",
    "usecase": "critical", "interactor": "critical",
    "auth": "critical", "database": "critical", "query": "critical",
    "model": "critical", "entity": "critical", "repository": "critical",
    "domain": "critical", "policy": "critical", "validator": "critical",
    "handler": "critical", "controller": "critical",
    # Suporte
    "worker": "supporting", "job": "supporting", "scheduler": "supporting",
    "route": "supporting", "middleware": "supporting", "adapter": "supporting",
    "gateway": "supporting", "client": "supporting", "provider": "supporting",
    "serializer": "supporting", "presenter": "supporting", "view": "supporting",
    "component": "supporting", "page": "supporting", "hook": "supporting",
    "composable": "supporting", "store": "supporting", "reducer": "supporting",
    "util": "supporting", "helper": "supporting",
    "migration": "supporting", "seed": "supporting", "test": "supporting",
    "fixture": "supporting",
    # Infraestrutura
    "infra": "infra", "cache": "infra", "queue": "infra", "event": "infra",
    "logging": "infra", "monitoring": "infra", "tracing": "infra",
    "observability": "infra", "exception": "infra",
    # Configuração
    "config": "config", "barrel": "config", "types": "config",
    "schema": "config", "dto": "config", "interface": "config",
    "shared": "config", "constant": "config", "enum": "config",
}

_LAYER_MAP: dict[str, str] = {
    # Apresentação
    "route": "presentation", "router": "presentation",
    "controller": "presentation", "handler": "presentation",
    "view": "presentation", "template": "presentation",
    "component": "presentation", "page": "presentation",
    "layout": "presentation", "presenter": "presentation",
    # Aplicação
    "service": "application", "usecase": "application",
    "interactor": "application", "job": "application",
    "command": "application", "query": "application",
    "mutation": "application", "resolver": "application",
    "worker": "application", "consumer": "application",
    # Domínio
    "model": "domain", "entity": "domain", "domain": "domain",
    "repository": "domain", "policy": "domain",
    "validator": "domain", "valueobject": "domain",
    # Infraestrutura
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
    # Node / Deno / Bun
    "server.ts", "server.js", "server.mjs", "server.cjs", "server.mts", "server.cts",
    "app.ts", "app.js", "app.mjs", "app.cjs",
    "main.ts", "main.js", "main.mjs", "main.cjs",
    "index.ts", "index.js", "index.mjs", "index.cjs",
    "cli.ts", "cli.js", "cli.mjs",
    # Python
    "server.py", "app.py", "main.py", "run.py", "manage.py", "wsgi.py", "asgi.py",
    "cli.py", "__main__.py",
    # Go
    "main.go", "server.go",
    # Rust
    "main.rs", "lib.rs",
    # Java / Kotlin (Main class patterns)
    "Application.java", "Main.java", "App.java", "Server.java",
    "Application.kt", "Main.kt", "App.kt",
    # C#
    "Program.cs", "Startup.cs",
    # Ruby
    "config.ru", "app.rb", "main.rb",
    # PHP
    "index.php", "server.php", "artisan",
    # Shell
    "start.sh", "run.sh", "deploy.sh",
})

# Compiled regex for hints extraction
_RE_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_HINT_PROBES = [
    (r"Bun\.sql|\.query\(|SELECT |INSERT |UPDATE |DELETE ", "database"),
    (r"fetch\(|axios\.|requests\.get|\.listen\(", "http"),
    (r"redis|\.set\(.*ex=|cache", "cache"),
    (r"password|argon|bcrypt|jwt|token|session|csrf", "auth"),
    (r"stripe|asaas|invoice|billing|subscription", "billing"),
]
_HINT_PROBES_COMPILED = [(re.compile(p, re.IGNORECASE), label) for p, label in _HINT_PROBES]

# Sub-interpreters availability flag (PEP 734)
try:
    import interpreters as _interpreters
    _INTERPRETERS_AVAILABLE = True
except ImportError:
    _interpreters = None
    _INTERPRETERS_AVAILABLE = False


class FileMetaDict(TypedDict, total=False):
    file: str
    file_type: dict[str, Any]
    domain: dict[str, Any]
    secondary_domain: str | None
    layer: str
    criticality: str
    entrypoint: bool
    complexity_label: str
    complexity_score: int
    capabilities: dict[str, list[str]]
    dependencies: list[str]
    internal_dependencies: list[str]
    warnings: list[str]
    is_in_cycle: bool
    docstrings: dict[str, str]
    type_hints: dict[str, dict[str, str]]
    chunks: list[str]
    module_doc: str | None
    hints: dict[str, Any]
    refactor_effort: float
    blast_radius: int


_EMPTY_META_TEMPLATE: dict[str, Any] = {
    "file_type": {"value": "module", "confidence": 0.0},
    "domain": {"value": "core", "confidence": 0.0},
    "secondary_domain": None,
    "layer": "unknown",
    "criticality": "supporting",
    "entrypoint": False,
    "complexity_label": "low",
    "complexity_score": 0,
    "capabilities": {"functions": [], "classes": [], "exports": []},
    "dependencies": [],
    "internal_dependencies": [],
    "warnings": ["parse error"],
    "is_in_cycle": False,
    "docstrings": {},
    "type_hints": {},
    "chunks": [],
    "module_doc": None,
    "hints": {"description": "", "keywords": []},
    "refactor_effort": 0.0,
    "blast_radius": 0,
}


class AnalysisEngine:
    """Orchestrates the full analysis pipeline for a project root."""

    def __init__(self, root: Path, config: IndexerConfig) -> None:
        if not root.is_dir():
            raise ValueError(f"Root must be an existing directory: {root}")
        self.root = root
        self.config = config
        self.cache = AnalysisCache(root)
        self.files: dict[str, FileMetadata] = {}
        self.graph: dict[str, list[str]] = {}
        self.rev: dict[str, list[str]] = {}
        self.ignore_dirs = _IGNORE_DIRS | self.config.exclude_dirs
        self.ignore_patterns = _IGNORE_PATTERNS + self.config.exclude_patterns
        self.generated_files = _GENERATED_FILES
        self.text_suffixes = _TEXT_SUFFIXES
        self.special_text_filenames = _SPECIAL_TEXT_FILENAMES | self.config.extra_text_filenames
        self._file_index: dict[str, str] = {}
        self._registry = ParserRegistry()
        self._register_default_parsers()

    def _register_default_parsers(self) -> None:
        self._registry.register(PythonParser())
        self._registry.register(TypeScriptParser())

    # ── Public API ────────────────────────────────────────────────────────────

    def run(
        self,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> None:
        t0 = time.time()
        log.info("AI Context Indexer v%s — %s", __version__, self.root)
        try:
            AnalysisPipeline(self).run(on_progress=on_progress)
        except KeyboardInterrupt:
            log.warning("Interrupted – saving partial cache")
            self.cache.save()
            raise
        elapsed = time.time() - t0
        log.info("Analysed %d files in %.2fs", len(self.files), elapsed)

    def _update_files_and_cache(self, results: list[tuple[str, AnalysisRecord | dict[str, Any]]]) -> None:
        for rel, record in results:
            analysis_record = record if isinstance(record, AnalysisRecord) else AnalysisRecord.from_dict(record)
            self.cache.set(self.root / rel, analysis_record.to_dict())
            self.files[rel] = self._meta_to_model(analysis_record)
        self.cache.save()

    def _post_process(self) -> None:
        self._build_graph()
        self._enrich_graph_metrics()
        self._compute_v8_metrics()
        self._apply_arch_rules()
        self._finalize_scores()
        self._generate_contexts()

    # ── File collection ───────────────────────────────────────────────────────

    def _resolve_scan_roots(self, ignore_dirs: frozenset[str]) -> list[Path]:
        """Return the directories that should actually be walked.

        Priority
        --------
        1. ``<root>/src`` exists  →  scan **only** that directory; all other
           top-level siblings are ignored.
        2. No ``<root>/src``  →  look one level deeper: any immediate
           sub-directory of *root* that contains a ``src/`` child is a
           candidate; collect all their ``src/`` paths and scan those.
        3. Neither found  →  fall back to scanning *root* as-is.
        """
        src_at_root = self.root / "src"
        if src_at_root.is_dir():
            log.info("src/ found at root — restricting analysis to %s", src_at_root)
            return [src_at_root]

        nested: list[Path] = []
        try:
            for child in sorted(self.root.iterdir()):
                if not child.is_dir() or child.name in ignore_dirs:
                    continue
                candidate = child / "src"
                if candidate.is_dir():
                    nested.append(candidate)
        except PermissionError:
            pass

        if nested:
            log.info(
                "No root src/ — scanning %d nested src/ dir(s): %s",
                len(nested),
                [str(s.relative_to(self.root)) for s in nested],
            )
            return nested

        return [self.root]

    def _collect_files(self) -> list[Path]:
        ignore_dirs = _IGNORE_DIRS | self.config.exclude_dirs
        ignore_patterns = _IGNORE_PATTERNS + self.config.exclude_patterns
        gi = GitignoreFilter(self.root)
        special_names = _SPECIAL_TEXT_FILENAMES | self.config.extra_text_filenames
        result: list[Path] = []

        scan_roots = self._resolve_scan_roots(ignore_dirs)

        for scan_root in scan_roots:
            for p in scan_root.rglob("*"):
                if not p.is_file():
                    continue
                if p.name in _GENERATED_FILES:
                    continue
                rel = p.relative_to(self.root)
                parts = rel.parts
                if any(part in ignore_dirs for part in parts[:-1]):
                    continue
                if any(fnmatch.fnmatch(p.name, pat) for pat in ignore_patterns):
                    continue
                if gi.should_ignore(rel):
                    continue
                suffix = p.suffix.lower()
                if suffix not in _TEXT_SUFFIXES and p.name not in special_names:
                    continue
                result.append(p)

        # Include-patterns whitelist: if configured, keep only matching files
        include_pats = self.config.include_patterns
        if include_pats:
            result = [
                p for p in result
                if any(
                    fnmatch.fnmatch(p.relative_to(self.root).as_posix(), pat)
                    for pat in include_pats
                )
            ]

        return result

    # ── File index ────────────────────────────────────────────────────────────

    def _build_file_index(self, paths: list[Path]) -> dict[str, str]:
        idx: dict[str, str] = {}
        for p in paths:
            rel = p.relative_to(self.root).as_posix()
            idx[rel] = rel
            idx[p.name] = rel
            idx[p.stem] = rel
            if len(p.parts) >= 2:
                idx[f"{p.parts[-2]}/{p.stem}"] = rel
                idx[p.parent.as_posix()] = rel
                idx["/".join(p.parts[-2:])] = rel
        return idx

    # ── Parallel analysis ─────────────────────────────────────────────────────

    def _analyse_parallel(
        self,
        paths: list[Path],
        aliases: dict[str, Path],
        bare: set[str],
        max_workers: int,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[tuple[str, AnalysisRecord | dict[str, Any]]]:
        results: list[tuple[str, AnalysisRecord | dict[str, Any]]] = []
        file_index = self._file_index
        total = len(paths)
        done = 0

        def _work(p: Path) -> tuple[str, AnalysisRecord | dict[str, Any]]:
            rel = p.relative_to(self.root).as_posix()
            cached = self.cache.get(p)
            if cached:
                return rel, cached
            resolver = ImportResolver(self.root, file_index, aliases, bare)
            return rel, self._analyse_file(p, resolver)

        # Try sub-interpreters first if available
        if _INTERPRETERS_AVAILABLE and len(paths) > 8:
            try:
                return self._run_subinterpreters(paths, _work)
            except Exception as e:
                log.warning("Sub-interpreter failed: %s, falling back to threads", e)

        # Fallback to ThreadPoolExecutor
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = {ex.submit(_work, p): p for p in paths}
                for fut in as_completed(futures):
                    try:
                        results.append(fut.result())
                    except Exception as exc:
                        log.error("Worker error for %s: %s", futures[fut], exc)
                    done += 1
                    if on_progress:
                        on_progress(done, total)
        except Exception as e:
            log.error("ThreadPool failed: %s, using serial processing", e)
            for p in paths:
                results.append(_work(p))
                done += 1
                if on_progress:
                    on_progress(done, total)

        return results

    def _run_subinterpreters(
        self,
        paths: list[Path],
        work_func: Callable[[Path], tuple[str, AnalysisRecord | dict[str, Any]]],
    ) -> list[tuple[str, AnalysisRecord | dict[str, Any]]]:
        # Sub-interpreters are not wired up yet. Keep behavior predictable by
        # executing the same work function serially instead of failing at runtime.
        return [work_func(p) for p in paths]

    # ── Single-file analysis ──────────────────────────────────────────────────

    def _analyse_file(self, path: Path, resolver: ImportResolver) -> AnalysisRecord:
        try:
            src = safe_read_text(path)
        except Exception as e:
            log.warning("Cannot read %s: %s", path, e)
            return self._empty_meta(path)

        rel = path.relative_to(self.root)
        pr = self._registry.parse(path, src, resolver)

        ftype_cv = classify_type(rel, src, self.config)
        domain_cv, secondary = classify_domain(rel, src, self.config)
        layer = classify_layer(ftype_cv.value, rel, src)
        entry = classify_entrypoint(rel, src)
        crit = classify_criticality(rel, ftype_cv.value, self.config)
        cx_score, cx_label = classify_complexity(pr.lines, pr.functions, pr.classes, pr.internal, src)
        hints_obj = classify_hints(
            rel, src, ftype_cv.value, domain_cv.value,
            pr.functions, pr.classes, pr.external, pr.module_doc
        )

        warnings: list[str] = []
        if self.config.security_enabled:
            try:
                from ai_indexer.utils.security import scan_secrets
                warnings.extend(scan_secrets(path, src))
            except Exception as e:
                log.debug("Secret scan failed for %s: %s", path, e)

        return AnalysisRecord(
            file=rel.as_posix(),
            file_type=ftype_cv,
            domain=domain_cv,
            secondary_domain=secondary,
            layer=layer,
            criticality=crit,
            entrypoint=entry,
            complexity_label=cx_label,
            complexity_score=cx_score,
            capabilities={"functions": pr.functions, "classes": pr.classes, "exports": pr.exports},
            dependencies=pr.external,
            internal_dependencies=pr.internal,
            warnings=warnings,
            is_in_cycle=False,
            docstrings=pr.docstrings,
            type_hints=pr.type_hints,
            chunks=pr.chunks,
            module_doc=pr.module_doc,
            hints=hints_obj,
            refactor_effort=0.0,
            blast_radius=0,
        )

    # ── Model construction ────────────────────────────────────────────────────

    def _meta_to_model(self, m: AnalysisRecord | dict[str, Any]) -> FileMetadata:
        record = m if isinstance(m, AnalysisRecord) else AnalysisRecord.from_dict(m)
        return FileMetadata(
            file=record.file,
            file_type=record.file_type,
            domain=record.domain,
            secondary_domain=record.secondary_domain,
            layer=record.layer,
            criticality=record.criticality,
            entrypoint=record.entrypoint,
            complexity_label=record.complexity_label,
            complexity_score=record.complexity_score,
            priority_score=0,
            priority_breakdown={},
            context="",
            role_hint="",
            capabilities=record.capabilities,
            dependencies=record.dependencies,
            internal_dependencies=record.internal_dependencies,
            warnings=record.warnings,
            is_in_cycle=record.is_in_cycle,
            docstrings=record.docstrings,
            type_hints=record.type_hints,
            chunks=record.chunks,
            module_doc=record.module_doc,
            hints=record.hints,
            refactor_effort=record.refactor_effort,
            blast_radius=record.blast_radius,
        )

    # ── Graph ─────────────────────────────────────────────────────────────────

    def _build_graph(self) -> None:
        self.graph, self.rev = build_graph(self.files, self._file_index)

    def _canonicalize(self, dep: str) -> str | None:
        if dep in self.files:
            return dep
        if dep in self._file_index:
            return self._file_index[dep]
        stem = Path(dep).stem
        if stem in self._file_index:
            return self._file_index[stem]
        return None

    # ── Graph metrics ─────────────────────────────────────────────────────────

    def _enrich_graph_metrics(self) -> None:
        enrich_graph_metrics(self.files, self.graph)

    def _compute_v8_metrics(self) -> None:
        """Compute refactor_effort and blast_radius for every file."""
        compute_v8_metrics(self.files, self.rev)

    # ── Architecture rules ────────────────────────────────────────────────────

    def _apply_arch_rules(self) -> None:
        cycles = self._detect_cycles()
        for node in cycles:
            if node in self.files:
                self.files[node].is_in_cycle = True
                self.files[node].warnings.append("🔁 File is part of a dependency cycle")
        for fd in self.files.values():
            if (fd.fan_in == 0 and not fd.entrypoint
                    and fd.file_type.value not in {"docs", "config", "asset", "template"}):
                fd.warnings.append("📭 Orphan file — no file imports it and it's not an entrypoint")

    def _finalize_scores(self) -> None:
        for fd in self.files.values():
            score, breakdown = self._priority_score(fd)
            fd.priority_score = score
            fd.priority_breakdown = breakdown

    def _generate_contexts(self) -> None:
        for fd in self.files.values():
            if fd.module_doc:
                fd.role_hint = f"{fd.file_type.value} – {fd.module_doc.strip()[:80]}"
            else:
                fd.role_hint = f"{fd.file_type.value} for {fd.domain.value}"

            caps_parts = []
            funcs = fd.capabilities.get("functions")
            if funcs:
                caps_parts.append(f"functions: {', '.join(funcs[:3])}")
            classes = fd.capabilities.get("classes")
            if classes:
                caps_parts.append(f"classes: {', '.join(classes[:2])}")

            cap_str = f" [{'; '.join(caps_parts)}]" if caps_parts else ""
            warn_str = f" [{len(fd.warnings)} warnings]" if fd.warnings else ""

            fd.context = (
                f"{fd.criticality.title()} {fd.file_type.value} for '{fd.domain.value}' domain."
                f"{cap_str}{warn_str} "
                f"Priority: {fd.priority_score}/100. "
                f"Blast radius: {fd.blast_radius} files. "
                f"Refactor effort: {fd.refactor_effort:.1f}."
            )

    # ── Detection helpers ─────────────────────────────────────────────────────

    def _detect_type(self, rel: Path, src: str) -> ConfidenceValue:
        segs = [p.lower() for p in rel.parts]
        stem = rel.stem.lower()
        suffix = rel.suffix.lower()
        exact_name = rel.name

        config = self.config

        # 1. Segment rules (combined)
        combined_segment_rules = config.type_segment_rules + _TYPE_SEGMENT_RULES
        for seg_kw, result, *rest in combined_segment_rules:
            conf = rest[0] if rest else 0.9
            if seg_kw in segs[:-1]:
                return ConfidenceValue(result, conf)

        # 2. Name rules (stem)
        combined_name_rules = config.type_name_rules + [(n, t, 0.75) for n, t in _TYPE_NAME_RULES]
        for name_kw, result, *rest in combined_name_rules:
            conf = rest[0] if rest else 0.75
            if name_kw in stem:
                return ConfidenceValue(result, conf)

        # 3. Suffix rules (user first)
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

        # 4. Exact name rules
        user_exact = config.type_exact_name_rules.get(exact_name)
        if user_exact:
            return ConfidenceValue(user_exact[0], user_exact[1])

        if exact_name in {"Dockerfile", "dockerfile"}:
            return ConfidenceValue("config", 0.9)
        if exact_name in {"Makefile", "Procfile"}:
            return ConfidenceValue("build", 0.85)

        # 5. Entrypoint or module
        if suffix in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py"}:
            if self._is_entrypoint(rel, src):
                return ConfidenceValue("entrypoint", 0.8)
            return ConfidenceValue("module", 0.55)

        return ConfidenceValue("module", 0.5)

    def _detect_domain(self, rel: Path, src: str) -> tuple[ConfidenceValue, str | None]:
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
        for prefix, dom in self.config.domain_overrides.items():
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

    def _detect_layer(self, ftype: str, rel: Path | None, src: str) -> str:
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

    def _is_entrypoint(self, rel: Path, src: str) -> bool:
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

    def _get_criticality(self, rel: Path, ftype: str) -> str:
        for prefix, crit in self.config.criticality_overrides.items():
            if rel.as_posix().startswith(prefix.lstrip("/")):
                return crit
        return _CRITICALITY_MAP.get(ftype, "supporting")

    @staticmethod
    def _complexity(lines: int, funcs: list[str], classes: list[str],
                    internal: list[str], src: str) -> tuple[int, str]:
        score = lines + len(funcs) * 12 + len(classes) * 25 + len(internal) * 8
        score += src.count("\n") // 20
        if score > 1200:
            return score, "extreme"
        if score > 600:
            return score, "high"
        if score > 200:
            return score, "medium"
        return score, "low"

    # ── PageRank ──────────────────────────────────────────────────────────────

    def _compute_pagerank(self, d: float = 0.85, iters: int = 30, tol: float = 1e-6) -> dict[str, float]:
        nodes = list(self.graph.keys())
        n = len(nodes)
        if not n:
            return {}
        out_deg = {node: len(nbs) for node, nbs in self.graph.items()}
        in_map: dict[str, list[str]] = defaultdict(list)
        for src, tgts in self.graph.items():
            for tgt in tgts:
                in_map[tgt].append(src)
        dangling = {node for node in nodes if out_deg[node] == 0}
        pr = {node: 1.0 / n for node in nodes}
        for _ in range(iters):
            total_d = sum(pr[node] for node in dangling)
            new_pr = {}
            for node in nodes:
                score = (1.0 - d) / n + d * (total_d / n)
                for src in in_map.get(node, []):
                    score += d * (pr[src] / max(1, out_deg[src]))
                new_pr[node] = score
            diff = sum(abs(new_pr[v] - pr[v]) for v in nodes)
            pr = new_pr
            if diff < tol:
                break
        total = sum(pr.values()) or 1.0
        return {k: v / total for k, v in pr.items()}

    def _impact_radius(self, node: str, depth: int = 2) -> int:
        visited: set[str] = set()
        q: deque[tuple[str, int]] = deque([(node, 0)])
        count = 0
        while q:
            cur, dist = q.popleft()
            if cur in visited or dist > depth:
                continue
            visited.add(cur)
            if cur != node:
                count += 1
            for nxt in self.graph.get(cur, []):
                if nxt not in visited:
                    q.append((nxt, dist + 1))
        return count

    def _detect_cycles(self) -> set[str]:
        index = 0
        stack: list[str] = []
        indices: dict[str, int] = {}
        lowlinks: dict[str, int] = {}
        on_stack: set[str] = set()
        cycle_nodes: set[str] = set()

        def strongconnect(v: str) -> None:
            nonlocal index
            indices[v] = lowlinks[v] = index
            index += 1
            stack.append(v)
            on_stack.add(v)

            for w in self.graph.get(v, []):
                if w not in indices:
                    strongconnect(w)
                    lowlinks[v] = min(lowlinks[v], lowlinks[w])
                elif w in on_stack:
                    lowlinks[v] = min(lowlinks[v], indices[w])

            if lowlinks[v] == indices[v]:
                comp: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack.remove(w)
                    comp.append(w)
                    if w == v:
                        break
                if len(comp) > 1:
                    cycle_nodes.update(comp)

        for node in self.graph:
            if node not in indices:
                strongconnect(node)
        return cycle_nodes

    # ── Priority score ────────────────────────────────────────────────────────

    @staticmethod
    def _priority_score(fd: FileMetadata) -> tuple[int, dict[str, float]]:
        bd: dict[str, float] = {}
        score = 0.0
        crit_map = {"critical": 30, "infra": 20, "config": 10, "supporting": 5}
        bd["criticality"] = float(crit_map.get(fd.criticality, 5))
        score += bd["criticality"]
        comp_map = {"extreme": 20, "high": 15, "medium": 8, "low": 3}
        bd["complexity"] = float(comp_map.get(fd.complexity_label, 3))
        score += bd["complexity"]
        bd["entrypoint"] = 15.0 if fd.entrypoint else 0.0
        score += bd["entrypoint"]
        pr_s = min(20.0, fd.pagerank * 1000.0)
        bd["pagerank"] = pr_s
        score += pr_s
        fi_s = min(10.0, fd.fan_in / 2.0)
        bd["fan_in"] = fi_s
        score += fi_s
        fo_p = min(5.0, max(0.0, fd.fan_out - 15.0))
        bd["fan_out_penalty"] = -fo_p
        score -= fo_p
        layer_b = {"domain": 5, "application": 4, "presentation": 3, "infrastructure": 2}.get(fd.layer, 0)
        bd["layer_bonus"] = float(layer_b)
        score += layer_b
        if fd.is_in_cycle:
            bd["cycle_penalty"] = -10.0
            score -= 10.0
        return max(0, min(100, int(round(score)))), bd

    # ── Hints ─────────────────────────────────────────────────────────────────

    def _extract_hints(
        self, rel: Path, src: str, ftype: str, domain: str,
        funcs: list[str], classes: list[str], deps: list[str], module_doc: str | None,
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

    # ── Empty fallback ────────────────────────────────────────────────────────

    def _empty_meta(self, path: Path) -> AnalysisRecord:
        rel = path.relative_to(self.root).as_posix()
        meta = dict(_EMPTY_META_TEMPLATE)
        meta["file"] = rel
        return AnalysisRecord.from_dict(meta)












