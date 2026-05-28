import asyncio
import json
import random
import time
import os
import websockets

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 5000))
MAX_PLAYERS = 4
PLAYER_SIZE = 40
SPEED = 3

MAP_WIDTH, MAP_HEIGHT = 1000, 700
GAME_DURATION = 180

POLICE = "police"
THIEF = "thief"

HOUSE = "house"
ROCK = "rock"
TREE = "tree"
WALL = "wall"

WAITING = "waiting"
READY = "ready"
PLAYING = "playing"
SPECTATING = "spectating"

MSG_WAITING = "waiting"
MSG_START = "start"
MSG_UPDATE = "update"
MSG_GAME_OVER = "game_over"
MSG_JOIN = "join"
MSG_MOVE = "move"
MSG_QUIT = "quit"
MSG_READY = "ready"
MSG_ERROR = "error"


class Player:
    def __init__(self, id, name, role, websocket=None):
        self.id = id
        self.name = name
        self.role = role
        self.websocket = websocket
        self.x = 0
        self.y = 0
        self.dx = 0
        self.dy = 0
        self.state = WAITING
        self.ready = False

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "x": self.x,
            "y": self.y,
            "state": self.state,
            "ready": self.ready
        }


players = {}
connections = {}  # websocket -> player_id
room_id = None
game_started = False
game_over = False
winner = None
start_time = 0
map_type = 0
houses = []
rocks = []
trees = []
walls = []

game_lock = asyncio.Lock()


def get_spawn_points(num_players):
    spawn_points = []
    if num_players >= 1:
        spawn_points.append({"id": 1, "role": POLICE, "x": MAP_WIDTH // 2, "y": MAP_HEIGHT // 2})
    if num_players >= 2:
        spawn_points.append({"id": 2, "role": THIEF, "x": 100, "y": 100})
    if num_players >= 3:
        spawn_points.append({"id": 3, "role": THIEF, "x": MAP_WIDTH - 100, "y": MAP_HEIGHT - 100})
    if num_players >= 4:
        spawn_points.append({"id": 4, "role": THIEF, "x": 100, "y": MAP_HEIGHT - 100})
    return spawn_points


def generate_map(selected_map_type=0):
    global houses, rocks, trees, walls
    houses = []
    rocks = []
    trees = []
    walls = []

    if selected_map_type == 1:
        houses = [
            {"type": 1, "x": 150, "y": 150},
            {"type": 2, "x": 300, "y": 200},
            {"type": 3, "x": 500, "y": 100},
            {"type": 1, "x": 700, "y": 150},
            {"type": 2, "x": 850, "y": 200}
        ]
        rocks = [{"x": 400, "y": 300}, {"x": 600, "y": 300}]
        trees = [{"x": 200, "y": 400}, {"x": 800, "y": 400}]
        walls = [{"x": 500, "y": 400, "width": 20, "height": 150}]
    else:
        houses = [
            {"type": 1, "x": 200, "y": 200},
            {"type": 2, "x": 800, "y": 200},
            {"type": 3, "x": 500, "y": 400}
        ]
        rocks = [{"x": 300, "y": 300}, {"x": 700, "y": 300}]
        trees = [{"x": 100, "y": 400}, {"x": 900, "y": 400}]
        walls = [{"x": 500, "y": 500, "width": 20, "height": 150}]


async def safe_send(ws, message):
    try:
        await ws.send(json.dumps(message))
        return True
    except:
        return False


async def broadcast(message, sender_id=None):
    async with game_lock:
        targets = []
        for player_id, player in players.items():
            if player_id != sender_id and player.websocket:
                targets.append((player_id, player.websocket))

    to_remove = []
    for player_id, ws in targets:
        ok = await safe_send(ws, message)
        if not ok:
            to_remove.append(player_id)

    for player_id in to_remove:
        await remove_player(player_id)


async def send_to_player(player_id, message):
    async with game_lock:
        player = players.get(player_id)
        if not player or not player.websocket:
            return
        ws = player.websocket

    ok = await safe_send(ws, message)
    if not ok:
        await remove_player(player_id)


async def get_player_by_conn(ws):
    async with game_lock:
        player_id = connections.get(ws)
        if player_id:
            return players.get(player_id)
        return None


async def update_waiting_list():
    async with game_lock:
        player_dicts = [p.to_dict() for p in players.values() if p.state == WAITING]
        current_room_id = room_id

    waiting_info = {
        "type": MSG_WAITING,
        "room_id": current_room_id,
        "players": player_dicts
    }
    await broadcast(waiting_info)


async def remove_player(player_id):
    global game_started

    should_update_waiting = False
    should_check_end = False

    async with game_lock:
        if player_id not in players:
            return

        player = players[player_id]
        ws_to_remove = player.websocket

        if ws_to_remove in connections:
            del connections[ws_to_remove]

        del players[player_id]

        if game_started:
            should_check_end = True
        else:
            should_update_waiting = True

    if game_started:
        await broadcast({
            "type": MSG_UPDATE,
            "players": [p.to_dict() for p in list(players.values())],
            "time_left": 0
        }, sender_id=player_id)

    if should_check_end:
        async with game_lock:
            active_players = [p for p in players.values() if p.state == PLAYING]

        if len(active_players) < 2:
            await end_game(active_players[0].id if active_players else None)

    elif should_update_waiting:
        await update_waiting_list()


async def start_game():
    global game_started, game_over, winner, start_time, map_type

    async with game_lock:
        if game_started or game_over:
            return

        ready_players = [p for p in players.values() if p.ready]
        if len(ready_players) < 2:
            return

        police_player = ready_players[0]
        thief_players = ready_players[1:]

        spawn_points = get_spawn_points(len(ready_players))

        police_player.role = POLICE
        police_player.state = PLAYING
        if len(spawn_points) > 0:
            police_player.x = spawn_points[0]["x"]
            police_player.y = spawn_points[0]["y"]

        for i, thief in enumerate(thief_players, start=1):
            thief.role = THIEF
            thief.state = PLAYING
            if i < len(spawn_points):
                thief.x = spawn_points[i]["x"]
                thief.y = spawn_points[i]["y"]
            else:
                thief.x, thief.y = 100, 100

        map_type = random.randint(0, 1)
        generate_map(map_type)

        game_started = True
        game_over = False
        winner = None
        start_time = time.time()

        current_players = list(players.values())
        current_room_id = room_id
        current_map_type = map_type
        current_houses = houses
        current_rocks = rocks
        current_trees = trees
        current_walls = walls

    for target_player in current_players:
        start_message = {
            "type": MSG_START,
            "room_id": current_room_id,
            "role": target_player.role,
            "players": [p.to_dict() for p in current_players],
            "time_left": GAME_DURATION,
            "map_type": current_map_type,
            "houses": current_houses,
            "rocks": current_rocks,
            "trees": current_trees,
            "walls": current_walls
        }
        await send_to_player(target_player.id, start_message)


async def end_game(winning_player_id=None):
    global game_over, winner, game_started

    async with game_lock:
        if game_over:
            return

        game_over = True
        game_started = False

        if winning_player_id and winning_player_id in players:
            winner = players[winning_player_id].name
        else:
            active_thieves = [p for p in players.values() if p.state == PLAYING and p.role == THIEF]
            if not active_thieves:
                winner = "Police Won!"
            else:
                winner = "Police Won!"

        end_message = {
            "type": MSG_GAME_OVER,
            "winner": winner
        }

    await broadcast(end_message)


async def handle_message(player, msg):
    global room_id

    msg_type = msg.get("type")

    async with game_lock:
        if game_over and msg_type != MSG_QUIT:
            return

        if player.id not in players:
            if msg_type == MSG_JOIN:
                player.name = msg.get("name", f"Player_{player.id}")
                players[player.id] = player
                connections[player.websocket] = player.id
                if room_id is None:
                    room_id = random.randint(1000, 9999)
                player.state = WAITING
                player.ready = False

                waiting_message = {
                    "type": MSG_WAITING,
                    "room_id": room_id,
                    "players": [p.to_dict() for p in players.values()]
                }
            else:
                waiting_message = None

        else:
            waiting_message = None

    if player.id not in players:
        if msg_type == MSG_JOIN:
            await send_to_player(player.id, waiting_message)
            await update_waiting_list()
        else:
            await safe_send(player.websocket, {
                "type": MSG_ERROR,
                "message": "Please join the game first."
            })
            await remove_player(player.id)
        return

    async with game_lock:
        current_player = players[player.id]

        if msg_type == MSG_READY:
            if not game_started and current_player.state == WAITING:
                current_player.ready = not current_player.ready
                trigger_waiting_update = True
                trigger_start = True
            else:
                trigger_waiting_update = False
                trigger_start = False

        elif msg_type == MSG_MOVE:
            if game_started and current_player.state == PLAYING:
                current_player.dx = msg.get("dx", 0)
                current_player.dy = msg.get("dy", 0)
            trigger_waiting_update = False
            trigger_start = False

        elif msg_type == MSG_QUIT:
            trigger_waiting_update = False
            trigger_start = False
            should_remove = True
        else:
            trigger_waiting_update = False
            trigger_start = False
            should_remove = False
            return

    if msg_type == MSG_READY:
        if trigger_waiting_update:
            await update_waiting_list()
        if trigger_start:
            await start_game()

    elif msg_type == MSG_QUIT:
        await remove_player(player.id)


async def handle_client(ws):
    player_id = random.randint(1000, 9999)
    temp_player = Player(id=player_id, name="Guest", role=None, websocket=ws)

    try:
        async for message in ws:
            try:
                msg = json.loads(message)
                await handle_message(temp_player, msg)

                async with game_lock:
                    if temp_player.id in players:
                        temp_player = players[temp_player.id]

            except json.JSONDecodeError:
                print("Received invalid JSON")
            except Exception as e:
                print(f"Error handling message: {e}")

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        player_to_remove = await get_player_by_conn(ws)
        if player_to_remove:
            await remove_player(player_to_remove.id)


async def game_loop():
    global game_started, game_over

    while True:
        await asyncio.sleep(1.0 / 10)

        should_end = None
        should_broadcast = None

        async with game_lock:
            if game_started and not game_over:
                current_time = time.time()
                time_left = GAME_DURATION - (current_time - start_time)

                active_players = []
                for player in players.values():
                    if player.state == PLAYING:
                        player.x += player.dx * SPEED * (1.0 / 10)
                        player.y += player.dy * SPEED * (1.0 / 10)

                        player.x = max(PLAYER_SIZE // 2, min(MAP_WIDTH - PLAYER_SIZE // 2, player.x))
                        player.y = max(PLAYER_SIZE // 2, min(MAP_HEIGHT - PLAYER_SIZE // 2, player.y))

                        active_players.append(player)

                if time_left <= 0:
                    should_end = None
                elif len(active_players) < 2:
                    should_end = active_players[0].id if active_players else None
                elif len(active_players) == 1 and active_players[0].role == THIEF:
                    should_end = active_players[0].id

                if not should_end and time_left > 0:
                    should_broadcast = {
                        "type": MSG_UPDATE,
                        "players": [p.to_dict() for p in players.values()],
                        "time_left": max(0, int(time_left))
                    }

        if should_end is not None or (should_end is None and game_started and not game_over and should_broadcast is None):
            await end_game(should_end)
        elif should_broadcast:
            await broadcast(should_broadcast)


async def main():
    global room_id
    room_id = random.randint(1000, 9999)
    print(f"Server starting on {HOST}:{PORT}")
    print(f"Initial Room ID: {room_id}")

    asyncio.create_task(game_loop())

    async with websockets.serve(handle_client, HOST, PORT):
        print("WebSocket server is running...")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
