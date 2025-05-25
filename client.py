import sys
import logging
import sqlite3
import json
import socketio
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QComboBox, QMessageBox, QTextEdit)
from PyQt6.QtCore import Qt, pyqtSignal
import irc.bot
import threading

logging.basicConfig(level=logging.DEBUG)

class IRCBot(irc.bot.SingleServerIRCBot):
    def __init__(self, channel, nickname, server, port=6667):
        irc.bot.SingleServerIRCBot.__init__(self, [(server, port)], nickname, nickname)
        self.channel = channel
        self.received_message = pyqtSignal(str, str)

    def on_welcome(self, connection, event):
        connection.join(self.channel)
        logging.debug(f"已连接到 IRC 频道 {self.channel}")

    def on_pubmsg(self, connection, event):
        sender = event.source.nick
        message = event.arguments[0]
        self.received_message.emit(sender, message)

    def send_message(self, message):
        self.connection.privmsg(self.channel, message)

class TenStepsClient(QMainWindow):
    update_ui_signal = pyqtSignal(dict)
    show_message_signal = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self.sio = socketio.Client()
        self.player_id = None
        self.game_id = None
        self.username = None
        self.irc_bot = None
        self.init_ui()
        self.setup_signals()
        self.setup_socketio()

    def init_ui(self):
        self.setWindowTitle("十步拳客户端")
        self.setGeometry(100, 100, 800, 600)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 登录面板
        self.login_panel = QWidget()
        login_layout = QVBoxLayout(self.login_panel)
        self.host_input = QLineEdit("localhost")
        self.port_input = QLineEdit("5000")
        self.username_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        login_button = QPushButton("登录")
        login_button.clicked.connect(self.handle_login)
        login_layout.addWidget(QLabel("主机:"))
        login_layout.addWidget(self.host_input)
        login_layout.addWidget(QLabel("端口:"))
        login_layout.addWidget(self.port_input)
        login_layout.addWidget(QLabel("用户名:"))
        login_layout.addWidget(self.username_input)
        login_layout.addWidget(QLabel("密码:"))
        login_layout.addWidget(self.password_input)
        login_layout.addWidget(login_button)
        main_layout.addWidget(self.login_panel)

        # 等待大厅
        self.lobby_panel = QWidget()
        lobby_layout = QVBoxLayout(self.lobby_panel)
        self.lobby_label = QLabel("等待其他玩家...")
        lobby_layout.addWidget(self.lobby_label)
        self.lobby_panel.setVisible(False)
        main_layout.addWidget(self.lobby_panel)

        # 角色选择面板
        self.selection_panel = QWidget()
        selection_layout = QVBoxLayout(self.selection_panel)
        self.character_combo = QComboBox()
        self.character_combo.addItems(["幸运儿", "战士", "医师", "圣骑士", "幽灵", "记录员", "超限者", "化妆师", "机器人", "催眠师"])
        self.style_combo = QComboBox()
        self.style_combo.addItems(["伤害流", "控制流", "回复流", "增益流", "防御流"])
        self.skill_combos = [QComboBox() for _ in range(5)]  # 无限乱斗技能选择
        for combo in self.skill_combos:
            combo.addItems(list(json.load(open("skills.json", encoding="utf-8")).keys()))
            selection_layout.addWidget(combo)
            combo.setVisible(False)
        select_button = QPushButton("确认选择")
        select_button.clicked.connect(self.handle_select_character)
        selection_layout.addWidget(QLabel("选择角色:"))
        selection_layout.addWidget(self.character_combo)
        selection_layout.addWidget(QLabel("选择流派:"))
        selection_layout.addWidget(self.style_combo)
        selection_layout.addWidget(select_button)
        self.player_labels = {}
        for i in range(4):
            label = QLabel(f"玩家 {i+1}: 未选择")
            self.player_labels[f"player_{i+1}"] = label
            selection_layout.addWidget(label)
        self.selection_panel.setVisible(False)
        main_layout.addWidget(self.selection_panel)

        # 战斗面板
        self.battle_panel = QWidget()
        battle_layout = QVBoxLayout(self.battle_panel)
        self.hp_label = QLabel("血量: 0/0")
        self.wins_label = QLabel("胜局: 0")
        self.move_combo = QComboBox()
        self.move_combo.addItems(["石头", "剪刀", "布"])
        self.skill_combo = QComboBox()
        self.target_combo = QComboBox()
        move_button = QPushButton("出拳")
        move_button.clicked.connect(self.handle_submit_move)
        skill_button = QPushButton("使用技能")
        skill_button.clicked.connect(self.handle_use_skill)
        battle_layout.addWidget(self.hp_label)
        battle_layout.addWidget(self.wins_label)
        battle_layout.addWidget(QLabel("选择出拳:"))
        battle_layout.addWidget(self.move_combo)
        battle_layout.addWidget(QLabel("选择技能:"))
        battle_layout.addWidget(self.skill_combo)
        battle_layout.addWidget(QLabel("选择目标:"))
        battle_layout.addWidget(self.target_combo)
        battle_layout.addWidget(move_button)
        battle_layout.addWidget(skill_button)
        self.battle_log = QTextEdit()
        self.battle_log.setReadOnly(True)
        battle_layout.addWidget(QLabel("战斗日志:"))
        battle_layout.addWidget(self.battle_log)
        self.battle_panel.setVisible(False)
        main_layout.addWidget(self.battle_panel)

        # 聊天面板
        self.chat_panel = QWidget()
        chat_layout = QVBoxLayout(self.chat_panel)
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_input = QLineEdit()
        chat_send_button = QPushButton("发送")
        chat_send_button.clicked.connect(self.handle_send_chat)
        chat_layout.addWidget(QLabel("聊天:"))
        chat_layout.addWidget(self.chat_display)
        chat_layout.addWidget(self.chat_input)
        chat_layout.addWidget(chat_send_button)
        self.chat_panel.setVisible(False)
        main_layout.addWidget(self.chat_panel)

    def setup_signals(self):
        self.update_ui_signal.connect(self.update_ui)
        self.show_message_signal.connect(self.show_message)

    def setup_socketio(self):
        self.sio.on("connect", self.on_connect, namespace="/game")
        self.sio.on("login_success", self.on_login_success, namespace="/game")
        self.sio.on("login_failed", self.on_login_failed, namespace="/game")
        self.sio.on("game_start", self.on_game_start, namespace="/game")
        self.sio.on("character_selected", self.on_character_selected, namespace="/game")
        self.sio.on("game_state", self.on_game_state, namespace="/game")
        self.sio.on("game_over", self.on_game_over, namespace="/game")

    def on_connect(self):
        logging.debug("已连接到服务器")

    def handle_login(self):
        host = self.host_input.text()
        port = self.port_input.text()
        self.username = self.username_input.text()
        password = self.password_input.text()
        try:
            self.sio.connect(f"http://{host}:{port}", namespaces=["/game"])
            self.sio.emit("login", {"username": self.username, "password": password}, namespace="/game")
            # 连接 IRC
            self.irc_bot = IRCBot("#tensteps", self.username, "irc.libera.chat")
            self.irc_bot.received_message.connect(self.append_chat_message)
            threading.Thread(target=self.irc_bot.start, daemon=True).start()
        except Exception as e:
            logging.error(f"连接失败: {str(e)}")
            QMessageBox.critical(self, "错误", f"连接失败: {str(e)}")

    def on_login_success(self, data):
        self.player_id = data["player_id"]
        self.game_id = data.get("game_id")
        self.update_ui_signal.emit({"action": "show_lobby"})

    def on_login_failed(self, data):
        self.show_message_signal.emit("错误", data["message"])

    def on_game_start(self, data):
        self.game_id = data["game_id"]
        self.mode = data["mode"]
        self.update_ui_signal.emit({"action": "show_selection"})

    def on_character_selected(self, data):
        self.update_ui_signal.emit({"action": "update_selection", "data": data})

    def on_game_state(self, data):
        self.update_ui_signal.emit({"action": "update_game_state", "data": data})

    def on_game_over(self, data):
        self.update_ui_signal.emit({"action": "game_over", "data": data})

    def update_ui(self, data):
        action = data.get("action")
        if action == "show_lobby":
            self.login_panel.hide()
            self.lobby_panel.show()
            self.lobby_label.setText(f"等待其他玩家... (玩家ID: {self.player_id})")
        elif action == "show_selection":
            self.lobby_panel.hide()
            self.selection_panel.show()
            for combo in self.skill_combos:
                combo.setVisible(self.mode == "infinite")
        elif action == "update_selection":
            for pid, player in data["data"]["players"].items():
                label = self.player_labels.get(pid)
                if label and player["character"]:
                    label.setText(f"{player['username']}: {player['character']} ({player['style']})")
        elif action == "update_game_state":
            self.update_game_state(data["data"])
        elif action == "game_over":
            winner = data["data"]["winner"]
            QMessageBox.information(self, "游戏结束", f"胜者: {winner}")
            self.battle_panel.hide()
            self.selection_panel.show()

    def update_game_state(self, game_state):
        self.selection_panel.hide()
        self.battle_panel.show()
        self.chat_panel.show()
        player = game_state["players"].get(self.player_id, {})
        self.hp_label.setText(f"血量: {player.get('hp', 0)}/{player.get('max_hp', 0)}")
        self.wins_label.setText(f"胜局: {player.get('wins', 0)}")
        self.update_skill_combo(game_state)
        self.update_target_combo(game_state)
        for effect in game_state.get("effects", []):
            self.battle_log.append(effect)
        for damage in game_state.get("damages", []):
            self.battle_log.append(damage)

    def update_skill_combo(self, game_state):
        self.skill_combo.clear()
        if self.player_id in game_state["players"]:
            player = game_state["players"][self.player_id]
            available_skills = player.get("available_skills", [])
            logging.debug(f"玩家 {self.player_id} 可用技能: {available_skills}")
            if not available_skills:
                logging.warning(f"玩家 {self.player_id} 无可用技能")
                self.skill_combo.addItem("无技能")
            else:
                self.skill_combo.addItems(available_skills)

    def update_target_combo(self, game_state):
        self.target_combo.clear()
        for pid, player in game_state["players"].items():
            if pid != self.player_id and player["is_alive"]:
                self.target_combo.addItem(player["username"])

    def handle_select_character(self):
        character = self.character_combo.currentText()
        style = self.style_combo.currentText()
        selected_skills = [combo.currentText() for combo in self.skill_combos] if self.mode == "infinite" else []
        self.sio.emit("select_character", {
            "game_id": self.game_id,
            "player_id": self.player_id,
            "character_name": character,
            "style": style,
            "username": self.username,
            "selected_skills": selected_skills
        }, namespace="/game")

    def handle_submit_move(self):
        move = self.move_combo.currentText()
        self.sio.emit("submit_move", {
            "game_id": self.game_id,
            "player_id": self.player_id,
            "move": move
        }, namespace="/game")

    def handle_use_skill(self):
        skill = self.skill_combo.currentText()
        target = self.target_combo.currentText()
        if not target:
            QMessageBox.warning(self, "警告", "请选择目标")
            return
        target_id = next(pid for pid, p in self.game_state["players"].items() if p["username"] == target)
        self.sio.emit("use_skill", {
            "game_id": self.game_id,
            "player_id": self.player_id,
            "skill_name": skill,
            "targets": [target_id],
            "params": {}
        }, namespace="/game")

    def handle_send_chat(self):
        message = self.chat_input.text()
        if message and self.irc_bot:
            self.irc_bot.send_message(f"{self.username}: {message}")
            self.append_chat_message(self.username, message)
            self.chat_input.clear()

    def append_chat_message(self, sender, message):
        self.chat_display.append(f"{sender}: {message}")

    def show_message(self, title, message):
        QMessageBox.critical(self, title, message)

    def closeEvent(self, event):
        if self.irc_bot:
            self.irc_bot.disconnect()
        self.sio.disconnect()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    client = TenStepsClient()
    client.show()
    sys.exit(app.exec())