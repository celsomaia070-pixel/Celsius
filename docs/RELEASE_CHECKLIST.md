# Checklist de Release e Piloto

Use este documento antes de entregar o Celsius a um computador de cliente.
Nenhum resultado deve ser marcado como aprovado apenas porque funciona no
computador de desenvolvimento.

## Portoes Automatizados

Execute:

```powershell
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
python tools\release_preflight.py --flavor thin
installer\build.bat thin exe
```

Para o pacote offline:

```powershell
python tools\release_preflight.py --flavor offline
installer\build.bat offline installer
```

Resultado minimo:

- Ruff sem erros.
- Todos os testes executados sem falhas.
- Apenas skips conhecidos e documentados.
- `self-test.json` com `"ok": true`.
- Nenhum dado real de cliente dentro de `dist/`.

## Testes Manuais Obrigatorios

### Instalacao

- Instalar sem executar como administrador.
- Abrir pelo menu Iniciar e pelo atalho.
- Confirmar criacao de `%LOCALAPPDATA%\Celsius`.
- Atualizar por cima da versao anterior sem perder dados.
- Desinstalar e confirmar que os dados empresariais foram preservados.

### Primeiro Uso e Modulos

- Cadastrar empresa, segmento, porte, descricao e necessidades.
- Revisar modulos sugeridos.
- Ativar e desativar modulos e confirmar atualizacao imediata da sidebar.
- Reiniciar o Celsius e confirmar persistencia do perfil e dos modulos.

### IA Local

- Fazer pergunta curta, pergunta longa e gerar um relatorio.
- Interromper uma resposta e enviar nova pergunta sem travamento.
- Reiniciar o programa e verificar memoria e historico.
- Testar em modo offline depois que os modelos estiverem instalados.

### Documentos e Multimodal

- Ler PDF com texto.
- Ler PDF digitalizado com OCR.
- Ler DOCX, ODT e planilha suportada.
- Analisar PNG e JPG com o modelo visual.
- Gerar PDF/DOCX e abrir o arquivo produzido.

### Gestao Empresarial

- Criar, editar, pesquisar e excluir cliente.
- Criar, editar, pesquisar e excluir fornecedor.
- Movimentar estoque e conferir historico e alertas de reposicao.
- Criar produto/servico, orcamento, lancamento financeiro e processo/prazo.
- Criar compromisso e confirmar alerta sonoro e visual.
- Gerar grafico e KPI com os dados cadastrados.

### Voz e Celular

- Gravar pelo microfone do computador.
- Reproduzir resposta no computador.
- Parear celular por QR Code.
- Enviar texto e voz pelo celular.
- Reproduzir a resposta no computador e no celular.
- Fechar e reabrir o acesso movel sem reiniciar o Celsius.

### Rede e Recursos Externos

- Confirmar aviso de certificado HTTPS local no primeiro pareamento.
- Confirmar que busca web informa quando esta offline.
- Confirmar que Edge TTS informa a necessidade de internet.
- Nao aprovar WhatsApp, e-mail ou SMS ate existir provedor configurado e teste real.

## Matriz Minima de Computadores

Teste pelo menos:

| Perfil | Memoria | GPU | Resultado esperado |
|---|---:|---|---|
| Basico | 16 GB | Sem GPU dedicada | Modelo leve, operacao mais lenta |
| Recomendado | 32 GB | AMD 8 GB | Modelo Qwen VL 7B completo |
| Alternativo | 16/32 GB | NVIDIA | GPU detectada ou fallback seguro |
| Compatibilidade | 16 GB | Intel integrada | Sem travamento, com aviso de desempenho |

Use Windows 10 22H2 e Windows 11 em pelo menos um equipamento cada.

## Funcionalidades Externas

As seguintes areas nao podem ser consideradas aprovadas apenas por testes
unitarios:

- WhatsApp, e-mail e SMS, pois exigem credenciais e servicos externos.
- Edge TTS, pois depende de internet.
- Navegacao com Playwright, pois depende do navegador Chromium instalado.
- Licenciamento comercial, ate que a chave publica real seja incorporada e a
  chave privada esteja armazenada fora do projeto.

## Registro do Piloto

Para cada cliente, registre:

- versao e hash do instalador;
- hardware e versao do Windows;
- sabor `thin` ou `offline`;
- modelo utilizado;
- duracao de instalacao e primeiro carregamento;
- funcionalidades aprovadas e falhas encontradas;
- caminho do log `%LOCALAPPDATA%\Celsius\logs\celsius.log`.
