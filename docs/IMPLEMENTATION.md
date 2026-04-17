# Implementação

Este projeto está organizado em camadas:

- `core/discovery.py`: descoberta de arquivos relevantes e índice de lookup.
- `core/classification.py`: heurísticas de tipo, domínio, camada, criticidade e sinais semânticos.
- `core/graph.py`: construção do grafo de dependências e métricas derivadas.
- `core/pipeline.py`: orquestração explícita das etapas de análise.
- `core/engine.py`: coordena a análise e a pós-etapa, sem carregar regras de domínio demais.

## Modelo de dados

O contrato principal de saída é `FileMetadata` em `src/ai_indexer/core/models.py`.
Ele concentra identidade, complexidade, narrativa, dependências, métricas e sinais extras.

Regras práticas:

- Prefira atualizar `FileMetadata` antes de espalhar novos campos em vários dicionários.
- Exporters devem tratar tanto a forma rica quanto a forma compacta.
- Mudanças no schema precisam de teste de regressão.

## Como estender

### Adicionar um parser

1. Implemente `BaseParser` em `src/ai_indexer/parsers/`.
2. Registre a extensão em `ParserRegistry`.
3. Adicione um teste de fixture pequeno cobrindo imports, símbolos e docstrings.

### Adicionar um exporter

1. Consuma o output canônico gerado por `main._build_output()`.
2. Trate campos compactos e ricos de forma consistente.
3. Adicione snapshot ou contract test do formato novo.

### Adicionar uma regra customizada

1. Prefira `IndexerConfig` para overrides de tipo, domínio e criticidade.
2. Coloque heurísticas gerais em `core/classification.py`.
3. Se a regra impactar grafo ou score, cubra com teste de regressão.

## Fixtures e snapshots

- Mantenha fixtures pequenas.
- Use projetos mínimos por idioma.
- Snapshot deve validar somente o que é estável no formato, não timestamps.
- Se o formato compactar campos, teste a normalização no exporter e no consumidor.

## Status funcional

- MCP e tour de áudio existem, mas devem ser tratados como integrações de produto, não como contrato principal da análise.
- O fluxo principal suportado é: analisar projeto, gerar saídas, consultar via MCP e exportar áudio.
