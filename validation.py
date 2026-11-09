
import re
from datetime import datetime


def validate_invoice(data):

    errors = []

    # 1. Mandatory field validation
    required_fields = [
        "Vendor Name",
        "Invoice Number",
        "Invoice Date",
        "GSTIN",
        "Subtotal",
        "Total Amount"
    ]

    for field in required_fields:
        value = data.get(field)

        if value is None or str(value).strip() in ["", "Not found"]:
            errors.append(f"Missing {field}")

    # 2. GSTIN validation
    gstin = str(data.get("GSTIN", "")).strip()

    if gstin and gstin != "Not found":
        if not re.fullmatch(
            r"\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9]Z[A-Z0-9]",
            gstin.upper()
        ):
            errors.append("Invalid GSTIN format")

    # 3. Invoice date validation
    invoice_date = str(data.get("Invoice Date", "")).strip()

    if invoice_date and invoice_date != "Not found":
        try:
            date = datetime.strptime(invoice_date, "%d-%b-%Y")

            if date.date() > datetime.today().date():
                errors.append("Invoice date is in the future")

        except ValueError:
            errors.append("Invalid invoice date format")

        # 4. Amount validation
    try:
        subtotal = float(
            str(data.get("Subtotal", "")).replace(",", "").replace("₹", "").strip()
        )

        total = float(
            str(data.get("Total Amount", "")).replace(",", "").replace("₹", "").strip()
        )

        if subtotal <= 0 or total <= 0:
            errors.append("Invoice amounts must be positive")

        if total < subtotal:
            errors.append("Total amount is less than subtotal")

    except (ValueError, TypeError, KeyError):
        errors.append("Invalid invoice amount")

    return {
        "valid": len(errors) == 0,
        "errors": errors
    }