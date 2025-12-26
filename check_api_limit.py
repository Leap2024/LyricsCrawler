import requests

API_KEY = "E8GewN6wi1sGY9KJmSQMRCPP4B1d1voVYdobnSVOzXff8OXhD8X9l-cVeKrc80LI"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "User-Agent": "genius-mfdoom-test"
}

PROXIES = {
    "http": "http://127.0.0.1:7890",
    "https": "http://127.0.0.1:7890"
}

def find_mf_doom_id():
    keywords = [
        "Doomsday MF DOOM",
        "Rapp Snitch Knishes",
        "Accordion MF DOOM",
        "ALL CAPS MF DOOM"
    ]

    for kw in keywords:
        print(f"\n🔍 searching: {kw}")
        r = requests.get(
            "https://api.genius.com/search",
            headers=HEADERS,
            params={"q": kw},
            proxies=PROXIES,
            timeout=20
        )

        if r.status_code != 200:
            print("  ❌ request failed")
            continue

        hits = r.json()["response"]["hits"]

        for h in hits:
            result = h["result"]
            artist = result["primary_artist"]

            name = artist["name"]
            artist_id = artist["id"]

            print(f"  🎵 {result['title']} → {name} (id={artist_id})")

            if name.lower() == "mf doom":
                print("\n✅ FOUND MF DOOM ID:", artist_id)
                return artist_id

    return None


if __name__ == "__main__":
    artist_id = find_mf_doom_id()
    print("\nFINAL RESULT:", artist_id)
