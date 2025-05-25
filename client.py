import sys
import logging
import json
import socketio
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QComboBox, QMessageBox, QTextEdit,
                             QGridLayout, QStackedWidget, QListWidget)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

logging.basicConfig(level=logging.DEBUG)

class TenStepsClient(QMainWindow):
    update_ui_signal = pyqtSignal(dict)
    show_message_signal = pyqtSignal(str, str)
    update_player_list_signal = pyqtSignal(list)
    show_login_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.sio = socketio.Client()
        self.player_id = None
        self.game_id = None
        self.username = None
        self.is_connecting = False
        self.player_labels = []
        self.mode = None
        self.players = {}
        self.current_chat_display = None
        self.game_state = {}
        self.init_ui()
        self.setup_signals()
        self.setup_socketio()

    def init_ui(self):
        self.setWindowTitle("十步拳")
        self.setGeometry(100, 100, 800, 600)
        self.setMinimumSize(600, 400)

        font = QFont("SF Pro Display", 13)
        QApplication.setFont(font)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(10)

        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)

        # Login Panel
        self.login_panel = QWidget()
        login_layout = QGridLayout(self.login_panel)
        login_layout.setSpacing(10)

        self.host_input = QLineEdit("localhost")
        self.host_input.setPlaceholderText("主机")
        self.host_input.setStyleSheet("padding: 8px; border-radius: 5px; border: 1px solid #ccc;")
        self.port_input = QLineEdit("5000")
        self.port_input.setPlaceholderText("端口")
        self.port_input.setStyleSheet("padding: 8px; border-radius: 5px; border: 1px solid #ccc;")
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("用户名")
        self.username_input.setStyleSheet("padding: 8px; border-radius: 5px; border: 1px solid #ccc;")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("密码")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setStyleSheet("padding: 8px; border-radius: 5px; border: 1px solid #ccc;")

        login_button = QPushButton("登录")
        login_button.setStyleSheet("padding: 10px; border-radius: 5px; background-color: #007AFF; color: white;")
        login_button.clicked.connect(self.handle_login)
        register_switch_button = QPushButton("注册账户")
        register_switch_button.setStyleSheet("padding: 10px; border-radius: 5px; background-color: transparent; color: #007AFF;")
        register_switch_button.clicked.connect(self.show_register_panel)

        login_layout.addWidget(QLabel("主机:"), 0, 0)
        login_layout.addWidget(self.host_input, 0, 1)
        login_layout.addWidget(QLabel("端口:"), 1, 0)
        login_layout.addWidget(self.port_input, 1, 1)
        login_layout.addWidget(QLabel("用户名:"), 2, 0)
        login_layout.addWidget(self.username_input, 2, 1)
        login_layout.addWidget(QLabel("密码:"), 3, 0)
        login_layout.addWidget(self.password_input, 3, 1)
        login_layout.addWidget(login_button, 4, 0, 1, 2)
        login_layout.addWidget(register_switch_button, 5, 0, 1, 2, Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(self.login_panel)

        # Register Panel
        self.register_panel = QWidget()
        register_layout = QGridLayout(self.register_panel)
        register_layout.setSpacing(10)

        self.reg_username_input = QLineEdit()
        self.reg_username_input.setPlaceholderText("用户名")
        self.reg_username_input.setStyleSheet("padding: 8px; border-radius: 5px; border: 1px solid #ccc;")
        self.reg_password_input = QLineEdit()
        self.reg_password_input.setPlaceholderText("密码")
        self.reg_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.reg_password_input.setStyleSheet("padding: 8px; border-radius: 5px; border: 1px solid #ccc;")
        self.reg_confirm_password_input = QLineEdit()
        self.reg_confirm_password_input.setPlaceholderText("确认密码")
        self.reg_confirm_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.reg_confirm_password_input.setStyleSheet("padding: 8px; border-radius: 5px; border: 1px solid #ccc;")

        register_button = QPushButton("注册")
        register_button.setStyleSheet("padding: 10px; border-radius: 5px; background-color: #007AFF; color: white;")
        register_button.clicked.connect(self.handle_register)
        login_switch_button = QPushButton("返回登录")
        login_switch_button.setStyleSheet("padding: 10px; border-radius: 5px; background-color: transparent; color: #007AFF;")
        login_switch_button.clicked.connect(self.show_login_panel)

        register_layout.addWidget(QLabel("用户名:"), 0, 0)
        register_layout.addWidget(self.reg_username_input, 0, 1)
        register_layout.addWidget(QLabel("密码:"), 1, 0)
        register_layout.addWidget(self.reg_password_input, 1, 1)
        register_layout.addWidget(QLabel("确认密码:"), 2, 0)
        register_layout.addWidget(self.reg_confirm_password_input, 2, 1)
        register_layout.addWidget(register_button, 3, 0, 1, 2)
        register_layout.addWidget(login_switch_button, 4, 0, 1, 2, Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(self.register_panel)

        # Lobby Panel
        self.lobby_panel = QWidget()
        lobby_layout = QVBoxLayout(self.lobby_panel)
        lobby_layout.setSpacing(10)
        self.lobby_label = QLabel("等待大厅")
        self.lobby_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lobby_label.setStyleSheet("font-size: 16px; padding: 20px;")
        self.player_list = QListWidget()
        self.player_list.setStyleSheet("padding: 8px; border-radius: 5px; border: 1px solid #ccc;")
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["普通模式", "Boss战", "无限乱斗"])
        self.mode_combo.setStyleSheet("padding: 8px; border-radius: 5px;")
        self.vote_button = QPushButton("投票")
        self.vote_button.setStyleSheet("padding: 10px; border-radius: 5px; background-color: #007AFF; color: white;")
        self.vote_button.clicked.connect(self.handle_vote_mode)
        self.vote_tally_label = QLabel("投票: 普通: 0, Boss: 0, 无限: 0")
        self.vote_tally_label.setStyleSheet("font-size: 14px;")
        self.force_start_button = QPushButton("强制开始")
        self.force_start_button.setStyleSheet("padding: 10px; border-radius: 5px; background-color: #007AFF; color: white;")
        self.force_start_button.clicked.connect(self.handle_force_start)
        self.force_start_button.setEnabled(False)
        self.lobby_chat_display = QTextEdit()
        self.lobby_chat_display.setReadOnly(True)
        self.lobby_chat_display.setStyleSheet("padding: 8px; border-radius: 5px; border: 1px solid #ccc;")
        self.lobby_chat_input = QLineEdit()
        self.lobby_chat_input.setPlaceholderText("输入消息...")
        self.lobby_chat_input.setStyleSheet("padding: 8px; border-radius: 5px; border: 1px solid #ccc;")
        lobby_chat_send_button = QPushButton("发送")
        lobby_chat_send_button.setStyleSheet("padding: 10px; border-radius: 5px; background-color: #007AFF; color: white;")
        lobby_chat_send_button.clicked.connect(self.handle_send_chat)
        lobby_layout.addWidget(self.lobby_label)
        lobby_layout.addWidget(QLabel("当前玩家:"))
        lobby_layout.addWidget(self.player_list)
        lobby_layout.addWidget(QLabel("选择模式:"))
        lobby_layout.addWidget(self.mode_combo)
        lobby_layout.addWidget(self.vote_button)
        lobby_layout.addWidget(self.vote_tally_label)
        lobby_layout.addWidget(self.force_start_button)
        lobby_layout.addWidget(QLabel("聊天:"))
        lobby_layout.addWidget(self.lobby_chat_display)
        lobby_layout.addWidget(self.lobby_chat_input)
        lobby_layout.addWidget(lobby_chat_send_button)
        self.stack.addWidget(self.lobby_panel)

        # Selection Panel
        self.selection_panel = QWidget()
        self.selection_layout = QVBoxLayout(self.selection_panel)
        self.selection_layout.setSpacing(10)
        self.character_combo = QComboBox()
        self.character_combo.addItems(["幸运儿", "战士", "医师", "圣骑士", "幽灵", "记录员", "超限者", "化妆师", "机器人", "催眠师"])
        self.character_combo.setStyleSheet("padding: 8px; border-radius: 5px;")
        self.style_combo = QComboBox()
        self.style_combo.addItems(["伤害流", "控制流", "回复流", "增益流", "防御流"])
        self.style_combo.setStyleSheet("padding: 8px; border-radius: 5px;")
        self.skill_combos = [QComboBox() for _ in range(5)]
        for combo in self.skill_combos:
            with open("skills.json", encoding="utf-8") as f:
                skills = json.load(f)
                combo.addItems(list(skills.keys()))
            combo.setStyleSheet("padding: 8px; border-radius: 5px;")
            self.selection_layout.addWidget(combo)
            combo.setVisible(False)
        self.select_button = QPushButton("确认选择")
        self.select_button.setStyleSheet("padding: 10px; border-radius: 5px; background-color: #007AFF; color: white;")
        self.select_button.clicked.connect(self.handle_select_character)
        self.select_button.setEnabled(True)
        self.selection_chat_display = QTextEdit()
        self.selection_chat_display.setReadOnly(True)
        self.selection_chat_display.setStyleSheet("padding: 8px; border-radius: 5px; border: 1px solid #ccc;")
        self.selection_chat_input = QLineEdit()
        self.selection_chat_input.setPlaceholderText("输入消息...")
        self.selection_chat_input.setStyleSheet("padding: 8px; border-radius: 5px; border: 1px solid #ccc;")
        selection_chat_send_button = QPushButton("发送")
        selection_chat_send_button.setStyleSheet("padding: 10px; border-radius: 5px; background-color: #007AFF; color: white;")
        selection_chat_send_button.clicked.connect(self.handle_send_chat)
        self.selection_layout.addWidget(QLabel("选择角色:"))
        self.selection_layout.addWidget(self.character_combo)
        self.selection_layout.addWidget(QLabel("选择流派:"))
        self.selection_layout.addWidget(self.style_combo)
        self.selection_layout.addWidget(self.select_button)
        self.selection_layout.addWidget(QLabel("聊天:"))
        self.selection_layout.addWidget(self.selection_chat_display)
        self.selection_layout.addWidget(self.selection_chat_input)
        self.selection_layout.addWidget(selection_chat_send_button)
        self.stack.addWidget(self.selection_panel)

        # Battle Panel
        self.battle_panel = QWidget()
        battle_layout = QHBoxLayout(self.battle_panel)
        battle_layout.setSpacing(10)
        # Left: Battle Controls
        battle_controls = QWidget()
        battle_controls_layout = QVBoxLayout(battle_controls)
        battle_controls_layout.setSpacing(10)
        self.hp_label = QLabel("血量: 0/0")
        self.hp_label.setStyleSheet("font-size: 14px;")
        self.wins_label = QLabel("胜局: 0")
        self.wins_label.setStyleSheet("font-size: 14px;")
        self.buff_label = QLabel("Buff: 无")
        self.buff_label.setStyleSheet("font-size: 14px;")
        self.task_label = QLabel("任务: 无")
        self.task_label.setStyleSheet("font-size: 14px;")
        self.expected_damage_label = QLabel("预计伤害: 0")
        self.expected_damage_label.setStyleSheet("font-size: 14px;")
        self.status_label = QLabel("请出拳")
        self.status_label.setStyleSheet("font-size: 14px; color: #666;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.move_combo = QComboBox()
        self.move_combo.addItems(["石头", "剪刀", "布"])
        self.move_combo.setStyleSheet("padding: 8px; border-radius: 5px;")
        self.skill_combo = QComboBox()
        self.skill_combo.setStyleSheet("padding: 8px; border-radius: 5px;")
        self.skill_combo.setVisible(False)
        self.skill_combo.currentIndexChanged.connect(self.update_expected_damage)
        self.target_combo = QComboBox()
        self.target_combo.setStyleSheet("padding: 8px; border-radius: 5px;")
        self.target_combo.setVisible(False)
        move_button = QPushButton("出拳")
        move_button.setStyleSheet("padding: 10px; border-radius: 5px; background-color: #007AFF; color: white;")
        move_button.clicked.connect(self.handle_submit_move)
        skill_button = QPushButton("使用技能")
        skill_button.setStyleSheet("padding: 10px; border-radius: 5px; background-color: #007AFF; color: white;")
        skill_button.clicked.connect(self.handle_use_skill)
        skill_button.setVisible(False)
        self.battle_log = QTextEdit()
        self.battle_log.setReadOnly(True)
        self.battle_log.setStyleSheet("padding: 8px; border-radius: 5px; border: 1px solid #ccc;")
        battle_controls_layout.addWidget(self.hp_label)
        battle_controls_layout.addWidget(self.wins_label)
        battle_controls_layout.addWidget(self.buff_label)
        battle_controls_layout.addWidget(self.task_label)
        battle_controls_layout.addWidget(self.expected_damage_label)
        battle_controls_layout.addWidget(self.status_label)
        battle_controls_layout.addWidget(QLabel("选择出拳:"))
        battle_controls_layout.addWidget(self.move_combo)
        battle_controls_layout.addWidget(QLabel("选择技能:"))
        battle_controls_layout.addWidget(self.skill_combo)
        battle_controls_layout.addWidget(QLabel("选择目标:"))
        battle_controls_layout.addWidget(self.target_combo)
        battle_controls_layout.addWidget(move_button)
        battle_controls_layout.addWidget(skill_button)
        battle_controls_layout.addWidget(QLabel("战斗日志:"))
        battle_controls_layout.addWidget(self.battle_log)
        # Right: Chat
        battle_chat = QWidget()
        battle_chat_layout = QVBoxLayout(battle_chat)
        battle_chat_layout.setSpacing(10)
        self.battle_chat_display = QTextEdit()
        self.battle_chat_display.setReadOnly(True)
        self.battle_chat_display.setStyleSheet("padding: 8px; border-radius: 5px; border: 1px solid #ccc;")
        self.battle_chat_input = QLineEdit()
        self.battle_chat_input.setPlaceholderText("输入消息...")
        self.battle_chat_input.setStyleSheet("padding: 8px; border-radius: 5px; border: 1px solid #ccc;")
        battle_chat_send_button = QPushButton("发送")
        battle_chat_send_button.setStyleSheet("padding: 10px; border-radius: 5px; background-color: #007AFF; color: white;")
        battle_chat_send_button.clicked.connect(self.handle_send_chat)
        battle_chat_layout.addWidget(QLabel("聊天:"))
        battle_chat_layout.addWidget(self.battle_chat_display)
        battle_chat_layout.addWidget(self.battle_chat_input)
        battle_chat_layout.addWidget(battle_chat_send_button)
        # Add to main layout
        battle_layout.addWidget(battle_controls, stretch=2)
        battle_layout.addWidget(battle_chat, stretch=1)
        self.stack.addWidget(self.battle_panel)

    def setup_signals(self):
        self.update_ui_signal.connect(self.update_ui)
        self.show_message_signal.connect(self.show_message)
        self.update_player_list_signal.connect(self.update_player_list)
        self.show_login_signal.connect(self.show_login_panel)

    def setup_socketio(self):
        self.sio.on("connect", self.on_connect, namespace="/game")
        self.sio.on("login_success", self.on_login_success, namespace="/game")
        self.sio.on("login_failed", self.on_login_failed, namespace="/game")
        self.sio.on("register_success", self.on_register_success, namespace="/game")
        self.sio.on("register_failed", self.on_register_failed, namespace="/game")
        self.sio.on("game_start", self.on_game_start, namespace="/game")
        self.sio.on("character_selected", self.on_character_selected, namespace="/game")
        self.sio.on("select_character_failed", self.on_select_character_failed, namespace="/game")
        self.sio.on("game_state", self.on_game_state, namespace="/game")
        self.sio.on("game_over", self.on_game_over, namespace="/game")
        self.sio.on("receive_chat", self.on_receive_chat, namespace="/game")
        self.sio.on("chat_error", self.on_chat_error, namespace="/game")
        self.sio.on("update_player_list", self.on_update_player_list, namespace="/game")
        self.sio.on("force_start_status", self.on_force_start_status, namespace="/game")
        self.sio.on("force_start_failed", self.on_force_start_failed, namespace="/game")
        self.sio.on("vote_mode_status", self.on_vote_mode_status, namespace="/game")
        self.sio.on("boss_skill_disabled", self.on_boss_skill_disabled, namespace="/game")
        self.sio.on("random_event", self.on_random_event, namespace="/game")
        self.sio.on("task_rewards", self.on_task_rewards, namespace="/game")

    def on_connect(self):
        self.is_connecting = False
        logging.debug("已连接到服务器")

    def show_login_panel(self):
        self.stack.setCurrentWidget(self.login_panel)
        self.current_chat_display = None

    def show_register_panel(self):
        self.stack.setCurrentWidget(self.register_panel)
        self.current_chat_display = None

    def handle_login(self):
        if self.is_connecting:
            logging.debug("正在连接中，忽略重复登录请求")
            return

        host = self.host_input.text().strip()
        port = self.port_input.text().strip()
        self.username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not all([host, port, self.username, password]):
            self.show_message_signal.emit("错误", "请填写所有字段")
            return

        try:
            if not self.sio.connected:
                self.is_connecting = True
                self.sio.connect(f"http://{host}:{port}", namespaces=["/game"])
                self.sio.emit("login", {"username": self.username, "password": password}, namespace="/game")
        except Exception as e:
            self.is_connecting = False
            logging.error(f"连接失败: {e}")
            self.show_message_signal.emit("错误", f"连接错误: {e}")

    def handle_register(self):
        username = self.reg_username_input.text().strip()
        password = self.reg_password_input.text().strip()
        confirm_password = self.reg_confirm_password_input.text().strip()

        if not all([username, password, confirm_password]):
            self.show_message_signal.emit("错误", "请填写所有字段")
            return
        if password != confirm_password:
            self.show_message_signal.emit("错误", "两次输入的密码不一致")
            return
        if len(username) < 4 or len(password) < 6:
            self.show_message_signal.emit("错误", "用户名需至少4个字符，密码需至少6个字符")
            return
        if not username.isalnum() or not password.isalnum():
            self.show_message_signal.emit("错误", "用户名和密码必须仅包含字母和数字")
            return

        try:
            if not self.sio.connected:
                host = self.host_input.text().strip()
                port = self.port_input.text().strip()
                self.is_connecting = True
                self.sio.connect(f"http://{host}:{port}", namespaces=["/game"])
            self.sio.emit("register", {"username": username, "password": password}, namespace="/game")
        except Exception as e:
            self.is_connecting = False
            logging.error(f"注册失败: {e}")
            self.show_message_signal.emit("错误", f"注册错误: {e}")

    def on_login_success(self, data):
        self.player_id = data["player_id"]
        self.game_id = data.get("game_id")
        self.update_ui_signal.emit({"action": "show_lobby"})

    def on_login_failed(self, data):
        self.is_connecting = False
        self.show_message_signal.emit("错误", data["message"])

    def on_register_success(self, data):
        self.show_message_signal.emit("成功", "注册成功，请登录")
        self.show_login_signal.emit()

    def on_register_failed(self, data):
        self.show_message_signal.emit("错误", data["message"])

    def on_game_start(self, data):
        logging.debug(f"收到 game_start 数据: {data}")
        self.game_id = data["game_id"]
        self.mode = data["mode"]
        self.players = {p["player_id"]: p for p in data["players"]}
        logging.debug(f"游戏开始: game_id={self.game_id}, player_id={self.player_id}, players={self.players}")
        self.update_ui_signal.emit({"action": "show_selection"})

    def on_character_selected(self, data):
        logging.debug(f"收到角色选择: {data}")
        self.update_ui_signal.emit({
            "action": "update_labels",
            "player_id": data["player_id"],
            "username": data["username"],
            "character": data["character_name"],
            "style": data["style"]
        })

    def on_select_character_failed(self, data):
        self.show_message_signal.emit("错误", data["message"])

    def on_game_state(self, data):
        logging.debug(f"收到 game_state 数据: {data}")
        self.update_ui_signal.emit({"action": "update_game_state", "data": data})

    def on_game_over(self, data):
        winner = data["winner"]
        tasks = data.get("tasks", {})
        task_message = ""
        if self.username in tasks:
            for task in tasks[self.username]:
                if task["completed"]:
                    task_message += f"{task['type']}: 已完成 (进度: {task['progress']})\n"
                else:
                    task_message += f"{task['type']}: 未完成 (进度: {task['progress']})\n"
        message = f"游戏结束，获胜者: {winner or '无'}\n任务状态:\n{task_message or '无'}"
        self.show_message_signal.emit("游戏结束", message)
        self.update_ui_signal.emit({"action": "show_lobby"})
        self.game_id = None
        self.players = {}
        self.mode = None
        self.move_combo.setEnabled(True)
        self.skill_combo.setEnabled(False)
        self.target_combo.setEnabled(False)

    def on_receive_chat(self, data):
        timestamp = data["timestamp"]
        username = data["username"]
        message = data["message"]
        if self.current_chat_display:
            self.current_chat_display.append(f"[{timestamp}] {username}: {message}")

    def on_chat_error(self, data):
        self.show_message_signal.emit("错误", data["message"])

    def on_update_player_list(self, data):
        self.update_player_list_signal.emit(data["players"])

    def on_force_start_status(self, data):
        self.show_message_signal.emit("提示", data["message"])

    def on_force_start_failed(self, data):
        self.show_message_signal.emit("错误", data["message"])

    def on_vote_mode_status(self, data):
        votes = data["votes"]
        self.vote_tally_label.setText(f"投票: 普通: {votes['standard']}, Boss: {votes['boss']}, 无限: {votes['infinite']}")

    def on_boss_skill_disabled(self, data):
        self.battle_log.append(f"BOSS技能 {data['skill_index']} 被禁用")
        self.show_message_signal.emit("提示", f"BOSS技能 {data['skill_index']} 被禁用")

    def on_random_event(self, data):
        self.battle_log.append(f"随机事件: {data['event']}")
        self.show_message_signal.emit("提示", f"随机事件: {data['event']}")

    def on_task_rewards(self, data):
        rewards = "\n".join([r["reward"] for r in data["rewards"]])
        self.show_message_signal.emit("任务奖励", f"获得奖励:\n{rewards}")
        self.battle_log.append(f"任务奖励: {rewards}")

    def handle_force_start(self):
        if self.player_id:
            mode_map = {"普通模式": "standard", "Boss战": "boss", "无限乱斗": "infinite"}
            mode = mode_map[self.mode_combo.currentText()]
            self.sio.emit("force_start", {"player_id": self.player_id, "mode": mode}, namespace="/game")

    def handle_vote_mode(self):
        mode = self.mode_combo.currentText()
        mode_map = {"普通模式": "standard", "Boss战": "boss", "无限乱斗": "infinite"}
        self.sio.emit("vote_mode", {
            "player_id": self.player_id,
            "mode": mode_map[mode]
        }, namespace="/game")

    def handle_select_character(self):
        character = self.character_combo.currentText()
        style = self.style_combo.currentText()
        selected_skills = [combo.currentText() for combo in self.skill_combos if combo.isVisible()]
        if self.mode == "infinite" and len(selected_skills) != 5:
            self.show_message_signal.emit("错误", "无限乱斗模式需选择5个技能")
            return
        logging.debug(f"提交角色选择: character={character}, style={style}, skills={selected_skills}")
        self.sio.emit("select_character", {
            "game_id": self.game_id,
            "player_id": self.player_id,
            "username": self.username,
            "character_name": character,
            "style": style,
            "selected_skills": selected_skills
        }, namespace="/game")

    def handle_submit_move(self):
        move = self.move_combo.currentText()
        self.sio.emit("submit_move", {
            "game_id": self.game_id,
            "player_id": self.player_id,
            "move": move
        }, namespace="/game")
        self.status_label.setText("等待其他玩家操作")
        self.move_combo.setEnabled(False)
        for widget in self.battle_panel.findChildren(QPushButton):
            if widget.text() == "出拳":
                widget.setEnabled(False)

    def handle_use_skill(self):
        skill = self.skill_combo.currentText()
        target = self.target_combo.currentText()
        if not target:
            self.show_message_signal.emit("警告", "请选择目标")
            return
        target_id = None
        if target == "BOSS" and self.mode == "boss":
            target_id = self.game_state.get("boss", {}).get("player_id")
        else:
            target_id = next((p["player_id"] for p in self.game_state["players"] if p["username"] == target), None)
        if not target_id:
            self.show_message_signal.emit("警告", "无效目标")
            return
        params = {}
        with open("skills.json", encoding="utf-8") as f:
            skills = json.load(f)
            if skills.get(skill, {}).get("use_win"):
                params["consume_win"] = True
        self.sio.emit("use_skill", {
            "game_id": self.game_id,
            "player_id": self.player_id,
            "skill_name": skill,
            "targets": [target_id],
            "params": params
        }, namespace="/game")
        self.status_label.setText("等待其他玩家操作")
        self.skill_combo.setEnabled(False)
        self.target_combo.setEnabled(False)
        for widget in self.battle_panel.findChildren(QPushButton):
            if widget.text() == "使用技能":
                widget.setEnabled(False)

    def handle_send_chat(self):
        if self.stack.currentWidget() == self.lobby_panel:
            message = self.lobby_chat_input.text().strip()
            input_widget = self.lobby_chat_input
        elif self.stack.currentWidget() == self.selection_panel:
            message = self.selection_chat_input.text().strip()
            input_widget = self.selection_chat_input
        elif self.stack.currentWidget() == self.battle_panel:
            message = self.battle_chat_input.text().strip()
            input_widget = self.battle_chat_input
        else:
            return
        if not message:
            return
        self.sio.emit("send_chat", {"username": self.username, "message": message}, namespace="/game")
        input_widget.clear()

    def update_ui(self, data):
        action = data.get("action")
        if action == "show_lobby":
            self.stack.setCurrentWidget(self.lobby_panel)
            self.current_chat_display = self.lobby_chat_display
            self.force_start_button.setEnabled(self.player_list.count() >= 2)
            self.player_labels.clear()
        elif action == "show_selection":
            self.stack.setCurrentWidget(self.selection_panel)
            self.current_chat_display = self.selection_chat_display
            for combo in self.skill_combos:
                combo.setVisible(self.mode == "infinite")
        elif action == "update_game_state":
            self.update_game_state(data["data"])
        elif action == "update_labels":
            self.update_player_labels(data["player_id"], data["username"], data["character"], data["style"])

    def update_player_list(self, players):
        self.player_list.clear()
        for player in players:
            self.player_list.addItem(f"{player['username']} ({player['player_id']})")
        self.force_start_button.setEnabled(self.player_list.count() >= 2)

    def update_player_labels(self, player_id, username, character, style):
        found = False
        for label in self.player_labels:
            if label.property("player_id") == player_id:
                label.setText(f"{username}: {character} ({style})")
                found = True
                break
        if not found:
            label = QLabel(f"{username}: {character} ({style})")
            label.setProperty("player_id", player_id)
            label.setStyleSheet("font-size: 14px;")
            self.selection_layout.addWidget(label)
            self.player_labels.append(label)
        logging.debug(f"更新标签: {username}: {character} ({style})")

    def update_game_state(self, game_state):
        self.stack.setCurrentWidget(self.battle_panel)
        self.current_chat_display = self.battle_chat_display
        player = next((p for p in game_state.get("players", []) if p["player_id"] == self.player_id), {})
        self.hp_label.setText(f"血量: {player.get('hp', 0)}/{player.get('max_hp', 0)}")
        self.wins_label.setText(f"胜局: {player.get('wins', 0)}")
        buffs = [b["name"] for b in player.get('buffs', [])]
        self.buff_label.setText(f"Buff: {', '.join(buffs) or '无'}")
        tasks = game_state.get("tasks", {}).get(self.username, [])
        task_text = ""
        for task in tasks:
            status = "已完成" if task["completed"] else f"进度: {task['progress']}"
            task_text += f"{task['type']}: {status}\n"
        self.task_label.setText(f"任务:\n{task_text or '无'}")
        self.game_state = game_state
        self.update_skill_combo()
        self.update_target_combo()
        for effect in game_state.get("effects", []):
            self.battle_log.append(effect)
        for damage in game_state.get("damages", []):
            self.battle_log.append(damage)
        has_wins = player.get("wins", 0) > 0
        self.move_combo.setVisible(not has_wins)
        self.move_combo.setEnabled(not has_wins)
        self.skill_combo.setVisible(has_wins)
        self.skill_combo.setEnabled(has_wins)
        self.target_combo.setVisible(has_wins)
        self.target_combo.setEnabled(has_wins)
        for widget in self.battle_panel.findChildren(QPushButton):
            if widget.text() == "出拳":
                widget.setVisible(not has_wins)
                widget.setEnabled(not has_wins)
            elif widget.text() == "使用技能":
                widget.setVisible(has_wins)
                widget.setEnabled(has_wins)
        self.status_label.setText("请选择技能" if has_wins else "请出拳")

    def update_skill_combo(self):
        player = next((p for p in self.game_state.get("players", []) if p["player_id"] == self.player_id), {})
        available_skills = player.get("available_skills", [])
        self.skill_combo.clear()
        self.skill_combo.addItems(available_skills)
        self.update_expected_damage()

    def update_target_combo(self):
        self.target_combo.clear()
        for player in self.game_state.get("players", []):
            if player["is_alive"]:
                self.target_combo.addItem(player["username"])
        if self.mode == "boss" and self.game_state.get("boss", {}).get("hp", 0) > 0:
            self.target_combo.addItem("BOSS")

    def update_expected_damage(self, *args):
        skill = self.skill_combo.currentText()
        if not skill:
            self.expected_damage_label.setText("预计伤害: 0")
            return
        try:
            with open("skills.json", encoding="utf-8") as f:
                skills = json.load(f)
                skill_data = skills.get(skill, {})
                base_damage = skill_data.get("damage", 0)
                player = next((p for p in self.game_state.get("players", []) if p["player_id"] == self.player_id), {})
                style = player.get("style", "")
                if style == "伤害流" and base_damage > 0:
                    base_damage += 1
                elif style == "增益流" and base_damage > 0:
                    base_damage *= 1.1
                self.expected_damage_label.setText(f"预计伤害: {base_damage:.1f}")
        except Exception as e:
            logging.error(f"加载技能数据失败: {e}")
            self.expected_damage_label.setText("预计伤害: 未知")

    def show_message(self, title, message):
        QMessageBox.information(self, title, message)

    def closeEvent(self, event):
        self.sio.disconnect()
        self.players = {}
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    client = TenStepsClient()
    client.show()
    sys.exit(app.exec())