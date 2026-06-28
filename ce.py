import json
import os
import webbrowser
from datetime import datetime

import numpy as np
import ollama
import streamlit as st
from duckduckgo_search import DDGS
from sentence_transformers import SentenceTransformer


ARQUIVO_MEMORIAS = "memorias.json"

# Carregar modelo de embedding uma unica vez.
modelo_embedding = SentenceTransformer("all-MiniLM-L6-v2")


def carregar_memorias():
    """Carrega as memorias salvas."""
    if os.path.exists(ARQUIVO_MEMORIAS):
        with open(ARQUIVO_MEMORIAS, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def salvar_memorias(memorias):
    """Salva as memorias em arquivo."""
    with open(ARQUIVO_MEMORIAS, "w", encoding="utf-8") as f:
        json.dump(memorias, f, ensure_ascii=False, indent=2)


def buscar_memorias(texto):
    """Busca memorias relevantes usando embedding."""
    try:
        memorias = carregar_memorias()
        if not memorias:
            return []

        embeddings = modelo_embedding.encode([texto] + memorias)
        query_embedding = embeddings[0]
        mem_embeddings = embeddings[1:]

        similarities = np.dot(mem_embeddings, query_embedding) / (
            np.linalg.norm(mem_embeddings, axis=1) * np.linalg.norm(query_embedding)
        )

        top_indices = np.argsort(similarities)[::-1][:3]
        return [memorias[i] for i in top_indices if similarities[i] > 0.3]
    except Exception as e:
        print(f"Erro na busca de memorias: {e}")
        return []


def pesquisar_web(texto):
    """Pesquisa rapidamente na web quando o usuario pedir."""
    try:
        resultados = []
        with DDGS() as ddgs:
            for item in ddgs.text(texto, max_results=3):
                titulo = item.get("title", "")
                resumo = item.get("body", "")
                link = item.get("href", "")
                resultados.append(f"- {titulo}: {resumo} ({link})")
        return "\n".join(resultados)
    except Exception as e:
        print(f"Erro na pesquisa web: {e}")
        return ""


def executar_comando(texto):
    """Executa comandos especificos."""
    texto_lower = texto.lower()

    if "abrir" in texto_lower and "navegador" in texto_lower:
        webbrowser.open("https://www.google.com")
        return "Abrindo navegador..."

    if "hora" in texto_lower:
        return f"A hora atual e: {datetime.now().strftime('%H:%M')}"

    return None


def gerar_resposta(prompt):
    """Gera resposta usando Ollama."""
    try:
        comando = executar_comando(prompt)
        if comando:
            return comando

        memorias_relevantes = buscar_memorias(prompt)
        contexto = (
            "\n".join(memorias_relevantes)
            if memorias_relevantes
            else "Nenhuma informacao de memoria relevante."
        )

        contexto_web = ""
        if any(palavra in prompt.lower() for palavra in ["pesquise", "pesquisar", "procure", "buscar na web"]):
            contexto_web = pesquisar_web(prompt)

        data_atual = datetime.now().strftime("%d/%m/%Y")

        prompt_completo = f"""
Data atual: {data_atual}

Contexto das memorias:
{contexto}

Contexto da web:
{contexto_web if contexto_web else "Nenhuma pesquisa web foi solicitada."}

Mensagem do usuario:
{prompt}

Regras:
- Voce e o CAFÚ, agente local de IA do Vitor.
- Não precisa se apresentar em cada pergunta
- Só se apresente se for perguntado
- Responda como um especialista.
- Use as informacoes de memoria quando relevante.
- Se nao souber responder, diga que nao tem certeza.
- Responda em portugues do Brasil.
- Termine com uma sugestao para continuar a conversa.
"""
        resposta = ollama.chat(
            model="gemma3:1b",
            messages=[
                {
                    "role": "user",
                    "content": prompt_completo,
                }
            ],
        )

        return resposta["message"]["content"]

    except Exception as e:
        return f"Erro ao gerar resposta: {e}"


# ==============================
# Interface Streamlit principal
# ==============================

st.set_page_config(page_title="LUKA'S agente local de IA")
st.title("LUKA'S agente local de IA")

if "mensagens" not in st.session_state:
    st.session_state.mensagens = []

with st.sidebar:
    st.header("Memorias")
    nova_memoria = st.text_area("Adicionar memoria", height=100)

    if st.button("Salvar memoria"):
        if nova_memoria.strip():
            memorias = carregar_memorias()
            memorias.append(nova_memoria.strip())
            salvar_memorias(memorias)
            st.success("Memoria salva com sucesso.")

# ========================
# Exibir mensagens anteriores
# ========================

for mensagem in st.session_state.mensagens:
    with st.chat_message(mensagem["role"]):
        st.write(mensagem["content"])

# ========================
# Entrada do usuario e resposta
# ========================

if prompt := st.chat_input("Digite uma pergunta..."):
    st.session_state.mensagens.append(
        {
            "role": "user",
            "content": prompt,
        }
    )

    with st.chat_message("user"):
        st.write(prompt)

    with st.spinner("Pensando..."):
        resposta = gerar_resposta(prompt)

    st.session_state.mensagens.append(
        {
            "role": "assistant",
            "content": resposta,
        }
    )

    with st.chat_message("assistant"):
        st.write(resposta)
