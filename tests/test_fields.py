import os
import sys

from src.multimodal.fields import extract_fields
from src.multimodal.ocr import OcrPage, OcrWord

failures = []


def check(name, actual, expected):
    status = "PASS" if actual == expected else "FAIL"
    print(f"{status}: {name} (got {actual!r}, expected {expected!r})")
    if actual != expected:
        failures.append(name)


def make_page(lines):
    words = []
    for line_index, line in enumerate(lines):
        items = [(text, 92.0) for text in line.split()] if isinstance(line, str) else line
        left = 0
        for text, confidence in items:
            words.append(
                OcrWord(
                    text=text,
                    confidence=confidence,
                    left=left,
                    top=line_index * 30,
                    width=len(text) * 10,
                    height=20,
                    line_key=(0, 0, line_index),
                )
            )
            left += len(text) * 10 + 10
    return OcrPage(
        words=words, width=1000, height=2000, sharpness=500.0,
        rotation_degrees=0.0, elapsed_seconds=0.1,
    )


def values(result, kind):
    return [item.value for item in result.of_kind(kind)]


# A: the clean test invoice (the colon after "Product" is missing, as in the blur-3 scan)
result = extract_fields(make_page([
    "INVOICE",
    "Order ID: 78231",
    "Date: 03/10/2026",
    "Amount: Rs 4500.00",
    "Product Wireless Mouse WM-200",
    "Error code: E-502",
]))
check("A order id", values(result, "order_id"), ["78231"])
check("A date", values(result, "date"), ["2026-10-03"])
check("A date flagged ambiguous", result.first("date").flags, ("ambiguous_day_month",))
check("A date alternative", result.first("date").alternatives, ("2026-03-10",))
check("A amount", [(i.value, i.label, i.flags) for i in result.of_kind("amount")],
      [("4500.00", "amount", ("currency_marked",))])
check("A error code", values(result, "error_code"), ["E-502"])
check("A product", values(result, "product"), ["Wireless Mouse WM-200"])

# B: the Amazon screenshot, with rupee signs misread as digits or symbols
result = extract_fields(make_page([
    "Return window closed on 24 September 2026",
    "~809.00",
    "Order placed 9 September 2026",
    "Order number 404-9349228-5677929",
    "Item(s) Subtotal: 2809.00",
    "Shipping: %40.00",
    "Marketplace Fee: 23.25",
    "Total: 3852.25",
    "Promotion Applied: -%80.45",
    "Grand Total: 2771.80",
    "Ask Product Question",
    "Write a product review",
]))
check("B order id", values(result, "order_id"), ["404-9349228-5677929"])
check("B dates", values(result, "date"), ["2026-09-24", "2026-09-09"])
check("B date labels", [i.label for i in result.of_kind("date")],
      ["return window closed on", "order placed"])
by_label = {item.label: item for item in result.of_kind("amount")}
check("B grand total value", by_label["grand total"].value, "2771.80")
check("B grand total flags", by_label["grand total"].flags, ("possible_currency_fusion",))
check("B grand total alternative", by_label["grand total"].alternatives, ("771.80",))
check("B subtotal alternative", by_label["subtotal"].alternatives, ("809.00",))
check("B marketplace fee alternative", by_label["marketplace fee"].alternatives, ("3.25",))
check("B total alternative", by_label["total"].alternatives, ("852.25",))
check("B shipping", (by_label["shipping"].value, by_label["shipping"].flags, by_label["shipping"].alternatives),
      ("40.00", ("currency_symbol_misread",), ()))
check("B promotion is negative", by_label["promotion applied"].value, "-80.45")
check("B unlabelled price", (by_label[""].value, by_label[""].flags), ("809.00", ("currency_symbol_misread",)))
check("B no products from button text", values(result, "product"), [])
check("B no error codes", values(result, "error_code"), [])

# C: the receipt text; phone, tax ID, table header and promo code must not become fields
result = extract_fields(make_page([
    "Bill No.: 36260",
    "Date 22/12/25",
    "Sub Total 104.76",
    "Grand Total \u20b9110.00",
    "GSTIN: 32FJQPR0134G1Z8 PH: 8590660960",
    "Item: Qty Price Amount",
    "Promo code: SAVE20",
]))
check("C order id", values(result, "order_id"), ["36260"])
check("C date", [(i.value, i.flags) for i in result.of_kind("date")], [("2025-12-22", ())])
check("C amounts", values(result, "amount"), ["104.76", "110.00"])
check("C no fusion without misread evidence", [i.alternatives for i in result.of_kind("amount")], [(), ()])
check("C no product from header", values(result, "product"), [])
check("C no error code from promo code", values(result, "error_code"), [])

# D: low OCR confidence is flagged
result = extract_fields(make_page([[("Order", 92.0), ("ID:", 92.0), ("78231", 40.0)]]))
check("D low confidence flag", result.first("order_id").flags, ("low_confidence",))
check("D confidence value", result.first("order_id").confidence, 40.0)

# E: values that must not be accepted as order IDs
result = extract_fields(make_page(["Order ID: abcdef", "Bill No Date", "Order ID: 22/12/2025"]))
check("E rejected order ids", values(result, "order_id"), [])

# F: date formats and invalid dates
result = extract_fields(make_page([
    "Delivered on 5/5/2026",
    "Sept 9, 2026",
    "Due 31/02/2026",
    "Paid 13/25/2026",
    "2026-10-03",
]))
check("F dates", values(result, "date"), ["2026-05-05", "2026-09-09", "2026-10-03"])
check("F same day and month is not ambiguous", result.first("date").flags, ())

os.environ["DOCUMENT_DATE_ORDER"] = "MDY"
result = extract_fields(make_page(["Date: 03/10/2026"]))
check("F month-first value", (result.first("date").value, result.first("date").alternatives),
      ("2026-03-10", ("2026-10-03",)))
os.environ.pop("DOCUMENT_DATE_ORDER")

# G: error codes
result = extract_fields(make_page([
    "Payment failed E1001",
    "Error: Something went wrong",
    "Error 502",
    "Status code: 0x80070005",
    "Promo code: SAVE20",
]))
check("G error codes", values(result, "error_code"), ["E1001", "502", "0x80070005"])

# H: products
result = extract_fields(make_page([
    "Product: Wireless Mouse",
    "Product: Details",
    "Model: WM-200",
    "Description: Qty Price",
]))
check("H products", values(result, "product"), ["Wireless Mouse", "WM-200"])

# I: amounts with currency markers, negatives, and numbers that are not amounts
result = extract_fields(make_page([
    "Pay Rs 4500 now",
    "Refund of INR 1,250.50",
    "Price 12.5",
    "Version 3.2.1",
    "Discount: -80.00",
    "Total: 3852.25",
]))
check("I amounts", [(i.value, i.label) for i in result.of_kind("amount")],
      [("4500.00", ""), ("1250.50", "refund"), ("-80.00", "discount"), ("3852.25", "total")])
check("I no fusion without misread evidence", [i.alternatives for i in result.of_kind("amount")],
      [(), (), (), ()])

if failures:
    print(f"\n{len(failures)} check(s) failed: {failures}")
    sys.exit(1)

print("\nAll checks passed.")