import requests
import json
import time
import re
from functools import lru_cache

STEAMID64_BASE = 76561197960265728


# ---------------- HERO CACHE ----------------

@lru_cache(maxsize=1)
def get_heroes():
    response = requests.get("https://api.opendota.com/api/heroes")
    return response.json()


# ---------------- PLAYER INFO ----------------

def get_player_nickname(account_id):
    url = f"https://api.opendota.com/api/players/{account_id}"

    try:
        r = requests.get(url, timeout=15)
    except requests.exceptions.RequestException:
        return None

    if r.status_code != 200:
        return None

    data = r.json()
    profile = data.get("profile")

    if not profile:
        return None

    return profile.get("personaname")


def get_player_info(account_id):
    url = f"https://api.opendota.com/api/players/{account_id}"

    try:
        r = requests.get(url, timeout=15)
    except requests.exceptions.RequestException:
        return None

    if r.status_code != 200:
        return None

    data = r.json()

    profile = data.get("profile")
    if not profile:
        return None

    return {
        "name": profile.get("personaname"),
        "avatar": profile.get("avatarfull")
    }


# ---------------- TIME FORMAT ----------------

def format_seconds(seconds: int) -> str:

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"


# ---------------- STEAM PROFILE PARSER ----------------

def steam_profile_url_to_steamid32(url: str) -> int:

    url = url.strip()

    m = re.search(r"steamcommunity\.com/profiles/(\d{17})", url)

    if m:
        steamid64 = int(m.group(1))
        return steamid64 - STEAMID64_BASE

    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Failed to open profile page: {e}")

    if r.status_code != 200:
        raise RuntimeError(f"Steam page returned HTTP {r.status_code}")

    html = r.text

    m = re.search(r'"steamid"\s*:\s*"(\d{17})"', html)

    if not m:
        m = re.search(r'\b(7656119\d{10})\b', html)

    if not m:
        raise ValueError("Could not find SteamID64 in page.")

    steamid64 = int(m.group(1))

    return steamid64 - STEAMID64_BASE


# ---------------- OPENDOTA REFRESH ----------------

def refresh_player(account_id):

    print("Requesting full history from OpenDota...")

    url = f"https://api.opendota.com/api/players/{account_id}/refresh"

    response = requests.post(url)

    if response.status_code == 200:

        print("Refresh requested successfully.")
        print("Waiting 5 seconds for OpenDota to parse matches...\n")

        time.sleep(5)

    else:

        print("Failed to request refresh. Status:", response.status_code)
        print("Continuing anyway...\n")


# ---------------- DOWNLOAD MATCH HISTORY ----------------

def download_full_match_history(account_id):

    print("Downloading full match history...")

    all_matches = []

    offset = 0

    while True:

        url = (
            f"https://api.opendota.com/api/players/{account_id}/matches"
            f"?limit=100&offset={offset}&significant=0"
        )

        response = requests.get(url)

        if response.status_code == 429:

            print("Rate limited. Waiting 3 seconds...")
            time.sleep(3)
            continue

        if response.status_code != 200:

            print("Error downloading matches.")
            return []

        matches = response.json()

        if not matches:
            break

        all_matches.extend(matches)

        print(f"Downloaded {len(all_matches)} matches...")

        offset += 100

        time.sleep(0.1)

    try:
        with open("matches.json", "w") as f:
            json.dump(all_matches, f)
    except:
        pass

    print(f"\nDownload complete. Total matches: {len(all_matches)}\n")

    return all_matches


# ---------------- HERO RESOLVER ----------------

def resolve_hero_id(hero_input, heroes):

    q = hero_input.strip().lower()

    name_to_id = {h["localized_name"].lower(): h["id"] for h in heroes}

    if q in name_to_id:
        return name_to_id[q]

    alias_to_id = {}

    for h in heroes:

        internal = (h.get("name") or "").lower()

        if internal.startswith("npc_dota_hero_"):

            alias = internal.replace("npc_dota_hero_", "")

            alias_to_id[alias] = h["id"]

    if q in alias_to_id:
        return alias_to_id[q]

    initials_to_ids = {}

    for h in heroes:

        parts = h["localized_name"].lower().split()

        initials = "".join(p[0] for p in parts if p)

        initials_to_ids.setdefault(initials, []).append(h["id"])

    if q in initials_to_ids:

        options = initials_to_ids[q]

        if len(options) == 1:
            return options[0]

        print("\nThat input matches multiple heroes:")

        for i, hid in enumerate(options, start=1):

            hero_name = next(h["localized_name"] for h in heroes if h["id"] == hid)

            print(f"{i}. {hero_name}")

        choice = input("Choose number: ").strip()

        if not choice.isdigit():
            return None

        idx = int(choice)

        if idx < 1 or idx > len(options):
            return None

        return options[idx - 1]

    suggestions = []

    for name, hid in name_to_id.items():

        if q in name:
            suggestions.append((name, hid))

    if len(suggestions) == 1:
        return suggestions[0][1]

    if len(suggestions) > 1:

        suggestions.sort(key=lambda x: (len(x[0]), x[0]))

        suggestions = suggestions[:10]

        print("\nDid you mean:")

        for i, (name, _) in enumerate(suggestions, start=1):

            print(f"{i}. {name.title()}")

        choice = input("Choose number: ").strip()

        if not choice.isdigit():
            return None

        idx = int(choice)

        if idx < 1 or idx > len(suggestions):
            return None

        return suggestions[idx - 1][1]

    print("Hero not found.")

    return None


# ---------------- MAIN (CLI VERSION) ----------------

def main():

    profile_url = input("Enter Steam profile URL: ")

    try:

        account_id = steam_profile_url_to_steamid32(profile_url)

        print("Detected SteamID32 (account_id):", account_id)

    except Exception as e:

        print("Error resolving Steam profile:", e)

        return

    while True:

        print("\nChoose an option:")

        print("1. Download full match history (one-time)")
        print("2. Exit")

        choice = input("Enter number: ")

        if choice == "1":

            refresh_player(account_id)

            download_full_match_history(account_id)

        elif choice == "2":

            print("Goodbye.")

            break

        else:

            print("Invalid choice.\n")


if __name__ == "__main__":
    main()