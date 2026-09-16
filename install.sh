#!/bin/bash
# Celsius AI - Instalacao 1-Clique (Linux/Mac)

set -e

echo "========================================"
echo "  Celsius AI - Instalacao 1-Clique"
echo "========================================"
echo ""

# Verificar se Docker esta instalado
if ! command -v docker &> /dev/null; then
    echo "[ERRO] Docker nao encontrado!"
    echo "Instale o Docker:"
    echo "  Linux: curl -fsSL https://get.docker.com | sh"
    echo "  Mac: brew install --cask docker"
    exit 1
fi

# Verificar se Docker Compose esta disponivel
if ! docker compose version &> /dev/null; then
    echo "[ERRO] Docker Compose nao encontrado!"
    echo "Instale: https://docs.docker.com/compose/install/"
    exit 1
fi

# Criar arquivo .env se nao existir
if [ ! -f .env ]; then
    echo "Criando arquivo .env..."
    cp .env.example .env
    echo "Arquivo .env criado com configuracoes padrao."
fi

echo ""
echo "Iniciando Celsius AI..."
echo "O servidor estara disponivel em: http://localhost:8790"
echo ""

# Build e inicio dos containers
docker compose up -d --build

echo ""
echo "========================================"
echo "  Celsius AI iniciado com sucesso!"
echo "========================================"
echo ""
echo "Acesse: http://localhost:8790"
echo ""
echo "Para ver logs: docker compose logs -f"
echo "Para parar: docker compose down"
echo ""
