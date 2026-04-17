# ai-indexer

> Analisa um projeto de software e gera metadados estruturados otimizados para consumo por LLMs.

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Versão](https://img.shields.io/badge/versão-0.0.5-green)](https://github.com/LucasSaud/ai-indexer)
[![Licença](https://img.shields.io/badge/licença-MIT-lightgrey)](LICENSE)

**[English version → README.en.md](README.en.md)**

---
> Estado atual: o fluxo principal de análise está estável; MCP e tour de áudio continuam como integrações de produto que podem evoluir mais rápido que o núcleo.

Documentação técnica complementar: [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)

## O que é

`ai-indexer` é uma ferramenta de linha de comando que varre um diretório de projeto, analisa o código-fonte (Python, TypeScript, JavaScript e mais), constrói um grafo de dependências e gera arquivos de saída compactos prontos para serem colados diretamente em uma janela de contexto de LLM (Claude, GPT-4, Gemini etc.).

O que o indexer produz para cada arquivo:

- **Domínio e tipo** detectados automaticamente (`auth`, `database`, `ui`, `api`, `billing`…)
- **Criticidade** (`critical`, `infra`, `config`, `supporting`)
- **Priority score** baseado em PageRank, fan-in, complexidade e entrypoints
- **Refactor effort** — custo estimado de refatoração (linhas × complexidade × acoplamento)
- **Blast radius** — quantos arquivos seriam impactados por uma mudança (2 hops no grafo)
- **Avisos arquiteturais** — ciclos de dependência, arquivos órfãos, acoplamento excessivo
- **Detecção de segredos** — chaves AWS, tokens GitHub, chaves Stripe, JWTs, senhas hardcoded e mais
- **Funções, classes e exports** extraídos do AST
- **Docstrings e type hints**
- **Contexto git** — histórico de commits, diff stat, frequência de mudanças por arquivo

---
> Estado atual: o fluxo principal de análise está estável; MCP e tour de áudio continuam como integrações de produto que podem evoluir mais rápido que o núcleo.

Documentação técnica complementar: [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)

## Instalação

### Instalação básica (sem dependências opcionais)

```bash
pip install ai-indexer
```

### Instalação completa (recomendada)

Inclui tree-sitter para parsing preciso de TypeScript/JS, tiktoken para contagem de tokens, Jinja2 para templates HTML e PyYAML para suporte a `.indexer.yaml`:

```bash
pip install "ai-indexer[full]"
```

### Instalação para desenvolvimento

```bash
git clone https://github.com/LucasSaud/ai-indexer
cd ai-indexer
pip install -e ".[full,dev]"
```

### Dependências opcionais por funcionalidade

| Funcionalidade | Pacotes necessários |
|---|---|
| Parsing preciso de TS/JS | `tree-sitter tree-sitter-typescript tree-sitter-javascript` |
| Contagem de tokens precisa | `tiktoken` |
| Templates HTML (Jinja2) | `jinja2` |
| Arquivo de config `.indexer.yaml` | `pyyaml` |
| Tour de áudio (TTS offline) | `pyttsx3 pydub` |
| Mixagem de música de fundo | `pydub` + `ffmpeg` instalado no sistema |

---
> Estado atual: o fluxo principal de análise está estável; MCP e tour de áudio continuam como integrações de produto que podem evoluir mais rápido que o núcleo.

Documentação técnica complementar: [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)

## Início Rápido

```bash
# Indexar o diretório atual e gerar todos os formatos de saída
ai-indexer

# Indexar um projeto específico
ai-indexer ~/projects/meu-app

# Gerar apenas o XML (melhor para colar no Claude)
ai-indexer --format xml ~/projects/meu-app

# Gerar apenas o TOON (mais eficiente em tokens)
ai-indexer --format toon --output context.toon ~/projects/meu-app
```

---
> Estado atual: o fluxo principal de análise está estável; MCP e tour de áudio continuam como integrações de produto que podem evoluir mais rápido que o núcleo.

Documentação técnica complementar: [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)

## Uso

```
ai-indexer [PROJECT_DIR] [opções]
```

Se `PROJECT_DIR` não for informado, usa o diretório atual. Se o projeto tiver uma pasta `src/` na raiz, a análise é automaticamente restrita a ela.

### Argumentos

#### Posicional

| Argumento | Descrição |
|---|---|
| `PROJECT_DIR` | Diretório raiz do projeto a analisar. Padrão: diretório atual. |

#### Output

| Flag | Padrão | Descrição |
|---|---|---|
| `--format, -f` | `all` | Formato de saída: `toon`, `json`, `md`, `html`, `xml` ou `all` |
| `--output, -o FILE` | — | Sobrescreve o caminho do arquivo de saída (apenas para um único `--format`) |

#### Enriquecimento de conteúdo

| Flag | Descrição |
|---|---|
| `--instruction-file FILE` | Arquivo de texto/Markdown cujo conteúdo é injetado como `instruction` em todas as saídas. No XML vira o primeiro elemento `<instruction>`, que o Claude lê como diretriz de contexto. |

#### Controle de análise

| Flag | Descrição |
|---|---|
| `--no-cache` | Ignora o cache incremental e reanalisá todos os arquivos do zero |
| `--no-security` | Desativa o escâner de segredos/credenciais |

#### Integrações

| Flag | Descrição |
|---|---|
| `--mcp` | Após indexar, inicia um servidor MCP JSON-RPC 2.0 no stdio para plugins de IDE e agentes de IA |

#### Tour de Áudio

| Flag | Padrão | Descrição |
|---|---|---|
| `--audio` | — | Gera um tour narrado do codebase usando TTS offline do sistema |
| `--audio-rate WPM` | `160` | Velocidade da fala em palavras por minuto |
| `--bg-music FILE` | — | Arquivo de música de fundo (MP3/WAV) misturado sob a narração |

#### Miscelânea

| Flag | Descrição |
|---|---|
| `--verbose, -v` | Habilita logging de nível DEBUG no stderr |
| `--version` | Exibe a versão e sai |
| `--help, -h` | Exibe o help completo e sai |

---
> Estado atual: o fluxo principal de análise está estável; MCP e tour de áudio continuam como integrações de produto que podem evoluir mais rápido que o núcleo.

Documentação técnica complementar: [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)

## Formatos de Saída

### `toon` — Formato TOON (mais eficiente em tokens)

Formato compacto proprietário com layout colunar `@rows`. Reduz ~40–60% dos tokens em comparação com o JSON equivalente. Ideal para colar diretamente em uma janela de contexto de LLM.

```
ai-indexer --format toon --output context.toon .
```

### `json` — JSON Completo

JSON minificado com todos os metadados: grafo de dependências, PageRank, métricas v8, docstrings, type hints, chunks de código e muito mais.

```
ai-indexer --format json .
```

### `html` — Dashboard Interativo 3D

Gera um arquivo HTML standalone com um visualizador de nebulosa 3D (Three.js) e um dashboard responsivo (mobile-first). Abre no navegador sem servidor.

- Vista Nebula: grafo de dependências em 3D com controles de órbita, zoom, clique nos nós
- Vista Dashboard: tabela de hotspots, módulos, avisos arquiteturais, estatísticas

```
ai-indexer --format html .
open estrutura_projeto.html
```

### `md` — Markdown

Resumo em Markdown com tabela de hotspots e lista de avisos. Útil para documentação ou PR descriptions.

```
ai-indexer --format md .
```

### `xml` — XML estruturado (recomendado para Claude)

Formato XML estruturado, recomendado pela Anthropic para uso com Claude. As tags tornam a estrutura do documento inequívoca.

```xml
<?xml version='1.0' encoding='utf-8'?>
<ai_index version="0.0.5" project="meu-app" generated_at="...">
  <instruction>Você está analisando um app de e-commerce...</instruction>
  <file_summary total_files="120" critical="8" domains="6" entrypoints="3"/>
  <hotspots>
    <file path="src/core/engine.py" priority="71" criticality="critical" .../>
  </hotspots>
  <files>
    <file path="src/auth/login.py" criticality="critical" domain="auth" ...>
      <capabilities>
        <functions>authenticate, refresh_token, logout</functions>
      </capabilities>
      <warnings>
        <warning>Possible secret detected: Hardcoded password (line 42)</warning>
      </warnings>
    </file>
  </files>
  <git_context>
    <recent_commits>...</recent_commits>
  </git_context>
</ai_index>
```

```
ai-indexer --format xml .
```

---
> Estado atual: o fluxo principal de análise está estável; MCP e tour de áudio continuam como integrações de produto que podem evoluir mais rápido que o núcleo.

Documentação técnica complementar: [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)

## Arquivos Gerados

Todos escritos no diretório do projeto (ou no `output_dir` configurado):

| Arquivo | Descrição |
|---|---|
| `estrutura_projeto.json` | Análise completa em JSON compacto |
| `estrutura_projeto.toon` | Formato TOON eficiente em tokens |
| `estrutura_projeto.html` | Dashboard interativo com nebulosa 3D |
| `estrutura_projeto.md` | Resumo em Markdown |
| `estrutura_projeto.xml` | XML estruturado para LLMs |
| `.aicontext_cache_v8.json` | Cache incremental por arquivo (não commitar) |

---
> Estado atual: o fluxo principal de análise está estável; MCP e tour de áudio continuam como integrações de produto que podem evoluir mais rápido que o núcleo.

Documentação técnica complementar: [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)

## Configuração

Crie um arquivo `.indexer.yaml` na raiz do projeto para sobrescrever os padrões. Todos os campos são opcionais. Requer `pip install pyyaml`.

```yaml
# ── Seleção de arquivos ───────────────────────────────────────────────────────

# Diretórios a ignorar (em qualquer nível da árvore)
exclude_dirs: ["scripts", "legacy", "migrations"]

# Padrões glob de arquivos a ignorar
exclude_patterns: ["*.generated.ts", "*.min.js", "*_pb2.py"]

# Whitelist: se definido, apenas arquivos que correspondam a estes padrões
# serão indexados. Deixar vazio para incluir tudo.
include_patterns:
  - "src/**/*.py"
  - "src/**/*.ts"

# ── Análise ───────────────────────────────────────────────────────────────────

# Profundidade máxima de travessia de diretórios
max_depth: 8

# Número de workers paralelos (0 = automático: cpu_count × 2)
max_workers: 0

# Tokens máximos por chunk de código
chunk_max_tokens: 800

# ── Saída ─────────────────────────────────────────────────────────────────────

# Diretório onde os arquivos de saída são escritos
output_dir: "."

# Formatos padrão quando usando --format all
output_formats: ["toon", "html", "md", "xml"]

# ── Overrides manuais ─────────────────────────────────────────────────────────

# Forçar criticidade de arquivos específicos
criticality_overrides:
  "src/core/engine.py": "critical"
  "src/auth/middleware.py": "critical"

# Forçar domínio de arquivos ou pastas
domain_overrides:
  "src/legacy/": "backend"
  "src/old_api.py": "api"

# ── Instrução injetada em todos os outputs ────────────────────────────────────

# Equivalente a --instruction-file na CLI
instruction_file: "AGENTS.md"

# ── Segurança ─────────────────────────────────────────────────────────────────

security:
  enabled: true   # false para desativar a detecção de segredos

# ── Contexto Git (desativado por padrão) ─────────────────────────────────────

git:
  include_logs: true       # incluir log de commits recentes
  logs_count: 10           # número de commits a incluir
  include_diffs: false     # incluir diff stat do HEAD
  sort_by_changes: false   # coletar frequência de mudanças por arquivo
  sort_max_commits: 100    # quantos commits analisar para frequência
```

---
> Estado atual: o fluxo principal de análise está estável; MCP e tour de áudio continuam como integrações de produto que podem evoluir mais rápido que o núcleo.

Documentação técnica complementar: [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)

## Métricas Explicadas

### Priority Score

Score de 0–100 que combina:
- **PageRank** no grafo de dependências (arquivos muito importados valem mais)
- **Fan-in** (quantos arquivos dependem deste)
- **Complexidade ciclomática** estimada
- **Criticidade** (bônus para `critical` e `infra`)
- **Entrypoint** (bônus para arquivos que são pontos de entrada)

### Refactor Effort

Custo estimado de refatoração em "unidades de esforço". Combina:
- Linhas de código
- Número de funções e classes
- Acoplamento de saída (fan-out)
- Complexidade do código

Útil para priorizar dívida técnica: arquivos com alto `refactor_effort` E alta `criticality` são os mais arriscados.

### Blast Radius

Quantos arquivos seriam potencialmente impactados por uma mudança neste arquivo, considerando 2 hops no grafo de dependências reverso.

Um blast radius alto não significa que o arquivo é ruim — mas significa que mudanças nele devem ser feitas com cuidado e testadas amplamente.

### Criticidade

| Nível | Descrição |
|---|---|
| `critical` | Núcleo da aplicação, falha aqui quebra tudo |
| `infra` | Infraestrutura: banco de dados, autenticação, cache |
| `config` | Configuração e bootstrapping |
| `supporting` | Utilitários, helpers, arquivos de suporte |

### Fan-in / Fan-out

- **Fan-in**: número de arquivos que importam este arquivo
- **Fan-out**: número de arquivos que este arquivo importa

Alta fan-in = arquivo muito dependido = mudanças são arriscadas.
Alta fan-out = arquivo muito acoplado = difícil de testar isoladamente.

---
> Estado atual: o fluxo principal de análise está estável; MCP e tour de áudio continuam como integrações de produto que podem evoluir mais rápido que o núcleo.

Documentação técnica complementar: [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)

## Detecção de Segredos

O indexer escaneia automaticamente todos os arquivos por padrões de credenciais. Findings aparecem como `warnings` em todos os formatos de saída.

Padrões detectados:
- Chaves de acesso AWS (`AKIA...`)
- Tokens GitHub (`ghp_...`, `github_pat_...`)
- Tokens GitLab (`glpat-...`)
- Headers de chave privada (`-----BEGIN ... PRIVATE KEY-----`)
- Chaves Stripe (`sk_live_...`, `sk_test_...`)
- Tokens Slack (`xox...`)
- JWTs (`eyJ...`)
- URLs de conexão com banco de dados com credenciais embutidas
- Senhas hardcoded (`password = "..."`, `api_key = "..."`)
- Chaves Google API (`AIza...`)
- Chaves SendGrid, Heroku, npm auth tokens

Para desativar:
```bash
ai-indexer --no-security
```
Ou no `.indexer.yaml`:
```yaml
security:
  enabled: false
```

---
> Estado atual: o fluxo principal de análise está estável; MCP e tour de áudio continuam como integrações de produto que podem evoluir mais rápido que o núcleo.

Documentação técnica complementar: [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)

## Injeção de Instrução

Injete um arquivo de texto em todas as saídas como diretriz de contexto para o LLM:

```bash
ai-indexer --instruction-file AGENTS.md --format xml
```

O conteúdo do arquivo aparece:
- Em JSON: chave `"instruction"` no root do objeto
- Em XML: elemento `<instruction>` como primeiro filho de `<ai_index>`
- Em TOON: campo `instruction:` no header

Exemplo de `AGENTS.md`:
```markdown
Você está analisando um e-commerce em Python/FastAPI.
O módulo de pagamentos (src/billing/) é crítico — nunca sugira mudanças
estruturais nele sem análise de impacto completa.
Foque em melhorias de performance no módulo de catálogo (src/catalog/).
```

---
> Estado atual: o fluxo principal de análise está estável; MCP e tour de áudio continuam como integrações de produto que podem evoluir mais rápido que o núcleo.

Documentação técnica complementar: [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)

## Contexto Git

Ative via `.indexer.yaml` para incluir informações do repositório git nas saídas:

```yaml
git:
  include_logs: true
  logs_count: 20
  include_diffs: true
  sort_by_changes: true
  sort_max_commits: 200
```

Isso adiciona ao output:
- `recent_commits`: lista de commits com hash, autor, data e mensagem
- `diff_stat`: stat das mudanças não comitadas (staged + unstaged)
- `change_frequency`: mapa de arquivo → número de commits que o tocaram

Útil para dar ao LLM contexto de "o que mudou recentemente" e "quais arquivos são mais voláteis".

---
> Estado atual: o fluxo principal de análise está estável; MCP e tour de áudio continuam como integrações de produto que podem evoluir mais rápido que o núcleo.

Documentação técnica complementar: [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)

## Servidor MCP

O modo `--mcp` expõe um servidor [Model Context Protocol](https://modelcontextprotocol.io/) JSON-RPC 2.0 via stdio, para integração com IDEs (Cursor, VS Code + Copilot) e agentes de IA.

```bash
ai-indexer --mcp ~/projects/meu-app
```

### Ferramentas disponíveis

| Ferramenta | Parâmetros | Descrição |
|---|---|---|
| `get_file_summary` | `file_path: str` | Retorna metadados completos de um arquivo |
| `get_dependents` | `file_path: str` | Lista arquivos que importam o arquivo dado |
| `search_symbol` | `symbol_name: str` | Encontra arquivos que definem ou exportam um símbolo |
| `list_hotspots` | `n: int = 10` | Top N arquivos por priority score |
| `list_orphans` | — | Arquivos sem importadores que não são entrypoints |
| `list_by_blast_radius` | `n: int = 10` | Top N arquivos por blast radius |
| `list_refactor_candidates` | `n: int = 10` | Top N arquivos por refactor effort |

### Protocolo

Cada requisição é uma linha JSON em stdin:
```json
{"jsonrpc":"2.0","id":1,"method":"list_hotspots","params":{"n":5}}
```

Cada resposta é uma linha JSON em stdout:
```json
{"jsonrpc":"2.0","id":1,"result":[{"file":"src/core/engine.py","priority_score":71,...}]}
```

---
> Estado atual: o fluxo principal de análise está estável; MCP e tour de áudio continuam como integrações de produto que podem evoluir mais rápido que o núcleo.

Documentação técnica complementar: [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)

## Tour de Áudio

Gera um tour narrado do codebase usando a engine de TTS do sistema operacional (completamente offline):

```bash
# Instalar dependências
pip install pyttsx3 pydub

# Gerar tour de áudio
ai-indexer --audio ~/projects/meu-app

# Com velocidade customizada e música de fundo
ai-indexer --audio --audio-rate 140 --bg-music ~/music/ambient.mp3 ~/projects/meu-app
```

O tour narra: visão geral do projeto, domínios detectados, arquivos críticos, hotspots, avisos arquiteturais.

Output: `tour_<nome-do-projeto>.mp3` no diretório de saída.

> Para música de fundo em MP3, `ffmpeg` deve estar instalado no sistema (`brew install ffmpeg` no macOS).

---
> Estado atual: o fluxo principal de análise está estável; MCP e tour de áudio continuam como integrações de produto que podem evoluir mais rápido que o núcleo.

Documentação técnica complementar: [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)

## Cache Incremental

O indexer mantém um cache em `.aicontext_cache_v8.json` na raiz do projeto. A chave é `path:mtime:size` — arquivos não modificados são retornados instantaneamente do cache.

```bash
# Ignorar cache (forçar reanálise completa)
ai-indexer --no-cache
```

Adicione ao `.gitignore`:
```
.aicontext_cache_v8.json
```

---
> Estado atual: o fluxo principal de análise está estável; MCP e tour de áudio continuam como integrações de produto que podem evoluir mais rápido que o núcleo.

Documentação técnica complementar: [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)

## Arquitetura

```
src/ai_indexer/
├── main.py                  # Entrypoint CLI, parser de argumentos, orquestração
├── core/
│   ├── engine.py            # Motor principal: descoberta de arquivos, análise paralela,
│   │                        # grafo de dependências, PageRank, enriquecimento de métricas
│   ├── models.py            # FileMetadata (dataclass com __slots__), ConfidenceValue
│   └── cache.py             # Cache incremental por arquivo (chave: path:mtime:size)
├── parsers/
│   ├── base.py              # ParseResult + BaseParser ABC + ParserRegistry
│   ├── python.py            # Parser Python (tree-sitter ou regex)
│   └── typescript.py        # Parser TS/JS/TSX/JSX (tree-sitter ou regex)
├── exporters/
│   ├── base.py              # BaseExporter ABC
│   ├── toon.py              # Exporter TOON (formato compacto colunar)
│   ├── html.py              # Exporter HTML (dashboard Nebula com Three.js)
│   └── xml_exporter.py      # Exporter XML (recomendado para Claude)
├── mcp/
│   └── server.py            # Servidor MCP JSON-RPC 2.0 via stdio
├── utils/
│   ├── config.py            # Carregador de .indexer.yaml → IndexerConfig
│   ├── io.py                # safe_read_text, count_tokens, ImportResolver,
│   │                        # GitignoreFilter, build_import_resolution_state
│   ├── security.py          # Scanner de segredos e credenciais
│   └── git_context.py       # Coleta de contexto git (logs, diffs, frequência)
├── audio_tours/
│   ├── narrator.py          # LocalNarrator: síntese TTS via pyttsx3
│   ├── script_builder.py    # ScriptBuilder: roteiro com limpeza fonética para TTS
│   └── mixer.py             # Mixagem de narração + música de fundo (pydub/ffmpeg)
└── tours/
    └── generator.py         # TourGenerator: constrói ProjectTour a partir do engine
```

### Fluxo de execução

```
main.py
  └─ AnalysisEngine.run()
       ├─ _resolve_scan_roots()     # src/ preferencial ou root
       ├─ _collect_files()          # filtros + include_patterns
       ├─ _analyse_parallel()       # ThreadPoolExecutor
       │    └─ _analyse_file()      # parser + domain + criticality + security scan
       ├─ _build_graph()            # grafo forward + reverse
       ├─ _compute_pagerank()       # iteração de PageRank
       └─ _enrich_metadata()        # priority_score, refactor_effort, blast_radius
  └─ _build_output()               # monta dict de saída + instrução + git context
  └─ _write_outputs()              # despacha para cada exporter
```

---
> Estado atual: o fluxo principal de análise está estável; MCP e tour de áudio continuam como integrações de produto que podem evoluir mais rápido que o núcleo.

Documentação técnica complementar: [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)

## Suporte a Linguagens

| Linguagem | Extensões | Parser |
|---|---|---|
| Python | `.py` | tree-sitter (fallback: regex) |
| TypeScript | `.ts`, `.tsx` | tree-sitter (fallback: regex) |
| JavaScript | `.js`, `.jsx`, `.mjs`, `.cjs` | tree-sitter (fallback: regex) |
| Outros | `.go`, `.rs`, `.java`, `.rb`, `.php`, `.cs`, `.cpp`, `.c`, `.h`, `.swift`, `.kt`, `.json`, `.yaml`, `.toml`, `.md`, e mais | Análise básica de texto |

---
> Estado atual: o fluxo principal de análise está estável; MCP e tour de áudio continuam como integrações de produto que podem evoluir mais rápido que o núcleo.

Documentação técnica complementar: [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)

## Requisitos

- **Python 3.11+** (testado em 3.11, 3.12, 3.14)
- Dependências obrigatórias: `pydantic>=2.0`, `pathspec>=0.11`
- Dependências opcionais: veja tabela na seção [Instalação](#instalação)

---
> Estado atual: o fluxo principal de análise está estável; MCP e tour de áudio continuam como integrações de produto que podem evoluir mais rápido que o núcleo.

Documentação técnica complementar: [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)

## Versionamento

O projeto segue [SemVer](https://semver.org/):

- `PATCH` — correções de bug, ajustes menores (`0.0.5` → `0.0.6`)
- `MINOR` — novas funcionalidades, novos exporters, novas flags (`0.0.5` → `0.1.0`)
- `MAJOR` — mudanças que quebram compatibilidade no formato de saída ou API pública

```bash
ai-indexer --version
```

---
> Estado atual: o fluxo principal de análise está estável; MCP e tour de áudio continuam como integrações de produto que podem evoluir mais rápido que o núcleo.

Documentação técnica complementar: [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)

## Contribuindo

```bash
# Clonar e instalar em modo desenvolvimento
git clone https://github.com/LucasSaud/ai-indexer
cd ai-indexer
pip install -e ".[full,dev]"

# Rodar testes
pytest

# Lint
ruff check src/

# Type checking
mypy src/
```

---
> Estado atual: o fluxo principal de análise está estável; MCP e tour de áudio continuam como integrações de produto que podem evoluir mais rápido que o núcleo.

Documentação técnica complementar: [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)

## Licença

MIT © Lucas Marinho Saud

