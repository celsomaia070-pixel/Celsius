"""Persist response delivery independently of agent execution and its effects."""

import json
import time

from core.file_security import validate_managed_path
from core.message_formatting import whatsapp_chunks
from core.sqlite_store import connect


class WhatsAppOutbox:
    def __init__(self, path, *, data_root):
        self.path = validate_managed_path(path, data_root=data_root)
        with connect(self.path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS deliveries (
                id TEXT PRIMARY KEY, group_id TEXT NOT NULL, jid TEXT NOT NULL,
                kind TEXT NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL,
                created REAL NOT NULL, error TEXT NOT NULL DEFAULT '')""")
            db.execute("UPDATE deliveries SET state='uncertain' WHERE state='sending'")

    def enqueue(self, message_id, jid, job):
        text = job.get("response") or job.get("error") or "Tarefa interrompida."
        payloads = [("text", {"text": "Celsius\n" + chunk}) for chunk in whatsapp_chunks(text)]
        payloads.extend(
            ("document", {"attachment_id": attachment["id"]})
            for attachment in job.get("attachments", [])
            if attachment.get("id")
        )
        with connect(self.path) as db:
            for index, (kind, payload) in enumerate(payloads):
                db.execute(
                    "INSERT OR IGNORE INTO deliveries VALUES(?,?,?,?,?,'queued',?,'')",
                    (
                        f"{message_id}:{index:05d}",
                        message_id,
                        jid,
                        kind,
                        json.dumps(payload, ensure_ascii=False),
                        time.time(),
                    ),
                )

    def pending(self, self_ids):
        with connect(self.path) as db:
            rows = db.execute(
                "SELECT * FROM deliveries WHERE state='queued' ORDER BY created,id"
            ).fetchall()
        return [dict(row) for row in rows if row["jid"] in self_ids]

    def mark(self, delivery_id, state, error=""):
        with connect(self.path) as db:
            db.execute(
                "UPDATE deliveries SET state=?,error=? WHERE id=?", (state, error, delivery_id)
            )

    def counts(self, self_ids):
        with connect(self.path) as db:
            rows = db.execute(
                "SELECT jid,state,COUNT(*) AS count FROM deliveries GROUP BY jid,state"
            ).fetchall()
        return {
            state: sum(
                row["count"] for row in rows if row["jid"] in self_ids and row["state"] == state
            )
            for state in ("queued", "uncertain", "sending", "sent", "failed")
        }

    def retry_latest(self, jid):
        with connect(self.path) as db:
            latest = db.execute(
                "SELECT group_id FROM deliveries WHERE jid=? ORDER BY created DESC LIMIT 1", (jid,)
            ).fetchone()
            if not latest:
                return False
            return bool(
                db.execute(
                    "UPDATE deliveries SET state='queued',error='' "
                    "WHERE group_id=? AND jid=? AND state IN ('uncertain','failed')",
                    (latest["group_id"], jid),
                ).rowcount
            )
