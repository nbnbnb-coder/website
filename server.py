import socket
import threading
import json
import time
import random

MAP_W = 1000
MAP_H = 700

PLAYER_SIZE = 40
ROOM_SIZE = 2
GAME_TIME = 60

HOUSE_SIZE = 80
ROCK_SIZE = 50
TREE_SIZE = 55

POLICE_SPAWN = (80, 80)
THIEF_SPAWN = (880, 580)

SAFE_RADIUS = 150

rooms = []
rooms_lock = threading.Lock()


def send_json(conn, data):
    try:
        conn.sendall((json.dumps(data) + "\n").encode())
    except:
        pass


def rects_overlap(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)


def inside_safe_zone(x, y, w, h, sx, sy, radius):
    safe_rect = (sx - radius, sy - radius, radius * 2, radius * 2)
    return rects_overlap((x, y, w, h), safe_rect)


def collides_any(rect, rect_list, padding=0):
    rx, ry, rw, rh = rect
    expanded = (rx - padding, ry - padding, rw + padding * 2, rh + padding * 2)
    for r in rect_list:
        if rects_overlap(expanded, r):
            return True
    return False


def generate_house_map():
    houses = []
    rocks = []
    trees = []
    blocked_rects = []

    house_count = random.randint(5, 10)
    rock_count = random.randint(4, 8)
    tree_count = random.randint(6, 12)

    # خانه‌ها
    for _ in range(house_count):
        placed = False
        for _try in range(120):
            x = random.randint(40, MAP_W - HOUSE_SIZE - 40)
            y = random.randint(40, MAP_H - HOUSE_SIZE - 40)
            rect = (x, y, HOUSE_SIZE, HOUSE_SIZE)

            if inside_safe_zone(x, y, HOUSE_SIZE, HOUSE_SIZE, POLICE_SPAWN[0], POLICE_SPAWN[1], SAFE_RADIUS):
                continue
            if inside_safe_zone(x, y, HOUSE_SIZE, HOUSE_SIZE, THIEF_SPAWN[0], THIEF_SPAWN[1], SAFE_RADIUS):
                continue
            if collides_any(rect, blocked_rects, padding=10):
                continue

            houses.append({
                "x": x,
                "y": y,
                "w": HOUSE_SIZE,
                "h": HOUSE_SIZE,
                "image": random.randint(1, 3)
            })
            blocked_rects.append(rect)
            placed = True
            break

    # سنگ‌ها
    for _ in range(rock_count):
        placed = False
        for _try in range(120):
            x = random.randint(30, MAP_W - ROCK_SIZE - 30)
            y = random.randint(30, MAP_H - ROCK_SIZE - 30)
            rect = (x, y, ROCK_SIZE, ROCK_SIZE)

            if inside_safe_zone(x, y, ROCK_SIZE, ROCK_SIZE, POLICE_SPAWN[0], POLICE_SPAWN[1], SAFE_RADIUS):
                continue
            if inside_safe_zone(x, y, ROCK_SIZE, ROCK_SIZE, THIEF_SPAWN[0], THIEF_SPAWN[1], SAFE_RADIUS):
                continue
            if collides_any(rect, blocked_rects, padding=8):
                continue

            rocks.append({
                "x": x,
                "y": y,
                "w": ROCK_SIZE,
                "h": ROCK_SIZE
            })
            blocked_rects.append(rect)
            placed = True
            break

    # درخت‌ها
    for _ in range(tree_count):
        placed = False
        for _try in range(120):
            x = random.randint(30, MAP_W - TREE_SIZE - 30)
            y = random.randint(30, MAP_H - TREE_SIZE - 30)
            rect = (x, y, TREE_SIZE, TREE_SIZE)

            if inside_safe_zone(x, y, TREE_SIZE, TREE_SIZE, POLICE_SPAWN[0], POLICE_SPAWN[1], SAFE_RADIUS):
                continue
            if inside_safe_zone(x, y, TREE_SIZE, TREE_SIZE, THIEF_SPAWN[0], THIEF_SPAWN[1], SAFE_RADIUS):
                continue
            if collides_any(rect, blocked_rects, padding=6):
                continue

            trees.append({
                "x": x,
                "y": y,
                "w": TREE_SIZE,
                "h": TREE_SIZE
            })
            blocked_rects.append(rect)
            placed = True
            break

    return houses, rocks, trees


def generate_fixed_maze():
    walls = [
        {"x": 180, "y": 60,  "w": 20,  "h": 220},
        {"x": 180, "y": 360, "w": 20,  "h": 220},

        {"x": 360, "y": 140, "w": 20,  "h": 220},
        {"x": 360, "y": 0,   "w": 20,  "h": 80},
        {"x": 360, "y": 440, "w": 20,  "h": 220},

        {"x": 540, "y": 60,  "w": 20,  "h": 220},
        {"x": 540, "y": 360, "w": 20,  "h": 220},

        {"x": 720, "y": 140, "w": 20,  "h": 220},
        {"x": 720, "y": 0,   "w": 20,  "h": 80},
        {"x": 720, "y": 440, "w": 20,  "h": 220},

        {"x": 120, "y": 180, "w": 180, "h": 20},
        {"x": 420, "y": 180, "w": 180, "h": 20},
        {"x": 700, "y": 180, "w": 180, "h": 20},

        {"x": 120, "y": 500, "w": 180, "h": 20},
        {"x": 420, "y": 500, "w": 180, "h": 20},
        {"x": 700, "y": 500, "w": 180, "h": 20},
    ]
    return walls


def create_room(room_id):
    return {
        "id": room_id,
        "players": [],
        "started": False,
        "game_over": False,
        "winner": None,
        "time_left": GAME_TIME,
        "start_time": None,
        "map_type": None,
        "houses": [],
        "rocks": [],
        "trees": [],
        "walls": [],
    }


def get_or_create_room():
    for room in rooms:
        if not room["started"] and len(room["players"]) < ROOM_SIZE:
            return room
    room = create_room(len(rooms) + 1)
    rooms.append(room)
    return room


def is_colliding_with_map(x, y, room):
    player_rect = (x, y, PLAYER_SIZE, PLAYER_SIZE)

    if room["map_type"] == 0:
        for h in room["houses"]:
            if rects_overlap(player_rect, (h["x"], h["y"], h["w"], h["h"])):
                return True
        for r in room["rocks"]:
            if rects_overlap(player_rect, (r["x"], r["y"], r["w"], r["h"])):
                return True
        for t in room["trees"]:
            if rects_overlap(player_rect, (t["x"], t["y"], t["w"], t["h"])):
                return True

    elif room["map_type"] == 1:
        for w in room["walls"]:
            if rects_overlap(player_rect, (w["x"], w["y"], w["w"], w["h"])):
                return True

    return False


def broadcast_room(room, data):
    for p in room["players"][:]:
        send_json(p["conn"], data)


def start_game_if_ready(room):
    if len(room["players"]) == ROOM_SIZE and not room["started"]:
        room["started"] = True
        room["game_over"] = False
        room["winner"] = None
        room["time_left"] = GAME_TIME
        room["start_time"] = time.time()

        room["map_type"] = random.randint(0, 1)

        if room["map_type"] == 0:
            room["houses"], room["rocks"], room["trees"] = generate_house_map()
            room["walls"] = []
        else:
            room["houses"] = []
            room["rocks"] = []
            room["trees"] = []
            room["walls"] = generate_fixed_maze()

        room["players"][0]["role"] = "police"
        room["players"][0]["x"] = POLICE_SPAWN[0]
        room["players"][0]["y"] = POLICE_SPAWN[1]

        room["players"][1]["role"] = "thief"
        room["players"][1]["x"] = THIEF_SPAWN[0]
        room["players"][1]["y"] = THIEF_SPAWN[1]

        for p in room["players"]:
            send_json(p["conn"], {
                "type": "start",
                "room_id": room["id"],
                "role": p["role"],
                "time_left": room["time_left"],
                "map_type": room["map_type"],
                "houses": room["houses"],
                "rocks": room["rocks"],
                "trees": room["trees"],
                "walls": room["walls"],
                "players": [
                    {
                        "id": pl["id"],
                        "role": pl["role"],
                        "x": pl["x"],
                        "y": pl["y"]
                    }
                    for pl in room["players"]
                ]
            })


def game_loop():
    while True:
        time.sleep(0.05)
        with rooms_lock:
            for room in rooms:
                if not room["started"] or room["game_over"]:
                    continue

                elapsed = int(time.time() - room["start_time"])
                left = max(0, GAME_TIME - elapsed)

                if left != room["time_left"]:
                    room["time_left"] = left
                    broadcast_room(room, {"type": "timer", "time_left": left})

                police = None
                thief = None

                for p in room["players"]:
                    if p["role"] == "police":
                        police = p
                    elif p["role"] == "thief":
                        thief = p

                if police and thief:
                    if rects_overlap(
                        (police["x"], police["y"], PLAYER_SIZE, PLAYER_SIZE),
                        (thief["x"], thief["y"], PLAYER_SIZE, PLAYER_SIZE)
                    ):
                        room["game_over"] = True
                        room["winner"] = "police"
                        broadcast_room(room, {"type": "game_over", "winner": "police"})
                        continue

                if room["time_left"] <= 0:
                    room["game_over"] = True
                    room["winner"] = "thief"
                    broadcast_room(room, {"type": "game_over", "winner": "thief"})


def remove_player_from_room(room, player_id):
    room["players"] = [p for p in room["players"] if p["id"] != player_id]

    if len(room["players"]) == 0:
        room["started"] = False
        room["game_over"] = False
        room["winner"] = None
        room["time_left"] = GAME_TIME
        room["start_time"] = None
        room["map_type"] = None
        room["houses"] = []
        room["rocks"] = []
        room["trees"] = []
        room["walls"] = []
    else:
        if room["started"] and not room["game_over"]:
            room["game_over"] = True
            remain_role = room["players"][0]["role"]
            winner = "thief" if remain_role == "thief" else "police"
            broadcast_room(room, {"type": "game_over", "winner": winner})


def handle_client(conn, addr, player_id):
    room = get_or_create_room()

    player = {
        "id": player_id,
        "conn": conn,
        "addr": addr,
        "x": 0,
        "y": 0,
        "role": None
    }

    with rooms_lock:
        room["players"].append(player)
        send_json(conn, {
            "type": "waiting",
            "room_id": room["id"],
            "player_number": len(room["players"])
        })
        start_game_if_ready(room)

    buffer = ""

    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break

            buffer += data.decode()

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue

                msg = json.loads(line)

                if msg["type"] == "move":
                    with rooms_lock:
                        if not room["started"] or room["game_over"]:
                            continue

                        nx = max(0, min(MAP_W - PLAYER_SIZE, int(msg["x"])))
                        ny = max(0, min(MAP_H - PLAYER_SIZE, int(msg["y"])))

                        if not is_colliding_with_map(nx, ny, room):
                            player["x"] = nx
                            player["y"] = ny

                        broadcast_room(room, {
                            "type": "state",
                            "players": [
                                {
                                    "id": pl["id"],
                                    "role": pl["role"],
                                    "x": pl["x"],
                                    "y": pl["y"]
                                }
                                for pl in room["players"]
                            ],
                            "time_left": room["time_left"]
                        })
    except:
        pass
    finally:
        with rooms_lock:
            remove_player_from_room(room, player_id)
        conn.close()


def main(HOST="0.0.0.0", PORT=5000):
    threading.Thread(target=game_loop, daemon=True).start()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen()
    print(f"Server started on {HOST}:{PORT}")

    next_player_id = 1

    while True:
        conn, addr = server.accept()
        print("Connected:", addr)
        threading.Thread(
            target=handle_client,
            args=(conn, addr, next_player_id),
            daemon=True
        ).start()
        next_player_id += 1


if __name__ == "__main__":
    main()
