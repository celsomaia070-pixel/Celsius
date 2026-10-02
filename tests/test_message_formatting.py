from core.message_formatting import whatsapp_chunks, whatsapp_text


def test_whatsapp_tables_become_labeled_items_and_links_survive():
    result = whatsapp_text("""# Estoque

| Item | Quantidade | Mínimo |
|------|-----------:|-------:|
| Martelo | 3 | 5 |
| Filtro\\|Azul | 2 | 4 |

**Fonte:** [Consulta](https://example.org/fonte)
""")
    assert "*Estoque*" in result
    assert "• Martelo\n  Quantidade: 3\n  Mínimo: 5" in result
    assert "• Filtro|Azul" in result
    assert "Consulta: https://example.org/fonte" in result
    assert "|------" not in result


def test_code_is_preserved_and_messages_split_at_paragraphs():
    assert "x | y" in whatsapp_text("```python\nx | y\n```")
    text = "\n\n".join("Parágrafo " + str(i) + " " + "a" * 80 for i in range(12))
    chunks = whatsapp_chunks(text, limit=300)
    assert all(len(chunk) <= 300 for chunk in chunks)
    assert "\n\n".join(chunks) == text


def test_relative_download_link_does_not_become_broken_whatsapp_url():
    assert whatsapp_text("[Baixar PDF](/api/v1/reports/id/download)") == "Baixar PDF"
