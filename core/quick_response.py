"""Responses about the product itself, before expensive AI preparation."""

from datetime import datetime

from core.message_intent import classify_intent


def quick_response(text: str, *, settings=None, has_attachment: bool = False) -> str | None:
    intent = classify_intent(text, has_attachment=has_attachment)
    if not intent.quick_key:
        return None
    if intent.quick_key == "social":
        return "Olá! Como posso ajudar?"
    if intent.quick_key == "time":
        return f"Hora atual: {datetime.now():%H:%M}"
    if intent.quick_key == "date":
        return f"Data atual: {datetime.now():%d/%m/%Y}"
    if settings is None:
        from core.settings import get_settings

        settings = get_settings()
    if intent.quick_key == "identity":
        return f"Sou o {settings.assistant.name}, {settings.assistant.profile}. Como posso ajudar?"
    return (
        f"Sou o {settings.assistant.name}. Posso responder perguntas, ajudar a analisar e "
        "preencher documentos, consultar o estoque, preparar relatórios, pesquisar na web "
        "e trabalhar com código, usando os recursos habilitados no computador. "
        "Também posso acompanhar tarefas em etapas. Alterações de dados e ações externas "
        "seguem as permissões e confirmações do Celsius. O que você precisa?"
    )
