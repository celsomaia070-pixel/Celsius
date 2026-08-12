# Estrutura dos modulos empresariais

O Celsius usa uma arquitetura modular por empresa. Cada modulo pode ser ativado ou
desativado nas configuracoes, e a sidebar mostra apenas os modulos habilitados para
aquele cliente.

## Principio

Os modulos nao devem assumir que toda empresa usa o mesmo fluxo. O segmento da
empresa serve para sugerir uma configuracao inicial, mas nao bloqueia uso geral.

## Modulos atuais

| Modulo | Papel no Celsius | Base inspirada em ERP/WMS |
| --- | --- | --- |
| Chat / Assistente | Conversa, raciocinio, arquivos e comandos | Atendimento operacional e copiloto local |
| Documentos | Base de conhecimento, origem, tipo e status | GED simples, documentos indexados e revisao |
| Clientes | Cadastro de clientes, pacientes ou empresas | CRM leve com status, responsavel e contato |
| Fornecedores | Cadastro de compras e reposicao | Compras, lead time, condicao comercial e categoria |
| Estoque | Itens, entradas, saidas e reposicao | WMS leve com minimo, maximo, criticidade e movimentacao |
| Produtos e servicos | Catalogo comercial | SKU, unidade, custo, preco, margem e status |
| Orcamentos | Propostas e follow-up comercial | Pipeline de cotacao: rascunho, enviado, aprovado e recusado |
| Financeiro | Lancamentos simples | Contas a pagar/receber, vencimento, status e centro de custo |
| Relatorios | Modelos e rotinas de relatorio | Indicadores por periodo, fonte de dados e periodicidade |
| Agenda | Compromissos, visitas, consultas e lembretes locais | Agenda operacional com status, responsavel, horario e lembrete |
| Processos e prazos | Casos, prazos e proximos passos | Controle sensivel para juridico, saude e servicos |
| Canais e notificacoes | Mensagens, templates e historico de comunicacao | WhatsApp, e-mail e SMS como canais opcionais |
| Configuracoes | Perfil, privacidade, voz, celular e modulos | Administracao local da instalacao |

## Fonte de verdade dos formularios

Os campos dos formularios modulares ficam em `core/module_schema.py`.

Cada schema define:

- campo principal do registro;
- campos exibidos no formulario;
- campos usados no resumo da lista;
- status do fluxo;
- proximas acoes esperadas no futuro.

Essa separacao permite reaproveitar a mesma estrutura no desktop, no acesso pelo
celular, em relatorios e em futuras APIs.

## Canais externos

O modulo de Canais e Notificacoes nasce como uma base segura para WhatsApp, e-mail
e SMS. Ele pode registrar rascunhos, mensagens, destinatarios, consentimento e
status localmente.

Envio real por WhatsApp, e-mail ou SMS deve ser tratado como integracao externa:

- exige internet;
- depende de provedor configurado;
- deve pedir confirmacao antes de enviar;
- deve respeitar consentimento do cliente;
- deve deixar historico local do que foi preparado, enviado ou bloqueado.

O WhatsApp deve seguir o caminho profissional da WhatsApp Business Platform/Cloud
API. Automacao de WhatsApp Web nao deve ser usada como base comercial.

## Agenda e lembretes

A Agenda usa os registros modulares de `agenda`, mas possui uma camada propria em
`core/agenda.py`.

Essa camada permite:

- listar compromissos futuros;
- interpretar datas em formatos comuns, como `31/07/2026 14:30`;
- emitir lembretes locais antes do compromisso;
- marcar lembretes como avisados para nao repetir alerta;
- inserir os proximos compromissos no contexto do LLM.

O LLM tambem recebe ferramentas para consultar e criar compromissos. Assim, quando
o usuario pedir algo como "me lembre amanha as 9h" ou "o que tenho na agenda?",
o Celsius pode agir sobre a agenda local, mantendo os dados no computador.

## Cuidados para areas sensiveis

Advocacia, saude e financeiro devem continuar usando dados locais por padrao. Antes
de implementar fluxos complexos nessas areas, a base deve receber:

- permissao por usuario;
- auditoria de acesso;
- backup local controlado;
- separacao forte por empresa e cliente;
- indicacao clara de qualquer recurso que dependa de internet.
