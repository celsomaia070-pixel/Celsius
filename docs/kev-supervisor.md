# KEV/JEV local supervisionado

O servidor de decisao local pode ser mantido ativo sem depender de uma janela
aberta. O supervisor inicia `kev.serve`, verifica `GET /v1/models` e reinicia o
processo se ele encerrar.

```powershell
.\scripts\kev-supervisor.ps1 -Action Start
.\scripts\kev-supervisor.ps1 -Action Status
.\scripts\kev-supervisor.ps1 -Action Stop
```

Os registros ficam em `logs/kev-supervisor.log`, `logs/kev-server.stdout.log`
e `logs/kev-server.stderr.log`. O supervisor nao cria um servico do Windows nem
uma tarefa agendada: ele permanece local e so e iniciado de forma explicita.
