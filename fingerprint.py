"""
fingerprint.py - Creates a unique "fingerprint" for an invoice.

The fingerprint is a SHA-256 hash of the five fields that identify an invoice:
supplier GSTIN, buyer GSTIN, invoice number, invoice date, and invoice amount.

Before hashing, every field is cleaned so that small typing differences cannot
be used to sneak the same invoice past the check. For example, all of these
produce the SAME fingerprint:
    "inv-001 "  and  "INV-001"
    "12/09/2026" and "2026-09-12"
    "50000"     and  "50000.00"

Only this fingerprint is stored on the blockchain - never the full invoice -
so banks can detect duplicates without sharing private business details.
"""

import hashlib
from datetime import datetime

# Date formats we accept from users. All of them are converted to YYYY-MM-DD.
ACCEPTED_DATE_FORMATS = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"]


# Cleans a text field: removes spaces at the ends and inside, and makes it uppercase.
def clean_text(value):
    return "".join(str(value).split()).upper()


# Converts a date written in any accepted format into the standard YYYY-MM-DD form.
def clean_date(value):
    text = str(value).strip()
    for date_format in ACCEPTED_DATE_FORMATS:
        try:
            return datetime.strptime(text, date_format).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"Invalid date: '{value}'. Use YYYY-MM-DD.")


# Converts an amount into text with exactly 2 decimal places, e.g. 50000 -> "50000.00".
def clean_amount(value):
    return f"{round(float(value), 2):.2f}"


# Builds the invoice fingerprint: clean all five fields, join them with "|", then SHA-256 hash.
def generate_fingerprint(supplier_gstin, buyer_gstin, invoice_number, invoice_date, amount):
    parts = [
        clean_text(supplier_gstin),
        clean_text(buyer_gstin),
        clean_text(invoice_number),
        clean_date(invoice_date),
        clean_amount(amount),
    ]
    combined = "|".join(parts)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()
