"""A small airport table (IATA code -> latitude, longitude, country) for flight distances and which rules apply.

Coordinates are rounded to 0.01 degrees, plenty for EU261 / UK261 distance bands (1,500 and 3,500 km).
MISSING: airports outside this list. A flight touching one gets no distance, so no compensation band.
"""

from __future__ import annotations

import math

AIRPORTS: dict[str, tuple[float, float, str]] = {
    # United States
    "ATL": (33.64, -84.43, "US"), "BOS": (42.36, -71.01, "US"), "CLT": (35.21, -80.94, "US"),
    "DCA": (38.85, -77.04, "US"), "DEN": (39.86, -104.67, "US"), "DFW": (32.90, -97.04, "US"),
    "DTW": (42.21, -83.35, "US"), "EWR": (40.69, -74.17, "US"), "HNL": (21.32, -157.92, "US"),
    "IAD": (38.94, -77.46, "US"), "IAH": (29.98, -95.34, "US"), "JFK": (40.64, -73.78, "US"),
    "LAS": (36.08, -115.15, "US"), "LAX": (33.94, -118.41, "US"), "LGA": (40.78, -73.87, "US"),
    "MCO": (28.43, -81.31, "US"), "MIA": (25.80, -80.29, "US"), "MSP": (44.88, -93.22, "US"),
    "ORD": (41.98, -87.90, "US"), "PDX": (45.59, -122.60, "US"), "PHL": (39.87, -75.24, "US"),
    "PHX": (33.43, -112.01, "US"), "SAN": (32.73, -117.19, "US"), "SEA": (47.45, -122.31, "US"),
    "SFO": (37.62, -122.38, "US"), "SLC": (40.79, -111.98, "US"),
    # Canada, Mexico
    "YYZ": (43.68, -79.63, "CA"), "YVR": (49.19, -123.18, "CA"), "MEX": (19.44, -99.07, "MX"),
    "CUN": (21.04, -86.87, "MX"),
    # United Kingdom, Ireland
    "LHR": (51.47, -0.45, "GB"), "LGW": (51.15, -0.19, "GB"), "MAN": (53.35, -2.28, "GB"),
    "EDI": (55.95, -3.37, "GB"), "DUB": (53.42, -6.27, "IE"),
    # European Union
    "AMS": (52.31, 4.76, "NL"), "ATH": (37.94, 23.94, "GR"), "BCN": (41.30, 2.08, "ES"),
    "BRU": (50.90, 4.48, "BE"), "CDG": (49.01, 2.55, "FR"), "CPH": (55.62, 12.66, "DK"),
    "FCO": (41.80, 12.25, "IT"), "FRA": (50.04, 8.56, "DE"), "HEL": (60.32, 24.96, "FI"),
    "LIS": (38.77, -9.13, "PT"), "MAD": (40.49, -3.57, "ES"), "MUC": (48.35, 11.79, "DE"),
    "MXP": (45.63, 8.72, "IT"), "ORY": (48.73, 2.36, "FR"), "VIE": (48.11, 16.57, "AT"),
    "ARN": (59.65, 17.92, "SE"), "WAW": (52.17, 20.97, "PL"), "PRG": (50.10, 14.26, "CZ"),
    # Asia, Middle East, Oceania
    "DXB": (25.25, 55.36, "AE"), "HKG": (22.31, 113.91, "HK"), "HND": (35.55, 139.78, "JP"),
    "NRT": (35.77, 140.39, "JP"), "ICN": (37.46, 126.44, "KR"), "SIN": (1.36, 103.99, "SG"),
    "SYD": (-33.95, 151.18, "AU"),
}

EU = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU",
      "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"}


def country(code: str | None) -> str | None:
    entry = AIRPORTS.get((code or "").upper())
    return entry[2] if entry else None


def distance_km(a: str, b: str) -> float | None:
    """Great-circle distance (haversine, Earth radius 6,371 km)."""
    pa, pb = AIRPORTS.get(a.upper()), AIRPORTS.get(b.upper())
    if not pa or not pb:
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, (pa[0], pa[1], pb[0], pb[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))
