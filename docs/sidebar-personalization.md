# Personalização do menu web

Na sidebar, **Personalizar menu** abre a seleção pessoal de módulos. Cada módulo
possui dois controles independentes:

- **Ativar**: inclui a tela no espaço do usuário.
- **Mostrar**: exibe seu atalho na sidebar, sem alterar a ativação.

As seleções rápidas são **Ensino e pesquisa** (Documentos, Agenda e Relatórios),
**Gestão de negócios** (todas as telas opcionais disponíveis) e **Só o essencial**.
Também é possível ocultar todos os atalhos opcionais, Memórias e a lista de
conversas. Assistente e configurações continuam acessíveis. Desativar ou ocultar
não exclui dados; Cancelar descarta as alterações ainda não salvas.

As preferências são persistidas na conta local e sincronizadas entre interfaces
web conectadas à mesma conta. Contas sem personalização herdam os padrões da
instalação. A seleção pessoal organiza telas e atalhos; não altera permissões de
acesso, ferramentas dos agentes ou configurações compartilhadas da instalação.

## Implementação

`PATCH /api/v1/settings/sidebar` aceita uma lista `enabled`, o mapa
`sidebar_visible` e as opções `show_memories` e `show_conversations`.
Atualizações parciais preservam os campos omitidos. IDs desconhecidos e valores
booleanos inválidos são rejeitados. A API identifica o usuário autenticado;
o cliente não pode selecionar outra conta. Contas com acesso de leitura também
podem personalizar o próprio menu, mantendo as demais restrições.

`GET /api/v1/modules` retorna a seleção efetiva da conta e
`GET /api/v1/navigation` retorna os atalhos visíveis e as preferências do menu.
O evento `sidebar.updated` informa interfaces conectadas à mesma conta para
recarregarem o menu. Os padrões compartilhados continuam em
`settings.modules`; as escolhas individuais ficam em `User.sidebar_preferences`.

## Verificação

`tests/test_sidebar_preferences.py` cobre isolamento entre contas, persistência
após reinício, ocultação sem desativação, atualização parcial, validação,
autenticação e manutenção dos acessos de leitura. A interface foi verificada
em uma instância isolada, incluindo seleção de ensino, ocultação de Relatórios,
salvamento, recarga e exibição em tela estreita.
