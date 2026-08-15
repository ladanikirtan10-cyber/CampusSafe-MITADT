from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import sqlite3, os, math, random
from datetime import datetime, timedelta
from collections import Counter, defaultdict

try:
    from sklearn.cluster import DBSCAN
    SKLEARN_AVAILABLE = True
except Exception:
    SKLEARN_AVAILABLE = False

app = Flask(__name__)
CORS(app)
DB = os.path.join(os.path.dirname(__file__), "campussafe.db")

# MIT ADT University reference campus
# Coordinate anchor is the university's published/identified location area.
# Individual POI coordinates below are REFERENCE/APPROXIMATE until MIT ADT
# provides an official campus GIS/POI dataset. Do not present them as surveyed coordinates.
CAMPUS_CENTER = (18.49291445, 74.02548631)

CAMPUS_NODES = {
    "Main Campus": CAMPUS_CENTER,
    "Main Entrance": (18.49255, 74.02563),
    "Central Library / KRC": (18.49335, 74.02495),
    "Academic Zone": (18.49375, 74.02575),
    "Hostel Zone": (18.49195, 74.02655),
    "Girls Hostel Zone": (18.49220, 74.02710),
    "Boys Hostel Zone": (18.49170, 74.02690),
    "Sports Complex": (18.49420, 74.02680),
    "Vishwaraj Hospital": (18.49300, 74.02755),
    "Cafeteria / Mess": (18.49270, 74.02595),
    "Auditorium Zone": (18.49380, 74.02455),
    "World Peace Dome": (18.49435, 74.02420),
    "RK Memorial": (18.49345, 74.02375),
    "Boat Club / River Side": (18.49500, 74.02335),
    "Parking Zone": (18.49225, 74.02410),
    "Security Point": (18.49255, 74.02550),
}

GRAPH = {
    "Main Campus": ["Main Entrance", "Academic Zone", "Central Library / KRC"],
    "Main Entrance": ["Main Campus", "Parking Zone", "Security Point"],
    "Central Library / KRC": ["Main Campus", "Academic Zone", "Auditorium Zone", "Cafeteria / Mess"],
    "Academic Zone": ["Main Campus", "Central Library / KRC", "Hostel Zone", "Auditorium Zone"],
    "Hostel Zone": ["Academic Zone", "Girls Hostel Zone", "Boys Hostel Zone", "Sports Complex", "Vishwaraj Hospital"],
    "Girls Hostel Zone": ["Hostel Zone", "Boys Hostel Zone", "Vishwaraj Hospital"],
    "Boys Hostel Zone": ["Hostel Zone", "Girls Hostel Zone", "Sports Complex"],
    "Sports Complex": ["Hostel Zone", "Boys Hostel Zone", "Vishwaraj Hospital", "Boat Club / River Side"],
    "Vishwaraj Hospital": ["Hostel Zone", "Sports Complex", "Girls Hostel Zone"],
    "Cafeteria / Mess": ["Central Library / KRC", "Academic Zone", "Main Campus"],
    "Auditorium Zone": ["Central Library / KRC", "Academic Zone", "World Peace Dome", "RK Memorial"],
    "World Peace Dome": ["Auditorium Zone", "RK Memorial", "Boat Club / River Side"],
    "RK Memorial": ["World Peace Dome", "Auditorium Zone", "Boat Club / River Side"],
    "Boat Club / River Side": ["RK Memorial", "World Peace Dome", "Sports Complex"],
    "Parking Zone": ["Main Entrance", "Main Campus"],
    "Security Point": ["Main Entrance", "Main Campus"],
}

CAMPUS_FACILITIES = [
    {"name":"Central Library / KRC","category":"Academic","description":"Central knowledge resource/library area."},
    {"name":"Sports Complex","category":"Sports","description":"Sports complex including outdoor and indoor facilities."},
    {"name":"Hostel Zone","category":"Residential","description":"Residential campus zone."},
    {"name":"Girls Hostel Zone","category":"Residential","description":"Girls' hostel area; exact building coordinates require university GIS confirmation."},
    {"name":"Boys Hostel Zone","category":"Residential","description":"Boys' hostel area; exact building coordinates require university GIS confirmation."},
    {"name":"Vishwaraj Hospital","category":"Emergency","description":"In-campus multispecialty hospital / healthcare facility."},
    {"name":"Cafeteria / Mess","category":"Food","description":"In-campus cafeteria and mess facilities."},
    {"name":"Auditorium Zone","category":"Events","description":"Auditoriums and seminar halls."},
    {"name":"World Peace Dome","category":"Landmark","description":"Major campus landmark/event area."},
    {"name":"RK Memorial","category":"Landmark","description":"Raj Kapoor Memorial area."},
    {"name":"Boat Club / River Side","category":"Outdoor","description":"Boat club / riverside activity area."},
    {"name":"Parking Zone","category":"Transport","description":"Reference parking area; exact lots should be verified by campus administration."},
    {"name":"Main Entrance","category":"Access","description":"Reference campus entrance point."},
    {"name":"Security Point","category":"Security","description":"Reference security point; exact position requires official confirmation."},
]

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS incidents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reporter_name TEXT,
        anonymous INTEGER DEFAULT 1,
        category TEXT NOT NULL,
        severity INTEGER NOT NULL,
        description TEXT NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        occurred_at TEXT NOT NULL,
        status TEXT DEFAULT 'Open',
        evidence_url TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS interventions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        incident_id INTEGER,
        action TEXT NOT NULL,
        assigned_to TEXT,
        status TEXT DEFAULT 'Assigned',
        created_at TEXT NOT NULL,
        FOREIGN KEY (incident_id) REFERENCES incidents(id)
    );
    """)
    conn.commit()
    conn.close()

def haversine(lat1, lon1, lat2, lon2):
    r = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2-lat1)
    dlon = math.radians(lon2-lon1)
    a = math.sin(dlat/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlon/2)**2
    return 2*r*math.asin(math.sqrt(a))

def incidents():
    conn = db()
    rows = conn.execute("SELECT * FROM incidents ORDER BY occurred_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def risk_for_point(lat, lon, hour=None):
    data = incidents()
    if not data:
        return 5
    if hour is None:
        hour = datetime.now().hour
    score = 3.0
    for x in data:
        d = haversine(lat, lon, x["latitude"], x["longitude"])
        if d <= 0.5:
            distance_factor = max(0, 1 - d/0.5)
            age_days = max(0, (datetime.now() - datetime.fromisoformat(x["occurred_at"])).total_seconds()/86400)
            recency = max(0.15, 1 - age_days/90)
            time_gap = min(abs(hour-int(x["occurred_at"][11:13])), 24-abs(hour-int(x["occurred_at"][11:13])))
            time_factor = max(0.2, 1 - time_gap/12)
            score += x["severity"] * 5.5 * distance_factor * recency * time_factor
    return int(max(0, min(100, round(score))))

def blackspots():
    data = incidents()
    if not data:
        return []
    pts = [(x["latitude"], x["longitude"]) for x in data]
    clusters = []
    if SKLEARN_AVAILABLE and len(pts) >= 2:
        # Approximate earth distance using degrees for a small campus.
        labels = DBSCAN(eps=0.0011, min_samples=2).fit(pts).labels_
        for label in sorted(set(labels)):
            if label == -1:
                continue
            group = [data[i] for i, lab in enumerate(labels) if lab == label]
            clusters.append(group)
    else:
        # Simple fallback: greedy groups within ~120m.
        used = set()
        for i, a in enumerate(data):
            if i in used: continue
            group = [a]; used.add(i)
            for j, b in enumerate(data):
                if j in used: continue
                if haversine(a["latitude"], a["longitude"], b["latitude"], b["longitude"]) < 0.12:
                    group.append(b); used.add(j)
            if len(group) >= 2:
                clusters.append(group)
    out = []
    for idx, g in enumerate(clusters, 1):
        lat = sum(x["latitude"] for x in g)/len(g)
        lon = sum(x["longitude"] for x in g)/len(g)
        severity = sum(x["severity"] for x in g)/len(g)
        risk = min(100, int(len(g)*12 + severity*10))
        out.append({
            "id": idx, "latitude": round(lat, 6), "longitude": round(lon, 6),
            "incidents": len(g), "risk": risk,
            "label": "Critical" if risk >= 80 else "High" if risk >= 55 else "Medium"
        })
    return sorted(out, key=lambda z: z["risk"], reverse=True)

def redzones():
    data = incidents()
    if not data:
        return []
    counts = Counter()
    severity = defaultdict(int)
    for x in data:
        h = int(x["occurred_at"][11:13])
        bucket = f"{h:02d}:00–{(h+2)%24:02d}:00"
        counts[bucket] += 1
        severity[bucket] += x["severity"]
    out = []
    for bucket, c in counts.items():
        risk = min(100, c*15 + severity[bucket]*4)
        out.append({"time": bucket, "incidents": c, "risk": risk,
                    "label": "Critical" if risk >= 80 else "High" if risk >= 50 else "Medium"})
    return sorted(out, key=lambda z: z["risk"], reverse=True)

def shortest_safe_route(start, end):
    # Dijkstra-like traversal where edge cost = physical distance + predicted risk penalty.
    if start not in CAMPUS_NODES or end not in CAMPUS_NODES:
        return {"error": "Unknown campus node"}
    import heapq
    dist = {n: float("inf") for n in GRAPH}
    prev = {}
    dist[start] = 0
    heap = [(0, start)]
    now = datetime.now().hour
    while heap:
        cost, u = heapq.heappop(heap)
        if cost != dist[u]: continue
        if u == end: break
        for v in GRAPH[u]:
            a, b = CAMPUS_NODES[u], CAMPUS_NODES[v]
            km = haversine(a[0], a[1], b[0], b[1])
            risk = risk_for_point(b[0], b[1], now)
            edge = km * 100 + risk * 0.8
            nc = cost + edge
            if nc < dist[v]:
                dist[v] = nc
                prev[v] = u
                heapq.heappush(heap, (nc, v))
    if dist[end] == float("inf"):
        return {"error": "No route"}
    path = []
    cur = end
    while cur != start:
        path.append(cur); cur = prev[cur]
    path.append(start); path.reverse()
    coords = [{"name": n, "lat": CAMPUS_NODES[n][0], "lng": CAMPUS_NODES[n][1],
               "risk": risk_for_point(*CAMPUS_NODES[n], now)} for n in path]
    return {"route": path, "points": coords, "risk": round(sum(x["risk"] for x in coords)/len(coords)),
            "score": round(dist[end], 2)}

@app.route("/")
def student():
    return render_template("student.html", nodes=list(CAMPUS_NODES.keys()))

@app.route("/admin")
def admin():
    return render_template("admin.html")

@app.get("/api/facilities")
def get_facilities():
    out = []
    for f in CAMPUS_FACILITIES:
        p = CAMPUS_NODES.get(f["name"], CAMPUS_CENTER)
        out.append({**f, "latitude": p[0], "longitude": p[1]})
    return jsonify(out)

@app.get("/api/summary")
def summary():
    data = incidents()
    open_count = sum(x["status"] == "Open" for x in data)
    critical = sum(x["severity"] >= 4 for x in data)
    return jsonify({
        "total_incidents": len(data), "open_incidents": open_count,
        "critical_incidents": critical, "blackspots": len(blackspots()),
        "redzones": len(redzones()), "sklearn": SKLEARN_AVAILABLE
    })

@app.get("/api/incidents")
def get_incidents():
    return jsonify(incidents())

@app.post("/api/incidents")
def create_incident():
    payload = request.get_json(force=True)
    required = ["category", "severity", "description", "latitude", "longitude"]
    if any(k not in payload for k in required):
        return jsonify({"error": "Missing required fields"}), 400
    try:
        severity = int(payload["severity"])
        lat, lng = float(payload["latitude"]), float(payload["longitude"])
        if not (1 <= severity <= 5): raise ValueError
        if not (-90 <= lat <= 90 and -180 <= lng <= 180): raise ValueError
    except Exception:
        return jsonify({"error": "Invalid severity or coordinates"}), 400
    occurred = payload.get("occurred_at") or datetime.now().isoformat(timespec="minutes")
    conn = db()
    cur = conn.execute("""
      INSERT INTO incidents
      (reporter_name, anonymous, category, severity, description, latitude, longitude,
       occurred_at, status, evidence_url, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Open', ?, ?)
    """, (
        None if payload.get("anonymous", True) else payload.get("reporter_name", "Student"),
        1 if payload.get("anonymous", True) else 0,
        payload["category"], severity, payload["description"], lat, lng,
        occurred, payload.get("evidence_url"), datetime.now().isoformat()
    ))
    conn.commit()
    iid = cur.lastrowid
    conn.close()
    return jsonify({"success": True, "incident_id": iid,
                    "new_risk": risk_for_point(lat, lng),
                    "message": "Incident reported successfully"}), 201

@app.patch("/api/incidents/<int:iid>")
def update_incident(iid):
    payload = request.get_json(force=True)
    status = payload.get("status")
    if status not in {"Open", "Investigating", "Resolved"}:
        return jsonify({"error": "Invalid status"}), 400
    conn = db()
    conn.execute("UPDATE incidents SET status=? WHERE id=?", (status, iid))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.post("/api/interventions")
def intervention():
    payload = request.get_json(force=True)
    conn = db()
    conn.execute("""INSERT INTO interventions
        (incident_id, action, assigned_to, status, created_at)
        VALUES (?, ?, ?, 'Assigned', ?)""",
        (payload.get("incident_id"), payload.get("action","Deploy security patrol"),
         payload.get("assigned_to","Campus Security"), datetime.now().isoformat()))
    conn.commit(); conn.close()
    return jsonify({"success": True})

@app.get("/api/blackspots")
def get_blackspots():
    return jsonify(blackspots())

@app.get("/api/redzones")
def get_redzones():
    return jsonify(redzones())

@app.get("/api/risk")
def get_risk():
    try:
        lat, lng = float(request.args["lat"]), float(request.args["lng"])
    except Exception:
        return jsonify({"error": "lat/lng required"}), 400
    return jsonify({"risk": risk_for_point(lat, lng)})

@app.get("/api/routes")
def route():
    return jsonify(shortest_safe_route(request.args.get("start"), request.args.get("end")))

@app.post("/api/seed")
def seed():
    conn = db()
    conn.execute("DELETE FROM incidents")
    base = datetime.now()
    # SIMULATED data only — clearly marked so it cannot be mistaken for real MIT ADT incidents.
    spots = [
        (18.49225,74.02410,"Poor Lighting",3,"SIMULATED: Low visibility reported around a parking-area path."),
        (18.49230,74.02415,"Suspicious Activity",4,"SIMULATED: Suspicious activity near parking zone."),
        (18.49345,74.02375,"Crowding",2,"SIMULATED: Event-related crowding around the memorial area."),
        (18.49350,74.02370,"Poor Lighting",3,"SIMULATED: Low visibility on a riverside approach."),
        (18.49495,74.02335,"Unsafe Infrastructure",3,"SIMULATED: Pathway condition near river-side activity zone."),
        (18.49215,74.02705,"Harassment",5,"SIMULATED: Safety complaint near girls hostel zone."),
        (18.49220,74.02700,"Suspicious Activity",4,"SIMULATED: Unfamiliar person reported near hostel approach."),
        (18.49300,74.02755,"Medical",2,"SIMULATED: Minor medical assistance request near hospital."),
        (18.49420,74.02680,"Theft",4,"SIMULATED: Property theft report near sports complex."),
        (18.49375,74.02575,"Other",2,"SIMULATED: Crowd movement after an event."),
    ]
    for i, (lat,lng,cat,sev,desc) in enumerate(spots):
        dt = base - timedelta(days=random.randint(0,25), hours=random.randint(0,23))
        conn.execute("""INSERT INTO incidents
        (reporter_name, anonymous, category, severity, description, latitude, longitude,
         occurred_at, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
         (None,1,cat,sev,desc,lat,lng,dt.isoformat(timespec="minutes"),
          "Resolved" if i%3==0 else "Open", dt.isoformat()))
    conn.commit(); conn.close()
    return jsonify({"success": True, "count": len(spots), "data_type": "SIMULATED"})

init_db()

if __name__ == "__main__":
    app.run(debug=True)
