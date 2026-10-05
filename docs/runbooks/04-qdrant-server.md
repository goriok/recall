# Runbook 04 — Qdrant servidor

Trocar o Qdrant embutido por um servidor, para acesso concorrente (CLI e `recall-mcp` ao mesmo tempo) ou para mais de cerca de 20 mil pontos por coleção.

```
+------------------------------+
| 1. Subir o servidor          |
+------------------------------+
               |
               v
+------------------------------+
| 2. Apontar o recall para ele |
+------------------------------+
               |
               v
+------------------------------+
| 3. Reindexar no servidor     |
+------------------------------+
               |
               v
+------------------------------+
| 4. Conferir                  |
+------------------------------+
```

## 1. Subir o servidor

Num clone do repositório, o `docker-compose.yml` sobe um Qdrant local nas portas 6333 (HTTP) e 6334 (gRPC):

```bash
podman compose -f docker-compose.yml up -d
curl -s localhost:6333/healthz
```

Para um servidor já existente, pule este passo; o `recall` só inicia o container sozinho para `localhost` em http.

## 2. Apontar o recall para ele

```bash
cat >> ~/.config/recall/.env <<'EOF'
RECALL_QDRANT_API_KEY=<API_KEY>
EOF
```

```toml
[qdrant]
host = "qdrant.interno.example.com"
port = 6333
prefer_grpc = true
grpc_port = 6334
https = true
api_key_env = "RECALL_QDRANT_API_KEY"
```

O `host` precisa estar declarado no `recall.toml` global, em `[security] trusted_hosts` ou em `RECALL_TRUSTED_HOSTS` se este `recall.toml` for de projeto, e a chave só é lida do `.env` global quando a variável começa com `RECALL_`.

## 3. Reindexar no servidor

```bash
recall ingest --all
```

O índice do store embutido não é copiado para o servidor, então as coleções são criadas de novo; as do store embutido ficam em `~/.local/share/recall/qdrant` até você apagá-las.

## 4. Conferir

```bash
recall collections list
```

A lista deve mostrar as coleções do servidor com a contagem de pontos, e nenhuma delas `recall-meta`, que o comando esconde.

## Troubleshooting

| Sintoma | Causa | Ação |
|---|---|---|
| `Qdrant at ... is not reachable` | servidor parado ou endereço errado, e o host não é `localhost` em http | conferir `host`, `port` e o `curl` do passo 1 |
| `docker-compose.yml not found` | o container local é iniciado a partir de um clone | rodar o passo 1 dentro do clone |
| `Podman not found` | Podman ausente | instalar o Podman ou usar um servidor existente |
| `refusing to talk to untrusted host` | host do Qdrant não declarado no lado global | declarar em `[security] trusted_hosts` ou `RECALL_TRUSTED_HOSTS` |
| `refusing to send $VAR to ... over plain http` | chave com `https = false` em host remoto | `https = true` |
| a chave não chega ao servidor | a variável de `api_key_env` não começa com `RECALL_` e não está no ambiente do processo | renomear para `RECALL_QDRANT_API_KEY` no `.env` global |
| `No results found.` depois de trocar para o servidor | as coleções ainda não existem no servidor | repetir o passo 3 |
