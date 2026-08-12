"""Shared commercial workflows for desktop, web and the local assistant."""

from __future__ import annotations

import re
import threading
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from core.business_records import BusinessRecord, BusinessRecordService, get_business_record_service
from core.modules import MODULE_CASES_DEADLINES, MODULE_QUOTES, MODULE_REPORTS
from core.settings import get_settings
from processors.report import GeradorRelatorio


class WorkflowError(ValueError):
    """Raised when a quote, case or report operation is invalid."""


class BusinessWorkflowService:
    def __init__(
        self,
        *,
        settings=None,
        record_service: BusinessRecordService | None = None,
        operations_service=None,
        relationship_service=None,
        event_hub=None,
        reports_dir: Path | None = None,
    ):
        use_global_services = settings is None
        self.settings = settings or get_settings()
        self.record_service = record_service or (
            get_business_record_service()
            if use_global_services
            else BusinessRecordService(settings=self.settings)
        )
        if operations_service is None and use_global_services:
            from core.operations import get_operations_service

            operations_service = get_operations_service()
        if relationship_service is None and use_global_services:
            from core.relationships import get_relationship_service

            relationship_service = get_relationship_service()
        self.operations_service = operations_service
        self.relationship_service = relationship_service
        self.event_hub = event_hub
        self.reports_dir = Path(reports_dir or self.settings.data_dir / "reports").resolve()

    def list_quotes(self, search: str = "") -> list[dict[str, Any]]:
        return [
            self._quote_item(item) for item in self.record_service.search(MODULE_QUOTES, search)
        ]

    def save_quote(self, values: dict[str, Any], quote_id: str = "") -> dict[str, Any]:
        existing = self._record(quote_id, MODULE_QUOTES, "Orcamento") if quote_id else None
        fields = dict(existing.fields) if existing else {}
        fields.update(self._clean(values))
        title = fields.get("titulo", existing.title if existing else "").strip()
        if not title:
            raise WorkflowError("Titulo do orcamento e obrigatorio.")
        number = fields.get("numero", "").strip() or self._next_quote_number()
        self._ensure_unique_quote_number(number, quote_id)
        fields.update(
            {
                "titulo": title,
                "numero": number,
                "status": fields.get("status", "Rascunho") or "Rascunho",
            }
        )
        self._validate_date(fields.get("validade", ""), "Validade")
        self._validate_money(fields.get("valor", ""), "Valor")
        record = self.record_service.save_record(MODULE_QUOTES, title, fields, record_id=quote_id)
        item = self._quote_item(record)
        self._publish("quotes.changed", "updated" if quote_id else "created", item)
        return item

    def delete_quote(self, quote_id: str) -> bool:
        self._record(quote_id, MODULE_QUOTES, "Orcamento")
        deleted = self.record_service.delete(quote_id)
        if deleted:
            self._publish("quotes.changed", "deleted", {"id": quote_id})
        return deleted

    def list_cases(self, search: str = "") -> list[dict[str, Any]]:
        records = self.record_service.search(MODULE_CASES_DEADLINES, search)
        return [self._case_item(item) for item in records]

    def save_case(self, values: dict[str, Any], case_id: str = "") -> dict[str, Any]:
        existing = (
            self._record(case_id, MODULE_CASES_DEADLINES, "Processo ou prazo") if case_id else None
        )
        fields = dict(existing.fields) if existing else {}
        fields.update(self._clean(values))
        title = fields.get("processo", existing.title if existing else "").strip()
        if not title:
            raise WorkflowError("Nome do processo ou caso e obrigatorio.")
        self._validate_date(fields.get("prazo", ""), "Prazo")
        fields.update(
            {
                "processo": title,
                "prioridade": fields.get("prioridade", "Normal") or "Normal",
                "status": fields.get("status", "Novo") or "Novo",
            }
        )
        record = self.record_service.save_record(
            MODULE_CASES_DEADLINES,
            title,
            fields,
            record_id=case_id,
        )
        item = self._case_item(record)
        self._publish("cases.changed", "updated" if case_id else "created", item)
        return item

    def delete_case(self, case_id: str) -> bool:
        self._record(case_id, MODULE_CASES_DEADLINES, "Processo ou prazo")
        deleted = self.record_service.delete(case_id)
        if deleted:
            self._publish("cases.changed", "deleted", {"id": case_id})
        return deleted

    def list_reports(self, search: str = "") -> list[dict[str, Any]]:
        return [
            self._report_item(item) for item in self.record_service.search(MODULE_REPORTS, search)
        ]

    def generate_report(self, values: dict[str, Any]) -> dict[str, Any]:
        title = str(values.get("titulo", "")).strip()
        if not title:
            raise WorkflowError("Titulo do relatorio e obrigatorio.")
        report_type = str(values.get("tipo", "Executivo") or "Executivo").strip()
        source = str(values.get("fonte_dados", report_type) or report_type).strip()
        output_format = str(values.get("formato", "pdf") or "pdf").lower().strip()
        if output_format not in {"pdf", "docx", "md"}:
            raise WorkflowError("Formato de relatorio invalido.")

        content, indicator = self._report_content(source, values.get("observacoes", ""))
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{self._slug(title)}-{stamp}.{output_format}"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        target = (self.reports_dir / filename).resolve()
        metadata = {
            "Tipo": report_type,
            "Fonte": source,
            "Periodo": str(values.get("periodo", "Atual") or "Atual"),
            "Privacidade": "Gerado localmente pelo Celsius",
        }
        if output_format == "pdf":
            GeradorRelatorio.exportar_pdf(title, content, str(target), metadata)
        elif output_format == "docx":
            GeradorRelatorio.exportar_docx(title, content, str(target), metadata)
        else:
            target.write_text(
                GeradorRelatorio.gerar_markdown(title, content, metadata),
                encoding="utf-8",
            )

        fields = self._clean(values)
        fields.update(
            {
                "titulo": title,
                "tipo": report_type,
                "fonte_dados": source,
                "indicador": str(values.get("indicador", "")).strip() or indicator,
                "periodicidade": str(values.get("periodicidade", "Sob demanda")),
                "status": "Gerado",
                "formato": output_format,
                "arquivo": str(target),
            }
        )
        record = self.record_service.save_record(MODULE_REPORTS, title, fields)
        item = self._report_item(record)
        self._publish("reports.changed", "created", item)
        return item

    def delete_report(self, report_id: str) -> bool:
        record = self._record(report_id, MODULE_REPORTS, "Relatorio")
        file_path = Path(record.fields.get("arquivo", "")) if record.fields.get("arquivo") else None
        deleted = self.record_service.delete(report_id)
        if deleted and file_path and self._inside_reports_dir(file_path):
            file_path.unlink(missing_ok=True)
        if deleted:
            self._publish("reports.changed", "deleted", {"id": report_id})
        return deleted

    def report_file(self, report_id: str) -> Path:
        record = self._record(report_id, MODULE_REPORTS, "Relatorio")
        raw_path = record.fields.get("arquivo", "")
        if not raw_path:
            raise WorkflowError("Este relatorio nao possui arquivo gerado.")
        path = Path(raw_path).resolve()
        if not self._inside_reports_dir(path) or not path.is_file():
            raise WorkflowError("Arquivo do relatorio nao encontrado.")
        return path

    def format_quotes(self, search: str = "", limit: int = 50) -> str:
        items = self.list_quotes(search)[: max(1, min(int(limit or 50), 200))]
        if not items:
            return "Nenhum orcamento encontrado na base local."
        lines = [f"Orcamentos locais ({len(items)}):"]
        for item in items:
            lines.append(
                f"- [{item['number']}] {item['title']} | {item['customer'] or 'sem cliente'} | "
                f"{item['value'] or 'sem valor'} | {item['status']}"
            )
        return "\n".join(lines)

    def format_cases(self, search: str = "", limit: int = 50) -> str:
        items = self.list_cases(search)[: max(1, min(int(limit or 50), 200))]
        if not items:
            return "Nenhum processo ou prazo encontrado na base local."
        lines = [f"Processos e prazos locais ({len(items)}):"]
        for item in items:
            alert = " | ATRASADO" if item["overdue"] else ""
            lines.append(
                f"- {item['title']} | prazo: {item['deadline'] or 'nao informado'} | "
                f"{item['priority']} | {item['status']}{alert}"
            )
        return "\n".join(lines)

    def _report_content(self, source: str, notes: Any) -> tuple[str, str]:
        key = source.casefold()
        sections: list[str] = []
        indicator = "Resumo operacional local"
        if "estoque" in key or "execut" in key or "operacional" in key:
            items = self.operations_service.list_inventory() if self.operations_service else []
            units = sum(item["quantity"] for item in items)
            critical = [item for item in items if item["needs_restock"]]
            sections.extend(
                [
                    "## Estoque",
                    f"- Itens cadastrados: {len(items)}",
                    f"- Unidades registradas: {units}",
                    f"- Itens que exigem reposicao: {len(critical)}",
                ]
            )
            sections.extend(
                f"- {item['name']}: {item['quantity']} unidades ({item['health']})"
                for item in items[:20]
            )
            indicator = f"{len(critical)} itens em reposicao"
        if "cliente" in key or "execut" in key:
            customers = (
                self.relationship_service.list_customers() if self.relationship_service else []
            )
            sections.extend(["", "## Clientes", f"- Clientes cadastrados: {len(customers)}"])
            sections.extend(f"- {item['name']}: {item['status']}" for item in customers[:20])
        if "fornecedor" in key or "execut" in key:
            suppliers = (
                self.relationship_service.list_suppliers() if self.relationship_service else []
            )
            sections.extend(
                ["", "## Fornecedores", f"- Fornecedores cadastrados: {len(suppliers)}"]
            )
            sections.extend(f"- {item['name']}: {item['status']}" for item in suppliers[:20])
        if "venda" in key or "orcamento" in key or "execut" in key:
            quotes = self.list_quotes()
            approved = [item for item in quotes if item["status"] == "Aprovado"]
            total = sum((Decimal(str(item["value_number"])) for item in approved), Decimal("0"))
            sections.extend(
                [
                    "",
                    "## Orcamentos",
                    f"- Propostas cadastradas: {len(quotes)}",
                    f"- Propostas aprovadas: {len(approved)}",
                    f"- Valor aprovado: R$ {total:,.2f}",
                ]
            )
            indicator = f"R$ {total:,.2f} aprovados"
        if "process" in key or "prazo" in key or "execut" in key:
            cases = self.list_cases()
            overdue = [item for item in cases if item["overdue"]]
            sections.extend(
                [
                    "",
                    "## Processos e prazos",
                    f"- Registros acompanhados: {len(cases)}",
                    f"- Prazos vencidos: {len(overdue)}",
                ]
            )
        if not sections:
            sections = ["## Resumo", "Nenhuma fonte operacional compativel foi selecionada."]
        notes_text = str(notes or "").strip()
        if notes_text:
            sections.extend(["", "## Observacoes", notes_text])
        return "\n".join(sections), indicator

    def _next_quote_number(self) -> str:
        prefix = f"ORC-{date.today().year}-"
        used = []
        for item in self.list_quotes():
            number = item["number"]
            if number.startswith(prefix) and number[len(prefix) :].isdigit():
                used.append(int(number[len(prefix) :]))
        return f"{prefix}{max(used, default=0) + 1:04d}"

    def _ensure_unique_quote_number(self, number: str, current_id: str) -> None:
        normalized = number.casefold()
        for item in self.list_quotes():
            if item["number"].casefold() == normalized and item["id"] != current_id:
                raise WorkflowError("Ja existe um orcamento com este numero.")

    def _record(self, record_id: str, module_id: str, label: str) -> BusinessRecord:
        record = self.record_service.get(record_id)
        if record is None or record.module_id != module_id:
            raise WorkflowError(f"{label} nao encontrado.")
        return record

    @classmethod
    def _quote_item(cls, record: BusinessRecord) -> dict[str, Any]:
        fields = record.fields
        value = cls._money(fields.get("valor", ""))
        valid_until = fields.get("validade", "")
        expired = bool(
            valid_until
            and cls._date(valid_until)
            and cls._date(valid_until) < date.today()
            and fields.get("status", "Rascunho") not in {"Aprovado", "Recusado", "Expirado"}
        )
        return {
            "id": record.id,
            "number": fields.get("numero", ""),
            "title": record.title,
            "customer": fields.get("cliente", ""),
            "valid_until": valid_until,
            "value": fields.get("valor", ""),
            "value_number": float(value),
            "margin": fields.get("margem", ""),
            "responsible": fields.get("responsavel", ""),
            "status": fields.get("status", "Rascunho"),
            "items": fields.get("itens", ""),
            "notes": fields.get("observacoes", ""),
            "expired": expired,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }

    @classmethod
    def _case_item(cls, record: BusinessRecord) -> dict[str, Any]:
        fields = record.fields
        deadline = fields.get("prazo", "")
        parsed = cls._date(deadline)
        open_case = fields.get("status", "Novo") not in {"Concluido", "Arquivado"}
        days_remaining = (parsed - date.today()).days if parsed else None
        return {
            "id": record.id,
            "title": record.title,
            "customer": fields.get("cliente", ""),
            "type": fields.get("tipo", ""),
            "deadline": deadline,
            "days_remaining": days_remaining,
            "overdue": bool(open_case and days_remaining is not None and days_remaining < 0),
            "due_soon": bool(open_case and days_remaining is not None and 0 <= days_remaining <= 7),
            "priority": fields.get("prioridade", "Normal"),
            "responsible": fields.get("responsavel", ""),
            "status": fields.get("status", "Novo"),
            "next_step": fields.get("proximo_passo", ""),
            "notes": fields.get("observacoes", ""),
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }

    def _report_item(self, record: BusinessRecord) -> dict[str, Any]:
        fields = record.fields
        raw_path = fields.get("arquivo", "")
        path = Path(raw_path).resolve() if raw_path else None
        downloadable = bool(path and self._inside_reports_dir(path) and path.is_file())
        return {
            "id": record.id,
            "title": record.title,
            "type": fields.get("tipo", "Operacional"),
            "period": fields.get("periodo", ""),
            "source": fields.get("fonte_dados", ""),
            "indicator": fields.get("indicador", ""),
            "periodicity": fields.get("periodicidade", "Sob demanda"),
            "responsible": fields.get("responsavel", ""),
            "status": fields.get("status", "Modelo"),
            "format": fields.get("formato", path.suffix.lstrip(".") if path else ""),
            "downloadable": downloadable,
            "download_url": f"/api/v1/reports/{record.id}/download" if downloadable else "",
            "notes": fields.get("observacoes", ""),
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }

    def _inside_reports_dir(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.reports_dir)
            return True
        except ValueError:
            return False

    @staticmethod
    def _clean(values: dict[str, Any]) -> dict[str, str]:
        return {key: str(value or "").strip() for key, value in values.items()}

    @staticmethod
    def _date(value: str) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(value[:10])
        except (TypeError, ValueError):
            return None

    @classmethod
    def _validate_date(cls, value: str, label: str) -> None:
        if value and cls._date(value) is None:
            raise WorkflowError(f"{label} invalido.")

    @classmethod
    def _validate_money(cls, value: str, label: str) -> None:
        if not value:
            return
        try:
            cls._money(value)
        except InvalidOperation as exc:
            raise WorkflowError(f"{label} invalido.") from exc

    @staticmethod
    def _money(value: Any) -> Decimal:
        normalized = str(value or "").replace("R$", "").replace(" ", "")
        if "," in normalized:
            normalized = normalized.replace(".", "").replace(",", ".")
        return Decimal(normalized or "0")

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
        return slug[:80] or "relatorio"

    def _publish(self, event_type: str, action: str, item: dict[str, Any]) -> None:
        if self.event_hub is not None:
            self.event_hub.publish(event_type, {"action": action, "item": item})


_workflow_service: BusinessWorkflowService | None = None
_workflow_lock = threading.Lock()


def get_workflow_service() -> BusinessWorkflowService:
    global _workflow_service
    if _workflow_service is None:
        with _workflow_lock:
            if _workflow_service is None:
                _workflow_service = BusinessWorkflowService()
    return _workflow_service


def reset_workflow_service() -> None:
    global _workflow_service
    _workflow_service = None
