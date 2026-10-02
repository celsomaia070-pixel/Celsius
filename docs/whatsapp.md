# Celsius no WhatsApp comum

A conexão usa pareamento por QR Code com WhatsApp Web através de Baileys.
É uma integração não oficial: mudanças do WhatsApp podem interromper a conexão
ou exigir novo pareamento. A versão da biblioteca está fixada no arquivo de
dependências. Não há envio em massa nem acesso público para receber comandos.

## Usar

1. Abra o Celsius web e entre na sua conta.
2. Na sidebar, clique em **Conectar WhatsApp** e depois em **Conectar**.
3. No celular, abra WhatsApp → **Dispositivos conectados** → **Conectar um
   dispositivo** e escaneie o QR Code.
4. Aguarde **Conectado**. O Celsius envia uma mensagem inicial na conversa com
   **seu próprio número**, normalmente identificada pelo seu nome e **(Você)**.
   Abra essa conversa e envie seu pedido por texto. Não é criado um contato
   separado chamado Celsius.
5. Caso não encontre a conversa, use **Abrir minha conversa no WhatsApp**.
   **Enviar mensagem inicial** permite reenviar a apresentação para seu próprio
   número. O envio automático acontece uma vez por conta pareada, sem repetir
   a mensagem a cada reconexão.

Exemplos:

- `Celsius, gere um relatório do estoque`
- `Celsius, dê entrada de 10 peças do item X`
- `Mande mensagem para João: o relatório está pronto`
- `Mande mensagem para +5514999999999: o relatório está pronto`

Relatórios e demais tarefas usam os agentes e ferramentas já existentes no
Celsius. Os arquivos produzidos pela tarefa são enviados de volta à conversa.
As mensagens e o andamento também aparecem no computador. O computador deve
permanecer ligado, com internet e com o Celsius em execução.

Saudações e mensagens de conversa chegam ao chat sem o prefixo `TAREFA:`.
Pedidos de trabalho são encaminhados como tarefas, com seleção automática do
modo: estoque, documentos, pesquisador, desenvolvedor ou executor. A integração
envia esse modo explicitamente, sem depender da seleção na tela do computador.
Mensagens de continuação e autorizações preservam a conversa e o modo do trabalho.
As confirmações de alterações e envios continuam obrigatórias.
Autorizações dos agentes
(`AUTORIZAR código`, `RETOMAR código` e `CANCELAR código`) mantêm o escopo da mesma
conversa e podem ser enviados pelo WhatsApp quando solicitados pelo Celsius.

## Controles

- `AJUDA`: exemplos e comandos disponíveis.
- `STATUS`: tarefa WhatsApp em execução.
- `CANCELAR`: solicita interrupção da tarefa WhatsApp atual.
- `NOVA CONVERSA`: inicia outro contexto após a tarefa atual terminar.
- `CONFIRMAR código`: confirma um envio específico para um contato; válido por
  dez minutos e utilizado apenas uma vez.

O nome do contato precisa corresponder a um único contato sincronizado.
Quando isso não for possível, o Celsius solicita o telefone com DDI e DDD.
O nome e o texto aparecem antes da confirmação. Uma falha de entrega não deve
ser interpretada como sucesso; verifique a conversa antes de repetir o envio.

**Pausar conexão** interrompe a comunicação e preserva o pareamento. Conectar
novamente retoma a sessão. Para revogar a autorização pelo celular, remova
o dispositivo Celsius na lista de dispositivos conectados do WhatsApp.

## Privacidade e execução

A conta do Celsius que inicia o pareamento é a proprietária da conexão. Outras
contas não podem ler seu QR nem controlar a sessão. Mensagens de contatos,
grupos, históricos e respostas do próprio agente não são executadas como
comandos. Somente mensagens novas enviadas pelo titular na conversa consigo
mesmo são aceitas. As permissões e confirmações das ferramentas existentes
continuam valendo.

O executor de inferência é compartilhado com o computador: quando estiver
ocupado, os pedidos ficam na fila. Não é carregado um segundo modelo de IA
e a conexão não abre outro navegador. Sessões e a fila ficam em
`data/whatsapp`, com proteção de acesso local quando suportada pelo sistema.
Mensagens repetidas usam o identificador do WhatsApp para evitar tarefas
duplicadas. Uma tarefa em execução durante um encerramento inesperado é
marcada como interrompida; operações de estoque não são repetidas
automaticamente após reiniciar.

Esta primeira integração recebe pedidos por **texto** e envia texto e arquivos
gerados. Áudios e anexos recebidos pelo WhatsApp ainda não são processados.

## Instalação e arquitetura

Requer Node.js 22 ou superior. Execute `scripts/install-whatsapp.ps1` para
instalar as dependências locais. O código do componente está em
`integrations/whatsapp/bridge.mjs`, com dependências fixadas em
`integrations/whatsapp/package-lock.json`.

`core/whatsapp.py` administra o subprocesso, o protocolo JSON-lines, a fila
SQLite e a entrega do resultado. O subprocesso usa conexões de saída ao
WhatsApp; não escuta em uma porta. A API autenticada expõe somente o estado
e as ações conectar, pausar, desvincular e enviar a apresentação para o próprio
número em `/api/v1/whatsapp`. O link da conversa só aparece para a conta
proprietária quando a conexão está pronta. `data/whatsapp/status.json` registra
somente o estado da conexão e o código de desconexão, sem QR, números ou textos.

`tests/test_whatsapp.py` verifica deduplicação, rejeição de contatos e grupos,
isolamento do QR, confirmações de uso único, compartilhamento do executor,
entrega de arquivos registrados e interrupção sem repetição após reinício.
O teste completo de envio e recebimento reais depende do pareamento humano.

Referência da biblioteca: https://github.com/WhiskeySockets/Baileys
