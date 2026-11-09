import sqlite3

# Use the exact same database path as the rest of SmartInvoice AI.
# This prevents duplicate detection from accidentally checking a
# different smartinvoice.db file when Streamlit is launched elsewhere.
from database import DB_NAME


def detect_duplicate(invoice_number, gstin):
    """
    Check whether an invoice with the same invoice number and GSTIN
    already exists in the SmartInvoice AI database.
    """

    invoice_number = str(invoice_number or "").strip()
    gstin = str(gstin or "").strip()

    if (
        not invoice_number
        or not gstin
        or invoice_number.lower() == "not found"
        or gstin.lower() == "not found"
    ):
        return {
            "is_duplicate": False,
            "existing_invoice": None
        }

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT invoice_id, invoice_number, gstin, total_amount
            FROM invoices
            WHERE UPPER(TRIM(invoice_number)) = UPPER(TRIM(?))
              AND UPPER(TRIM(gstin)) = UPPER(TRIM(?))
            ORDER BY invoice_id ASC
            LIMIT 1
            """,
            (invoice_number, gstin)
        )

        record = cursor.fetchone()

        if record:
            return {
                "is_duplicate": True,
                "existing_invoice": dict(record)
            }

        return {
            "is_duplicate": False,
            "existing_invoice": None
        }

    finally:
        conn.close()
