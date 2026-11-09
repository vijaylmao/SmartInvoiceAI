
import sqlite3

DB_NAME = "smartinvoice.db"


def match_purchase_order(invoice):

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Find the purchase order
    cursor.execute("""
        SELECT
            po.*,
            v.vendor_name,
            v.gstin
        FROM purchase_orders po
        JOIN vendors v
        ON po.vendor_id = v.vendor_id
        WHERE po.po_number = ?
    """, (invoice["po_number"],))

    po = cursor.fetchone()

    if not po:
        conn.close()
        return {
            "status": "REVIEW",
            "reason": "Purchase order not found"
        }

    # Check vendor GSTIN
    if invoice["gstin"] != po["gstin"]:
        conn.close()
        return {
            "status": "REVIEW",
            "reason": "Vendor GSTIN mismatch"
        }

    # Check vendor approval
    cursor.execute("""
        SELECT is_approved
        FROM vendors
        WHERE vendor_id = ?
    """, (po["vendor_id"],))

    vendor = cursor.fetchone()

    if not vendor or vendor["is_approved"] != 1:
        conn.close()
        return {
            "status": "REVIEW",
            "reason": "Vendor is not approved"
        }

    # Compare subtotal with PO subtotal
    invoice_amount = float(invoice["subtotal"])
    po_amount = float(po["subtotal"])

    tolerance = float(po["tolerance_percent"])

    difference = abs(invoice_amount - po_amount)

    allowed_difference = po_amount * tolerance / 100

    conn.close()

    if difference > allowed_difference:
        return {
            "status": "REVIEW",
            "reason": "Invoice amount exceeds PO tolerance"
        }

    return {
        "status": "MATCHED",
        "reason": "Vendor and PO details matched successfully"
    }


# Test with sample invoice
if __name__ == "__main__":

    sample_invoice = {
        "po_number": "PO-2026-0087",
        "gstin": "36AABCA1234F1Z5",
        "subtotal": 95000
    }

    result = match_purchase_order(sample_invoice)

    print("Purchase Order Matching Result")
    print("--------------------------------")
    print("Status:", result["status"])
    print("Reason:", result["reason"])
