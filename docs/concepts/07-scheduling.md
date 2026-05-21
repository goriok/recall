# Scheduling

**TL;DR** — `recall scheduler run` é um daemon asyncio que lê `[[schedules]]` do TOML, calcula o próximo fire via croniter (UTC), e executa jobs em `asyncio.to_thread`; sem estado persistente entre restarts.

## Intuição

`recall ingest --all` funciona bem manualmente, mas em produção você quer indexação contínua sem intervenção humana. O scheduler resolve isso: um daemon de longa duração que acorda nos momentos certos (cron), executa o job de ingest, e notifica via GChat.

Por que não usar o cron do sistema operacional (`/etc/cron.d`, `crontab -e`)?

- **Visibilidade zero**: cron do SO não tem UI de "qual job está rodando", "quando vai rodar next", sem notificações de falha fáceis de configurar.
- **Frágil em containers**: containers descartáveis perdem o crontab ao reiniciar; montar um volume com crontab é feio.
- **Coupling ao SO**: depende de `crond` estar rodando, de o binário `recall` estar no PATH do cron environment.

Com daemon próprio, o scheduler é parte do binary — configurado no TOML, restartável pelo Docker, com observabilidade via GChat.

## Como o recall faz

**Config** — `src/recall/scheduler/config.py:6-69`:

```python
_KNOWN_JOBS = {
    "confluence:page", "confluence:folder", "confluence:space", "confluence:label",
    "local:all", "local:project", "local:source",
}
_REQUIRED_PARAMS: dict[str, str] = {
    "confluence:page": "page_id",
    "confluence:folder": "folder_id",
    "confluence:space": "space",
    "confluence:label": "label",
    "local:project": "project",
    "local:source": "source",
}
```

Whitelist de job types na inicialização — TOML inválido falha rápido com mensagem clara antes de qualquer job rodar.

**Loop por schedule** — `src/recall/scheduler/worker.py:14-50`:

```python
async def run_schedule_loop(entry, *, callbacks, stop_event):
    while not stop_event.is_set():
        now = datetime.now(tz=timezone.utc)
        nxt = next_fire(entry.cron, now)                # próximo fire via croniter
        delta = (nxt - now).total_seconds()
        await asyncio.sleep(max(0.0, delta))             # dorme até o momento certo
        output = await asyncio.to_thread(dispatch, entry)  # job em thread (IO-bound)
```

Cada `[[schedules]]` entry tem sua própria `asyncio.Task` — schedules independentes não se bloqueiam. O `asyncio.to_thread` evita que o event loop fique bloqueado durante o ingest (que faz múltiplos calls HTTP síncronos ao Ollama e Qdrant).

**Cron UTC** — `src/recall/scheduler/cron.py` usa `croniter(expr, now_utc).get_next(datetime)`. Toda expressão cron é interpretada em UTC. Sem ambiguidade de DST.

**Jobs** — `src/recall/scheduler/jobs.py` despacha para:
- `local:all/project/source` → `commands.ingest._run_local_ingest`
- `confluence:*` → `commands.ingest_confluence.run_confluence_ingest`

**GChat side-effects** — `src/recall/scheduler/gchat.py` envia Cards v2 via POST para `$GCHAT_WEBHOOK_URL` em três momentos: `on_start`, `on_result` (sucesso + duração), `on_error` (nome do erro). Se `GCHAT_WEBHOOK_URL` não estiver definido, GChat é silenciosamente ignorado e o job roda normalmente.

**Sem estado persistente** — não há arquivo de "last run", banco de dados, ou lock file. Ao reiniciar o daemon, o próximo fire de cada schedule é calculado a partir de `datetime.now()` — exatamente como se o daemon acabasse de subir pela primeira vez.

## Por que essa escolha

**No persistence** — simplicidade extrema; zero dependências extras (sem SQLite, Redis, sem arquivo de estado). Tradeoff: se o daemon fica offline entre as 00:00 e 06:00 e o schedule é `0 * * * *`, 6 fires são perdidos. Aceito porque ingest é idempotente ([05-idempotency.md](05-idempotency.md)) — o próximo fire cobre o gap. Se a janela de perda importar (ex: ingest de Confluence crítico a cada hora), a solução é garantir restart automático (Docker `restart: unless-stopped`) em vez de adicionar complexidade ao scheduler.

**Asyncio em vez de threads** — ingest é quase inteiramente IO-bound: chamadas HTTP ao Ollama, Qdrant, Confluence REST. Threads adicionariam overhead de sincronização sem ganho de paralelismo real para IO. Com asyncio, múltiplos schedules coexistem no mesmo thread sem se bloquear.

**`asyncio.to_thread` para dispatch** — `dispatch(entry)` é síncrono (chama código Python síncrono que usa httpx síncrono, etc.). Wrapped em `to_thread` para não bloquear o event loop durante a execução. O número de threads cresce com schedules simultâneos, mas schedules raramente disparam ao mesmo tempo.

**GChat como observabilidade** — Cards v2 com botão, duração e output aparecem no canal de GChat assim que o job termina. Alternativa (Prometheus/Grafana) seria mais completa mas requer infraestrutura adicional. Para um scheduler local, GChat é suficiente e zero config extra (só um webhook URL).

**UTC fixo** — `cron = "0 9 * * *"` significa 09:00 UTC, não "9h no fuso do servidor". Previsível independente de onde o container roda. Tradeoff: quem quer "todo dia às 9h da manhã local" precisa fazer a conta de offset.

## Quando quebra

**Overlap** — schedule `* * * * *` (a cada minuto) com job que leva 90 segundos. A segunda fire começa enquanto a primeira ainda roda. Não há locking ou detecção de sobreposição. Sintoma: dois threads executando o mesmo ingest simultaneamente, dobro de writes no Qdrant (idempotente, mas desperdício de CPU). Workaround: schedules espaçados além da duração esperada do job. Fix real: adicionar `asyncio.Lock` por schedule antes de disparar.

**TOML inválido** — `parse_schedules` lança `ScheduleConfigError` no startup. O daemon não sobe e imprime o erro. Intencionalmente fail-fast: melhor descobrir no deploy do que silenciosamente perder schedules.

**Schedule vazio** — `[[schedules]]` ausente ou vazio. O daemon sobe com "0 job(s)" e fica em idle para sempre. Não é erro — comportamento esperado se o TOML ainda não tem schedules configurados.

**GChat webhook inválido** — o job roda normalmente, mas a notificação falha silenciosamente (exception capturada em `gchat.py`). Output vai apenas para `~/.cache/recall/logs/<schedule>.log`.

## Relacionado

- [05-idempotency.md](05-idempotency.md) — por que perder fires não corrompe o índice
- [docs/runbooks/scheduler-docker.md](../runbooks/scheduler-docker.md) — subir scheduler containerizado
- [docs/runbooks/scheduler-host.md](../runbooks/scheduler-host.md) — rodar daemon no host
- [docs/runbooks/add-schedule.md](../runbooks/add-schedule.md) — adicionar e editar schedules
