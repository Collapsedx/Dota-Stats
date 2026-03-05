import streamlit as st
import requests
import pandas as pd

from dotacheckScript import (
    steam_profile_url_to_steamid32,
    download_full_match_history,
    format_seconds,
    get_player_info
)

# ---------------- HERO CACHE ----------------

@st.cache_data(ttl=24 * 60 * 60)
def get_heroes():
    return requests.get("https://api.opendota.com/api/heroes").json()


# ---------------- HERO IMAGE ----------------

def get_hero_image(hero_id, heroes):
    hero = next((h for h in heroes if h["id"] == hero_id), None)

    if not hero:
        return None

    internal = hero["name"].replace("npc_dota_hero_", "")

    return (
        "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/"
        f"dota_react/heroes/{internal}.png"
    )

# ---------------- HERO RESOLVER ----------------

def resolve_hero_id_streamlit(hero_input, heroes):
    q = hero_input.strip().lower()
    if not q:
        return None, None

    name_to_id = {h["localized_name"].lower(): h["id"] for h in heroes}

    # exact full name
    if q in name_to_id:
        return name_to_id[q], None

    # internal dota aliases
    alias_to_id = {}
    for h in heroes:
        internal = (h.get("name") or "").lower()
        if internal.startswith("npc_dota_hero_"):
            alias = internal.replace("npc_dota_hero_", "")
            alias_to_id[alias] = h["id"]

    if q in alias_to_id:
        return alias_to_id[q], None

    # initials (earth spirit -> es)
    initials_map = {}
    for h in heroes:
        parts = h["localized_name"].lower().split()
        if len(parts) >= 2:
            initials = "".join(p[0] for p in parts)
            initials_map.setdefault(initials, []).append(h["id"])

    if q in initials_map:
        ids = initials_map[q]

        if len(ids) == 1:
            return ids[0], None

        names = [
            next(h["localized_name"] for h in heroes if h["id"] == hid)
            for hid in ids
        ]
        return None, names

    # substring search only if query >= 3 characters
    if len(q) < 3:
        return None, None

    suggestions = []
    for name, hid in name_to_id.items():
        if q in name:
            suggestions.append((name, hid))

    if len(suggestions) == 1:
        return suggestions[0][1], None

    if len(suggestions) > 1:
        suggestions = suggestions[:10]
        names = [s[0].title() for s in suggestions]
        return None, names

    return None, None


# ---------------- HERO TABLE BUILDER ----------------

def build_top_heroes_rows(matches):

    heroes = get_heroes()
    id_to_name = {h["id"]: h["localized_name"] for h in heroes}

    hero_stats = {}

    for match in matches:

        hero_id = match.get("hero_id")
        if hero_id is None:
            continue

        duration = match.get("duration", 0)
        player_slot = match.get("player_slot", 0)
        radiant_win = match.get("radiant_win", False)

        if hero_id not in hero_stats:
            hero_stats[hero_id] = {"games": 0, "wins": 0, "seconds": 0}

        hero_stats[hero_id]["games"] += 1
        hero_stats[hero_id]["seconds"] += duration

        is_win = (
            (player_slot < 128 and radiant_win) or
            (player_slot >= 128 and not radiant_win)
        )

        if is_win:
            hero_stats[hero_id]["wins"] += 1

    rows = []

    for hero_id, s in hero_stats.items():

        games = s["games"]
        wins = s["wins"]
        losses = games - wins
        wr = (wins / games) * 100 if games else 0

        rows.append({
            "Hero": id_to_name.get(hero_id, f"Unknown ({hero_id})"),
            "Games": games,
            "W": wins,
            "L": losses,
            "WR%": round(wr, 2),
            "Time": format_seconds(s["seconds"]),
        })

    return rows


# ---------------- LAST 20 GAMES ----------------

def compute_last_n_stats(matches, n=20):
    last_n = matches[:n]  # OpenDota usually returns newest -> oldest

    wins = 0
    losses = 0
    total_seconds = 0
    hero_counts = {}

    for m in last_n:
        total_seconds += m.get("duration", 0)

        hero_id = m.get("hero_id")
        if hero_id is not None:
            hero_counts[hero_id] = hero_counts.get(hero_id, 0) + 1

        player_slot = m.get("player_slot", 0)
        radiant_win = m.get("radiant_win", False)

        is_win = (
            (player_slot < 128 and radiant_win) or
            (player_slot >= 128 and not radiant_win)
        )

        if is_win:
            wins += 1
        else:
            losses += 1

    games = wins + losses
    wr = (wins / games) * 100 if games else 0

    most_played_hero_id = None
    most_played_games = 0
    if hero_counts:
        most_played_hero_id = max(hero_counts, key=hero_counts.get)
        most_played_games = hero_counts[most_played_hero_id]

    avg_game = (total_seconds / games) if games else 0

    return {
        "games": games,
        "wins": wins,
        "losses": losses,
        "wr": wr,
        "total_seconds": total_seconds,
        "avg_seconds": avg_game,
        "most_played_hero_id": most_played_hero_id,
        "most_played_games": most_played_games,
    }

def show_podium(rows, heroes, title):

    st.subheader(title)

    id_to_name = {h["id"]: h["localized_name"] for h in heroes}
    name_to_id = {h["localized_name"]: h["id"] for h in heroes}

    top3 = rows[:3]

    if len(top3) < 3:
        st.write("Not enough data")
        return

    hero1 = top3[0]
    hero2 = top3[1]
    hero3 = top3[2]

    col_space1, col1, col_space2 = st.columns([1,2,1])

    # 🥇 first place
    with col1:
        hero_id = name_to_id[hero1["Hero"]]
        img = get_hero_image(hero_id, heroes)

        st.image(img, width=120)
        st.markdown("### 🥇")
        st.write(hero1["Hero"])
        st.write(f"{hero1['WR%']}% WR")
        st.write(f"{hero1['Games']} games")

    col2, col3 = st.columns(2)

    # 🥈 second
    with col2:
        hero_id = name_to_id[hero2["Hero"]]
        img = get_hero_image(hero_id, heroes)

        st.image(img, width=100)
        st.markdown("### 🥈")
        st.write(hero2["Hero"])
        st.write(f"{hero2['WR%']}% WR")

    # 🥉 third
    with col3:
        hero_id = name_to_id[hero3["Hero"]]
        img = get_hero_image(hero_id, heroes)

        st.image(img, width=100)
        st.markdown("### 🥉")
        st.write(hero3["Hero"])
        st.write(f"{hero3['WR%']}% WR")

# ---------------- UI ----------------

st.title("🎮 Dota 2 Stats Viewer")

profile_url = st.text_input("Enter Steam profile URL")

# ---------- LOAD PLAYER ----------

if st.button("Load Player"):

    try:
        account_id = steam_profile_url_to_steamid32(profile_url)
        player = get_player_info(account_id)

        st.session_state["account_id"] = account_id
        st.session_state["player"] = player

    except Exception as e:
        st.error(str(e))

# ---------- AFTER PLAYER LOADED ----------

if "account_id" in st.session_state:
    player = st.session_state.get("player")

    if player:

        col1, col2 = st.columns([1,4])

        with col1:
            st.image(player["avatar"], width=100)

        with col2:
            st.success(f"Player: {player['name']}")
            st.write(f"SteamID32: {st.session_state['account_id']}")

    account_id = st.session_state["account_id"]

    st.subheader("Actions")

    if st.button("Download Match History"):
        matches = download_full_match_history(account_id)
        st.session_state["matches"] = matches
        st.success(f"Matches loaded: {len(matches)}")

    if "matches" in st.session_state:

        matches = st.session_state["matches"]
        heroes = get_heroes()

        id_to_hero = {h["id"]: h for h in heroes}
        id_to_name = {h["id"]: h["localized_name"] for h in heroes}

        tab1, tab2 = st.tabs(["Hero Stats", "Top Heroes"])

        # ---------- HERO TAB ----------

        with tab1:

            st.subheader("Last 20 Games Performance")

            last = compute_last_n_stats(matches, n=20)

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Games", last["games"])
            c2.metric("W", last["wins"])
            c3.metric("L", last["losses"])
            c4.metric("WR%", f"{last['wr']:.2f}%")

            st.write(f"**Total time:** {format_seconds(last['total_seconds'])}")
            st.write(f"**Avg game:** {format_seconds(int(last['avg_seconds']))}")

            if last["most_played_hero_id"] is not None:
                mph_id = last["most_played_hero_id"]
                mph_name = id_to_name.get(mph_id, f"Unknown ({mph_id})")
                mph_img = get_hero_image(mph_id, heroes)
                
                st.write(f"**Most played hero (last 20):** {mph_name} ({last['most_played_games']} games)")

                col_img, col_txt = st.columns([1, 3])
                with col_img:
                    st.image(mph_img, width=110)
                with col_txt:
                    pass  # keeps layout clean

            st.divider()

            st.subheader("Hero Summary")

            hero_query = st.text_input("Enter hero name (mag, es, shaker...)")

            hero_id, options = resolve_hero_id_streamlit(hero_query, heroes)

            if options:

                choice = st.selectbox(
                    "Multiple heroes match your input:",
                    options
                )

                if st.button("Confirm Hero"):

                    name_to_id = {
                        h["localized_name"]: h["id"]
                        for h in heroes
                    }

                    st.session_state["hero_id"] = name_to_id.get(choice)

            if "hero_id" in st.session_state:
                hero_id = st.session_state["hero_id"]

            if hero_id:

                total_seconds = 0
                total_games = 0
                wins = 0

                for match in matches:

                    if match.get("hero_id") == hero_id:

                        total_seconds += match.get("duration", 0)
                        total_games += 1

                        player_slot = match.get("player_slot", 0)
                        radiant_win = match.get("radiant_win", False)

                        if (
                            (player_slot < 128 and radiant_win)
                            or
                            (player_slot >= 128 and not radiant_win)
                        ):
                            wins += 1

                hero = id_to_hero.get(hero_id)
                hero_name = hero["localized_name"] if hero else f"Unknown ({hero_id})"
                hero_img = get_hero_image(hero_id, heroes)

                losses = total_games - wins
                winrate = (wins / total_games) * 100 if total_games else 0

                col1, col2 = st.columns([1, 3])

                with col1:
                    st.image(hero_img, width=140)

                with col2:
                    st.write(f"**Hero:** {hero_name}")
                    st.write(f"**Games:** {total_games}")
                    st.write(f"**W/L:** {wins}/{losses}")
                    st.write(f"**Winrate:** {winrate:.2f}%")
                    st.write(f"**Time played:** {format_seconds(total_seconds)}")

        # ---------- TOP HEROES TAB ----------

        with tab2:

            st.subheader("Top Heroes Tables")

            min_wr = st.number_input(
                "Minimum games for BEST/WORST winrate lists",
                min_value=1,
                value=10
            )

            if st.button("Show Top Heroes"):

                rows = build_top_heroes_rows(matches)

                most_played = sorted(
                    rows,
                    key=lambda x: x["Games"],
                    reverse=True
                )[:10]

                wr_candidates = [
                    r for r in rows
                    if r["Games"] >= min_wr
                ]

                show_podium(most_played, heroes, "Top Picked Heroes")

                df = pd.DataFrame(most_played[3:])
                df.index = range(4, len(df) + 4)
                st.table(df)

                if wr_candidates:

                    best_wr = sorted(
                        wr_candidates,
                        key=lambda x: x["WR%"],
                        reverse=True
                    )[:10]

                    worst_wr = sorted(
                        wr_candidates,
                        key=lambda x: x["WR%"]
                    )[:10]

                    show_podium(best_wr, heroes, "Best Winrate Heroes")

                    df = pd.DataFrame(best_wr[3:])
                    df.index = range(4, len(df) + 4)
                    st.table(df)


                    show_podium(worst_wr, heroes, "Worst Winrate Heroes")

                    df = pd.DataFrame(worst_wr[3:])
                    df.index = range(4, len(df) + 4)
                    st.table(df)