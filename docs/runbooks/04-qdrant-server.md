# Runbook 04 — Qdrant servidor

Trocar o Qdrant embutido por um servidor, para acesso concorrente (CLI e `recall-mcp` ao mesmo tempo) ou para mais de cerca de 20 mil pontos por coleção.

```
+------------------------------+
| 1. Subir o servidor local    |
+------------------------------+
               |
               v
+------------------------------+
| 2. Mantê-lo após reinício    |
+------------------------------+
               |
               v
+------------------------------+
| 3. Apontar o recall para ele |
+------------------------------+
               |
               v
+------------------------------+
| 4. Reindexar no servidor     |
+------------------------------+
               |
               v
+------------------------------+
| 5. Conferir                  |
+------------------------------+
```

## 1. Subir o servidor local

```bash
recall server start
```

Cria o container do Qdrant com o Podman (publicado só em `127.0.0.1`, portas 6333 e 6334), espera ele responder e não faz nada se ele já estiver no ar; para usar um servidor que já existe em outra máquina, pule este passo e o próximo.

## 2. Mantê-lo após reinício

```bash
recall server enable
recall server status
```

Instala um serviço systemd de usuário com reinício automático e liga o lingering, de modo que o Qdrant volta depois de reiniciar o notebook e depois de uma queda do container, sem esperar você abrir uma sessão; `recall server disable` remove o serviço e mantém os dados no volume `recall_qdrant_data`.

## 3. Apontar o recall para ele

```bash
cat >> ~/.config/recall/.env <<'EOF'
RECALL_QDRANT_API_KEY=<API_KEY>
EOF
```

```toml
[qdrant]
host = "localhost"
port = 6333
prefer_grpc = true
grpc_port = 6334
```

Para um servidor local não precisa de chave; para um servidor remoto acrescente `host`, `https = true` e `api_key_env = "RECALL_QDRANT_API_KEY"`, e o host precisa estar declarado no `recall.toml` global, em `[security] trusted_hosts` ou em `RECALL_TRUSTED_HOSTS` quando este `recall.toml` for de projeto; a chave só é lida do `.env` global quando a variável começa com `RECALL_`.

## 4. Reindexar no servidor

```bash
recall ingest --all
```

O índice do store embutido não é copiado para o servidor, então as coleções são criadas de novo; as do store embutido ficam em `~/.local/share/recall/qdrant` até você apagá-las.

## 5. Conferir

```bash
recall collections list
```

A lista deve mostrar as coleções do servidor com a contagem de pontos, e nenhuma delas `recall-meta`, que o comando esconde.

## Troubleshooting

| Sintoma | Causa | Ação |
|---|---|---|
| `Qdrant at ... is not reachable` | o host não é `localhost:6333` em http, então o `recall` não o sobe sozinho | conferir `host` e `port`, ou `recall server start` para o local |
| `port 6333 or 6334 is already in use` | outro processo ou o container antigo `recall_qdrant_1` usa as portas | `podman rm -f recall_qdrant_1` (os dados ficam no volume) ou parar o outro processo |
| `the old compose container 'recall_qdrant_1' holds the ports` | `recall server enable` com o container antigo rodando | `podman rm -f recall_qdrant_1` e repetir o `enable` |
| `podman not found` | Podman ausente | instalar o Podman ou usar um servidor existente |
| `systemctl not found` | `recall server enable` precisa de uma sessão systemd de usuário no Linux | no macOS ou sem systemd, usar `recall server start` a cada sessão |
| depois de `recall server stop` o Qdrant volta sozinho | o serviço continua habilitado e volta no próximo boot ou login | `recall server disable` para desligar de vez |
| `recall server status` mostra `lingering=False` | o serviço só inicia depois do seu login | `loginctl enable-linger $USER` ou repetir `recall server enable` |
| `refusing to talk to untrusted host` | host do Qdrant não declarado no lado global | declarar em `[security] trusted_hosts` ou `RECALL_TRUSTED_HOSTS` |
| `refusing to send $VAR to ... over plain http` | chave com `https = false` em host remoto | `https = true` |
| a chave não chega ao servidor | a variável de `api_key_env` não começa com `RECALL_` e não está no ambiente do processo | renomear para `RECALL_QDRANT_API_KEY` no `.env` global |
| `No results found.` depois de trocar para o servidor | as coleções ainda não existem no servidor | repetir o passo 4 |
