@echo off
REM Celsius AI - Instalacao 1-Clique (Windows)
REM Execute como Administrador

echo ========================================
echo   Celsius AI - Instalacao 1-Clique
echo ========================================
echo.

REM Verificar se Docker esta instalado
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Docker nao encontrado!
    echo Baixe e instale o Docker Desktop:
    echo https://www.docker.com/products/docker-desktop/
    echo.
    pause
    exit /b 1
)

REM Verificar se Docker Compose esta disponivel
docker compose version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Docker Compose nao encontrado!
    echo Atualize o Docker Desktop para a versao mais recente.
    pause
    exit /b 1
)

REM Criar arquivo .env se nao existir
if not exist .env (
    echo Criando arquivo .env...
    copy .env.example .env
    echo Arquivo .env criado com configuracoes padrao.
)

echo.
echo Iniciando Celsius AI...
echo O servidor estara disponivel em: http://localhost:8790
echo.

REM Build e inicio dos containers
docker compose up -d --build

if %errorlevel% neq 0 (
    echo.
    echo [ERRO] Falha ao iniciar os containers.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Celsius AI iniciado com sucesso!
echo ========================================
echo.
echo Acesse: http://localhost:8790
echo.
echo Para ver logs: docker compose logs -f
echo Para parar: docker compose down
echo.

pause
