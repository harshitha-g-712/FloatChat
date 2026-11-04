"""Prints the true numbers (straight from SQL) for questions you can ask the website.

Put this file in the FloatChatNew folder and run:   python check_numbers.py
Then ask the same questions on the site and compare. Both values should match.
"""
import sqlite3

DB = "backend/floatchat.db"
c = sqlite3.connect(DB)
J = "FROM measurements m JOIN profiles p ON p.id = m.profile_id"


def avg(col, lo, hi, pmax=50):
    return c.execute(f"SELECT ROUND(AVG(m.{col}),3), COUNT(m.{col}) {J} WHERE p.timestamp >= ? AND p.timestamp < ? "
                     f"AND m.pressure <= ? AND m.{col} IS NOT NULL", (lo, hi, pmax)).fetchone()


def mx(col, lo, hi):
    return c.execute(f"SELECT MAX(m.{col}), COUNT(m.{col}) {J} WHERE p.timestamp >= ? AND p.timestamp < ? "
                     f"AND m.{col} IS NOT NULL", (lo, hi)).fetchone()


print("Database window:", c.execute("SELECT MIN(timestamp), MAX(timestamp) FROM profiles").fetchone())
print("Floats / profiles:", c.execute("SELECT COUNT(DISTINCT platform), COUNT(*) FROM profiles").fetchone())
print("Floats / profiles WITH measurements:",
      c.execute("SELECT COUNT(DISTINCT p.platform), COUNT(DISTINCT p.id) " + J).fetchone())
print()
print("Q: Average temperature in March 2024            (value, observations):", avg("temperature", "2024-03-01", "2024-04-01"))
print("Q: What was the average salinity in February 2023?                    :", avg("salinity", "2023-02-01", "2023-03-01"))
print("Q: Compare salinity between July 2023 and July 2024  Jul 2023 :", avg("salinity", "2023-07-01", "2023-08-01"))
print("                                                      Jul 2024 :", avg("salinity", "2024-07-01", "2024-08-01"))
print("Q: Compare average temperature 2023 vs 2024          2023      :", avg("temperature", "2023-01-01", "2024-01-01"))
print("                                                      2024      :", avg("temperature", "2024-01-01", "2025-01-01"))
print("Q: Average temperature in the north-east monsoon (Oct 2023-Jan 2024):", avg("temperature", "2023-10-01", "2024-02-01"))
print("Q: Average salinity in the south-west monsoon 2024 (Jun-Sep)        :", avg("salinity", "2024-06-01", "2024-10-01"))
print("Q: Maximum salinity in April 2024 (all depths)                       :", mx("salinity", "2024-04-01", "2024-05-01"))
print("Q: Maximum temperature in May 2023 (all depths)                      :", mx("temperature", "2023-05-01", "2023-06-01"))
print("Q: How many profiles in April 2024 (with measurements)              :",
      c.execute(f"SELECT COUNT(DISTINCT p.id) {J} WHERE p.timestamp >= '2024-04-01' AND p.timestamp < '2024-05-01'").fetchone()[0])
print("\nMonthly mean temperature, upper 50 dbar (for 'Warmest month in the data'):")
for ym, v, n in c.execute(f"SELECT substr(p.timestamp,1,7), ROUND(AVG(m.temperature),2), COUNT(m.temperature) {J} "
                          "WHERE m.pressure <= 50 AND m.temperature IS NOT NULL GROUP BY 1 ORDER BY 1"):
    print(f"  {ym}  {v}  ({n} obs)")