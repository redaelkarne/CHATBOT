import requests
import math
from dealership_data import dealerships
def geocode_address_nominatim(address: str):
    print(f"Geocoding address: {address}")
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": address,
        "format": "json",
        "limit": 1
    }
    headers = {
        "User-Agent": "YourAppName/1.0 (your.email@example.com)"
    }
    response = requests.get(url, params=params, headers=headers)
    if response.status_code == 200:
        results = response.json()
        if results:
            lat = float(results[0]["lat"])
            lon = float(results[0]["lon"])
            print(f"Result lat: {lat}, lon: {lon}")
            return lat, lon
        else:
            print("No results found for address.")
    else:
        print(f"Geocoding failed: {response.status_code} - {response.text}")
    return None, None
def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in kilometers
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = math.sin(d_phi/2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda/2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def find_closest_dealership(user_lat, user_lon):
    closest = None
    min_distance = float('inf')
    for dealer in dealerships:
        dist = haversine(user_lat, user_lon, dealer["latitude"], dealer["longitude"])
        if dist < min_distance:
            min_distance = dist
            closest = dealer
    return closest, min_distance