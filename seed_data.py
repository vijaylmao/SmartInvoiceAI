
import sqlite3

DB_NAME = "smartinvoice.db"


def insert_demo_data():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Insert approved vendor
    cursor.execute("""
        INSERT OR IGNORE INTO vendors
        (vendor_name, gstin, email, is_approved)
        VALUES (?, ?, ?, ?)
    """, (
        "ABC Office Supplies Pvt. Ltd.",
        "36AABCA1234F1Z5",
        "billing@abcofficesupplies.example",
        1
    ))

    cursor.execute("""
        SELECT vendor_id FROM vendors
        WHERE gstin = ?
    """, ("36AABCA1234F1Z5",))

    vendor_id = cursor.fetchone()[0]

    # Insert demo purchase order
    cursor.execute("""
        INSERT OR IGNORE INTO purchase_orders
        (po_number, vendor_id, subtotal, tax_amount,
         total_amount, tolerance_percent, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        "PO-2026-0087",
        vendor_id,
        95000,
        17100,
        112100,
        2.0,
        "Open"
    ))

    cursor.execute("""
        SELECT po_id FROM purchase_orders
        WHERE po_number = ?
    """, ("PO-2026-0087",))

    po_id = cursor.fetchone()[0]

    # Insert demo PO item if it doesn't exist
    cursor.execute("""
        SELECT COUNT(*) FROM po_items
        WHERE po_id = ?
    """, (po_id,))

    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO po_items
            (po_id, description, quantity, unit_price)
            VALUES (?, ?, ?, ?)
        """, (
            po_id,
            "Office Supplies",
            1,
            95000
        ))

    conn.commit()
    conn.close()

    print("Demo vendor and purchase order inserted successfully!")


if __name__ == "__main__":
    insert_demo_data()
