#!/usr/bin/env python3
"""Convert a legacy Oracle exp backup into the grocery STOCK CSV for Tariq Mart.

Only STOCK is read (STOCK2/medicine inventory is excluded). RATE is exported as
retail_price per the store's confirmed mapping. PRATE and RTLRATE are ignored.
"""
from __future__ import annotations

import argparse
import csv
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARSER_JAR = ROOT / "vendor" / "oracledmpparser-0.0.8.jar"


def grocery_category(name: str) -> str:
    text = name.casefold()
    groups = [
        ("Fresh Produce", ("vegetable", "tomato", "potato", "onion", "fruit", "mango", "apple", "banana")),
        ("Dairy & Bakery", ("milk", "egg", "bread", "bun", "cake", "biscuit", "cream", "butter", "yogurt", "curd")),
        ("Personal Care", ("shampoo", "sunsilk", "palmolive", "soap", "toothpaste", "tooth brush", "toothbrush", "face wash", "deodorant", "anti lice", "hair color", "conditioner", "lotion")),
        ("Cleaning & Household", ("detergent", "washing powder", "washing soap", "dishwash", "dish wash", "bleach", "floor cleaner", "match", "tissue", "toilet cleaner", "surf excel", "brite", "vim")),
        ("Tea & Coffee", ("tea", "chai", "coffee", "nescafe", "lipton", "tapal", "deer tea", "danedar")),
        ("Grocery & Pantry", ("rice", "daal", "dal ", "chana", "lentil", "flour", "atta", "maida", "sugar", "salt", "ghee", "oil", "masala", "spice", "besan", "pulse", "bean", "noodle", "pasta", "ketchup", "sauce", "pickle", "biryani", "cereal", "corn", "gram", "pea", "wheat", "sago", "suji", "semolina")),
        ("Snacks & Sweets", ("chips", "snack", "chocolate", "candy", "toffee", "sweet", "nimco", "nimko", "wafer", "chewing gum")),
        ("Drinks", ("juice", "water", "drink", "cola", "pepsi", "coke", "soda", "7up", "dew", "sting", "rooh afza")),
    ]
    for category, keywords in groups:
        if any(keyword in text for keyword in keywords):
            return category
    return "Other Grocery"


def text_value(item):
    value = item.stringValue
    return str(value).strip() if value is not None else ""


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("backup", type=Path, help="Oracle legacy .DMP backup")
    cli.add_argument("csv_file", type=Path, help="CSV destination")
    args = cli.parse_args()
    if not args.backup.is_file():
        cli.error(f"backup file does not exist: {args.backup}")
    if not PARSER_JAR.is_file():
        cli.error(f"bundled parser jar is missing: {PARSER_JAR}")
    try:
        import jpype
    except ImportError:
        cli.error("Install converter requirements first: python -m pip install -r tools/requirements-dmp-converter.txt")

    image_matches = {}
    mapping_file = ROOT / "product_image_matches.csv"
    if mapping_file.is_file():
        with mapping_file.open(encoding="utf-8-sig", newline="") as mapping_stream:
            image_matches = {row["sku"].strip(): row["image_url"].strip() for row in csv.DictReader(mapping_stream) if row.get("sku") and row.get("image_url")}

    try:
        if not jpype.isJVMStarted():
            jpype.startJVM(classpath=[str(PARSER_JAR)])
        Parser = jpype.JClass("com.jansensystems.oracledmpparser.DMPParser")
        FileInputStream = jpype.JClass("java.io.FileInputStream")
        Arrays = jpype.JClass("java.util.Arrays")
        parser = Parser()
        stream = FileInputStream(str(args.backup.resolve()))
        try:
            tables = parser.parseFile(stream, Arrays.asList("STOCK"))
        finally:
            stream.close()
        if not tables:
            raise ValueError("No STOCK table was found in this Oracle export.")
        table = tables[0]
        positions = {str(name).upper(): index for index, name in enumerate(table.fieldNames)}
        required = {"ITEMCODE", "ITEMNAME", "QTY", "RATE"}
        missing = required - positions.keys()
        if missing:
            raise ValueError("The STOCK table is missing required fields: " + ", ".join(sorted(missing)))

        output = args.csv_file.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        written = skipped_no_rate = clamped_negative = 0
        seen_codes = set()
        with output.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(["sku", "name", "quantity", "retail_price", "pack_size", "brand", "category", "image_url"])
            for row_number, record in enumerate(table.dataRows, start=1):
                items = record.items
                sku = text_value(items[positions["ITEMCODE"]])
                name = text_value(items[positions["ITEMNAME"]])
                raw_quantity = text_value(items[positions["QTY"]])
                raw_rate = text_value(items[positions["RATE"]])
                if not sku or not name:
                    continue
                if sku in seen_codes:
                    raise ValueError(f"Duplicate ITEMCODE {sku!r} in STOCK row {row_number}.")
                seen_codes.add(sku)
                if not raw_rate:
                    skipped_no_rate += 1
                    continue
                try:
                    quantity_decimal = Decimal(raw_quantity or "0")
                    rate = Decimal(raw_rate)
                except InvalidOperation as exc:
                    raise ValueError(f"Unrecognized QTY/RATE value in STOCK row {row_number} for {sku}.") from exc
                if not rate.is_finite() or rate <= 0:
                    skipped_no_rate += 1
                    continue
                quantity = int(quantity_decimal)
                if Decimal(quantity) != quantity_decimal:
                    raise ValueError(f"Non-whole inventory quantity in STOCK row {row_number} for {sku}.")
                if quantity < 0:
                    quantity = 0
                    clamped_negative += 1
                pack_size = text_value(items[positions["PSIZE"]]) if "PSIZE" in positions else ""
                brand = text_value(items[positions["MNF"]]) if "MNF" in positions else ""
                category = text_value(items[positions["CATAGRY"]]) if "CATAGRY" in positions else ""
                category = category or grocery_category(name)
                writer.writerow([sku, name, quantity, f"{rate:.2f}", pack_size, brand, category, image_matches.get(sku, "")])
                written += 1
        print(f"Converted STOCK only: {written} rows; skipped {skipped_no_rate} items without a positive RATE; negative quantities set to zero: {clamped_negative}.")
        print("RATE became retail_price. RTLRATE, PRATE, and STOCK2 were not read.")
        print(f"CSV: {output}")
        return 0
    except Exception as exc:
        print(f"Conversion failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
