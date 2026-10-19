"""
Guards a CSV export cell against formula injection (CWE-1236): a cell whose
text starts with =, +, -, @, or a tab/carriage return is interpreted as a
formula by Excel/Google Sheets/LibreOffice when the file is opened, not shown
as the text it actually is. A family member's own name, or a broker's name
pulled from an import, is free text an account holder or a CSV import
controls — "=HYPERLINK(...)" as a name is a realistic way for a report opened
later by an admin to exfiltrate other cells or chain into a DDE/macro issue in
older spreadsheet software.

Prefixing the value with a bare quote forces spreadsheet software to render
it as literal text instead of evaluating it, without changing what a human
reading the CSV as plain text sees.
"""

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value) -> str:
    """The value as a string, safe to put in a CSV cell a spreadsheet app
    might open: still the same text, but never evaluated as a formula."""
    s = "" if value is None else str(value)
    return "'" + s if s and s[0] in _FORMULA_PREFIXES else s
