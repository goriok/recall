# Runbook 05 — Testar e publicar uma versão

Para quem altera o `recall`: rodar a suíte, validar os manifestos de plugin, subir a versão e atualizar cada host.

```
+------------------------------+
| 1. Preparar o ambiente       |
+------------------------------+
               |
               v
+------------------------------+
| 2. Rodar a suíte             |
+------------------------------+
               |
               v
+------------------------------+
| 3. Testes de integração      |
+------------------------------+
               |
               v
+------------------------------+
| 4. Validar os plugins        |
+------------------------------+
               |
               v
+------------------------------+
| 5. Subir a versão            |
+------------------------------+
               |
               v
+------------------------------+
| 6. Publicar e atualizar      |
+------------------------------+
```

## 1. Preparar o ambiente

```bash
uv sync --group dev
```

O grupo `dev` traz `pytest`, `pytest-cov` e as gramáticas tree-sitter, então a suíte roda contra os parsers reais; use `uv run python -m pytest`, porque o atalho `uv run pytest` não acha o executável.

## 2. Rodar a suíte

```bash
uv run python -m pytest --cov
```

A suíte unitária deixa de fora os testes marcados `integration` e `remote`, e o gate de cobertura é 90%.

## 3. Testes de integração

```bash
podman run -d --rm --name recall-it-qdrant -p 16333:6333 -p 16334:6334 docker.io/qdrant/qdrant:latest
RECALL_TEST_QDRANT_URL=http://localhost:16333 uv run python -m pytest -m integration
RECALL_TEST_QDRANT_URL=http://localhost:16333 RECALL_TEST_QDRANT_GRPC_PORT=16334 uv run python -m pytest -m integration
podman stop recall-it-qdrant
RECALL_TEST_EMBEDDING_URL="https://embeddings.example.com/v1" RECALL_EMBEDDING_API_KEY="<API_KEY>" uv run python -m pytest -m remote
```

O servidor descartável sobe em portas diferentes das do [runbook 04](04-qdrant-server.md) para não colidir com um Qdrant real, e os testes `remote` falam com um endpoint de embeddings de verdade.

## 4. Validar os plugins

```bash
claude plugin validate .
hermes plugins validate .
agy plugin validate ./plugins/recall
```

Os três precisam passar; o aviso do Claude Code sobre o `CLAUDE.md` na raiz é esperado.

## 5. Subir a versão

```bash
sed -i 's/^version = ".*"/version = "X.Y.Z"/' pyproject.toml
sed -i 's/"version": "[0-9.]*"/"version": "X.Y.Z"/' plugin.json .claude-plugin/plugin.json
uv lock
uv run python -m pytest tests/test_plugin_packaging.py
```

`pyproject.toml`, `plugin.json` e `.claude-plugin/plugin.json` precisam ter a mesma versão, e o teste de empacotamento falha se divergirem; o `uv lock` atualiza o `uv.lock`.

## 6. Publicar e atualizar

```bash
git add -A
git commit -m "chore: bump recall to X.Y.Z"
git push origin main
```

O repositório não usa tags; o marketplace e o `uvx` do plugin leem o branch `main`. Depois do push, cada host precisa atualizar:

```bash
uv tool install --reinstall --from "recall[code] @ git+https://github.com/goriok/recall.git" recall
hermes plugins update recall
```

No Claude Code, rode `/plugin marketplace update goriok/recall` e `/reload-plugins`; no agy, `git pull` no clone e `agy plugin install ./recall/plugins/recall` de novo.

## Troubleshooting

| Sintoma | Causa | Ação |
|---|---|---|
| `Failed to spawn: pytest` | o atalho `uv run pytest` não acha o executável | usar `uv run python -m pytest` |
| `Required test coverage of 90.0% not reached` | código novo sem teste | cobrir o código novo; o gate é do repositório inteiro |
| `test_every_plugin_manifest_carries_the_package_version` falha | versão diferente entre os três arquivos | repetir os dois `sed` do passo 5 |
| `uv tool upgrade recall` responde `Nothing to upgrade` | `upgrade` não atualiza ferramentas instaladas de um repositório Git | usar `uv tool install --reinstall --from ...` |
| os testes `integration` pulam sem rodar | `RECALL_TEST_QDRANT_URL` ausente | exportar a variável com o endereço do servidor descartável |
| os testes `remote` pulam sem rodar | `RECALL_TEST_EMBEDDING_URL` ou `RECALL_EMBEDDING_API_KEY` ausentes | exportar as duas variáveis |
| o plugin continua na versão antiga em um host | cache do host | atualizar com o comando do passo 6 daquele host |
