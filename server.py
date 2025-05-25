from flask import Flask, request
from flask_socketio import SocketIO, Namespace, emit, join_room
import sqlite3
import logging
from game_logic import GameEngine

logging.basicConfig(level=logging.DEBUG)

def init_db():
    """初始化 SQLite 数据库"""
    try:
        conn = sqlite3.connect("ten_steps.db")
        cursor = conn.cursor()

        # 创建 users 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL
            )
        """)

        # 创建 game_history 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS game_history (
                game_id TEXT PRIMARY KEY,
                mode TEXT,
                winner TEXT,
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 插入测试用户（仅在表为空时）
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            test_users = [
                ("user1", "111111"),
                ("user2", "111111"),
                ("user3", "111111"),
                ("user4", "111111")
            ]
            cursor.executemany("INSERT INTO users (username, password) VALUES (?, ?)", test_users)
            logging.debug("插入测试用户: user1, user2, user3, user4")

        conn.commit()
        logging.info("数据库初始化成功")
    except Exception as e:
        logging.error(f"数据库初始化失败: {str(e)}")
    finally:
        conn.close()

app = Flask(__name__)
app.config["SECRET_KEY"] = "ten_steps_secret"
socketio = SocketIO(app, cors_allowed_origins="*")
games = {}
players = {}

class GameNamespace(Namespace):
    def on_connect(self):
        logging.debug(f"客户端连接: {request.sid}")

    def on_disconnect(self):
        player_id = players.get(request.sid)
        if player_id:
            for game_id, game in games.items():
                if player_id in game.players:
                    del game.players[player_id]
                    socketio.emit("game_state", game.get_public_state(), room=game_id, namespace="/game")
            del players[request.sid]

    def on_login(self, data):
        username = data.get("username")
        password = data.get("password")
        try:
            conn = sqlite3.connect("ten_steps.db")
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM users WHERE username = ? AND password = ?", (username, password))
            result = cursor.fetchone()
            conn.close()
            if result:
                player_id = f"player_{len(players) + 1}"
                players[request.sid] = player_id
                game_id = self.find_or_create_game(player_id)
                emit("login_success", {"player_id": player_id, "game_id": game_id})
                join_room(game_id)
                logging.debug(f"收到登录请求: {username}, 分配玩家ID: {player_id}")
            else:
                emit("login_failed", {"message": "用户名或密码错误"})
        except Exception as e:
            logging.error(f"登录错误: {str(e)}")
            emit("login_failed", {"message": str(e)})

    def find_or_create_game(self, player_id):
        for game_id, game in games.items():
            if len(game.players) < 4:
                game.players[player_id]["socket_id"] = request.sid
                return game_id
        game_id = f"game_{len(games) + 1}"
        mode = "boss" if len(games) % 2 == 0 and len(players) >= 4 else "standard"
        games[game_id] = GameEngine([player_id], mode=mode)
        games[game_id].players[player_id]["socket_id"] = request.sid
        return game_id

    def on_select_character(self, data):
        game_id = data["game_id"]
        player_id = data["player_id"]
        character_name = data["character_name"]
        style = data["style"]
        username = data["username"]
        selected_skills = data.get("selected_skills", [])
        if game_id in games:
            result = games[game_id].select_character(player_id, character_name, style, username, selected_skills)
            if result["success"]:
                socketio.emit("character_selected", games[game_id].get_public_state(), room=game_id, namespace="/game")
                if games[game_id].all_players_ready():
                    socketio.emit("game_start", {"game_id": game_id, "mode": games[game_id].mode}, room=game_id, namespace="/game")
            else:
                emit("error", result)

    def on_submit_move(self, data):
        game_id = data["game_id"]
        player_id = data["player_id"]
        move = data["move"]
        if game_id in games:
            result = games[game_id].submit_move(player_id, move)
            if result["success"] and games[game_id].all_moves_submitted():
                round_result = games[game_id].process_round()
                socketio.emit("game_state", round_result, room=game_id, namespace="/game")
                if round_result.get("game_over"):
                    # 记录游戏结果
                    try:
                        conn = sqlite3.connect("ten_steps.db")
                        cursor = conn.cursor()
                        cursor.execute(
                            "INSERT INTO game_history (game_id, mode, winner) VALUES (?, ?, ?)",
                            (game_id, games[game_id].mode, round_result.get("winner", "无"))
                        )
                        conn.commit()
                        conn.close()
                        logging.debug(f"游戏 {game_id} 结果已记录")
                    except Exception as e:
                        logging.error(f"记录游戏历史失败: {str(e)}")
                    socketio.emit("game_over", games[game_id].get_game_result(), room=game_id, namespace="/game")
            elif not result["success"]:
                emit("error", result)

    def on_use_skill(self, data):
        game_id = data["game_id"]
        player_id = data["player_id"]
        skill_name = data["skill_name"]
        targets = data["targets"]
        params = data.get("params", {})
        if game_id in games:
            result = games[game_id].use_skill(player_id, skill_name, targets, params)
            if not result["success"]:
                emit("error", result)

# 初始化数据库
init_db()

if __name__ == "__main__":
    logging.info("十步拳服务器启动中...")
    socketio.on_namespace(GameNamespace("/game"))
    socketio.run(app, host="0.0.0.0", port=5000, allow_unsafe_werkzeug=True)