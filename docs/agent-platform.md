# Plataforma agêntica local

O Celsius executa tarefas como unidades persistentes e supervisionadas. Cada
`tarefa` tem um objetivo, modo, limites congelados, histórico de passos,
autorizações e uma área de trabalho em `data/agent_workspaces/<id>`.

## Uso

- Envie `TAREFA: <objetivo>` em um modo executor.
- Consulte `TAREFAS`, interrompa com `CANCELAR TAREFA <id>` e continue com
  `RETOMAR <id>`.
- Ações de escrita, exclusão, rede externa ou risco desconhecido sempre param
  para confirmação individual.
- A API expõe tarefas em `/api/v1/agents/tasks`, evidências em
  `/api/v1/agents/tasks/{id}/artifacts` e agendamentos em
  `/api/v1/agents/schedules`.

## Equipe de agentes no modo Work

O modo Work pode selecionar até cinco especialistas. Cada agente recebe um
contexto independente e somente as ferramentas liberadas para seu papel. No
hardware alvo (Ryzen 5 5500, 32 GB e RX 7600 de 8 GB), as inferências são
serializadas para evitar disputa pela VRAM; ao final, um supervisor sem acesso a
ferramentas consolida as contribuições e preserva fontes, divergências e erros.

As execuções ficam em `data/agent_runs.db` e podem ser consultadas em
`/api/v1/agents/runs`. Se uma ferramenta exigir autorização, o checkpoint fica
em `waiting_confirmation`; `AUTORIZAR <codigo>` retoma a mesma execução, mantém
os agentes concluídos e executa somente os restantes.

## Garantias locais

- Uma execução de modelo por vez, evitando disputa de VRAM/RAM no computador.
- Ações interrompidas durante uma ferramenta não são repetidas automaticamente.
- Saídas do workspace são inventariadas com tamanho, extensão e SHA-256.
- JSON produzido é validado; arquivos ausentes ou vazios deixam evidência na
  verificação em vez de uma falsa conclusão.
- Cada uso de ferramenta gera registro local em `data/agent_audit.jsonl`.
- Agendamentos são persistentes e, ao reiniciar o app, voltam a ser verificados.
  Eles avançam antes do despacho para nunca repetir silenciosamente uma tarefa
  que possa escrever dados. Escritas ainda aguardam confirmação humana.
- A fila ocupada libera o agendamento para nova tentativa curta, sem esperar o
  intervalo completo. Despachos registram o último job e a contagem de execuções.
- Tokens persistidos são hashes. Cookies de acesso e renovação são `HttpOnly`,
  a interface não guarda credenciais no `localStorage` e a renovação revoga o
  token de acesso anterior da mesma sessão.
- O diretório de dados e os caches de terceiros recebem permissões privadas e
  ACL herdável no Windows.

## Operação do JEV

Use `scripts/kev-supervisor.ps1 -Action Start` para manter a camada JEV/KEV
local disponível. O supervisor verifica o endpoint e recria o processo caso ele
pare. Nenhum dado é enviado para fora pela supervisão.
