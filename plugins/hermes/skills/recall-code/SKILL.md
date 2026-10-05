---
name: recall-code
description: Encontra e navega código-fonte indexado pelo recall (MCP search_code e explain_architecture) e devolve repo, arquivo, intervalo de linhas e símbolo exatos. Use quando a pergunta é "onde está implementado X", "como funciona Y neste repositório" ou "o que muda se eu alterar Z", antes de grep ou leitura manual de vários arquivos.
---

# Navegar código com o recall

Cada resultado de `search_code` aponta para um trecho exato: `repo`, `file_path` (relativo à raiz do repo), `start-end` (linhas, 1-indexadas), `symbol`, e, quando o Graphify estava disponível no ingest, `community`, `god_node` e `related`. O objetivo é abrir só aquelas linhas, não o arquivo inteiro.

## Fluxo

1. Se você não sabe quais repos existem, chame `list_sources` primeiro. Ele mostra cada repo indexado, a data do último ingest e se o modelo de embedding configurado difere do usado no índice.
2. Chame `search_code(query, repo=...)`. Descreva o comportamento ("renova o token quando expira") ou use o identificador; restrinja com `repo` sempre que souber o repo, porque o ranking entre repos não é normalizado.
3. Resolva `file_path` contra o checkout local do repo (o MCP nunca devolve caminho absoluto). Se o checkout não estiver no diretório atual, pergunte ao usuário onde está em vez de adivinhar.
4. Leia o intervalo `start-end` com uma margem pequena. O índice pode estar atrasado: confira se o texto lido bate com o trecho do resultado antes de editar e compare `indexed` do `list_sources` com o último commit do arquivo se houver dúvida.
5. Edite no arquivo real, nunca no texto do resultado.

## Como ler os símbolos

- `Classe.metodo` é um método; em Go o prefixo é o tipo do receiver, em Rust o tipo do `impl`.
- `Cache (impl Store)` é o cabeçalho de um `impl Trait for Tipo` em Rust.
- `Classe.<resto>` são linhas de uma classe fora dos métodos (atributos, constantes).
- `<module>` é código de módulo fora de funções e classes, em trechos contíguos.
- Símbolo vazio com intervalo fixo é uma janela de linhas: linguagem sem suporte a símbolos, só o texto.
- Comentários de documentação, JSDoc e atributos Rust (`#[...]`) fazem parte do chunk do símbolo que descrevem.

## Antes de mexer em algo grande

Chame `explain_architecture(repo)`: ele lista os god nodes (símbolos mais conectados do repo) e o relatório do Graphify. Em um resultado, `god_node: true` e uma lista longa em `related` indicam raio de impacto grande.

`related` é uma amostra limitada de chamadas, heranças e imports declarados, não a lista completa de quem usa o símbolo. Para saber todos os chamadores antes de mudar uma assinatura, confirme com `grep` pelo nome.

## Quando não usar

- Texto exato (mensagem de erro, ID, string literal): `grep` é mais preciso.
- Repo que não aparece no `list_sources`: peça ao usuário para indexá-lo (skill `recall-ingest`) em vez de varrer o disco.
- Documentação em Markdown: use `search_docs` (skill `recall-search`).
- Resultado que fala em "code collection": é o `search_docs` recusando uma coleção de código; use `search_code`.
