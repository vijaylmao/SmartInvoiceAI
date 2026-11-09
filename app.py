import sqlite3
import re
import os
import shutil

import streamlit as st
import pymupdf as fitz
import pytesseract
import io 
from PIL import Image
# Tesseract OCR configuration (Local + Cloud)
tesseract_path = shutil.which("tesseract")

if tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path
else:
    windows_tesseract_path = (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )

    if os.path.exists(windows_tesseract_path):
        pytesseract.pytesseract.tesseract_cmd = (
            windows_tesseract_path
        )

from validation import validate_invoice
from duplicate import detect_duplicate
from matching import match_purchase_order
from decision_engine import make_decision
from datetime import datetime, timedelta

from database import (
    DB_NAME,
    create_tables,
    insert_invoice,
    update_invoice_status,
    log_processing,
)


# ============================================================
# PAGE CONFIGURATION + DATABASE
# ============================================================

st.set_page_config(
    page_title="SmartInvoice AI",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

create_tables()


def ensure_grn_tables():
    """Create GRN tables if missing; keep all existing invoice and PO data."""
    conn = sqlite3.connect(DB_NAME)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS goods_receipts (
                grn_id INTEGER PRIMARY KEY AUTOINCREMENT,
                grn_number TEXT NOT NULL UNIQUE,
                po_id INTEGER NOT NULL,
                vendor_id INTEGER,
                received_date TEXT,
                received_amount REAL NOT NULL DEFAULT 0,
                received_quantity REAL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (po_id) REFERENCES purchase_orders(po_id),
                FOREIGN KEY (vendor_id) REFERENCES vendors(vendor_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS grn_items (
                grn_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                grn_id INTEGER NOT NULL,
                description TEXT,
                quantity REAL,
                unit_price REAL,
                amount REAL,
                FOREIGN KEY (grn_id) REFERENCES goods_receipts(grn_id)
            )
        """)
        conn.commit()
    finally:
        conn.close()


ensure_grn_tables()


# ============================================================
# LIGHT THEME - PURPLE ACCENTS
# ============================================================

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    :root {
        --navy: #102F2B;
        --navy-soft: #17443D;

        --green: #16856B;
        --green-dark: #106B56;

        --mint: #E8F5EF;
        --mint-soft: #F3FAF6;

        --canvas: #F5F8F6;
        --ink: #172B27;
        --muted: #71817B;

        --line: #DDE9E2;
        --white: #FFFFFF;
    }

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    .stApp {
        background: var(--canvas);
        color: var(--ink);
    }

    [data-testid="stHeader"] {
        background: rgba(245, 248, 246, 0.96);
    }

    [data-testid="stSidebar"] {
        background: var(--navy);
        border-right: 1px solid #244B43;
    }

    [data-testid="stSidebar"] > div:first-child {
        padding-top: 1.2rem;
    }

    [data-testid="stSidebar"] * {
        color: #E8F4EF;
    }

    [data-testid="stSidebar"] [data-testid="stRadio"] label {
        border-radius: 9px;
        padding: 0.35rem 0.55rem;
    }

    [data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
        background: #1B4B41;
    }

    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] hr {
        border-color: #31584F;
    }

    .brand {
        font-size: 1.35rem;
        font-weight: 800;
        color: #FFFFFF;
        padding: 0.35rem 0 1.2rem 0.2rem;
        letter-spacing: -0.5px;
    }

    .brand span { color: #72D6AE; }

    .page-eyebrow {
        color: var(--green);
        text-transform: uppercase;
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 1.2px;
        margin-bottom: 0.25rem;
    }

    .page-title {
        color: var(--ink);
        font-size: 2rem;
        font-weight: 800;
        letter-spacing: -1px;
        margin: 0;
    }

    .page-subtitle {
        color: var(--muted);
        font-size: 0.92rem;
        margin-top: 0.25rem;
        margin-bottom: 1.2rem;
    }

    .section-heading {
        color: var(--ink);
        font-size: 1.05rem;
        font-weight: 750;
        margin: 0.3rem 0 0.8rem 0;
    }

    .kpi-card {
        background: var(--white);
        border: 1px solid var(--line);
        border-radius: 16px;
        padding: 17px 18px;
        min-height: 112px;
        box-shadow: 0 5px 18px rgba(16, 47, 43, 0.045);
    }

    .kpi-label { color: var(--muted); font-size: 0.82rem; font-weight: 600; }
    .kpi-value { color: var(--ink); font-size: 2rem; line-height: 1.25; font-weight: 800; margin-top: 7px; }
    .kpi-icon { float: right; font-size: 1.5rem; color: var(--green); background: var(--mint); border-radius: 12px; padding: 7px 10px; }

    .panel, .comparison-card {
        background: var(--white);
        border: 1px solid var(--line);
        border-radius: 16px;
        padding: 18px;
        box-shadow: 0 5px 18px rgba(16, 47, 43, 0.035);
        margin-bottom: 14px;
    }

    .comparison-card { padding: 22px; min-height: 145px; }
    .comparison-label { color: var(--muted); font-size: 0.85rem; font-weight: 600; margin-bottom: 14px; }
    .comparison-amount { color: var(--navy); font-size: 1.8rem; font-weight: 800; letter-spacing: -0.7px; }
    .comparison-note { color: var(--muted); font-size: 0.78rem; margin-top: 9px; }

    .pipeline-step {
        background: var(--mint-soft);
        border: 1px solid #CDE7D9;
        border-radius: 12px;
        text-align: center;
        padding: 13px 8px;
        min-height: 86px;
        color: var(--ink);
        font-size: 0.8rem;
        font-weight: 650;
    }

    .pipeline-icon { color: var(--green); font-size: 1.35rem; display: block; margin-bottom: 5px; }

    div.stButton > button {
        background: linear-gradient(90deg, #147A62, #20A17D);
        color: white;
        border: 0;
        border-radius: 10px;
        font-weight: 700;
        padding: 0.55rem 1rem;
    }

    div.stButton > button:hover { background: var(--green-dark); color: white; border: 0; }
    div.stButton > button:focus { box-shadow: 0 0 0 0.2rem rgba(32, 161, 125, 0.22); }

    [data-testid="stFileUploader"] {
        background: var(--mint-soft);
        border: 1.5px dashed #76BFA1;
        border-radius: 14px;
        padding: 12px;
    }

    [data-testid="stMetric"] {
        background: var(--white);
        border: 1px solid var(--line);
        border-radius: 14px;
        padding: 12px;
    }

    [data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }
    [data-testid="stExpander"] { border: 1px solid var(--line); border-radius: 12px; background: var(--white); }
    .muted { color: var(--muted); font-size: 0.82rem; }
    hr { border-color: var(--line); }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# DATABASE HELPERS
# ============================================================

def query_db(query, params=()):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_dashboard_counts():
    rows = query_db(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN decision = 'Approved' THEN 1 ELSE 0 END) AS approved,
            SUM(CASE WHEN decision = 'Pending' THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN decision = 'Rejected' THEN 1 ELSE 0 END) AS rejected
        FROM invoices
        """
    )
    row = rows[0] if rows else {}
    return (
        row.get("total") or 0,
        row.get("approved") or 0,
        row.get("pending") or 0,
        row.get("rejected") or 0,
    )



def get_next_value(text, label):
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    field_labels = [
        "Invoice Number", "Invoice Date",
        "Purchase Order", "PO Number",
        "Due Date", "Payment Terms",
        "GSTIN", "Subtotal", "CGST",
        "SGST", "Grand Total", "Total Amount"
    ]

    for i, line in enumerate(lines):
        match = re.search(
            rf"\b{re.escape(label)}\b\s*[:#-]?\s*(.*)",
            line,
            re.IGNORECASE
        )

        if not match:
            continue

        value = match.group(1).strip()

        # Check whether the same line contains only another field label
        if value and not any(
            re.fullmatch(
                rf"{re.escape(field)}\s*[:#-]?",
                value,
                re.IGNORECASE
            )
            for field in field_labels
        ):
            return value

        # Skip other field labels and find the next actual value
        for next_line in lines[i + 1:]:
            if any(
                re.fullmatch(
                    rf"{re.escape(field)}\s*[:#-]?",
                    next_line,
                    re.IGNORECASE
                )
                for field in field_labels
            ):
                continue

            return next_line

    return "Not found"


def get_date_value(text, label):
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    date_pattern = (
        r'\b\d{1,2}[-/][A-Za-z]{3}[-/]\d{4}\b'
        r'|\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b'
        r'|\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b'
    )

    # First, search for a date beside the requested label
    for i, line in enumerate(lines):
        if re.search(rf'\b{re.escape(label)}\b', line, re.IGNORECASE):
            match = re.search(date_pattern, line, re.IGNORECASE)
            if match:
                return match.group(0)

            # Check the next few lines for the labelled date
            for next_line in lines[i + 1:i + 4]:
                match = re.search(date_pattern, next_line, re.IGNORECASE)
                if match:
                    return match.group(0)

    # If Invoice Date is blank, find another date in the document.
    # Exclude the date explicitly labelled as Due Date.
    if label.lower() == "invoice date":
        due_date = None

        for i, line in enumerate(lines):
            if re.search(r'\bDue Date\b', line, re.IGNORECASE):
                match = re.search(date_pattern, line, re.IGNORECASE)

                if not match and i + 1 < len(lines):
                    match = re.search(date_pattern, lines[i + 1], re.IGNORECASE)

                if match:
                    due_date = match.group(0)
                    break

        for line in lines:
            for match in re.finditer(date_pattern, line, re.IGNORECASE):
                found_date = match.group(0)

                if found_date != due_date:
                    return found_date

    return "Not found"
    

def get_invoice_number(text):
    patterns = [
        r'\b[A-Z]{2,10}-\d{4}-\d+\b',
        r'\b[A-Z]{2,10}-INV-\d+\b',
        r'\bINV-\d{4}-\d+\b',
        r'\bINV-\d+\b'
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).upper()

    return "Not found"



def get_gstin(text):
    match = re.search(
        r"GSTIN:\s*([A-Z0-9]{15})",
        text,
        re.IGNORECASE,
    )
    return match.group(1).upper() if match else "Not found"


def get_amount(text, label):
    pattern = (
        rf"{label}\s*\n?\s*(?:INR|₹)?\s*"
        rf"([\d,]+(?:\.\d{{2}})?)"
    )
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1) if match else "Not found"

def calculate_due_date(invoice_date, payment_terms):
    if invoice_date == "Not found":
        return "Not found"

    try:
        date_obj = datetime.strptime(invoice_date, "%d-%b-%Y")

        match = re.search(r"Net\s+(\d+)\s+days?", payment_terms, re.IGNORECASE)

        if match:
            days = int(match.group(1))
            due_date = date_obj + timedelta(days=days)
            return due_date.strftime("%d-%b-%Y")

    except ValueError:
        return "Not found"

    return "Not found"

def extract_invoice_data(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # --------------------------------
    # 1. Extract the correct vendor name
    # --------------------------------
    vendor = "Not found"

    ignored_lines = [
        "TAX INVOICE",
        "INDEPENDENT SAMPLE VENDOR",
        "SMARTINVOICE AI TEST DATA",
    ]

    vendor_candidates = []

    for line in lines:
        upper_line = line.upper()

        if any(item in upper_line for item in ignored_lines):
            continue

        if (
            "GSTIN" in upper_line
            or "EMAIL" in upper_line
            or "INVOICE NUMBER" in upper_line
            or "PURCHASE ORDER" in upper_line
            or "INVOICE DATE" in upper_line
            or "BILL TO" in upper_line
            or "SUBTOTAL" in upper_line
            or "CGST" in upper_line
            or "SGST" in upper_line
        ):
            continue

        vendor_candidates.append(line)

    # Prefer a company name containing a business suffix
    for line in vendor_candidates:
        if re.search(
            r"\b(PVT\.?\s*LTD|PRIVATE LIMITED|LIMITED|LLP|INC\.?|CORPORATION)\b",
            line,
            re.IGNORECASE,
        ):
            vendor = line
            break

    # Fallback: use the first reasonable candidate
    if vendor == "Not found" and vendor_candidates:
        vendor = vendor_candidates[0]

    # --------------------------------
    # 2. Extract amounts from the PDF
    # --------------------------------
    def extract_labeled_amount(labels):
        for label in labels:
            pattern = (
                rf"(?im)^\s*{label}\s*"
                rf"(?::|-)?\s*(?:INR|Rs\.?|₹)?\s*"
                rf"([\d,]+(?:\.\d{{1,2}})?)"
            )

            match = re.search(pattern, text)

            if match:
                return match.group(1)

        return "Not found"

    subtotal = extract_labeled_amount([r"Subtotal"])

    cgst = extract_labeled_amount([r"CGST"])

    sgst = extract_labeled_amount([r"SGST"])

    total_amount = extract_labeled_amount([
        r"Grand Total",
        r"Total Amount",
    ])

    # --------------------------------
    # 3. Return extracted invoice data
    # --------------------------------
    invoice_date = get_date_value(text, "Invoice Date")
    payment_terms = get_next_value(text, "Payment Terms")
    due_date = get_date_value(text, "Due Date")

    if due_date == "Not found":
        due_date = calculate_due_date(invoice_date, payment_terms)
    return {
        "Vendor Name": vendor,
        "Invoice Number": get_invoice_number(text),
        "Invoice Date": invoice_date,
        "PO Number": get_next_value(text, "Purchase Order"),
        "Due Date": due_date,
        "GSTIN": get_gstin(text),
        "Subtotal": subtotal,
        "CGST": cgst,
        "SGST": sgst,
        "Total Amount": total_amount,
    }


def numeric_amount(value):
    if value is None or str(value).strip() in ("", "Not found"):
        return 0.0
    return float(str(value).replace(",", "").replace("₹", "").strip())


def get_po_context(po_number, gstin):
    rows = query_db(
        """
        SELECT po.po_id, po.subtotal, po.tolerance_percent,
               v.vendor_id, v.is_approved, v.gstin
        FROM purchase_orders po
        JOIN vendors v ON po.vendor_id = v.vendor_id
        WHERE UPPER(TRIM(po.po_number)) = UPPER(TRIM(?))
          AND UPPER(TRIM(v.gstin)) = UPPER(TRIM(?))
        LIMIT 1
        """,
        (po_number, gstin),
    )
    return rows[0] if rows else None


def get_vendor_approval(gstin):
    rows = query_db(
        "SELECT is_approved FROM vendors WHERE UPPER(TRIM(gstin)) = UPPER(TRIM(?)) LIMIT 1",
        (gstin,),
    )
    return bool(rows and rows[0]["is_approved"] == 1)


def money(value):
    if value is None:
        return "—"
    try:
        return f"₹{float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


# ============================================================
# SIDEBAR NAVIGATION
# ============================================================

with st.sidebar:
    st.markdown(
        '<div class="brand">▤ SmartInvoice <span>AI</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    page = st.radio(
        "NAVIGATION",
        [
            "Dashboard",
            "Upload Invoice",
            "Invoice Processing",
            "Three-Way Matching",
            "Invoices",
            "Vendor Management",
            "Analytics",
            "Settings",
            "About",
        ],
        label_visibility="collapsed",
        key="main_navigation",
    )
    st.markdown("---")
    st.markdown(
        '<div class="muted">Intelligent Accounts Payable<br>Processing Platform</div>',
        unsafe_allow_html=True,
    )


# ============================================================
# REUSABLE PAGE HEADER + KPI CARDS
# ============================================================

def page_header(title, subtitle):
    st.markdown('<div class="page-eyebrow">SMARTINVOICE AI</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-title">{title}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def show_kpis():
    total, approved, pending, rejected = get_dashboard_counts()
    cols = st.columns(4)
    cards = [
        ("Total Invoices", total, "▤"),
        ("Approved", approved, "✓"),
        ("Pending Review", pending, "◷"),
        ("Rejected", rejected, "×"),
    ]
    for col, (label, value, icon) in zip(cols, cards):
        with col:
            st.markdown(
                f"""
                <div class="kpi-card">
                    <span class="kpi-icon">{icon}</span>
                    <div class="kpi-label">{label}</div>
                    <div class="kpi-value">{value:,}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    return total, approved, pending, rejected


def show_pipeline():
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-heading">Invoice Processing Pipeline</div>', unsafe_allow_html=True)
    stages = [
        ("▤", "1. Extract", "PDF / OCR"),
        ("✓", "2. Validate", "Invoice data"),
        ("▰", "3. Check", "Duplicate"),
        ("↔", "4. PO", "Matching"),
        ("⚙", "5. Decision", "Engine"),
        ("▤", "6. Save to", "Database"),
    ]
    cols = st.columns(6)
    for col, (icon, line1, line2) in zip(cols, stages):
        with col:
            st.markdown(
                f'<div class="pipeline-step"><span class="pipeline-icon">{icon}</span>{line1}<br>{line2}</div>',
                unsafe_allow_html=True,
            )
    st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# INVOICE PROCESSING FUNCTION
# ============================================================

def process_uploaded_invoice(uploaded_file):
    with st.status("Processing invoice...", expanded=True) as status:
        st.write("1. Extracting PDF text")
        pdf = fitz.open(
            stream=uploaded_file.getvalue(),
            filetype="pdf"
        )

        extracted_text = ""

        for page_obj in pdf:

            # First, try normal PDF text extraction
            page_text = page_obj.get_text().strip()

            if page_text:
                extracted_text += page_text + "\n"

            else:
                # If no readable text exists, use OCR
                pix = page_obj.get_pixmap(
                    matrix=fitz.Matrix(300 / 72, 300 / 72),
                    alpha=False
                )

                image = Image.open(
        io.BytesIO(pix.tobytes("png"))
                )

                ocr_text = pytesseract.image_to_string(
                    image,
                    lang="eng"
                )

                extracted_text += ocr_text + "\n"

        pdf.close()

        if not extracted_text.strip():
            status.update(
                label="No readable text found",
                state="error"
            )
            st.error("Unable to extract text from this PDF, even with OCR.")
            return

        invoice_data = extract_invoice_data(extracted_text)
        invoice_data["File Name"] = uploaded_file.name

        st.write("2. Validating invoice")
        validation_result = validate_invoice(invoice_data)

        if not isinstance(validation_result, dict):
            raise ValueError("The validation module returned an unexpected result.")

        st.write("3. Checking duplicate invoice")
        invoice_number = invoice_data.get("Invoice Number", "Not found")
        gstin = invoice_data.get("GSTIN", "Not found")

        duplicate_result = {
            "is_duplicate": False,
            "existing_invoice": None,
        }
        if invoice_number != "Not found" and gstin != "Not found":
            duplicate_result = detect_duplicate(invoice_number, gstin)

        st.write("4. Matching purchase order")
        po_number = invoice_data.get("PO Number", "Not found")
        subtotal = numeric_amount(invoice_data.get("Subtotal"))
        po_context = None

        if po_number != "Not found" and gstin != "Not found" and subtotal > 0:
            matching_input = {
                "po_number": po_number,
                "gstin": gstin,
                "subtotal": subtotal,
            }
            po_match_result = match_purchase_order(matching_input)
            po_context = get_po_context(po_number, gstin)
        else:
            po_match_result = {
                "status": "REVIEW",
                "reason": "Required PO details are missing.",
            }

        vendor_approved = get_vendor_approval(gstin)
        po_amount = float(po_context["subtotal"]) if po_context else 0.0
        tolerance = float(po_context["tolerance_percent"]) if po_context else 2.0

        st.write("5. Running decision engine")
        decision_result = make_decision(
            validation_result=validation_result,
            duplicate_result=duplicate_result,
            vendor_approved=vendor_approved,
            po_match_result=po_match_result,
            invoice_amount=subtotal,
            po_amount=po_amount,
            tolerance_percent=tolerance,
        )

        decision = decision_result["status"]
        reason = decision_result["reason"]

        st.write("6. Saving result")
        if duplicate_result.get("is_duplicate", False):
            existing = duplicate_result.get("existing_invoice") or {}
            invoice_id = existing.get("invoice_id")
            saved_new_record = False
            st.warning("Duplicate invoice detected. A second database record was not created.")
        else:
            # Find vendor independently using GSTIN
            vendor_rows = query_db(
                """
                SELECT vendor_id
                FROM vendors    
                WHERE UPPER(TRIM(gstin)) = UPPER(TRIM(?))
                LIMIT 1
                """,
                (invoice_data.get("GSTIN"),)
            )

            # Use PO vendor ID if matched; otherwise use GSTIN lookup
            vendor_id = (
                po_context["vendor_id"]
                if po_context
                else (vendor_rows[0]["vendor_id"] if vendor_rows else None)
            )

            # Link PO only when a matching PO exists
            po_id = po_context["po_id"] if po_context else None
            
            invoice_id = insert_invoice(invoice_data, vendor_id, po_id)
            update_invoice_status(invoice_id, decision, reason)
            log_processing(
                invoice_id,
                "Validation",
                "Passed" if validation_result.get("valid") else "Failed",
                str(validation_result.get("errors", [])),
            )
            log_processing(invoice_id, "Duplicate Detection", "Passed", str(duplicate_result))
            log_processing(
                invoice_id,
                "PO Matching",
                po_match_result.get("status", "REVIEW"),
                po_match_result.get("reason", ""),
            )
            log_processing(invoice_id, "Decision Engine", decision, reason)
            saved_new_record = True

        status.update(label="Invoice processing completed", state="complete", expanded=False)

    # Persist the most recent processing result so it can be viewed from other pages.
    st.session_state["last_processing"] = {
        "invoice_data": invoice_data,
        "validation_result": validation_result,
        "duplicate_result": duplicate_result,
        "po_match_result": po_match_result,
        "decision": decision,
        "reason": reason,
        "invoice_id": invoice_id,
        "saved_new_record": saved_new_record,
        "extracted_text": extracted_text,
    }


def show_last_processing():
    result = st.session_state.get("last_processing")
    if not result:
        st.info("No invoice has been processed in this session yet. Upload a PDF to begin.")
        return

    data = result["invoice_data"]
    st.markdown('<div class="section-heading">Extracted Invoice Details</div>', unsafe_allow_html=True)
    left, right = st.columns(2)
    with left:
        st.write("**Vendor:**", data.get("Vendor Name"))
        st.write("**Invoice number:**", data.get("Invoice Number"))
        st.write("**Invoice date:**", data.get("Invoice Date"))
        st.write("**PO number:**", data.get("PO Number"))
        st.write("**Due date:**", data.get("Due Date"))
    with right:
        st.write("**GSTIN:**", data.get("GSTIN"))
        st.write("**Subtotal:**", data.get("Subtotal"))
        st.write("**CGST:**", data.get("CGST"))
        st.write("**SGST:**", data.get("SGST"))
        st.write("**Total amount:**", data.get("Total Amount"))

    st.markdown("---")
    a, b, c = st.columns(3)
    with a:
        if result["validation_result"].get("valid"):
            st.success("Validation passed")
        else:
            st.error("Validation failed")
    with b:
        if result["duplicate_result"].get("is_duplicate"):
            st.error("Duplicate detected")
        else:
            st.success("No duplicate found")
    with c:
        if result["po_match_result"].get("status") == "MATCHED":
            st.success("PO matched")
        else:
            st.warning("PO requires review")

    st.markdown("### Final Decision")
    decision = result["decision"]
    if decision == "Approved":
        st.success(f"APPROVED — {result['reason']}")
    elif decision == "Pending":
        st.warning(f"PENDING REVIEW — {result['reason']}")
    else:
        st.error(f"REJECTED — {result['reason']}")

    if result["invoice_id"] is not None:
        st.caption(f"Database invoice ID: {result['invoice_id']}")
    if not result["saved_new_record"]:
        st.info("This was an existing invoice. No additional invoice row was inserted.")

    with st.expander("View extracted PDF text"):
        st.text_area("Extracted text", result["extracted_text"], height=220)


# ============================================================
# PAGE: DASHBOARD
# ============================================================

if page == "Dashboard":
    page_header(
        "Dashboard",
        "Intelligent invoice processing and three-way matching overview.",
    )
    total, approved, pending, rejected = show_kpis()

    show_pipeline()

    left, right = st.columns([1.55, 1])
    with left:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown('<div class="section-heading">Recent Invoices</div>', unsafe_allow_html=True)
        recent = query_db(
            """
            SELECT invoice_number AS 'Invoice No.',
                   gstin AS 'GSTIN',
                   total_amount AS 'Amount (INR)',
                   decision AS 'Decision',
                   created_at AS 'Processed On'
            FROM invoices
            ORDER BY invoice_id DESC
            LIMIT 8
            """
        )
        if recent:
            st.dataframe(recent, use_container_width=True, hide_index=True)
        else:
            st.info("No invoices have been saved yet.")
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown('<div class="section-heading">Invoices by Decision</div>', unsafe_allow_html=True)
        st.bar_chart(
            {
                "Invoices": {
                    "Approved": approved,
                    "Pending": pending,
                    "Rejected": rejected,
                }
            },
            use_container_width=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# PAGE: UPLOAD INVOICE
# ============================================================

elif page == "Upload Invoice":
    page_header(
        "Upload Invoice",
        "Upload a supplier invoice PDF and run the six-stage processing workflow.",
    )

    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-heading">Select invoice PDF</div>', unsafe_allow_html=True)
    uploaded_file = st.file_uploader(
        "Drag and drop an invoice PDF here, or browse to choose a file.",
        type=["pdf"],
        key="invoice_pdf_upload",
    )
    st.caption("Supported format: PDF. Scanned PDFs require OCR, which is not configured in the current backend.")
    if uploaded_file:
        st.success(f"Ready to process: {uploaded_file.name}")
        if st.button("Process Invoice", type="primary", use_container_width=True):
            try:
                process_uploaded_invoice(uploaded_file)
            except Exception as error:
                st.error(f"Invoice processing failed: {error}")
                st.exception(error)
    st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.get("last_processing"):
        st.markdown("### Latest Processing Result")
        show_last_processing()


# ============================================================
# PAGE: INVOICE PROCESSING
# ============================================================

elif page == "Invoice Processing":
    page_header(
        "Invoice Processing",
        "Review the latest extraction, validation, duplicate and decision results.",
    )
    show_pipeline()
    show_last_processing()


# ============================================================
# PAGE: THREE-WAY MATCHING
# ============================================================

elif page == "Three-Way Matching":
    page_header(
        "Three-Way Matching",
        "Register goods receipts and compare supplier invoices, purchase orders and received goods.",
    )

    st.info(
        "This version performs an amount-level three-way check: invoice subtotal, PO subtotal "
        "and GRN received amount. Item-by-item quantity matching is not yet enabled because "
        "the current invoice upload workflow does not extract invoice line items."
    )

    po_options = query_db(
        """SELECT p.po_id, p.po_number, p.subtotal, p.total_amount, p.vendor_id,
                  v.vendor_name, v.gstin
           FROM purchase_orders p LEFT JOIN vendors v ON v.vendor_id = p.vendor_id
           ORDER BY p.po_id DESC"""
    )

    if not po_options:
        st.warning("No purchase orders are available. Add a purchase order before registering a GRN.")
    else:
        po_labels = {
            row["po_id"]: f'{row["po_number"]} · {row.get("vendor_name") or "Unknown vendor"} · PO subtotal {money(row.get("subtotal"))}'
            for row in po_options
        }

        st.markdown("### Register Goods Receipt Note (GRN)")
        with st.form("register_grn_form", clear_on_submit=True):
            selected_po_for_grn = st.selectbox(
                "Purchase Order", options=[r["po_id"] for r in po_options],
                format_func=lambda value: po_labels[value],
            )
            grn_col1, grn_col2 = st.columns(2)
            with grn_col1:
                grn_number = st.text_input("GRN number", placeholder="GRN-2026-0001")
                received_date = st.date_input("Goods received date")
            with grn_col2:
                received_amount = st.number_input(
                    "Received goods value (₹, before tax)", min_value=0.0,
                    step=100.0, format="%.2f",
                    help="Enter the accepted value of goods actually received against this PO.",
                )
                received_quantity = st.number_input(
                    "Total received quantity (optional)", min_value=0.0,
                    step=1.0, format="%.2f",
                )
            grn_notes = st.text_area("Notes (optional)", placeholder="Shortages, damaged goods or delivery references")
            save_grn = st.form_submit_button("Save Goods Receipt Note", type="primary", use_container_width=True)

        if save_grn:
            clean_grn_number = grn_number.strip()
            if not clean_grn_number:
                st.error("Enter a GRN number before saving.")
            elif received_amount <= 0:
                st.error("Received goods value must be greater than zero.")
            else:
                selected_po = next(r for r in po_options if r["po_id"] == selected_po_for_grn)
                conn = sqlite3.connect(DB_NAME)
                try:
                    conn.execute("PRAGMA foreign_keys = ON")
                    conn.execute(
                        """INSERT INTO goods_receipts
                           (grn_number, po_id, vendor_id, received_date, received_amount, received_quantity, notes)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (clean_grn_number, selected_po_for_grn, selected_po.get("vendor_id"),
                         received_date.isoformat(), float(received_amount),
                         float(received_quantity) if received_quantity > 0 else None,
                         grn_notes.strip() or None),
                    )
                    conn.commit()
                    st.success(f"GRN {clean_grn_number} saved successfully.")
                    st.rerun()
                except sqlite3.IntegrityError as error:
                    st.error(f"GRN number already exists or selected PO is invalid: {error}")
                finally:
                    conn.close()

        st.markdown("---")
        st.markdown("### Run Three-Way Match")
        invoice_options = query_db(
            """SELECT i.invoice_id, i.invoice_number, i.gstin, i.subtotal, i.decision,
                      v.vendor_name, i.po_id, p.po_number
               FROM invoices i LEFT JOIN vendors v ON v.vendor_id = i.vendor_id
               LEFT JOIN purchase_orders p ON p.po_id = i.po_id
               WHERE i.po_id IS NOT NULL ORDER BY i.invoice_id DESC LIMIT 500"""
        )
        grn_options = query_db(
            """SELECT g.grn_id, g.grn_number, g.po_id, g.received_date,
                      g.received_amount, g.received_quantity, p.po_number
               FROM goods_receipts g JOIN purchase_orders p ON p.po_id = g.po_id
               ORDER BY g.grn_id DESC"""
        )

        if not invoice_options:
            st.info("No invoices linked to purchase orders are available for matching yet.")
        elif not grn_options:
            st.info("Register a GRN above, then select an invoice and its GRN here.")
        else:
            invoice_labels = {
                r["invoice_id"]: f'ID {r["invoice_id"]} · {r["invoice_number"] or "No invoice number"} · {r.get("vendor_name") or "Unknown vendor"}'
                for r in invoice_options
            }
            selected_invoice_id = st.selectbox(
                "Select invoice", options=[r["invoice_id"] for r in invoice_options],
                format_func=lambda value: invoice_labels[value], key="three_way_invoice_select",
            )
            selected_invoice = next(r for r in invoice_options if r["invoice_id"] == selected_invoice_id)
            invoice_po_id = selected_invoice["po_id"]
            eligible_grns = [r for r in grn_options if r["po_id"] == invoice_po_id]

            if not eligible_grns:
                st.warning(f'No GRN is registered for PO {selected_invoice.get("po_number") or invoice_po_id}. Register one above.')
            else:
                grn_labels = {
                    r["grn_id"]: f'{r["grn_number"]} · {r["received_date"] or "Date not set"} · Received {money(r["received_amount"])}'
                    for r in eligible_grns
                }
                selected_grn_id = st.selectbox(
                    "Select GRN for this purchase order", options=[r["grn_id"] for r in eligible_grns],
                    format_func=lambda value: grn_labels[value], key="three_way_grn_select",
                )
                selected_grn = next(r for r in eligible_grns if r["grn_id"] == selected_grn_id)
                selected_po = next(r for r in po_options if r["po_id"] == invoice_po_id)

                st.markdown("#### Document comparison")
                cols = st.columns(3)
                for col, (label, amount) in zip(cols, [
                    ("Supplier Invoice", selected_invoice.get("subtotal")),
                    ("Purchase Order", selected_po.get("subtotal")),
                    ("Goods Receipt Note", selected_grn.get("received_amount")),
                ]):
                    with col:
                        st.metric(label, money(amount))

                tolerance_pct = st.number_input(
                    "Allowed amount variance (%)", min_value=0.0, max_value=100.0,
                    value=2.0, step=0.5, key="three_way_tolerance",
                )
                if st.button("Compare all three documents", type="primary", width="stretch", key="run_three_way_match"):
                    inv_amt = float(selected_invoice.get("subtotal") or 0)
                    po_amt = float(selected_po.get("subtotal") or 0)
                    grn_amt = float(selected_grn.get("received_amount") or 0)

                    def amount_matches(a, b, pct):
                        if a <= 0 or b <= 0:
                            return False
                        return abs(a - b) <= max(a, b) * pct / 100.0

                    checks = [
                        ("Invoice ↔ PO", amount_matches(inv_amt, po_amt, tolerance_pct)),
                        ("PO ↔ GRN", amount_matches(po_amt, grn_amt, tolerance_pct)),
                        ("Invoice ↔ GRN", amount_matches(inv_amt, grn_amt, tolerance_pct)),
                    ]
                    check_cols = st.columns(3)
                    for col, (label, passed) in zip(check_cols, checks):
                        with col:
                            if passed:
                                st.success(f"{label}: Matched")
                            else:
                                st.error(f"{label}: Variance detected")
                    if all(passed for _, passed in checks):
                        st.success("THREE-WAY MATCH PASSED — all three document amounts are within tolerance.")
                    else:
                        st.warning("THREE-WAY MATCH REQUIRES REVIEW — one or more amounts are outside tolerance or missing.")
                    st.caption("This informational check does not change the invoice's existing approval/rejection decision.")

        st.markdown("---")
        st.markdown("### Goods Receipt Register")
        st.caption("A record of goods received aganist registered purchase orders.")
        all_grns = query_db(
            """SELECT g.grn_number AS 'GRN Number', p.po_number AS 'PO Number',
                      v.vendor_name AS 'Vendor', g.received_date AS 'Received Date',
                      g.received_amount AS 'Received Amount (INR)',
                      g.received_quantity AS 'Received Quantity', g.notes AS 'Notes'
               FROM goods_receipts g JOIN purchase_orders p ON p.po_id = g.po_id
               LEFT JOIN vendors v ON v.vendor_id = g.vendor_id
               ORDER BY g.grn_id DESC LIMIT 200"""
        )
        if all_grns:
            st.dataframe(
                all_grns,
                use_container_width=True,
                hide_index=True,
                height=180,
                column_config={
                    "GRN Number": st.column_config.TextColumn("GRN Number"),
                    "PO Number": st.column_config.TextColumn("Purchase Order"),
                    "Vendor": st.column_config.TextColumn("Vendor"),
                    "Received Date": st.column_config.TextColumn("Received Date"),
                    "Received Amount (INR)": st.column_config.NumberColumn(
                        "Received Amount",
                        format="₹%.2f",
                   ),
                    "Received Quantity": st.column_config.NumberColumn(
                        "Received Quantity",
                        format="%.2f",
                   ),
                    "Notes": st.column_config.TextColumn("Notes"),
                },
            )
        else:
            st.info("No Goods Receipt Notes have been registered yet.")


# ============================================================
# PAGE: INVOICES
# ============================================================

elif page == "Invoices":
    page_header(
        "Invoice Management",
        "Search, filter and inspect invoices stored in your database.",
    )

    search_text = st.text_input(
        "Search invoices",
        placeholder="Search by invoice number, vendor name or GSTIN...",
        key="invoice_search_text",
    )

    filter_col, sort_col = st.columns([1, 1])
    with filter_col:
        filter_choice = st.selectbox(
            "Filter by decision",
            ["All", "Approved", "Pending", "Rejected"],
            key="invoice_decision_filter",
        )
    with sort_col:
        sort_choice = st.selectbox(
            "Sort by",
            ["Newest first", "Oldest first", "Highest amount", "Lowest amount"],
            key="invoice_sort_choice",
        )

    invoice_query = """
        SELECT i.invoice_id AS 'Database ID',
               i.invoice_number AS 'Invoice Number',
               COALESCE(v.vendor_name, 'Unknown vendor') AS 'Vendor',
               i.gstin AS 'GSTIN',
               i.invoice_date AS 'Invoice Date',
               i.total_amount AS 'Total Amount (INR)',
               i.decision AS 'Decision',
               i.created_at AS 'Processed At'
        FROM invoices i
        LEFT JOIN vendors v ON i.vendor_id = v.vendor_id
        WHERE 1 = 1
    """
    query_params = []

    if filter_choice != "All":
        invoice_query += " AND i.decision = ?"
        query_params.append(filter_choice)

    if search_text.strip():
        search_pattern = f"%{search_text.strip()}%"
        invoice_query += """
            AND (
                i.invoice_number LIKE ?
                OR i.gstin LIKE ?
                OR v.vendor_name LIKE ?
            )
        """
        query_params.extend([search_pattern, search_pattern, search_pattern])

    if sort_choice == "Oldest first":
        invoice_query += " ORDER BY i.invoice_id ASC"
    elif sort_choice == "Highest amount":
        invoice_query += " ORDER BY i.total_amount DESC"
    elif sort_choice == "Lowest amount":
        invoice_query += " ORDER BY i.total_amount ASC"
    else:
        invoice_query += " ORDER BY i.invoice_id DESC"

    invoice_query += " LIMIT 500"
    invoice_rows = query_db(invoice_query, tuple(query_params))

    st.caption(f"{len(invoice_rows)} invoice record(s) found")

    if invoice_rows:
        st.dataframe(
            invoice_rows,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Total Amount (INR)": st.column_config.NumberColumn(
                    "Total Amount (INR)",
                    format="₹%.2f",
                ),
            },
        )

        available_ids = [row["Database ID"] for row in invoice_rows]
        selected_id = st.selectbox(
            "Select an invoice to view details",
            available_ids,
            format_func=lambda invoice_id: next(
                (
                    f'{row["Invoice Number"]} · {row["Vendor"]} · '
                    f'ID {invoice_id}'
                    for row in invoice_rows
                    if row["Database ID"] == invoice_id
                ),
                f"Invoice ID {invoice_id}",
            ),
            key="selected_invoice_detail_id",
        )

        detail_rows = query_db(
            """
            SELECT i.invoice_id,
                   i.invoice_number,
                   i.invoice_date,
                   i.due_date,
                   i.gstin,
                   i.subtotal,
                   i.cgst,
                   i.sgst,
                   i.total_amount,
                   i.decision,
                   i.decision_reason,
                   i.file_name,
                   i.created_at,
                   v.vendor_name,
                   p.po_number
            FROM invoices i
            LEFT JOIN vendors v ON i.vendor_id = v.vendor_id
            LEFT JOIN purchase_orders p ON i.po_id = p.po_id
            WHERE i.invoice_id = ?
            LIMIT 1
            """,
            (selected_id,),
        )

        if detail_rows:
            detail = detail_rows[0]
            st.markdown("### Invoice Details")
            detail_left, detail_right = st.columns(2)

            with detail_left:
                st.write("**Invoice number:**", detail["invoice_number"] or "—")
                st.write("**Vendor:**", detail["vendor_name"] or "—")
                st.write("**GSTIN:**", detail["gstin"] or "—")
                st.write("**Invoice date:**", detail["invoice_date"] or "—")
                st.write("**Due date:**", detail["due_date"] or "—")
                st.write("**Purchase order:**", detail["po_number"] or "—")

            with detail_right:
                st.write("**Subtotal:**", money(detail["subtotal"]))
                st.write("**CGST:**", money(detail["cgst"]))
                st.write("**SGST:**", money(detail["sgst"]))
                st.write("**Total amount:**", money(detail["total_amount"]))
                st.write("**File name:**", detail["file_name"] or "—")
                st.write("**Processed at:**", detail["created_at"] or "—")

            if detail["decision"] == "Approved":
                st.success(f"Decision: Approved — {detail['decision_reason'] or ''}")
            elif detail["decision"] == "Pending":
                st.warning(f"Decision: Pending review — {detail['decision_reason'] or ''}")
            else:
                st.error(f"Decision: Rejected — {detail['decision_reason'] or ''}")
    else:
        st.info("No invoices match your search and filter settings.")



# ============================================================
# PAGE: VENDOR MANAGEMENT
# ============================================================

elif page == "Vendor Management":
    page_header(
        "Vendor Management",
        "Register suppliers, maintain vendor details and control approval status.",
    )

    vendor_search = st.text_input(
        "Search vendors",
        placeholder="Search by vendor name or GSTIN...",
        key="vendor_search_text",
    )

    vendor_query = """
        SELECT vendor_id AS 'Vendor ID',
               vendor_name AS 'Vendor Name',
               gstin AS 'GSTIN',
               email AS 'Email',
               is_approved AS 'Approval Status'
        FROM vendors
        WHERE 1 = 1
    """
    vendor_params = []
    if vendor_search.strip():
        pattern = f"%{vendor_search.strip()}%"
        vendor_query += " AND (vendor_name LIKE ? OR gstin LIKE ?)"
        vendor_params.extend([pattern, pattern])
    vendor_query += " ORDER BY vendor_id DESC"
    vendor_rows = query_db(vendor_query, tuple(vendor_params))

    total_vendors = query_db("SELECT COUNT(*) AS total FROM vendors")[0]["total"]
    approved_vendors = query_db(
        "SELECT COUNT(*) AS total FROM vendors WHERE is_approved = 1"
    )[0]["total"]
    inactive_vendors = total_vendors - approved_vendors

    metric_cols = st.columns(3)
    metric_cols[0].metric("Total Vendors", total_vendors)
    metric_cols[1].metric("Approved Vendors", approved_vendors)
    metric_cols[2].metric("Not Approved", inactive_vendors)

    st.markdown("---")
    add_tab, manage_tab = st.tabs(["Add Vendor", "View / Edit Vendors"])

    with add_tab:
        st.markdown("### Register a new vendor")
        with st.form("add_vendor_form", clear_on_submit=True):
            new_vendor_name = st.text_input(
                "Vendor / Company Name",
                placeholder="Enter registered company name",
            )
            new_vendor_gstin = st.text_input(
                "GSTIN",
                placeholder="15-character GSTIN",
                max_chars=15,
            ).strip().upper()
            new_vendor_email = st.text_input(
                "Email Address",
                placeholder="vendor@example.com",
            ).strip()
            new_vendor_approved = st.checkbox(
                "Approve this vendor",
                value=False,
                help="Only approve vendors after completing your verification.",
            )
            add_vendor_submit = st.form_submit_button(
                "Save Vendor", type="primary", use_container_width=True
            )

        if add_vendor_submit:
            clean_name = new_vendor_name.strip()
            clean_gstin = new_vendor_gstin
            if not clean_name:
                st.error("Enter the vendor or company name.")
            elif len(clean_gstin) != 15:
                st.error("Enter a valid 15-character GSTIN.")
            else:
                conn = sqlite3.connect(DB_NAME)
                try:
                    conn.execute(
                        """
                        INSERT INTO vendors (vendor_name, gstin, email, is_approved)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            clean_name,
                            clean_gstin,
                            new_vendor_email or None,
                            1 if new_vendor_approved else 0,
                        ),
                    )
                    conn.commit()
                    st.success(f"Vendor '{clean_name}' added successfully.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("This GSTIN is already registered. Search for the vendor instead.")
                except sqlite3.Error as error:
                    st.error(f"Could not save vendor: {error}")
                finally:
                    conn.close()

    with manage_tab:
        st.markdown("### Registered vendors")
        if vendor_rows:
            display_rows = [
                {
                    **row,
                    "Approval Status": (
                        "Approved" if row["Approval Status"] == 1 else "Not approved"
                    ),
                }
                for row in vendor_rows
            ]
            st.dataframe(
                display_rows,
                use_container_width=True,
                hide_index=True,
            )

            vendor_ids = [row["Vendor ID"] for row in vendor_rows]
            selected_vendor_id = st.selectbox(
                "Select vendor to edit or update approval",
                vendor_ids,
                format_func=lambda vendor_id: next(
                    (
                        f'{row["Vendor Name"]} · {row["GSTIN"]}'
                        for row in vendor_rows
                        if row["Vendor ID"] == vendor_id
                    ),
                    f"Vendor ID {vendor_id}",
                ),
                key="selected_vendor_management_id",
            )
            selected_vendor = next(
                row for row in vendor_rows if row["Vendor ID"] == selected_vendor_id
            )

            st.markdown("#### Edit vendor details")
            with st.form("edit_vendor_form"):
                edit_name = st.text_input(
                    "Vendor / Company Name",
                    value=selected_vendor["Vendor Name"] or "",
                    key=f"edit_vendor_name_{selected_vendor_id}",
                )
                edit_gstin = st.text_input(
                    "GSTIN",
                    value=selected_vendor["GSTIN"] or "",
                    max_chars=15,
                    key=f"edit_vendor_gstin_{selected_vendor_id}",
                ).strip().upper()
                edit_email = st.text_input(
                    "Email Address",
                    value=selected_vendor["Email"] or "",
                    key=f"edit_vendor_email_{selected_vendor_id}",
                ).strip()
                save_vendor_changes = st.form_submit_button(
                    "Save Changes", type="primary"
                )

            if save_vendor_changes:
                if not edit_name.strip():
                    st.error("Vendor name cannot be empty.")
                elif len(edit_gstin) != 15:
                    st.error("Enter a valid 15-character GSTIN.")
                else:
                    conn = sqlite3.connect(DB_NAME)
                    try:
                        conn.execute(
                            """
                            UPDATE vendors
                            SET vendor_name = ?, gstin = ?, email = ?
                            WHERE vendor_id = ?
                            """,
                            (
                                edit_name.strip(),
                                edit_gstin,
                                edit_email or None,
                                selected_vendor_id,
                            ),
                        )
                        conn.commit()
                        st.success("Vendor details updated successfully.")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("That GSTIN is already assigned to another vendor.")
                    except sqlite3.Error as error:
                        st.error(f"Could not update vendor: {error}")
                    finally:
                        conn.close()

            current_approval = selected_vendor["Approval Status"] == 1
            st.markdown("#### Vendor approval")
            st.write(
                "Current status:",
                "Approved" if current_approval else "Not approved",
            )
            if current_approval:
                if st.button(
                    "Deactivate Vendor",
                    key=f"deactivate_vendor_{selected_vendor_id}",
                ):
                    conn = sqlite3.connect(DB_NAME)
                    try:
                        conn.execute(
                            "UPDATE vendors SET is_approved = 0 WHERE vendor_id = ?",
                            (selected_vendor_id,),
                        )
                        conn.commit()
                        st.success("Vendor deactivated.")
                        st.rerun()
                    finally:
                        conn.close()
            else:
                if st.button(
                    "Approve Vendor",
                    type="primary",
                    key=f"approve_vendor_{selected_vendor_id}",
                ):
                    conn = sqlite3.connect(DB_NAME)
                    try:
                        conn.execute(
                            "UPDATE vendors SET is_approved = 1 WHERE vendor_id = ?",
                            (selected_vendor_id,),
                        )
                        conn.commit()
                        st.success("Vendor approved.")
                        st.rerun()
                    finally:
                        conn.close()
        else:
            st.info("No vendors found. Add your first vendor using the Add Vendor tab.")


# ============================================================
# PAGE: ANALYTICS
# ============================================================

elif page == "Analytics":
    page_header("Analytics", "Understand invoice outcomes and processing volumes.")

    total, approved, pending, rejected = show_kpis()
    chart_left, chart_right = st.columns(2)

    with chart_left:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown('<div class="section-heading">Decision Breakdown</div>', unsafe_allow_html=True)
        st.bar_chart(
            {"Count": {"Approved": approved, "Pending": pending, "Rejected": rejected}},
            use_container_width=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    with chart_right:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown('<div class="section-heading">Invoice Processing Volume</div>', unsafe_allow_html=True)
        daily = query_db(
            """
            SELECT DATE(created_at) AS processing_date,
                   COUNT(*) AS invoice_count
            FROM invoices
            GROUP BY DATE(created_at)
            ORDER BY processing_date
            """
        )
        if daily:
            chart_values = [
                row["invoice_count"]
                for row in daily
                if row["processing_date"] is not None
            ]
            st.line_chart({"Invoices": chart_values}, use_container_width=True)
            st.caption(
                "Daily counts are ordered by processing date. "
                "See the invoice register for exact timestamps."
            )
        else:
            st.info("No processing history available.")
        st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# PAGE: SETTINGS + ABOUT
# ============================================================

elif page == "Settings":
    page_header("Settings", "Application configuration and current system capabilities.")
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.write("**Application:** SmartInvoice AI")
    st.write("**Database:** SQLite")
    st.write("**Invoice format:** PDF")
    st.write("**Duplicate key:** Invoice Number + GSTIN")
    st.write("**Theme:** Light with purple accents")
    st.write("**OCR:** Not configured for scanned PDFs")
    st.markdown("</div>", unsafe_allow_html=True)

elif page == "About":
    page_header("About SmartInvoice AI", "Intelligent accounts-payable invoice automation.")
    st.markdown(
        """
        <div class="panel">
            <h3 style="color:#17443D;">SmartInvoice AI</h3>
            <p style="color:#71817B;">
                SmartInvoice AI automates key accounts-payable activities:
                PDF text extraction, invoice validation, duplicate detection,
                purchase-order matching, decision generation and database storage.
            </p>
            <p style="color:#71817B;">
                The current backend supports invoice-to-purchase-order matching.
                A complete three-way match additionally requires goods-receipt data.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# FOOTER
# ============================================================

st.markdown("---")
st.caption("SmartInvoice AI · Automated Accounts Payable Processing")
