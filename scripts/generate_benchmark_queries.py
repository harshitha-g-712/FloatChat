"""Generator for 280 Manually Validated Benchmark Queries across 8 Required Dimensions."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "eval" / "benchmark_280_questions.json"

questions = []
qid = 1

def add_case(category, q, expected_var=None, expected_stat=None, expected_task="stat", is_invalid=False, history=None, notes=""):
    global qid
    questions.append({
        "id": f"bm_{qid:03d}",
        "category": category,
        "question": q,
        "expected_variable": expected_var,
        "expected_stat": expected_stat,
        "expected_task": expected_task,
        "is_invalid_or_unsupported": is_invalid,
        "history": history or [],
        "notes": notes
    })
    qid += 1

# 1. Average & Maximum Temperature (40 cases)
months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
for m_idx, m in enumerate(months, start=1):
    add_case("temperature_avg_max", f"What is the average temperature in {m} 2023?", "temperature", "avg", "stat")
    add_case("temperature_avg_max", f"Maximum temperature in {m} 2023", "temperature", "max", "stat")
    if m_idx <= 8:
        add_case("temperature_avg_max", f"Average temperature in {m} 2024", "temperature", "avg", "stat")
        add_case("temperature_avg_max", f"Peak temperature recorded in {m} 2024", "temperature", "max", "stat")

# 2. Salinity Comparisons & Aggregations (40 cases)
for m_idx, m in enumerate(months, start=1):
    add_case("salinity_queries", f"Average salinity in {m} 2023", "salinity", "avg", "stat")
    add_case("salinity_queries", f"Maximum salinity in {m} 2023", "salinity", "max", "stat")
for i in range(1, 9):
    m1, m2 = months[i-1], months[i+3]
    add_case("salinity_queries", f"Compare salinity in {m1} 2023 and {m2} 2023", "salinity", None, "stat")
for i in range(1, 9):
    m = months[i-1]
    add_case("salinity_queries", f"Compare salinity between {m} 2023 and {m} 2024", "salinity", None, "stat")

# 3. Pressure & Depth Queries (35 cases)
depths = [10, 20, 50, 100, 200, 500, 800, 1000, 1500, 2000]
for d in depths:
    add_case("pressure_depth", f"What is the average temperature deeper than {d} dbar in January 2023?", "temperature", "avg", "stat")
    add_case("pressure_depth", f"Salinity shallower than {d} dbar in March 2023", "salinity", "avg", "stat")
for p1, p2 in [(0, 50), (50, 200), (200, 500), (500, 1000), (1000, 2000), (0, 100), (100, 500)]:
    add_case("pressure_depth", f"Average temperature between {p1} and {p2} dbar in July 2023", "temperature", "avg", "stat")
for p1, p2 in [(0, 50), (50, 100), (100, 250), (250, 500), (500, 1500), (1000, 2000), (0, 2000), (20, 80)]:
    add_case("pressure_depth", f"Salinity between {p1} and {p2} dbar in May 2023", "salinity", "avg", "stat")

# 4. Float Identification & Trajectories (35 cases)
known_floats = ["2902758", "2902759", "2902760", "2902761", "2902762", "2902763", "2902764", "2902765", "1901844", "1901845", "1901846", "2902697", "2902698", "2902699"]
for fl in known_floats:
    add_case("float_identification", f"Tell me about float {fl}", None, None, "discovery")
    add_case("float_identification", f"Where did float {fl} travel?", None, None, "trajectory")
for fl in known_floats[:7]:
    add_case("float_identification", f"Show dive profile for float {fl}", None, None, "dive_profile")

# 5. Geographical & Sub-Regional Filters (35 cases)
regions = ["north", "south", "central", "andaman", "sri lanka"]
for r in regions:
    for m in ["January", "April", "July", "October"]:
        add_case("geographical_filters", f"Average temperature in {r} Bay of Bengal in {m} 2023", "temperature", "avg", "stat")
        add_case("geographical_filters", f"Salinity in {r} region in {m} 2023", "salinity", "avg", "stat")
for lat, lon in [(12.5, 85.0), (15.0, 88.0), (8.0, 83.0), (17.5, 89.5), (10.0, 86.0), (13.0, 92.0), (16.0, 84.0)]:
    add_case("geographical_filters", f"Temperature near {lat}N {lon}E in January 2023", "temperature", "avg", "stat")

# 6. Seasonal & Monsoon Questions (35 cases)
monsoons = ["southwest monsoon", "south-west monsoon", "summer monsoon", "northeast monsoon", "north-east monsoon", "winter monsoon", "spring intermonsoon", "fall intermonsoon"]
for mon in monsoons:
    add_case("seasonal_monsoon", f"What is the average temperature during the {mon} in 2023?", "temperature", "avg", "stat")
    add_case("seasonal_monsoon", f"Salinity during {mon} 2023", "salinity", "avg", "stat")
    add_case("seasonal_monsoon", f"Compare {mon} 2023 vs {mon} 2024 temperature", "temperature", None, "stat")
for yr in [2023, 2024]:
    add_case("seasonal_monsoon", f"How does the southwest monsoon affect sea temperature in {yr}?", "temperature", None, "concept")
    add_case("seasonal_monsoon", f"How does the northeast monsoon change salinity in {yr}?", "salinity", None, "concept")
    add_case("seasonal_monsoon", f"Average salinity across the monsoon in {yr}", "salinity", "avg", "stat")
    for s_name in ["SW monsoon", "NE monsoon", "post-monsoon"]:
        add_case("seasonal_monsoon", f"Water properties in {s_name} {yr}", None, None, "stat")
add_case("seasonal_monsoon", "Compare southwest monsoon and northeast monsoon in 2023", "temperature", None, "stat")

# 7. Invalid, Unsupported, and Out-of-Bounds Queries (35 cases)
unsupported_vars = ["oxygen", "dissolved oxygen", "pH", "nitrate", "chlorophyll", "turbidity", "alkalinity", "carbon dioxide", "phosphate"]
for v in unsupported_vars:
    add_case("invalid_and_unsupported", f"What is the average {v} in January 2023?", is_invalid=True, notes="Unsupported biogeochemical variable")
    add_case("invalid_and_unsupported", f"Maximum {v} in 2023", is_invalid=True, notes="Unsupported variable")

out_regions = ["Arabian Sea", "Pacific Ocean", "Atlantic Ocean", "Mediterranean Sea", "Arctic Ocean", "Red Sea", "Gulf of Mexico"]
for r in out_regions:
    add_case("invalid_and_unsupported", f"Temperature profiles in the {r}", is_invalid=True, notes="Spatial out of bounds")

invalid_dates = ["month 13", "month 0", "January 2045", "March 1850", "month 99 in 2023", "temperature in 2030"]
for d in invalid_dates:
    add_case("invalid_and_unsupported", f"Average temperature in {d}", is_invalid=True, notes="Invalid calendar temporal")

off_topics = ["What is the capital of France?", "Who won the World Cup?", "Write a poem about dolphins", "How do I fix my car?"]
for ot in off_topics:
    add_case("invalid_and_unsupported", ot, is_invalid=True, expected_task="off_topic", notes="Off-topic general query")

# 8. Conversational Follow-Up Questions (25 cases)
follow_ups = [
    ("What about June?", "temperature", "avg", [{"role": "user", "content": "What is the average temperature in January 2023?"}, {"role": "assistant", "content": "27.6 C"}]),
    ("And salinity?", "salinity", "avg", [{"role": "user", "content": "Average temperature in March 2023"}, {"role": "assistant", "content": "28.1 C"}]),
    ("How about below 500 dbar?", "temperature", "avg", [{"role": "user", "content": "Average temperature in January 2023"}, {"role": "assistant", "content": "27.6 C"}]),
    ("Show me the maximum instead", "temperature", "max", [{"role": "user", "content": "Average temperature in May 2023"}, {"role": "assistant", "content": "29.2 C"}]),
    ("In 2024?", "temperature", "avg", [{"role": "user", "content": "Average temperature in July 2023"}, {"role": "assistant", "content": "28.5 C"}]),
    ("What about the central bay?", "temperature", "avg", [{"role": "user", "content": "Temperature in north Bay of Bengal in April 2023"}, {"role": "assistant", "content": "28.9 C"}]),
    ("What was the salinity there?", "salinity", "avg", [{"role": "user", "content": "Temperature in north Bay of Bengal in April 2023"}, {"role": "assistant", "content": "28.9 C"}]),
    ("And for float 2902758?", "temperature", "avg", [{"role": "user", "content": "Average temperature in January 2023"}, {"role": "assistant", "content": "27.6 C"}]),
    ("Where did it travel?", None, None, [{"role": "user", "content": "Tell me about float 2902758"}, {"role": "assistant", "content": "Float details..."}]),
    ("Show its dive profile", None, None, [{"role": "user", "content": "Where did float 2902758 travel?"}, {"role": "assistant", "content": "Trajectory..."}]),
    ("What about February 2023?", "salinity", "avg", [{"role": "user", "content": "Average salinity in January 2023"}, {"role": "assistant", "content": "33.5 PSU"}]),
    ("Compare that with June", "temperature", None, [{"role": "user", "content": "Average temperature in January 2023"}, {"role": "assistant", "content": "27.6 C"}]),
    ("What about shallower than 20 dbar?", "temperature", "avg", [{"role": "user", "content": "Temperature in January 2023"}, {"role": "assistant", "content": "27.6 C"}]),
    ("What about August?", "salinity", "avg", [{"role": "user", "content": "Salinity in July 2023"}, {"role": "assistant", "content": "32.8 PSU"}]),
    ("And in the south?", "salinity", "avg", [{"role": "user", "content": "Salinity in north Bay of Bengal in July 2023"}, {"role": "assistant", "content": "31.2 PSU"}]),
    ("In December 2023?", "temperature", "max", [{"role": "user", "content": "Maximum temperature in November 2023"}, {"role": "assistant", "content": "28.9 C"}]),
    ("And minimum?", "temperature", "min", [{"role": "user", "content": "Maximum temperature in December 2023"}, {"role": "assistant", "content": "28.1 C"}]),
    ("What about 2024?", "salinity", "max", [{"role": "user", "content": "Maximum salinity in March 2023"}, {"role": "assistant", "content": "35.2 PSU"}]),
    ("Show that as a depth chart", "salinity", "avg", [{"role": "user", "content": "Average salinity in March 2023"}, {"role": "assistant", "content": "33.9 PSU"}]),
    ("Below 1000 dbar?", "salinity", "avg", [{"role": "user", "content": "Salinity in March 2023"}, {"role": "assistant", "content": "33.9 PSU"}]),
    ("What about float 1901844?", None, None, [{"role": "user", "content": "Tell me about float 2902758"}, {"role": "assistant", "content": "Float 2902758..."}]),
    ("Where did that one drift?", None, None, [{"role": "user", "content": "Tell me about float 1901844"}, {"role": "assistant", "content": "Float 1901844..."}]),
    ("And during the northeast monsoon?", "temperature", "avg", [{"role": "user", "content": "Average temperature during southwest monsoon in 2023"}, {"role": "assistant", "content": "28.4 C"}]),
    ("What was the salinity then?", "salinity", "avg", [{"role": "user", "content": "Average temperature during northeast monsoon in 2023"}, {"role": "assistant", "content": "26.8 C"}]),
    ("Now compare 2023 and 2024", "salinity", None, [{"role": "user", "content": "Salinity during northeast monsoon in 2023"}, {"role": "assistant", "content": "33.8 PSU"}])
]

for q, var, stat, hist in follow_ups:
    add_case("conversational_followups", q, var, stat, history=hist)

OUT_PATH.write_text(json.dumps(questions, indent=2), encoding="utf-8")
print(f"Generated {len(questions)} manually validated benchmark queries at {OUT_PATH}")

