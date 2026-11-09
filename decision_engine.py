
def make_decision(
    validation_result,
    duplicate_result,
    vendor_approved,
    po_match_result,
    invoice_amount,
    po_amount,
    tolerance_percent=2.0
):
    """
    Decide whether an invoice should be Approved,
    Pending Review, or Rejected.
    """

    # Rule 1: Duplicate invoice
    if duplicate_result.get("is_duplicate", False):
        return {
            "status": "Rejected",
            "reason": "Duplicate invoice detected."
        }

    # Rule 2: Invalid invoice
    if not validation_result.get("valid", False):
        return {
            "status": "Rejected",
            "reason": "Invoice validation failed."
        }

    # Rule 3: Vendor approval
    if not vendor_approved:
        return {
            "status": "Rejected",
            "reason": "Vendor is not approved."
        }

    # Rule 4: Purchase Order matching
    if po_match_result.get("status") != "MATCHED":
        return {
            "status": "Pending",
            "reason": "Purchase Order requires manual review."
        }

    # Rule 5: PO amount tolerance
    if po_amount <= 0:
        return {
            "status": "Pending",
            "reason": "Invalid Purchase Order amount."
        }

    difference = abs(invoice_amount - po_amount)
    allowed_difference = po_amount * tolerance_percent / 100

    if difference > allowed_difference:
        return {
            "status": "Pending",
            "reason": "Invoice amount exceeds PO tolerance."
        }

    # All checks passed
    return {
        "status": "Approved",
        "reason": "All invoice checks passed successfully."
    }
