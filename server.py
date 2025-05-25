import sqlite3
import logging
from flask import Flask, request
from flask_socketio import SocketIO, Namespace, emit
from datetime import datetime
from game_logic import GameEngine

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

logging.basicConfig(level=logging.DEBUG)

def init_db():
    try:
        conn = sqlite3.connect("ten_steps.db")
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS player_proficiency (
                username TEXT,
                character_name TEXT,
                proficiency INTEGER DEFAULT 0,
                PRIMARY KEY (username, character_name)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                username TEXT,
                task_type TEXT,
                progress INTEGER DEFAULT 0,
                completed BOOLEAN DEFAULT FALSE,
                PRIMARY KEY (username, task_type)
            )
        """)
        conn.commit()
        conn.close()
        logging.debug("数据库初始化成功")
    except Exception as e:
        logging.error(f"数据库初始化失败: {str(e)}")

class GameNamespace(Namespace):
    def __init__(self, namespace):
        super().__init__(namespace)
        self.players = {}
        self.game_engine = None
        self.game_started = False
        self.game_id = None
        self.task_triggers = {
            "output": {"damage_dealt": 0},
            "control": {"control_skills": 0, "wins": 0},
            "regen": {"survive_rounds": 0},
            "defense": {"evasions": 0}
        }

    def on_connect(self):
        logging.debug(f"客户端连接: {request.sid}")

    def on_disconnect(self):
        player_id = None
        for pid, info in list(self.players.items()):
            if pid == request.sid:
                player_id = pid
                break
        if player_id:
            username = self.players[player_id]["username"]
            del self.players[player_id]
            if self.game_engine and player_id in self.game_engine.players:
                self.game_engine.players[player_id]["is_alive"] = False
                self.check_game_status()
            emit("player_left", {"player_id": player_id, "username": username}, broadcast=True)
            logging.debug(f"玩家离开: {player_id} ({username})")
            self.broadcast_player_list()
            if len(self.players) < 2:
                self.game_started = False
                self.game_engine = None
                self.game_id = None
                emit("game_terminated", {"message": "玩家数量不足，游戏终止"}, broadcast=True)

    def on_register(self, data):
        username = data.get("username")
        password = data.get("password")
        try:
            conn = sqlite3.connect("ten_steps.db")
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM users WHERE username = ?", (username,))
            if cursor.fetchone():
                conn.close()
                emit("register_failed", {"message": "用户名已存在"})
                return
            cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
            conn.close()
            logging.debug(f"用户注册成功: {username}")
            emit("register_success", {"message": "注册成功"})
        except Exception as e:
            logging.error(f"注册错误: {str(e)}")
            emit("register_failed", {"message": str(e)})

    def on_login(self, data):
        username = data.get("username")
        password = data.get("password")
        try:
            conn = sqlite3.connect("ten_steps.db")
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM users WHERE username = ? AND password = ?", (username, password))
            user = cursor.fetchone()
            conn.close()
            if user:
                player_id = request.sid
                self.players[player_id] = {
                    "username": username,
                    "force_start": False,
                    "mode_vote": None
                }
                logging.debug(f"用户登录成功: {username}, player_id: {player_id}")
                emit("login_success", {"player_id": player_id}, to=player_id)
                self.send_chat_history(to=player_id)
                self.broadcast_player_list()
                player_count = len(self.players)
                if player_count == 4 and not self.game_started:
                    self.start_game("standard")
            else:
                logging.debug(f"用户登录失败: {username}")
                emit("login_failed", {"message": "用户名或密码错误"})
        except Exception as e:
            logging.error(f"登录错误: {str(e)}")
            emit("login_failed", {"message": str(e)})

    def on_send_chat(self, data):
        username = data.get("username")
        message = data.get("message")
        if not username or not message:
            emit("chat_error", {"message": "用户名或消息不能为空"})
            return
        try:
            conn = sqlite3.connect("ten_steps.db")
            cursor = conn.cursor()
            cursor.execute("INSERT INTO chat_messages (username, message) VALUES (?, ?)", (username, message))
            conn.commit()
            conn.close()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logging.debug(f"聊天消息保存: {username}: {message}")
            emit("receive_chat", {"username": username, "message": message, "timestamp": timestamp}, broadcast=True)
        except Exception as e:
            logging.error(f"保存聊天消息失败: {str(e)}")
            emit("chat_error", {"message": str(e)})

    def send_chat_history(self, to=None):
        try:
            conn = sqlite3.connect("ten_steps.db")
            cursor = conn.cursor()
            cursor.execute("SELECT username, message, timestamp FROM chat_messages ORDER BY timestamp DESC LIMIT 50")
            messages = cursor.fetchall()
            conn.close()
            for username, message, timestamp in reversed(messages):
                emit("receive_chat", {"username": username, "message": message, "timestamp": timestamp}, to=to or None, broadcast=(not to))
        except Exception as e:
            logging.error(f"获取聊天历史失败: {str(e)}")

    def on_force_start(self, data):
        player_id = data.get("player_id")
        mode = data.get("mode", "standard")
        if player_id not in self.players:
            emit("force_start_failed", {"message": "玩家未登录"})
            return
        player_count = len(self.players)
        if player_count < 2 or player_count > 4:
            emit("force_start_failed", {"message": "玩家数量必须为 2 到 4 人"})
            return
        self.players[player_id]["force_start"] = True
        self.players[player_id]["mode_vote"] = mode
        logging.debug(f"玩家 {player_id} 请求强制开始，模式: {mode}")
        all_ready = all(info["force_start"] for info in self.players.values())
        mode_votes = [info["mode_vote"] for info in self.players.values() if info["mode_vote"]]
        selected_mode = max(set(mode_votes), key=mode_votes.count, default="standard") if mode_votes else "standard"
        if all_ready and not self.game_started:
            self.start_game(selected_mode)
        else:
            emit("force_start_status", {
                "message": f"等待其他玩家同意 ({sum(1 for p in self.players.values() if p['force_start'])}/{player_count})",
                "mode": selected_mode
            }, broadcast=True)

    def on_select_character(self, data):
        player_id = data.get("player_id")
        if player_id not in self.players:
            logging.error(f"角色选择失败: 玩家 {player_id} 未登录")
            emit("select_character_failed", {"message": "玩家未登录"}, to=player_id)
            return
        if not self.game_engine:
            logging.error(f"角色选择失败: 游戏未初始化")
            emit("select_character_failed", {"message": "游戏未初始化"}, to=player_id)
            return

        game_id = data.get("game_id")
        character = data.get("character_name")
        style = data.get("style")
        username = data.get("username")
        selected_skills = data.get("selected_skills", [])

        result = self.game_engine.select_character(player_id, character, style, username, selected_skills)
        if not result["success"]:
            logging.error(f"角色选择失败: {result['message']}")
            emit("select_character_failed", {"message": result['message']}, to=player_id)
            return

        # 更新熟练度
        try:
            conn = sqlite3.connect("ten_steps.db")
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO player_proficiency (username, character_name, proficiency)
                VALUES (?, ?, COALESCE((SELECT proficiency FROM player_proficiency WHERE username = ? AND character_name = ?), 0) + 1)
            """, (username, character, username, character))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"更新熟练度失败: {str(e)}")

        logging.debug(f"玩家 {player_id} ({username}) 选择角色: {character}, 流派: {style}, 技能: {selected_skills}")
        emit("character_selected", {
            "player_id": player_id,
            "username": username,
            "character_name": character,
            "style": style,
            "selected_skills": selected_skills
        }, broadcast=True)

        if self.game_engine.all_players_ready():
            self.game_started = True
            self.initialize_tasks()
            self.broadcast_game_state()

    def on_submit_move(self, data):
        player_id = data.get("player_id")
        if player_id not in self.players:
            emit("submit_move_failed", {"message": "玩家未登录"}, to=player_id)
            return
        if not self.game_engine or not self.game_started:
            emit("submit_move_failed", {"message": "游戏未开始"})
            return

        move = data.get("move")
        result = self.game_engine.submit_move(player_id, move)
        if not result["success"]:
            emit("submit_move_failed", {"message": result["message"]}, to=player_id)
            return

        logging.debug(f"玩家 {player_id} 提交动作: {move}")
        if self.game_engine.all_moves_submitted():
            self.process_round()

    def on_use_skill(self, data):
        player_id = data.get("player_id")
        if player_id not in self.players:
            emit("use_skill_failed", {"message": "玩家未登录"})
            return
        if not self.game_engine or not self.game_started:
            emit("use_skill_failed", {"message": "游戏未开始"})
            return

        skill_name = data.get("skill_name")
        targets = data.get("targets", [])
        params = data.get("params", {})
        result = self.game_engine.apply_skill(player_id, skill_name, targets, params)
        if not result["success"]:
            emit("use_skill_failed", {"message": result["message"]}, to=player_id)
            return

        logging.debug(f"玩家 {player_id} 使用技能: {skill_name}, 目标: {targets}, 参数: {params}")
        self.update_task_progress(player_id, skill_name, result)
        if self.game_engine.all_moves_submitted():
            self.process_round()

    def start_game(self, mode):
        self.game_started = True
        self.game_id = f"game_{datetime.now().timestamp()}"
        player_ids = list(self.players.keys())
        self.game_engine = GameEngine(player_ids, mode=mode)
        for pid in player_ids:
            self.game_engine.players[pid]["socket_id"] = pid
            self.game_engine.players[pid]["username"] = self.players[pid]["username"]
            if mode == "boss" and pid == player_ids[0]:  # 第一个玩家为 BOSS
                self.game_engine.set_boss(pid, base_hp=50, hp_per_player=10)
        logging.debug(f"游戏开始: game_id={self.game_id}, mode={mode}, players={player_ids}")
        game_state = self.game_engine.get_public_state()
        emit("game_start", {
            "game_id": self.game_id,
            "mode": mode,
            "players": game_state["players"],
            "boss": game_state.get("boss", None)
        }, broadcast=True)

    def process_round(self):
        if not self.game_engine:
            logging.error("无法处理回合: 游戏引擎未初始化")
            return
        round_result = self.game_engine.process_round()
        logging.debug(f"回合 {self.game_engine.current_round} 处理完成: {round_result}")

        # 更新任务进度
        for player_id in self.players:
            self.update_task_progress(player_id, None, round_result)

        # BOSS 战：血量削弱禁用技能
        if self.game_engine.mode == "boss" and "boss" in round_result:
            hp_percentage = round_result["boss"]["hp"] / round_result["boss"]["max_hp"]
            if hp_percentage <= 0.8 and not round_result["boss"].get("skill_disabled_1"):
                self.game_engine.disable_boss_skill(1)
                emit("boss_skill_disabled", {"skill_index": 1}, broadcast=True)
            elif hp_percentage <= 0.6 and not round_result["boss"].get("skill_disabled_2"):
                self.game_engine.disable_boss_skill(2)
                emit("boss_skill_disabled", {"skill_index": 2}, broadcast=True)

        # 随机事件
        if self.game_engine.current_round % 3 == 0:
            self.trigger_random_event()

        emit("game_state", round_result, broadcast=True)
        if round_result.get("game_over"):
            self.game_started = False
            self.distribute_task_rewards()
            emit("game_over", {"winner": round_result["winner"], "tasks": self.get_task_status()}, broadcast=True)
            self.game_engine = None
            self.game_id = None
            self.reset_force_start()

    def check_game_status(self):
        if self.game_engine and self.game_engine.check_game_over():
            self.game_started = False
            result = self.game_engine.get_game_result()
            self.distribute_task_rewards()
            emit("game_over", {"winner": result["winner"], "tasks": self.get_task_status()}, broadcast=True)
            self.game_engine = None
            self.game_id = None
            self.reset_force_start()

    def broadcast_game_state(self):
        if self.game_engine:
            state = self.game_engine.get_public_state()
            emit("game_state", state, broadcast=True)
            logging.debug(f"广播游戏状态: 回合 {state['round']}")

    def get_player_list(self):
        return [{"player_id": pid, "username": info["username"]} for pid, info in self.players.items()]

    def broadcast_player_list(self):
        emit("update_player_list", {"players": self.get_player_list()}, broadcast=True)

    def reset_force_start(self):
        for player in self.players.values():
            player["force_start"] = False
            player["mode_vote"] = None

    def initialize_tasks(self):
        try:
            conn = sqlite3.connect("ten_steps.db")
            cursor = conn.cursor()
            for player_id, info in self.players.items():
                username = info["username"]
                tasks = [
                    ("output", 0, False),
                    ("control", 0, False),
                    ("regen", 0, False),
                    ("defense", 0, False)
                ]
                for task_type, progress, completed in tasks:
                    cursor.execute("""
                        INSERT OR REPLACE INTO tasks (username, task_type, progress, completed)
                        VALUES (?, ?, ?, ?)
                    """, (username, task_type, progress, completed))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"初始化任务失败: {str(e)}")

    def update_task_progress(self, player_id, skill_name, result):
        if not self.game_engine or player_id not in self.players:
            return
        username = self.players[player_id]["username"]
        player = self.game_engine.players.get(player_id)
        if not player:
            return

        try:
            conn = sqlite3.connect("ten_steps.db")
            cursor = conn.cursor()

            # 输出流：3回合内造成15点伤害
            if "damage_dealt" in result:
                cursor.execute("""
                    UPDATE tasks SET progress = progress + ? WHERE username = ? AND task_type = 'output' AND completed = FALSE
                """, (result["damage_dealt"].get(player_id, 0), username))
                cursor.execute("SELECT progress FROM tasks WHERE username = ? AND task_type = 'output'", (username,))
                progress = cursor.fetchone()[0]
                if progress >= 15:
                    cursor.execute("UPDATE tasks SET completed = TRUE WHERE username = ? AND task_type = 'output'", (username,))

            # 控制流：使用3次控制技能并胜利
            if skill_name and self.game_engine.is_control_skill(skill_name) and result.get("win", False):
                cursor.execute("""
                    UPDATE tasks SET progress = progress + 1 WHERE username = ? AND task_type = 'control' AND completed = FALSE
                """, (username,))
                cursor.execute("SELECT progress FROM tasks WHERE username = ? AND task_type = 'control'", (username,))
                progress = cursor.fetchone()[0]
                if progress >= 3:
                    cursor.execute("UPDATE tasks SET completed = TRUE WHERE username = ? AND task_type = 'control'", (username,))

            # 回复流：以回复流角色存活5回合
            if player.get("style") == "回复流" and player["is_alive"]:
                cursor.execute("""
                    UPDATE tasks SET progress = progress + 1 WHERE username = ? AND task_type = 'regen' AND completed = FALSE
                """, (username,))
                cursor.execute("SELECT progress FROM tasks WHERE username = ? AND task_type = 'regen'", (username,))
                progress = cursor.fetchone()[0]
                if progress >= 5:
                    cursor.execute("UPDATE tasks SET completed = TRUE WHERE username = ? AND task_type = 'regen'", (username,))

            # 防御流：3回合内规避2次伤害
            if "evasions" in result:
                cursor.execute("""
                    UPDATE tasks SET progress = progress + ? WHERE username = ? AND task_type = 'defense' AND completed = FALSE
                """, (result["evasions"].get(player_id, 0), username))
                cursor.execute("SELECT progress FROM tasks WHERE username = ? AND task_type = 'defense'", (username,))
                progress = cursor.fetchone()[0]
                if progress >= 2:
                    cursor.execute("UPDATE tasks SET completed = TRUE WHERE username = ? AND task_type = 'defense'", (username,))

            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"更新任务进度失败: {str(e)}")

    def distribute_task_rewards(self):
        try:
            conn = sqlite3.connect("ten_steps.db")
            cursor = conn.cursor()
            for player_id, info in self.players.items():
                username = info["username"]
                cursor.execute("SELECT task_type FROM tasks WHERE username = ? AND completed = TRUE", (username,))
                completed_tasks = cursor.fetchall()
                rewards = []
                for (task_type,) in completed_tasks:
                    if task_type == "output":
                        self.game_engine.grant_win(player_id, 1)
                        rewards.append({"task": "output", "reward": "1胜局"})
                    elif task_type == "control":
                        self.game_engine.adjust_hp(player_id, 2)
                        rewards.append({"task": "control", "reward": "血量+2"})
                    elif task_type == "regen":
                        self.game_engine.unlock_temp_skill(player_id, "吃个桃桃")
                        rewards.append({"task": "regen", "reward": "临时解锁‘吃个桃桃’"})
                    elif task_type == "defense":
                        self.game_engine.grant_block(player_id, 1)
                        rewards.append({"task": "defense", "reward": "1格挡"})
                if rewards:
                    emit("task_rewards", {"username": username, "rewards": rewards}, to=player_id)
            conn.close()
        except Exception as e:
            logging.error(f"分发任务奖励失败: {str(e)}")

    def trigger_random_event(self):
        events = [
            {"type": "heal_all", "value": 2, "description": "全场血量+2"},
            {"type": "disable_control", "duration": 1, "description": "禁用控制技能1回合"}
        ]
        event = events[self.game_engine.current_round % len(events)]  # 简单轮换
        self.game_engine.apply_random_event(event)
        emit("random_event", {"event": event["description"]}, broadcast=True)
        logging.debug(f"触发随机事件: {event['description']}")

    def get_task_status(self):
        try:
            conn = sqlite3.connect("ten_steps.db")
            cursor = conn.cursor()
            status = {}
            for player_id, info in self.players.items():
                username = info["username"]
                cursor.execute("SELECT task_type, progress, completed FROM tasks WHERE username = ?", (username,))
                tasks = cursor.fetchall()
                status[username] = [{"type": t, "progress": p, "completed": c} for t, p, c in tasks]
            conn.close()
            return status
        except Exception as e:
            logging.error(f"获取任务状态失败: {str(e)}")
            return {}

socketio.on_namespace(GameNamespace("/game"))

if __name__ == "__main__":
    init_db()
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)