from database.db_utils import get_connection

con = get_connection()

columns = [
    ("close", "DOUBLE"),
    ("volume", "BIGINT"),
    ("return_1d", "DOUBLE"),
    ("return_5d", "DOUBLE"),
    ("return_20d", "DOUBLE"),
    ("return_50d", "DOUBLE"),
    ("volume_ratio", "DOUBLE"),
    ("new_high_252", "BOOLEAN"),
    ("new_low_252", "BOOLEAN"),
    ("above_ema20", "BOOLEAN"),
    ("above_ema50", "BOOLEAN"),
    ("above_ema150", "BOOLEAN"),
    ("above_ema200", "BOOLEAN"),
]

for name, dtype in columns:
    try:
        con.execute(
            f"ALTER TABLE features.technical_features ADD COLUMN {name} {dtype}"
        )
        print(f"Added {name}")
    except Exception:
        print(f"{name} already exists")

con.close()

print("Done.")