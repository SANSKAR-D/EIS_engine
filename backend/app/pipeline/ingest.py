# backend/app/pipeline/ingest.py
import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from app.pipeline.hygiene import (
    inspect_attachment_hygiene,
    normalize_subject,
    strip_quoted_replies,
)


def parse_timestamp_utc(ts_str: str) -> datetime:
    """Parses ISO timestamp string to a timezone-aware UTC datetime."""
    s = (ts_str or "").strip()
    if not s:
        return datetime.now(timezone.utc)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def parse_email_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parses and normalizes a single CSV row into typed schema format:
    - Normalizes recipients and participants into lowercase email arrays.
    - Strips nested quotes into clean_body while preserving raw_body byte-for-byte.
    - Normalizes subjects and turns empty in_reply_to into None.
    - Parses ISO UTC timestamps.
    """
    email_id = str(row.get("email_id", "")).strip()
    thread_id = str(row.get("thread_id", "")).strip() or None
    raw_in_reply_to = str(row.get("in_reply_to", "")).strip()
    in_reply_to = raw_in_reply_to if raw_in_reply_to else None

    sender = str(row.get("sender", "")).strip().lower()

    # Semicolon or comma-separated recipients
    raw_recipients = str(row.get("recipients", "") or "")
    recipients = [
        r.strip().lower()
        for r in re.split(r"[;,]", raw_recipients)
        if r.strip()
    ]

    # Participants: sender + unique recipients
    seen_participants = set()
    participants = []
    for p in [sender] + recipients:
        if p and p not in seen_participants:
            seen_participants.add(p)
            participants.append(p)

    subject = str(row.get("subject", "")).strip()
    norm_subject = normalize_subject(subject)

    sent_at = parse_timestamp_utc(str(row.get("timestamp", "")))

    raw_body = str(row.get("body", ""))
    clean_body = strip_quoted_replies(raw_body)

    raw_attachments = str(row.get("attachments", "") or "")
    attachments = [
        a.strip()
        for a in re.split(r"[;,]", raw_attachments)
        if a.strip()
    ]

    return {
        "email_id": email_id,
        "raw_thread_id": thread_id,
        "in_reply_to": in_reply_to,
        "sender_email": sender,
        "recipients": recipients,
        "participants": participants,
        "subject": subject,
        "norm_subject": norm_subject,
        "sent_at": sent_at,
        "raw_body": raw_body,
        "clean_body": clean_body,
        "attachment_names": attachments,
    }


def load_emails_csv(
    csv_path: Union[Path, str],
    attachments_dir: Optional[Union[Path, str]] = None,
) -> Dict[str, Any]:
    """
    Synchronously reads and parses emails.csv and applies deterministic hygiene.
    Returns parsed emails and attachment records with noise flags.
    """
    csv_file = Path(csv_path)
    if not csv_file.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    att_dir = Path(attachments_dir) if attachments_dir else csv_file.parent / "attachments"
    seen_hash_counts: Dict[str, int] = {}
    parsed_emails: List[Dict[str, Any]] = []
    attachment_records: List[Dict[str, Any]] = []
    skipped_noise_count = 0

    with open(csv_file, mode="r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            parsed = parse_email_row(row)
            parsed_emails.append(parsed)

            for att_name in parsed["attachment_names"]:
                att_path = att_dir / att_name
                hygiene_res = inspect_attachment_hygiene(att_path, seen_hash_counts)
                if hygiene_res["skip"]:
                    skipped_noise_count += 1

                attachment_records.append({
                    "email_id": parsed["email_id"],
                    "filename": att_name,
                    "file_path": str(att_path),
                    "file_size_bytes": hygiene_res["size"],
                    "sha256_hash": hygiene_res["sha256"],
                    "is_skipped_noise": hygiene_res["skip"],
                    "skip_reason": hygiene_res["reason"],
                })

    return {
        "emails_count": len(parsed_emails),
        "attachments_count": len(attachment_records),
        "skipped_noise_count": skipped_noise_count,
        "parsed_emails": parsed_emails,
        "attachment_records": attachment_records,
    }


async def ingest_csv(
    csv_path: Union[Path, str],
    attachments_dir: Optional[Union[Path, str]] = None,
    pool: Any = None,
) -> Dict[str, Any]:
    """
    Loads emails.csv and associated attachments idempotently.
    Upserts into PostgreSQL when pool is provided.
    """
    result = load_emails_csv(csv_path=csv_path, attachments_dir=attachments_dir)
    parsed_emails = result["parsed_emails"]
    attachment_records = result["attachment_records"]

    if pool is not None:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                email_records = [
                    (
                        e["email_id"],
                        e["raw_thread_id"],
                        e["in_reply_to"],
                        e["sender_email"],
                        e["recipients"],
                        e["participants"],
                        e["subject"],
                        e["norm_subject"],
                        e["sent_at"],
                        e["raw_body"],
                        e["clean_body"],
                    )
                    for e in parsed_emails
                ]
                await cur.executemany(
                    """
                    INSERT INTO emails (
                        email_id, raw_thread_id, in_reply_to, sender_email, recipients,
                        participants, subject, norm_subject, sent_at, raw_body, clean_body
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (email_id) DO UPDATE SET
                        raw_thread_id = EXCLUDED.raw_thread_id,
                        in_reply_to = EXCLUDED.in_reply_to,
                        sender_email = EXCLUDED.sender_email,
                        recipients = EXCLUDED.recipients,
                        participants = EXCLUDED.participants,
                        subject = EXCLUDED.subject,
                        norm_subject = EXCLUDED.norm_subject,
                        sent_at = EXCLUDED.sent_at,
                        raw_body = EXCLUDED.raw_body,
                        clean_body = EXCLUDED.clean_body;
                    """,
                    email_records,
                )

                if attachment_records:
                    att_tuples = [
                        (
                            a["email_id"],
                            a["filename"],
                            a["file_path"],
                            a["file_size_bytes"],
                            a["sha256_hash"],
                            a["is_skipped_noise"],
                            a["skip_reason"],
                        )
                        for a in attachment_records
                    ]
                    await cur.executemany(
                        """
                        INSERT INTO attachments (
                            email_id, filename, file_path, file_size_bytes, sha256_hash,
                            is_skipped_noise, skip_reason
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (email_id, filename) DO UPDATE SET
                            file_path = EXCLUDED.file_path,
                            file_size_bytes = EXCLUDED.file_size_bytes,
                            sha256_hash = EXCLUDED.sha256_hash,
                            is_skipped_noise = EXCLUDED.is_skipped_noise,
                            skip_reason = EXCLUDED.skip_reason;
                        """,
                        att_tuples,
                    )

    return result
