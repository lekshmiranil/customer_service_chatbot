import csv

path = "dataset/raw/dataset.csv"  # adjust path if needed

with open(path, newline='', encoding='utf-8', errors='replace') as f:
    reader = csv.reader(f)
    header = next(reader)
    expected_cols = len(header)
    print(f"Header: {header} ({expected_cols} columns)")

    try:
        for i, row in enumerate(reader, start=2):  # start=2 since header is line 1
            if len(row) != expected_cols:
                print(f"Line {i}: expected {expected_cols} columns, got {len(row)}")
                print(f"  Row content: {row}")
    except csv.Error as e:
        print(f"CSV parsing error near line {reader.line_num}: {e}")