# Melhorias Para Levar o `ai-indexer` Muito Mais Longe

## Objetivo

Este documento consolida tudo o que eu faria para elevar o `ai-indexer` de uma boa base funcional para uma ferramenta realmente robusta, previsível, extensível e confiável para uso real em projetos grandes, pipelines automatizados, IDEs e agentes de IA.

O foco aqui não é só "polir o código". É transformar o projeto em um produto técnico consistente.

---

## Leitura Executiva

Hoje o projeto já tem:

- uma proposta clara
- um fluxo principal funcional
- boa separação inicial entre engine, parsers, exporters e utilitários
- features interessantes como MCP, HTML dashboard, cache incremental e tour de áudio

Mas ainda há gargalos importantes:

- regras demais concentradas no `engine.py`
- inconsistência entre contratos internos e formatos exportados
- ausência de testes automatizados
- problemas de lint e tipagem
- heurísticas fortes demais e pouco validadas
- claims de maturidade acima do estado real do código

Se a meta for deixar o projeto "mil % melhor", eu trataria em 6 frentes:

1. Confiabilidade do core
2. Arquitetura e modularidade
3. Qualidade de engenharia
4. Precisão analítica
5. Produto e experiência de uso
6. Operação, distribuição e roadmap

---

## 1. Confiabilidade do Core

### 1.1 Unificar versionamento do projeto

Hoje há divergência entre:

- `pyproject.toml`
- `src/ai_indexer/__init__.py`
- `src/ai_indexer/core/engine.py`

O ideal é:

- definir a versão em um único ponto de verdade
- fazer CLI, exporters, metadata e outputs consumirem essa mesma origem
- validar isso com teste

Melhoria concreta:

- criar um módulo `version.py`
- importar a versão dele em todo o projeto
- impedir strings de versão hardcoded em outros arquivos

### 1.2 Congelar um contrato de saída

O projeto exporta em `json`, `xml`, `html`, `md` e `toon`, mas hoje há sinais de inconsistência entre:

- formato interno rico
- formato compacto
- campos lidos pelos exporters

O ideal é definir explicitamente:

- schema interno canônico
- schema compacto para LLM
- schema por exporter
- regras de compatibilidade entre versões

Melhoria concreta:

- introduzir modelos tipados para `ProjectAnalysis`, `ProjectStats`, `HotspotRecord`, `FileRecord`
- impedir acesso solto por `dict.get(...)` em exporters
- usar adaptadores claros: `rich -> compact -> exporter view`

### 1.3 Corrigir incompatibilidades entre compactação e exportação

O projeto hoje mistura:

- campos completos como `criticality`
- campos compactos como `c`

Isso abre espaço para bugs silenciosos no HTML e XML.

Melhoria concreta:

- nunca fazer exporter interpretar formato misto
- criar uma camada de normalização por formato
- adicionar snapshots de saída para detectar regressões

### 1.4 Tornar falhas explícitas e auditáveis

Hoje algumas falhas são absorvidas silenciosamente com fallback.

Isso é útil para robustez, mas perigoso para confiança do resultado.

Eu faria:

- separar `warning`, `degraded mode` e `hard error`
- adicionar relatório de execução no output final
- incluir flags como:
  - `tree_sitter_available`
  - `yaml_available`
  - `tiktoken_available`
  - `git_context_enabled`
  - `security_scan_enabled`
  - `analysis_mode: full|degraded`

---

## 2. Arquitetura e Modularidade

### 2.1 Quebrar o `engine.py`

Esse é o principal refactor estrutural.

Hoje o arquivo concentra:

- descoberta de arquivos
- filtros
- construção de índice de caminhos
- parsing
- enriquecimento semântico
- heurísticas de domínio e criticidade
- grafo
- métricas
- regras arquiteturais
- geração de contexto textual

Isso é funcional, mas difícil de manter.

Eu dividiria em módulos como:

- `discovery.py`
- `classification.py`
- `analysis_runner.py`
- `graph_builder.py`
- `scoring.py`
- `architecture_rules.py`
- `context_builder.py`
- `analysis_pipeline.py`

### 2.2 Introduzir pipeline explícito

Hoje o pipeline existe, mas está implícito.

Eu criaria uma estrutura como:

```python
pipeline = AnalysisPipeline(
    discover=FileDiscovery(...),
    parse=ParseStage(...),
    classify=ClassificationStage(...),
    graph=GraphStage(...),
    enrich=MetricsStage(...),
    validate=ArchitectureStage(...),
    present=OutputStage(...),
)
```

Benefícios:

- melhor testabilidade
- melhor extensão
- fácil medir custo por etapa
- fácil habilitar/desabilitar features

### 2.3 Separar heurística de classificação do motor de execução

As regras de:

- tipo
- domínio
- camada
- criticidade
- entrypoint

deveriam virar componentes próprios, por exemplo:

- `TypeClassifier`
- `DomainClassifier`
- `LayerClassifier`
- `CriticalityClassifier`
- `EntrypointDetector`

Isso permite:

- testar cada classificador isoladamente
- injetar regras customizadas
- comparar heurística atual versus futura

### 2.4 Criar sistema de plugins internos

Se o projeto quer crescer, precisa de extension points reais.

Exemplo:

- parsers plugáveis
- scanners plugáveis
- scoring plugável
- detectores arquiteturais plugáveis
- exporters plugáveis

Interface desejável:

- registrar componentes por entrypoint ou registry local
- permitir pacote externo adicionar suporte a linguagem
- permitir regras customizadas por empresa/projeto

---

## 3. Qualidade de Engenharia

### 3.1 Criar suíte de testes de verdade

Hoje esse é o maior gap de maturidade.

Eu criaria 5 camadas de teste:

#### Testes unitários

Para:

- `compute_refactor_effort`
- `compute_blast_radius_2hop`
- `ImportResolver`
- `GitignoreFilter`
- `scan_secrets`
- detectores de tipo, domínio e entrypoint

#### Testes de parser

Fixtures curtas para:

- Python com imports absolutos e relativos
- Python com docstrings e type hints
- TS/JS com import/export/re-export
- TSX/JSX
- arquivos inválidos e parciais

#### Testes de integração do engine

Com projetos de fixture simulando:

- app Python simples
- app TS com alias
- monorepo leve
- projeto híbrido Python + TS
- projeto com ciclos
- projeto com arquivos órfãos

#### Testes de snapshot

Para validar saída estável de:

- JSON
- XML
- TOON
- Markdown
- HTML

#### Testes end-to-end da CLI

Verificando:

- execução padrão
- `--format`
- `--output`
- `--no-cache`
- `--mcp`
- `--audio` quando dependências existirem

### 3.2 Fazer `ruff`, `mypy` e `pytest` passarem sempre

Não basta declarar tooling no README.

Eu colocaria como critério mínimo:

- `ruff check src` verde
- `mypy src` verde
- `pytest` verde

E adicionaria:

- `ruff format`
- cobertura mínima em módulos críticos

### 3.3 Adicionar CI

Pipeline recomendado:

- Windows
- Linux
- macOS

Etapas:

- install
- lint
- type-check
- tests
- package build
- smoke test da CLI

Opcional:

- publicar artefato de preview
- benchmark pequeno

### 3.4 Melhorar tipagem

Hoje há `dict[str, Any]` demais.

Eu faria:

- substituir dicionários soltos por dataclasses ou Pydantic models
- reduzir `Any`
- tipar retorno de exporters
- tipar tours e MCP de ponta a ponta
- remover ignores desnecessários

### 3.5 Criar invariantes explícitas

Exemplos de invariantes úteis:

- todo `file` exportado existe no `files`
- toda aresta do grafo aponta para arquivo conhecido
- `fan_in` e `fan_out` batem com os grafos
- `priority_score` fica em `0..100`
- `criticality` sempre está em enum permitido
- `domain` nunca é vazio

Isso pode virar:

- validação interna pós-análise
- testes
- modo debug

---

## 4. Precisão Analítica

### 4.1 Melhorar resolução de imports

Esse é um ponto central para qualidade do grafo.

Hoje eu melhoraria:

- aliases mais completos de TS
- suporte a `pyproject.toml` e layout Python moderno
- namespace packages
- monorepos com múltiplos roots
- `package.json` workspaces
- `tsconfig` estendido
- reexports e barrels

### 4.2 Melhorar classificação de domínio

A classificação atual é fortemente heurística por palavras-chave.

Isso é útil, mas tende a errar.

Eu faria um classificador em camadas:

1. regras explícitas do usuário
2. convenções de caminho
3. dependências/imports
4. símbolos e docstrings
5. fallback heurístico

Também adicionaria:

- score por evidência
- explicação do motivo da classificação
- suporte a múltiplos domínios mais formal

### 4.3 Melhorar criticidade

Hoje a criticidade parece muito derivada de tipo.

Eu ampliaria com sinais como:

- é entrypoint?
- depende de banco ou auth?
- está em fluxo de pagamento?
- tem alto blast radius?
- é altamente central no grafo?
- contém segredos ou infra crítica?

Ideal:

- criticidade baseada em regra combinada, não só lookup estático

### 4.4 Melhorar cálculo de complexidade

O score atual é simples e útil como proxy, mas ainda raso.

Eu faria:

- complexidade sintática real por parser
- contagem de branching
- profundidade de nesting
- número de responsabilidades por arquivo
- entropia de imports
- tamanho médio de funções

Isso permitiria diferenciar:

- arquivo grande mas simples
- arquivo pequeno mas arquiteturalmente arriscado

### 4.5 Evoluir `priority_score`

Hoje ele combina sinais úteis, mas eu refinaria:

- peso calibrado por dados
- score explicável no output
- possibilidade de presets:
  - `review`
  - `refactor`
  - `incident`
  - `onboarding`

Exemplo:

- em `incident mode`, peso maior para entrypoint e blast radius
- em `refactor mode`, peso maior para complexity e change frequency

### 4.6 Melhorar detecção arquitetural

Eu incluiria regras extras:

- dependência circular por camada
- violação de fronteira arquitetural
- módulo excessivamente centralizador
- barrel file mascarando acoplamento
- “god file”
- diretórios com responsabilidade difusa
- dependência de infra subindo para domínio
- arquivos muito voláteis e centrais

### 4.7 Melhorar secret scanning

Evoluções recomendadas:

- severidade por finding
- confidence por regex
- baseline de findings conhecidos
- allowlist/suppressions
- agrupamento por tipo
- opção de mascarar conteúdo sensível no output
- modo “strict security”

### 4.8 Adicionar análise semântica de documentação

O projeto já extrai docstrings; eu iria além:

- detectar módulos sem documentação
- detectar divergência entre nome e função aparente
- detectar docs desatualizadas
- gerar resumo arquitetural por módulo

---

## 5. Produto e Experiência de Uso

### 5.1 Melhorar UX da CLI

Eu adicionaria:

- `--format summary`
- `--stdout`
- `--quiet`
- `--fail-on-warnings`
- `--fail-on-secrets`
- `--project-name`
- `--config FILE`
- `--include-gitignore false`
- `--explain-score FILE`

### 5.2 Criar perfis de análise

Exemplo:

- `--profile fast`
- `--profile standard`
- `--profile deep`
- `--profile security`
- `--profile llm-context`

Cada perfil ajustaria:

- profundidade
- chunking
- scans
- quantidade de metadados
- custo de processamento

### 5.3 Melhorar o HTML dashboard

O HTML já é uma boa vitrine, mas eu ampliaria bastante:

- filtros por domínio, criticidade e camada
- busca textual
- clique no nó mostrando dependentes e dependências
- destaque de ciclos
- timeline se houver contexto git
- modo comparativo entre execuções
- mapa de calor por diretório
- explicação do score no painel lateral
- export do dashboard em JSON embutido + view state

### 5.4 Melhorar o formato Markdown

Hoje o Markdown é mais um resumo simples.

Eu criaria versões:

- `summary`
- `review`
- `onboarding`
- `refactor-plan`

Exemplo:

- Markdown de onboarding com “por onde começar”
- Markdown de review com hotspots e riscos
- Markdown de refactor com ranking de dívida técnica

### 5.5 Melhorar o XML e TOON para LLMs

Como o produto é muito voltado para IA, eu faria:

- schema mais estável
- menos ambiguidades
- campos de explicação do score
- contexto por diretório/módulo
- output opcional orientado a prompts de review
- compactação sem sacrificar semântica

### 5.6 Melhorar o MCP

Hoje ele é útil, mas ainda básico.

Eu adicionaria:

- paginação
- filtros
- consultas por domínio
- consulta por camada
- consulta por warnings
- obter subgrafo de um arquivo
- explicar score de um arquivo
- listar ciclos
- listar arquivos por volatilidade git
- buscar por diretório/módulo

Também faria:

- schema formal das respostas
- versionamento de protocolo
- testes de contrato MCP

### 5.7 Melhorar o tour de áudio

Hoje é uma feature criativa, mas ainda acessória.

Eu faria:

- corrigir uso de tipos e texto gerado
- permitir idioma
- permitir voz selecionável via CLI
- dividir por sessões
- exportar script puro
- gerar “tour para onboarding” e “tour para review”

---

## 6. Configuração e Personalização

### 6.1 Evoluir `.indexer.yaml`

Sugestões:

- validar schema da config
- mensagens melhores para campos inválidos
- suportar múltiplos perfis
- permitir merge de config local + global
- suportar presets

Exemplo:

```yaml
profiles:
  review:
    output_formats: ["xml", "md"]
    security:
      enabled: true
  fast:
    chunk_max_tokens: 400
    git:
      include_logs: false
```

### 6.2 Permitir regras customizadas de classificação

Muito importante para adoção séria.

Eu permitiria:

- keywords por domínio
- score por diretório
- overrides de criticidade por glob
- disable de detectores específicos
- pesos customizados do score

### 6.3 Permitir múltiplas raízes de scan

Hoje existe lógica de `src/`, mas eu abriria:

- monorepo com vários apps
- workspaces
- backend + frontend em diretórios distintos
- exclusão seletiva por pacote

---

## 7. Performance e Escalabilidade

### 7.1 Benchmarking formal

Eu criaria benchmarks com:

- projeto pequeno
- projeto médio
- monorepo
- codebase com muitos arquivos de texto

Métricas:

- tempo total
- tempo por etapa
- uso de memória
- cache hit rate
- tempo por parser

### 7.2 Melhorar paralelismo

Hoje há tentativa de subinterpreters não concluída.

Eu faria uma escolha clara:

- ou remover o caminho incompleto
- ou implementar de verdade

Antes disso, eu mediria:

- se `ThreadPoolExecutor` já resolve bem
- se há gargalo de CPU ou IO
- se vale migrar parsing pesado para processos

### 7.3 Cache mais inteligente

Melhorias:

- invalidar por versão do parser/config
- separar cache por etapa
- registrar “cache provenance”
- suportar prune de entradas antigas
- estatística de cache no resumo final

### 7.4 Reduzir custo de outputs grandes

Em projetos grandes, eu faria:

- lazy output
- limite configurável de detalhes
- chunks opcionais
- modos `full` e `compact`
- streaming para arquivos grandes

---

## 8. Observabilidade e Debug

### 8.1 Criar modo diagnóstico

Exemplo:

```bash
ai-indexer --diagnostics
```

Saída desejável:

- quais dependências opcionais estão disponíveis
- quais parsers foram usados
- quantos arquivos foram descartados e por quê
- quantos vieram do cache
- quantos falharam no parse
- qualidade estimada da análise

### 8.2 Instrumentar etapas

Eu adicionaria métricas de runtime:

- tempo de descoberta
- tempo de parsing
- tempo de grafo
- tempo de exporters
- tempo por arquivo extremo

### 8.3 Modo explainability

Muito útil para confiança.

Exemplo:

- por que esse arquivo foi classificado como `billing`?
- por que esse score é 83?
- por que esse arquivo é `critical`?

Isso poderia aparecer:

- em JSON
- no dashboard
- via MCP

---

## 9. Distribuição, Documentação e Posicionamento

### 9.1 Ajustar o posicionamento do README

O README está forte em ambição e marketing. Isso é bom até certo ponto.

Mas eu deixaria mais preciso em relação ao estado real:

- o que já está sólido
- o que é heurístico
- o que é experimental
- quais features dependem de libs opcionais

### 9.2 Adicionar documentação técnica interna

Eu criaria docs como:

- arquitetura do pipeline
- modelo de dados
- como adicionar um parser
- como adicionar um exporter
- como calibrar scoring
- como escrever fixtures de teste

### 9.3 Criar changelog de verdade

Com isso:

- releases ficam auditáveis
- schemas podem ser acompanhados
- consumidores de MCP sabem o que mudou

### 9.4 Publicação e confiança

Se a meta for adoção real:

- semantic versioning disciplinado
- tags de release
- pipeline de publish
- smoke test do pacote publicado

---

## 10. Funcionalidades Novas de Alto Impacto

### 10.1 Diff mode

Muito valioso para PR review e agentes.

Exemplo:

```bash
ai-indexer --diff HEAD~1..HEAD
```

Ou:

- comparar dois snapshots
- mostrar impacto arquitetural das mudanças
- destacar hotspots tocados pela alteração

### 10.2 Histórico comparativo

Gerar snapshots e comparar:

- aumento de complexidade
- surgimento de ciclos
- expansão de blast radius
- novos hotspots

### 10.3 Recomendações automáticas

Não só mapear, mas sugerir:

- top 10 alvos de refactor
- riscos de review
- pontos de onboarding
- sequência de leitura recomendada

### 10.4 Modo “AI review pack”

Saída otimizada para uso por agentes:

- instruction
- hotspots
- changed files
- neighboring graph
- warnings
- symbols principais

### 10.5 Modo “team handoff pack”

Saída voltada para humanos:

- visão do sistema
- módulos
- pontos críticos
- riscos
- arquivos prioritários

### 10.6 Suporte a mais linguagens de forma séria

Hoje há parsing forte em Python e TS/JS.

Para crescer com qualidade:

- Go
- Java
- C#
- Rust

Mas só vale se vier com parser e testes decentes.

---

## 11. Roadmap Prioritário

### Fase 1: Consertar a base

- unificar versionamento
- corrigir bugs de exporter
- fazer `ruff` passar
- fazer `mypy` passar
- criar testes unitários e de integração mínimos
- estabilizar contrato interno de dados

### Fase 2: Dar previsibilidade

- snapshots de output
- validações pós-análise
- explainability de score/classificação
- relatórios de fallback/degradação
- CI multi-plataforma

### Fase 3: Modularizar o core

- quebrar `engine.py`
- extrair classificadores
- extrair grafo/scoring
- refatorar exporters para adaptadores tipados

### Fase 4: Melhorar precisão

- import resolution melhor
- classificação de domínio mais confiável
- scoring calibrável
- regras arquiteturais mais ricas

### Fase 5: Melhorar produto

- dashboard mais forte
- MCP mais completo
- profiles de análise
- diff mode
- outputs especializados para agentes

---

## 12. O Que Eu Faria Primeiro, na Prática

Se eu fosse assumir a evolução do projeto agora, eu começaria assim:

### Sprint 1

- corrigir inconsistências de versão
- corrigir exporters HTML/XML
- remover código incompleto ou experimental exposto
- limpar lint e tipagem básica

### Sprint 2

- criar fixtures pequenas de teste
- adicionar testes de parser, engine e exporters
- validar outputs por snapshot

### Sprint 3

- dividir `engine.py`
- formalizar schema do output
- adicionar validações pós-processamento

### Sprint 4

- melhorar import resolution e scoring
- expandir MCP
- adicionar explainability

### Sprint 5

- lançar `diff mode`
- melhorar dashboard
- revisar README e posicionamento do projeto

---

## 13. Estado Desejado do Projeto

Para eu considerar o `ai-indexer` realmente em outro patamar, ele precisaria ter:

- contrato interno estável
- outputs consistentes e testados
- CI verde
- cobertura mínima nos módulos críticos
- engine modular
- heurísticas explicáveis
- performance medida
- recursos experimentais claramente marcados
- documentação técnica boa
- integração MCP confiável

---

## 14. Conclusão

O projeto já tem um bom núcleo e uma visão interessante. O maior risco hoje não é falta de ideia; é excesso de ambição concentrado em poucas partes do código, com pouca blindagem por testes e contratos formais.

O caminho para deixá-lo "mil % melhor" não é sair adicionando feature nova de imediato.

É fazer nesta ordem:

1. estabilizar
2. testar
3. modularizar
4. refinar precisão
5. expandir produto

Se isso for feito com disciplina, o `ai-indexer` pode sair de “ferramenta promissora” para “infra de contexto confiável para IA”.
