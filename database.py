
import sqlite3
import os

DB_NAME = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "smartinvoice.db"
)


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Approved vendors
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vendors (
            vendor_id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_name TEXT NOT NULL,
            gstin TEXT UNIQUE,
            email TEXT,
            is_approved INTEGER DEFAULT 1
        )
    """)

    # 2. Purchase orders
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS purchase_orders (
            po_id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_number TEXT UNIQUE NOT NULL,
            vendor_id INTEGER,
            subtotal REAL,
            tax_amount REAL,
            total_amount REAL,
            tolerance_percent REAL DEFAULT 2.0,
            status TEXT DEFAULT 'Open',
            FOREIGN KEY (vendor_id) REFERENCES vendors(vendor_id)
        )
    """)

    # 3. Purchase order line items
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS po_items (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_id INTEGER,
            description TEXT,
            quantity REAL,
            unit_price REAL,
            FOREIGN KEY (po_id) REFERENCES purchase_orders(po_id)
        )
    """)

    # 4. Invoice records
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            invoice_id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number TEXT,
            vendor_id INTEGER,
            po_id INTEGER,
            invoice_date TEXT,
            due_date TEXT,
            gstin TEXT,
            subtotal REAL,
            cgst REAL,
            sgst REAL,
            total_amount REAL,
            decision TEXT DEFAULT 'Pending',
            decision_reason TEXT,
            file_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (vendor_id) REFERENCES vendors(vendor_id),
            FOREIGN KEY (po_id) REFERENCES purchase_orders(po_id)
        )
    """)

    # 5. Invoice line items
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS invoice_items (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER,
            description TEXT,
            quantity REAL,
            unit_price REAL,
            amount REAL,
            FOREIGN KEY (invoice_id) REFERENCES invoices(invoice_id)
        )
    """)

    # 6. Processing history
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processing_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER,
            stage TEXT,
            status TEXT,
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (invoice_id) REFERENCES invoices(invoice_id)
        )
    """)

    conn.commit()
    conn.close()

    print("Database and tables created successfully!")


if __name__ == "__main__":
    create_tables()



def insert_invoice(data, vendor_id=None, po_id=None):

    conn = get_connection()
    cursor = conn.cursor()

    def amount(value):
        if value is None or str(value).strip() in ("", "Not found"):
            return None
        return float(str(value).replace(",", "").replace("₹", "").strip())

    cursor.execute("""
        INSERT INTO invoices (
            invoice_number, vendor_id, po_id,
            invoice_date, due_date, gstin,
            subtotal, cgst, sgst, total_amount,
            file_name
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("Invoice Number"),
        vendor_id,
        po_id,
        data.get("Invoice Date"),
        data.get("Due Date"),
        data.get("GSTIN"),
        amount(data.get("Subtotal")),
        amount(data.get("CGST")),
        amount(data.get("SGST")),
        amount(data.get("Total Amount")),
        data.get("File Name")
    ))

    invoice_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return invoice_id


def update_invoice_status(invoice_id, decision, reason):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE invoices
        SET decision = ?, decision_reason = ?
        WHERE invoice_id = ?
    """, (decision, reason, invoice_id))

    conn.commit()
    conn.close()


def log_processing(invoice_id, stage, status, message):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO processing_logs
        (invoice_id, stage, status, message)
        VALUES (?, ?, ?, ?)
    """, (invoice_id, stage, status, message))

    conn.commit()
    conn.close()
