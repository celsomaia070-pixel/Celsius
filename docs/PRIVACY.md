# Privacidade e Protecao de Dados

Este documento descreve a postura tecnica atual do Celsius. Ele nao substitui
avaliacao juridica nem declara conformidade automatica com a LGPD.

## Principios

- Processamento local por padrao para chat, documentos, memoria e dados empresariais.
- Minimizacao: cadastrar apenas informacoes necessarias ao uso contratado.
- Transparencia: recursos que usam internet ou terceiros devem ser identificados na interface.
- Isolamento: cada instalacao usa seu proprio diretorio de dados.
- Controle do titular: dados locais podem ser consultados, corrigidos e excluidos.

## Dados Armazenados Localmente

O Celsius pode armazenar perfil da empresa, conversas, memorias, documentos
indexados, estoque, agenda e registros dos modulos habilitados. Arquivos de
configuracao e bancos locais nao devem ser adicionados ao Git nem incorporados
ao instalador de distribuicao.

## Recursos Externos

O Edge TTS, downloads de modelos, pesquisa web e canais como WhatsApp, e-mail ou
SMS dependem de internet e podem enviar os dados necessarios ao respectivo
provedor. Esses recursos devem permanecer opcionais e claramente sinalizados.

A telemetria OpenTelemetry permanece desligada por padrao. Quando o perfil da
empresa exige operacao local/offline, o Celsius impede sua inicializacao mesmo
que uma variavel de ambiente tente ativa-la. Quando permitida, a telemetria envia
somente metadados operacionais; consultas, argumentos e conteudo nao devem ser
incluidos em spans.

## Responsabilidades da Empresa Usuaria

A empresa controladora deve definir finalidade e base legal, limitar acessos,
atender solicitacoes dos titulares e estabelecer prazos de retencao. Dados de
saude, juridicos, financeiros e outros dados sensiveis exigem avaliacao adicional.

## Controles Antes de Uso em Producao

- Criar usuarios individuais e aplicar permissoes por funcao.
- Manter trilha de auditoria para leitura, alteracao, exportacao e exclusao.
- Criptografar backups e testar restauracao periodicamente.
- Separar rigorosamente dados de empresas e clientes distintos.
- Formalizar politica de retencao, descarte e resposta a incidentes.
- Documentar operadores externos e transferencias de dados aplicaveis.

Os controles de permissao granular e auditoria ainda fazem parte da evolucao do
produto. Ate sua conclusao, instalacoes com dados sensiveis devem ser tratadas
como pilotos controlados, com acesso restrito ao computador e aos backups.
