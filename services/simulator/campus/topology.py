from dataclasses import dataclass, field


@dataclass
class Room:
    room_id: str
    building_id: str
    floor: int
    room_type: str   # classroom | lab | office | canteen | auditorium | hostel | outdoor | library | server_room
    capacity: int
    sensors: list[str] = field(default_factory=list)


@dataclass
class Building:
    building_id: str
    name: str
    rooms: list[Room] = field(default_factory=list)


# Sensor bundles
STANDARD   = ["temperature", "occupancy", "energy"]   # classrooms, labs, offices, halls
OUTDOOR    = ["occupancy"]                              # open-air spaces
SERVER     = ["temperature", "energy"]                  # server rooms (no human occupancy)


def _room(bld_id: str, floor: int, suffix: str, room_type: str, capacity: int, sensors: list[str]) -> Room:
    return Room(f"{bld_id}-f{floor}-{suffix}", bld_id, floor, room_type, capacity, sensors)


def _acad_floors(
    bld_id: str,
    n_floors: int,
    cls_cap: int,
    lab_cap: int = 0,
    has_lab: bool = True,
    n_cls: int = 2,
    n_labs: int = 1,
    office_cap: int = 12,
) -> list[Room]:
    """
    Academic block generator.

    Per floor: n_cls classrooms + 1 office + (n_labs labs if has_lab).
    Classroom suffixes: cls-a, cls-b, …  Lab suffixes: lab (single) or lab-1, lab-2, …
    """
    rooms: list[Room] = []
    for f in range(1, n_floors + 1):
        for ci in range(n_cls):
            suffix = f"cls-{chr(ord('a') + ci)}"
            rooms.append(_room(bld_id, f, suffix, "classroom", cls_cap, STANDARD))
        rooms.append(_room(bld_id, f, "office", "office", office_cap, STANDARD))
        if has_lab and lab_cap > 0:
            for li in range(n_labs):
                lab_sfx = f"lab-{li + 1}" if n_labs > 1 else "lab"
                rooms.append(_room(bld_id, f, lab_sfx, "lab", lab_cap, STANDARD))
    return rooms


class CampusTopology:
    """
    26-zone University of Moratuwa campus topology.

    Capacities calibrated against uom_congestion_data.csv typical HIGH/PEAK weekday counts:
      Engineering depts  ~4 860 students total  (peak 5 400)
      IT Faculty         ~1 600 students         (peak 2 000)
      Architecture       ~2 700 students         (peak 2 900)
      Business Faculty   ~  750 students         (peak   800)
      Medicine Faculty   ~  560 students         (peak   560)
      Campus-wide max      10 320 students

    Rooms per building are sized so that concurrent classroom seats ≥ ~50 % of
    typical enrollment (peak single-slot demand), with labs at ~20 % of enrollment.
    """

    def __init__(self) -> None:
        self._buildings: dict[str, Building] = {}
        self._build()

    # ------------------------------------------------------------------
    def _build(self) -> None:

        # 1. Lagaan — outdoor theater, 700 cap, event-driven
        lagaan = Building("lagaan", "Lagaan Outdoor Theater")
        lagaan.rooms = [_room("lagaan", 1, "stage", "outdoor", 700, OUTDOOR)]

        # 2. Multipurpose Hall — 1000 cap auditorium
        mph = Building("multipurpose-hall", "Multipurpose Hall")
        mph.rooms = [_room("multipurpose-hall", 1, "main-hall", "auditorium", 1000, STANDARD)]

        # 3. Hostel A — women's hostel, 200 residents
        hostel_a = Building("hostel-a", "Hostel A (Women's)")
        hostel_a.rooms = [_room("hostel-a", 1, "block", "hostel", 200, STANDARD)]

        # ── Engineering departments ────────────────────────────────────────────
        # Combined typical: ~4 860  |  peak: ~5 400

        # 4. Dept of Textile & Clothing — ~480 students
        #    3 floors × (2 cls@65 + 1 lab@40 + office@12)
        textile = Building("dept-textile", "Dept of Textile & Clothing")
        textile.rooms = _acad_floors("dept-textile", 3, cls_cap=65, lab_cap=40)

        # 5. Dept of Transport & Logistics — ~480 students
        #    3 floors × (2 cls@65 + 1 lab@30 + office@12)
        transport = Building("dept-transport", "Dept of Transport & Logistics")
        transport.rooms = _acad_floors("dept-transport", 3, cls_cap=65, lab_cap=30)

        # 6. Dept of Civil Engineering — ~540 students
        #    3 floors × (2 cls@80 + 1 lab@40 + office@12)
        civil = Building("dept-civil", "Dept of Civil Engineering")
        civil.rooms = _acad_floors("dept-civil", 3, cls_cap=80, lab_cap=40)

        # 7. Sumanadasa Building (CS & Engineering) — ~900 students
        #    Floor 1:   generic academic (2 cls@100 + 1 lab@50 + office@15)
        #    Floor 2:   specific rooms per actual CSE floor plan
        #    Floor 3/4: generic academic (2 cls@100 + 1 lab@50 + office@15)
        sumanadasa = Building("sumanadasa", "Dept of CS & Engineering (Sumanadasa)")
        sumanadasa.rooms = (
            # Floors 1, 3, 4 — generic academic pattern
            [r for f in (1, 3, 4) for r in [
                _room("sumanadasa", f, "cls-a",  "classroom", 100, STANDARD),
                _room("sumanadasa", f, "cls-b",  "classroom", 100, STANDARD),
                _room("sumanadasa", f, "lab",    "lab",        50, STANDARD),
                _room("sumanadasa", f, "office", "office",     15, STANDARD),
            ]]
            # Floor 2 — specific rooms from CSE floor plan
            + [
                # Top row
                _room("sumanadasa", 2, "seminar",           "classroom",  100, STANDARD),
                _room("sumanadasa", 2, "codegen-lab",       "lab",         40, STANDARD),
                _room("sumanadasa", 2, "sysco-lounge",      "classroom",   30, STANDARD),
                _room("sumanadasa", 2, "insight-hub",       "lab",         50, STANDARD),
                _room("sumanadasa", 2, "network-lab",       "lab",         50, STANDARD),
                _room("sumanadasa", 2, "embedded-lab",      "lab",         30, STANDARD),
                _room("sumanadasa", 2, "hpc-lab",           "lab",         20, STANDARD),
                _room("sumanadasa", 2, "intellisense-lab",  "lab",         35, STANDARD),
                _room("sumanadasa", 2, "l3-lab",            "lab",        200, STANDARD),
                # Middle sections (staircases omitted — no sensors)
                _room("sumanadasa", 2, "studio",            "classroom",   20, STANDARD),
                _room("sumanadasa", 2, "oldcodegen-lab",    "lab",         30, STANDARD),
                _room("sumanadasa", 2, "open-area-n",       "classroom",   60, STANDARD),
                _room("sumanadasa", 2, "open-area-s",       "classroom",  100, STANDARD),
                _room("sumanadasa", 2, "instructor-room",   "office",      12, STANDARD),
                # Bottom row
                _room("sumanadasa", 2, "server",            "server_room",  0, SERVER),
                _room("sumanadasa", 2, "ice-room",          "office",      50, STANDARD),
                _room("sumanadasa", 2, "staff-room",        "office",      30, STANDARD),
                _room("sumanadasa", 2, "ra-lab",            "lab",         35, STANDARD),
                _room("sumanadasa", 2, "gtn-lab",           "lab",         40, STANDARD),
                _room("sumanadasa", 2, "research-lab",      "lab",         45, STANDARD),
            ]
        )

        # 8. Goda Canteen — 100 cap + overflow queue
        goda = Building("goda-canteen", "Goda Canteen")
        goda.rooms = [_room("goda-canteen", 1, "hall", "canteen", 100, STANDARD)]

        # 9. Sentra Court — 100 cap food court
        sentra = Building("sentra-court", "Sentra Court")
        sentra.rooms = [_room("sentra-court", 1, "court", "canteen", 100, STANDARD)]

        # 10. L Canteen — 40 cap
        l_canteen = Building("l-canteen", "L Canteen")
        l_canteen.rooms = [_room("l-canteen", 1, "hall", "canteen", 40, STANDARD)]

        # 11. Faculty of IT — ~1 600 students  (peak 2 000)
        #     4 floors × (2 cls@120 + 2 labs@60 + office@15) + server room on floor 5
        faculty_it = Building("faculty-it", "Faculty of Information Technology")
        faculty_it.rooms = (
            _acad_floors("faculty-it", 4, cls_cap=120, lab_cap=60, n_labs=2, office_cap=15)
            + [_room("faculty-it", 5, "server", "server_room", 0, SERVER)]
        )

        # 12. Hostel C — 500 residents
        hostel_c = Building("hostel-c", "Hostel C")
        hostel_c.rooms = [_room("hostel-c", 1, "block", "hostel", 500, STANDARD)]

        # 13. Faculty of Business Science — ~750 students  (peak 800)
        #     4 floors × (2 cls@100 + office@15)  — no wet labs
        business = Building("faculty-business", "Faculty of Business Science")
        business.rooms = _acad_floors("faculty-business", 4, cls_cap=100, has_lab=False, office_cap=15)

        # 14. Dept of Mathematics — working/service dept, ~60 staff + visitors
        #     2 floors, small seminar rooms used for service teaching (not student-congestion-driven)
        maths = Building("dept-maths", "Dept of Mathematics")
        maths.rooms = [
            _room("dept-maths", 1, "cls-a",   "office", 35, STANDARD),
            _room("dept-maths", 1, "cls-b",   "office", 35, STANDARD),
            _room("dept-maths", 2, "cls-c",   "office", 35, STANDARD),
            _room("dept-maths", 1, "office",  "office", 15, STANDARD),
            _room("dept-maths", 2, "office-b","office", 10, STANDARD),
        ]

        # 15. Faculty of Medicine — ~560 students  (peak 560)
        #     4 floors × (2 cls@75 + 1 lab@35 + office@12)
        medicine = Building("faculty-medicine", "Faculty of Medicine")
        medicine.rooms = _acad_floors("faculty-medicine", 4, cls_cap=75, lab_cap=35)

        # 16. Dept of Electronics & Telecom Engineering — ~720 students
        #     4 floors × (2 cls@80 + 1 lab@45 + office@12)
        ete = Building("dept-ete", "Dept of Electronics & Telecom Engineering")
        ete.rooms = _acad_floors("dept-ete", 4, cls_cap=80, lab_cap=45)

        # 17. NA lecture halls — lecture halls for Maths, 300 cap each
        na_hall = Building("na-hall", "NA Lecture Halls")
        na_hall.rooms = [
            _room("na-hall", 1, "na1", "classroom", 300, STANDARD),
            _room("na-hall", 2, "na2", "classroom", 300, STANDARD),
            _room("na-hall", 3, "na3", "classroom", 300, STANDARD),
        ]

        # 18. Wala Canteen — 200 cap
        wala = Building("wala-canteen", "Wala Canteen")
        wala.rooms = [_room("wala-canteen", 1, "hall", "canteen", 200, STANDARD)]

        # 19. Dept of Material Science & Engineering — ~540 students
        #     3 floors × (2 cls@70 + 1 lab@45 + office@12)
        material = Building("dept-material", "Dept of Material Science & Engineering")
        material.rooms = _acad_floors("dept-material", 3, cls_cap=70, lab_cap=45)

        # 20. Dept of Chemical & Process Engineering — ~540 students
        #     3 floors × (2 cls@70 + 1 lab@45 + office@12)
        chemical = Building("dept-chemical", "Dept of Chemical & Process Engineering")
        chemical.rooms = _acad_floors("dept-chemical", 3, cls_cap=70, lab_cap=45)

        # 21. Dept of Mechanical Engineering — ~540 students
        #     3 floors × (2 cls@70 + 1 lab@45 + office@12)
        mechanical = Building("dept-mechanical", "Dept of Mechanical Engineering")
        mechanical.rooms = _acad_floors("dept-mechanical", 3, cls_cap=70, lab_cap=45)

        # 22. Registrar Office & Examination — up to 300
        registrar = Building("registrar", "Registrar Office & Examination")
        registrar.rooms = [
            _room("registrar", 1, "exam-hall", "classroom", 150, STANDARD),
            _room("registrar", 1, "office-a",  "office",     25, STANDARD),
            _room("registrar", 1, "office-b",  "office",     25, STANDARD),
        ]

        # 23. Admin Building — up to 200 admin staff
        admin = Building("admin", "Admin Building")
        admin.rooms = [
            _room("admin", 1, "office-a", "office", 30, STANDARD),
            _room("admin", 1, "office-b", "office", 30, STANDARD),
            _room("admin", 2, "office-c", "office", 30, STANDARD),
            _room("admin", 2, "office-d", "office", 30, STANDARD),
            _room("admin", 2, "office-e", "office", 30, STANDARD),
        ]

        # 24. Dept of Integrated Design (Architecture) — ~2 700 students  (peak 2 900)
        #     5 floors × (2 cls@100 + 2 design-studios@50 + office@15)
        design = Building("dept-design", "Dept of Integrated Design")
        design.rooms = _acad_floors(
            "dept-design", 5, cls_cap=100, lab_cap=50, n_labs=2, office_cap=15
        )

        # 25. Faculty of Graduate Studies — ~300 students
        #     3 floors × (2 cls@50 + 1 lab@30 + office@15)
        grad = Building("faculty-grad", "Faculty of Graduate Studies")
        grad.rooms = _acad_floors("faculty-grad", 3, cls_cap=50, lab_cap=30, office_cap=15)

        # 26. Library — 1 000 students, 3 stories
        library = Building("library", "University Library")
        library.rooms = [
            _room("library", 1, "reading-hall",   "library", 400, STANDARD),
            _room("library", 2, "study-area",      "library", 350, STANDARD),
            _room("library", 3, "research-lounge", "library", 250, STANDARD),
        ]

        for bld in (
            lagaan, mph, hostel_a,
            textile, transport, civil, sumanadasa,
            goda, sentra, l_canteen,
            faculty_it, hostel_c, business,
            maths, medicine, ete, na_hall,
            wala, material, chemical, mechanical,
            registrar, admin, design, grad, library,
        ):
            self._buildings[bld.building_id] = bld

    # ------------------------------------------------------------------
    @property
    def buildings(self) -> dict[str, Building]:
        return self._buildings

    def all_rooms(self) -> list[Room]:
        return [r for bld in self._buildings.values() for r in bld.rooms]

    def rooms_with_sensor(self, sensor_type: str) -> list[Room]:
        return [r for r in self.all_rooms() if sensor_type in r.sensors]
