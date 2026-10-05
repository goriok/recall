# Runbook 03 — Embeddings remotos

Ajustar, confiar e trocar o provedor de embeddings; o endereço, o modelo e a chave básicos são gravados no passo 3 do [runbook 01](01-install-plugin-and-first-index.md#3-configurar-embeddings).

```
+------------------------------+
| 1. Ajustar as opções         |
+------------------------------+
               |
               v
+------------------------------+
| 2. Declarar hosts confiáveis |
+------------------------------+
               |
               v
+------------------------------+
| 3. Usar outro provedor       |
|    em uma fonte              |
+------------------------------+
               |
               v
+------------------------------+
| 4. Trocar o provedor de      |
|    uma coleção               |
+------------------------------+
               |
               v
+------------------------------+
| 5. Conferir                  |
+------------------------------+
```

## 1. Ajustar as opções

```bash
cat >> ~/.config/recall/.env <<'EOF'
RECALL_EMBEDDING_PROVIDER=openai
RECALL_EMBEDDING_API_KEY_ENV=RECALL_MINHA_CHAVE
RECALL_EMBEDDING_BATCH_SIZE=16
EOF
```

`RECALL_EMBEDDING_API_KEY_ENV` indica outra variável `RECALL_*` que guarda a chave e `RECALL_EMBEDDING_BATCH_SIZE` aceita no máximo 32; o `recall` lê desse arquivo só variáveis `RECALL_*`, nunca um `.env` do diretório atual.

## 2. Declarar hosts confiáveis

```bash
cat >> ~/.config/recall/.env <<'EOF'
RECALL_TRUSTED_HOSTS=outro-host.example.com,qdrant.interno.example.com
EOF
```

Um `recall.toml` de projeto só pode usar um endereço remoto (embeddings ou Qdrant) que o `.env` global, o `recall.toml` global, `[security] trusted_hosts` ou `RECALL_TRUSTED_HOSTS` já declarem, e só com a variável de chave que o arquivo global associa àquele host; hosts remotos exigem https.

## 3. Usar outro provedor em uma fonte

```toml
[[sources]]
root = "~/sources/goriok/ctx-langs/topics"
[sources.embedding]
provider = "ollama"
model = "nomic-embed-text"
```

A tabela `embedding` de uma fonte, de um repo ou de um projeto sobrescreve o padrão global, o que mantém conteúdo pessoal no Ollama local enquanto o resto usa o endpoint remoto.

## 4. Trocar o provedor de uma coleção

```bash
recall ingest my-backend --recreate
```

Uma coleção fica presa ao modelo que a criou, porque vetores de modelos diferentes não são comparáveis, então trocar o provedor exige refazê-la.

## 5. Conferir

```bash
recall search "retry with backoff" --in code.my-backend --top 3
```

No host, `list_sources` mostra o modelo de cada coleção e avisa `MODEL MISMATCH` quando o modelo configurado difere do usado no índice.

## Troubleshooting

| Sintoma | Causa | Ação |
|---|---|---|
| `embedding endpoint returned HTTP 400` | `batch_size` acima de 32 ou modelo inválido | usar `batch_size <= 32` |
| `embedding endpoint returned HTTP 401` | chave inválida | corrigir `RECALL_EMBEDDING_API_KEY` no `~/.config/recall/.env` |
| `embedding endpoint returned HTTP 404` | nome do modelo errado | corrigir `RECALL_EMBEDDING_MODEL` |
| `environment variable RECALL_EMBEDDING_API_KEY is not set` | chave ausente | gravar a variável no `~/.config/recall/.env` (vale em todos os hosts, inclusive o Hermes, que filtra o ambiente do servidor MCP) |
| `refusing to talk to untrusted host` | `recall.toml` local aponta para um host que o global não declara | declarar o host no `.env` global, no `recall.toml` global, em `[security] trusted_hosts` ou em `RECALL_TRUSTED_HOSTS` |
| `$VAR is not authorized for` | o `recall.toml` local pede, para um host confiável, outra variável de chave que a do arquivo global | usar a variável que o arquivo global associa ao host |
| `refusing to send $VAR to ... over plain http` | endpoint remoto com chave em http | usar https |
| `was indexed with ... re-run 'recall ingest --recreate'` | coleção criada com outro modelo | passo 4 |
| `the selected collections use different embedding models` | busca ampla entre coleções de modelos diferentes | restringir com `--in` ou `project` |
