import os
import json
import math
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional

import requests
from flask import Flask, render_template, request, redirect, url_for, jsonify


app = Flask(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
TEACHERS_FILE = os.path.join(DATA_DIR, "teachers.json")
USER_AGENT = "TeacherFinder/1.0 (contact@example.com)"


def ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(TEACHERS_FILE):
        with open(TEACHERS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def geocode_address(address: str) -> Optional[Tuple[float, float]]:
    try:
        params = {
            "q": f"{address}, Egypt",
            "format": "json",
            "limit": 1,
            "addressdetails": 0,
        }
        headers = {"User-Agent": USER_AGENT}
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params=params,
            headers=headers,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None
        lat = float(data[0]["lat"])  # type: ignore[index]
        lon = float(data[0]["lon"])  # type: ignore[index]
        return lat, lon
    except Exception:
        return None


def query_overpass(lat: float, lon: float, radius_m: int) -> List[Dict[str, Any]]:
    query = f"""
    [out:json][timeout:30];
    (
      node["amenity"="school"](around:{radius_m},{lat},{lon});
      way["amenity"="school"](around:{radius_m},{lat},{lon});
      relation["amenity"="school"](around:{radius_m},{lat},{lon});
    );
    out center 200;
    """
    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]
    headers = {"User-Agent": USER_AGENT}

    last_error: Optional[Exception] = None
    for endpoint in endpoints:
        try:
            resp = requests.post(endpoint, data={"data": query}, headers=headers, timeout=60)
            resp.raise_for_status()
            payload = resp.json()
            elements: List[Dict[str, Any]] = payload.get("elements", [])
            results: List[Dict[str, Any]] = []
            for el in elements:
                tags = el.get("tags", {})
                name = tags.get("name") or tags.get("official_name") or tags.get("name:en") or "مدرسة"
                if "lat" in el and "lon" in el:
                    slat = el["lat"]
                    slon = el["lon"]
                else:
                    center = el.get("center", {})
                    slat = center.get("lat")
                    slon = center.get("lon")
                if slat is None or slon is None:
                    continue
                address_parts = []
                for key in ["addr:district", "addr:suburb", "addr:city", "addr:street"]:
                    if tags.get(key):
                        address_parts.append(tags[key])
                address = "، ".join(address_parts)
                results.append(
                    {
                        "name": name,
                        "lat": float(slat),
                        "lon": float(slon),
                        "address": address,
                        "osm_id": el.get("id"),
                        "osm_type": el.get("type"),
                        "tags": tags,
                    }
                )
            return results
        except Exception as e:
            last_error = e
            continue
    if last_error:
        print(f"Overpass query failed: {last_error}")
    return []


def enrich_with_distance(schools: List[Dict[str, Any]], lat: float, lon: float) -> List[Dict[str, Any]]:
    for s in schools:
        s["distance_km"] = round(haversine_km(lat, lon, s["lat"], s["lon"]), 2)
    schools.sort(key=lambda x: x.get("distance_km", 1e9))
    return schools


def save_teacher(teacher: Dict[str, Any]) -> None:
    ensure_data_dir()
    try:
        with open(TEACHERS_FILE, "r", encoding="utf-8") as f:
            arr = json.load(f)
        arr.append(teacher)
        with open(TEACHERS_FILE, "w", encoding="utf-8") as f:
            json.dump(arr, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Failed to save teacher: {e}")


@app.route("/")
def index() -> str:
    return render_template("index.html")


@app.route("/register", methods=["POST"])  # type: ignore[misc]
def register() -> str:
    full_name = request.form.get("full_name", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    subject = request.form.get("subject", "").strip()
    experience_years = request.form.get("experience_years", "").strip()
    address = request.form.get("address", "").strip()
    radius_km_str = request.form.get("radius_km", "5").strip()
    lat_str = request.form.get("lat")
    lon_str = request.form.get("lon")

    try:
        radius_km = max(1.0, min(50.0, float(radius_km_str)))
    except Exception:
        radius_km = 5.0

    lat: Optional[float] = None
    lon: Optional[float] = None

    if lat_str and lon_str:
        try:
            lat = float(lat_str)
            lon = float(lon_str)
        except Exception:
            lat = None
            lon = None

    if lat is None or lon is None:
        if address:
            geocoded = geocode_address(address)
            if geocoded is None:
                return render_template(
                    "index.html",
                    error_message="تعذّر تحديد الموقع من العنوان. جرّب كتابة العنوان بشكل أدق أو استخدم زر موقعي.",
                )
            lat, lon = geocoded
        else:
            return render_template(
                "index.html",
                error_message="من فضلك أدخل العنوان أو استخدم زر موقعي لتحديد الموقع.",
            )

    radius_m = int(radius_km * 1000)
    schools_raw = query_overpass(lat, lon, radius_m)
    schools = enrich_with_distance(schools_raw, lat, lon)

    teacher_record = {
        "full_name": full_name,
        "phone": phone,
        "email": email,
        "subject": subject,
        "experience_years": experience_years,
        "address": address,
        "lat": lat,
        "lon": lon,
        "radius_km": radius_km,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    save_teacher(teacher_record)

    results_payload = {
        "center": {"lat": lat, "lon": lon},
        "radius_km": radius_km,
        "schools": [
            {
                "name": s.get("name"),
                "lat": s.get("lat"),
                "lon": s.get("lon"),
                "distance_km": s.get("distance_km"),
                "address": s.get("address"),
                "osm_id": s.get("osm_id"),
                "osm_type": s.get("osm_type"),
            }
            for s in schools[:50]
        ],
    }

    return render_template(
        "results.html",
        full_name=full_name,
        subject=subject,
        address=address,
        radius_km=radius_km,
        center_lat=lat,
        center_lon=lon,
        results_json=json.dumps(results_payload, ensure_ascii=False),
    )


@app.route("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    ensure_data_dir()
    port = int(os.environ.get("PORT", "3000"))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)