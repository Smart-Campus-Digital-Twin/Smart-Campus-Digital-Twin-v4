"""
Dataset verification script — checks all three generated CSVs against
expected patterns from the simulator logic.
"""

import csv
import sys
import time
from datetime import datetime

def bar(done: int, total: int, width: int = 38) -> None:
    filled = int(width * done / total)
    pct    = 100 * done / total
    sys.stdout.write(
        f"\r  [{'█' * filled}{'░' * (width - filled)}] {pct:5.1f}%  ({done}/{total})"
    )
    sys.stdout.flush()


def section(title: str) -> None:
    print(f"\n{'═' * (len(title) + 6)}")
    print(f"   {title}")
    print(f"{'═' * (len(title) + 6)}")


def show(results: list) -> int:
    print()
    for name, detail, ok in results:
        sym = "✓" if ok else "✗"
        print(f"  {sym}  {name:<32}  {detail}")
    passed = sum(1 for _, _, ok in results if ok)
    print(f"\n  {passed}/{len(results)} checks passed")
    return passed


def get_hour_of_day(row: dict) -> float:
    dt = datetime.fromisoformat(row["timestamp"])
    return dt.hour + dt.minute / 60.0


def occ_ratio(row: dict) -> float:
    cap = float(row.get("capacity") or 0)
    avg = float(row.get("avg") or 0)
    return avg / cap if cap else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Dataset 1 — Canteen
# ─────────────────────────────────────────────────────────────────────────────
section("DATASET 1  canteen_congestion_2024_2025.csv")
results = []

with open("ml/datasets/canteen_congestion_2024_2025.csv") as f:
    rows = list(csv.DictReader(f))

TOTAL = 8
bar(0, TOTAL)

# 1  Row count
n = len(rows)
results.append(("Row count", f"{n:,}  (expected 140,352)", n == 140_352))
bar(1, TOTAL)

# 2  Room count
rooms = set(r["room_id"] for r in rows)
results.append(("Room count", f"{len(rooms)} rooms", len(rooms) == 4))
bar(2, TOTAL)

# 3  Midnight always closed (avg = 0)
mid = [r for r in rows if get_hour_of_day(r) == 0.0]
ok  = all(float(r["avg"]) == 0.0 for r in mid)
results.append(("Midnight avg = 0", f"{len(mid):,} midnight rows, all-zero = {ok}", ok))
bar(3, TOTAL)

# 4  Lunch peak on AW weekday (expect ~0.60+)
lunch_aw = [r for r in rows if get_hour_of_day(r) == 12.5
            and r["activity_type"] == "AW"
            and r["is_weekend"] == "0"
            and r["is_holiday"] == "0"]
avg_aw = sum(occ_ratio(r) for r in lunch_aw) / len(lunch_aw) if lunch_aw else 0
ok4    = avg_aw > 0.55
results.append(("AW lunch mean > 0.55",
                f"mean = {avg_aw:.4f}  ({len(lunch_aw)} rows)", ok4))
bar(4, TOTAL)

# 5  TUA period dampens canteen (May–Jul 2024, congestion_fraction ~ 0.63)
tua = [r for r in rows if r["tua_active"] == "1" and get_hour_of_day(r) == 12.5]
avg_tua = sum(occ_ratio(r) for r in tua) / len(tua) if tua else 0
ok5     = 0 < avg_tua < avg_aw * 0.90
results.append(("TUA lunch < AW lunch",
                f"TUA mean = {avg_tua:.4f}  AW mean = {avg_aw:.4f}", ok5))
bar(5, TOTAL)

# 6  Holiday rows → ~0.15 occupancy ratio (use hour 12.0 within operating window)
hol     = [r for r in rows if r["is_holiday"] == "1" and get_hour_of_day(r) == 12.0]
avg_hol = sum(occ_ratio(r) for r in hol) / len(hol) if hol else 0
ok6     = 0.10 < avg_hol < 0.22
results.append(("Holiday occ ≈ 0.15",
                f"mean = {avg_hol:.4f}  ({len(hol)} rows)", ok6))
bar(6, TOTAL)

# 7  Career fair gives canteen a boost: CF rows must beat same-period non-CF rows
#    (compare within each CF day vs a normal day with the same congestion_fraction)
cf_lunch = [r for r in rows if "career_fair" in r["active_events"].split("|")
            and get_hour_of_day(r) == 12.5
            and r["is_holiday"] == "0"]
avg_cf = sum(occ_ratio(r) for r in cf_lunch) / len(cf_lunch) if cf_lunch else 0
# Compare against rows with the same congestion_fraction range (±0.05)
cf_cong = sum(float(r["congestion_fraction"]) for r in cf_lunch) / len(cf_lunch) if cf_lunch else 0
same_cong = [r for r in rows if "career_fair" not in r["active_events"].split("|")
             and get_hour_of_day(r) == 12.5 and r["is_holiday"] == "0"
             and r["is_weekend"] == "0"
             and abs(float(r["congestion_fraction"]) - cf_cong) < 0.08]
avg_sc = sum(occ_ratio(r) for r in same_cong) / len(same_cong) if same_cong else 0
ok7    = avg_cf >= avg_sc * 0.98
results.append(("Career fair ≥ same-period baseline",
                f"CF={avg_cf:.4f}  same-cong={avg_sc:.4f}  ({len(same_cong)} ctrl rows)", ok7))
bar(7, TOTAL)

# 8  Food-festival active rows exist
ff = [r for r in rows if "food_festival" in r["active_events"].split("|")]
results.append(("Food-festival rows exist",
                f"{len(ff)} rows across 2024-2025", len(ff) > 0))
bar(8, TOTAL)

p1 = show(results)


# ─────────────────────────────────────────────────────────────────────────────
# Dataset 2 — Library
# ─────────────────────────────────────────────────────────────────────────────
section("DATASET 2  library_congestion_2024_2025.csv")
results2 = []

with open("ml/datasets/library_congestion_2024_2025.csv") as f:
    lib = list(csv.DictReader(f))

TOTAL = 9
bar(0, TOTAL)

# 1  Row count
results2.append(("Row count",
         f"{len(lib):,}  (expected 105,264)", len(lib) == 105_264))
bar(1, TOTAL)

# 2  Room count
rooms2 = set(r["room_id"] for r in lib)
results2.append(("Room count", f"{len(rooms2)} rooms", len(rooms2) == 3))
bar(2, TOTAL)

# 3  Closed before 08:00
bef = [r for r in lib if get_hour_of_day(r) < 8.0]
ok  = all(float(r["avg"]) == 0.0 for r in bef)
results2.append(("Closed before 08:00",
         f"{len(bef):,} rows, all-zero = {ok}", ok))
bar(3, TOTAL)

# 4  Closed at or after 21:00
aft = [r for r in lib if get_hour_of_day(r) >= 21.0]
ok  = all(float(r["avg"]) == 0.0 for r in aft)
results2.append(("Closed ≥ 21:00",
         f"{len(aft):,} rows, all-zero = {ok}", ok))
bar(4, TOTAL)

# 5  Post-lecture evening peak (17:30 AW weekday) > 0.45
eve     = [r for r in lib if get_hour_of_day(r) == 17.5
       and r["activity_type"] == "AW"
       and r["is_weekend"] == "0" and r["is_holiday"] == "0"]
avg_eve = sum(occ_ratio(r) for r in eve) / len(eve) if eve else 0
ok5     = avg_eve > 0.45
results2.append(("Evening peak (17:30) > 0.45",
         f"mean = {avg_eve:.4f}  ({len(eve)} rows)", ok5))
bar(5, TOTAL)

# 6  Exam period boosts library vs normal evening
exam = [r for r in lib if r["is_exam_period"] == "1"
    and get_hour_of_day(r) == 18.0 and r["is_holiday"] == "0"]
norm = [r for r in lib if r["is_exam_period"] == "0"
    and r["activity_type"] == "AW"
    and get_hour_of_day(r) == 18.0
    and r["is_weekend"] == "0" and r["is_holiday"] == "0"]
avg_exam = sum(occ_ratio(r) for r in exam) / len(exam) if exam else 0
avg_norm = sum(occ_ratio(r) for r in norm) / len(norm) if norm else 0
ok6      = avg_exam > avg_norm
results2.append(("Exam > normal at 18:00",
         f"exam = {avg_exam:.4f}  normal = {avg_norm:.4f}", ok6))
bar(6, TOTAL)

# 7  Weekend traffic lower than weekday
wknd     = [r for r in lib if r["is_weekend"] == "1"
        and get_hour_of_day(r) == 14.0 and r["is_holiday"] == "0"]
wkdy     = [r for r in lib if r["is_weekend"] == "0"
        and r["activity_type"] == "AW"
        and get_hour_of_day(r) == 14.0 and r["is_holiday"] == "0"]
avg_wknd = sum(occ_ratio(r) for r in wknd) / len(wknd) if wknd else 0
avg_wkdy = sum(occ_ratio(r) for r in wkdy) / len(wkdy) if wkdy else 0
ok7      = avg_wknd < avg_wkdy
results2.append(("Weekend 14:00 < weekday",
         f"wknd = {avg_wknd:.4f}  wkdy = {avg_wkdy:.4f}", ok7))
bar(7, TOTAL)

# 8  Holiday occ ≈ 0.20 (use 14:00 within open window)
hol_lib  = [r for r in lib if r["is_holiday"] == "1" and get_hour_of_day(r) == 14.0]
avg_hl   = sum(occ_ratio(r) for r in hol_lib) / len(hol_lib) if hol_lib else 0
ok8      = 0.14 < avg_hl < 0.28
results2.append(("Holiday occ ≈ 0.20",
         f"mean = {avg_hl:.4f}  ({len(hol_lib)} rows)", ok8))
bar(8, TOTAL)

# 9  Career fair drains library: compare CF vs non-CF with same congestion level
cf_lib   = [r for r in lib if "career_fair" in r["active_events"].split("|")
        and get_hour_of_day(r) == 14.0 and r["is_holiday"] == "0"]
cf_cong2 = sum(float(r["congestion_fraction"]) for r in cf_lib) / len(cf_lib) if cf_lib else 0
non_cf   = [r for r in lib if "career_fair" not in r["active_events"].split("|")
        and get_hour_of_day(r) == 14.0 and r["is_holiday"] == "0"
        and r["is_weekend"] == "0"
        and abs(float(r["congestion_fraction"]) - cf_cong2) < 0.08]
avg_cfl  = sum(occ_ratio(r) for r in cf_lib) / len(cf_lib) if cf_lib else 0
avg_ncfl = sum(occ_ratio(r) for r in non_cf) / len(non_cf) if non_cf else 0
ok9      = avg_cfl <= avg_ncfl
results2.append(("Career fair drains library",
         f"CF={avg_cfl:.4f}  same-cong={avg_ncfl:.4f}  ({len(non_cf)} ctrl)", ok9))
bar(9, TOTAL)

p2 = show(results2)


# ─────────────────────────────────────────────────────────────────────────────
# Dataset 3 — Energy
# ─────────────────────────────────────────────────────────────────────────────
section("DATASET 3  energy_forecast_2024_2025.csv")
results3 = []

with open("ml/datasets/energy_forecast_2024_2025.csv") as f:
    eng = list(csv.DictReader(f))

TOTAL = 8
bar(0, TOTAL)

# 1  Row count — 2024 leap year (366) + 2025 (365) = 731 days
expected = 26 * 731 * 24
results3.append(("Row count",
                 f"{len(eng):,}  (expected {expected:,})", len(eng) == expected))
bar(1, TOTAL)

# 2  All 26 buildings present
blds = set(r["building_id"] for r in eng)
results3.append(("26 buildings present",
                 f"{len(blds)} found: {'ok' if len(blds)==26 else sorted(blds)}", len(blds) == 26))
bar(2, TOTAL)

# 3  All building_types assigned (no 'other')
types = set(r["building_type"] for r in eng)
ok3   = "other" not in types
results3.append(("No untyped buildings",
                 f"types = {sorted(types)}", ok3))
bar(3, TOTAL)

# 4  Server-room building never drops below standby
srv = [r for r in eng if r["building_id"] == "faculty-it"]
min_srv = min(float(r["total_energy_w"]) for r in srv)
ok4     = min_srv > 300      # faculty-it has a server room + many other rooms
results3.append(("faculty-it min energy > 300 W",
                 f"min = {min_srv:.1f} W", ok4))
bar(4, TOTAL)

# 5  goda-canteen night standby ≈ 80 W (1 room × 80 W standby)
goda_n = [r for r in eng if r["building_id"] == "goda-canteen"
          and get_hour_of_day(r) == 2.0]
avg_gn = sum(float(r["total_energy_w"]) for r in goda_n) / len(goda_n) if goda_n else 0
ok5    = 55 < avg_gn < 115
results3.append(("goda-canteen night ≈ 80 W",
                 f"mean = {avg_gn:.1f} W  ({len(goda_n)} rows)", ok5))
bar(5, TOTAL)

# 6  Academic building: lecture-hour energy > night energy (≥ 1.5×)
it_noon = [r for r in eng if r["building_id"] == "faculty-it"
           and get_hour_of_day(r) == 10.0
           and r["activity_type"] == "AW"
           and r["is_weekend"] == "0" and r["is_holiday"] == "0"]
it_nite = [r for r in eng if r["building_id"] == "faculty-it"
           and get_hour_of_day(r) == 2.0]
avg_noon = sum(float(r["total_energy_w"]) for r in it_noon) / len(it_noon) if it_noon else 0
avg_nite = sum(float(r["total_energy_w"]) for r in it_nite) / len(it_nite) if it_nite else 0
ok6      = avg_noon > avg_nite * 1.5
results3.append(("Lecture-hour > 1.5× night",
                 f"10h = {avg_noon:.0f} W   02h = {avg_nite:.0f} W", ok6))
bar(6, TOTAL)

# 7  Holiday reduces academic energy vs AW
hol_it = [r for r in eng if r["building_id"] == "faculty-it"
          and r["is_holiday"] == "1" and get_hour_of_day(r) == 10.0]
aw_it  = [r for r in eng if r["building_id"] == "faculty-it"
          and r["activity_type"] == "AW"
          and r["is_weekend"] == "0" and r["is_holiday"] == "0"
          and get_hour_of_day(r) == 10.0]
avg_h  = sum(float(r["total_energy_w"]) for r in hol_it) / len(hol_it) if hol_it else 0
avg_a  = sum(float(r["total_energy_w"]) for r in aw_it) / len(aw_it)   if aw_it  else 0
ok7    = avg_h < avg_a
results3.append(("Holiday energy < AW energy",
                 f"holiday = {avg_h:.0f} W   AW = {avg_a:.0f} W", ok7))
bar(7, TOTAL)

# 8  Library building standby at night (3 rooms × 40 W = 120 W)
lib_n = [r for r in eng if r["building_id"] == "library"
         and get_hour_of_day(r) == 3.0]
avg_ln = sum(float(r["total_energy_w"]) for r in lib_n) / len(lib_n) if lib_n else 0
ok8    = avg_ln > 100
results3.append(("Library night standby > 100 W",
                 f"mean = {avg_ln:.1f} W", ok8))
bar(8, TOTAL)

p3 = show(results3)


# ─────────────────────────────────────────────────────────────────────────────
# Grand total
# ─────────────────────────────────────────────────────────────────────────────
total = p1 + p2 + p3
print(f"\n{'═'*52}")
print(f"   GRAND TOTAL  {total}/25 checks passed")
print(f"{'═'*52}\n")
