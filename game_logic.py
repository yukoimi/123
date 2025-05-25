import json
import random
import logging
from typing import Dict, List, Optional
from copy import deepcopy
from skills import SkillSystem
from characters import CharacterSystem

logging.basicConfig(level=logging.DEBUG)

class GameEngine:
    def __init__(self, player_ids: List[str], mode: str = "standard"):
        self.players = {
            pid: {
                "socket_id": None,
                "username": f"Player {pid}",
                "hp": 0,
                "max_hp": 0,
                "wins": 0,
                "character": None,
                "style": None,
                "available_skills": [],
                "skill_cooldowns": {},
                "buffs": [],
                "debuffs": [],
                "states": {},
                "pending_moves": None,
                "pending_skills": [],
                "is_alive": True,
                "ghost_hits": 0,
                "revive_timer": 0,
                "recorded_skills": [],
                "mimic_character": None,
                "proficiency": {},
                "tasks": [],
                "revive_count": 0,
                "puppet_master": None,
            } for pid in player_ids
        }
        self.current_round = 0
        self.moves = {}
        self.ready_players = set()
        self.game_over = False
        self.winner = None
        self.characters = CharacterSystem()
        self.skills = SkillSystem()
        self.common_skills = list(self.skills.get_all_skills().keys())
        self.mode = mode
        self.boss_id = None
        self.MAX_WINS = 3
        self.MOVE_OPTIONS = ["石头", "剪刀", "布"]

    def select_character(self, player_id: str, character_name: str, style: str, username: str, selected_skills: List[str] = []) -> Dict:
        if player_id not in self.players:
            return {"success": False, "message": "玩家不存在"}
        if character_name not in self.characters.get_all_characters():
            return {"success": False, "message": "角色不存在"}
        if style not in ["伤害流", "控制流", "回复流", "增益流", "防御流"]:
            return {"success": False, "message": "无效流派"}
        if self.mode == "infinite" and len(selected_skills) != 5:
            return {"success": False, "message": "无限乱斗需选择5个技能"}

        player = self.players[player_id]
        character = self.characters.get_character(character_name)
        player["character"] = character_name
        player["style"] = style
        player["username"] = username
        player["max_hp"] = character.get("max_hp", 15)
        player["hp"] = player["max_hp"]
        if character_name in ["幽灵", "超限者"] and "breakthrough_hp" in character:
            player["max_hp"] = character["breakthrough_hp"]
            player["hp"] = player["max_hp"]
        if self.mode == "infinite":
            player["max_hp"] = 12
            player["hp"] = 12

        # 流派效果
        if style == "伤害流":
            player["buffs"].append({"name": "伤害流", "duration": -1, "effect_data": {"damage_bonus": 1}})
        elif style == "控制流":
            player["buffs"].append({"name": "控制流", "duration": -1, "effect_data": {"control_bonus": 1}})
        elif style == "回复流":
            player["buffs"].append({"name": "回复流", "duration": -1, "effect_data": {"heal_bonus": 1}})
        elif style == "增益流":
            player["buffs"].append({"name": "增益流", "duration": -1, "effect_data": {"buff_multiplier": 1.1}})
        elif style == "防御流":
            player["buffs"].append({"name": "防御流", "duration": -1, "effect_data": {"damage_reduction": 1}})

        # 初始化技能
        player["available_skills"] = selected_skills if self.mode == "infinite" else self.characters.get_character_skills(character_name)
        if self.mode == "infinite":
            player["available_skills"].append("鸿运当头")

        # 熟练度
        player["proficiency"][character_name] = player["proficiency"].get(character_name, 0) + 1

        # 初始化被动
        self.characters.apply_passive_effects(character_name, player)
        self.ready_players.add(player_id)
        logging.debug(f"玩家 {player_id} ({username}) 选择角色 {character_name} ({style})，技能: {player['available_skills']}")

        # BOSS战初始化
        if self.mode == "boss" and not self.boss_id and len(self.ready_players) == len(self.players):
            self.boss_id = random.choice(list(self.players.keys()))
            self.players[self.boss_id]["max_hp"] = 50 + 10 * len(self.players)
            self.players[self.boss_id]["hp"] = self.players[self.boss_id]["max_hp"]
            self.players[self.boss_id]["available_skills"] += ["横扫", "要害锁定", "震天撼地", "能屈能伸", "复刻"]

        return {"success": True}

    def submit_move(self, player_id: str, move: str) -> Dict:
        if player_id not in self.players:
            return {"success": False, "message": "玩家不存在"}
        if move not in self.MOVE_OPTIONS:
            return {"success": False, "message": "无效出拳"}
        if not self.players[player_id]["is_alive"]:
            return {"success": False, "message": "玩家已死亡"}
        if self.mode == "boss" and player_id == self.boss_id:
            return {"success": False, "message": "BOSS不参与猜拳"}

        self.moves[player_id] = move
        return {"success": True}

    def use_skill(self, player_id: str, skill_name: str, targets: List[str], params: Dict = {}, consume_win: bool = False) -> Dict:
        if player_id not in self.players:
            return {"success": False, "message": "玩家不存在"}
        if not self.players[player_id]["is_alive"]:
            return {"success": False, "message": "玩家已死亡"}
        if skill_name not in self.players[player_id]["available_skills"]:
            return {"success": False, "message": "技能不可用"}
        if consume_win and self.players[player_id]["wins"] <= 0:
            return {"success": False, "message": "没有胜局可消耗"}

        player = self.players[player_id]
        skill_data = self.skills.get_skill(skill_name)
        if not skill_data:
            skill_data = self.get_boss_skill(skill_name)
        if not skill_data:
            return {"success": False, "message": "技能数据不存在"}

        if skill_name in player["skill_cooldowns"] and player["skill_cooldowns"][skill_name] > 0:
            return {"success": False, "message": "技能在冷却中"}
        if "usage_limit" in skill_data and sum(1 for s in player["pending_skills"] if s["skill_name"] == skill_name) >= skill_data["usage_limit"]:
            return {"success": False, "message": "技能使用次数已达上限"}

        if not self.validate_targets(skill_data, targets, player_id):
            return {"success": False, "message": "无效目标"}

        if consume_win:
            player["wins"] -= 1

        player["pending_skills"].append({"skill_name": skill_name, "targets": targets, "params": params})
        return {"success": True}

    def get_boss_skill(self, skill_name: str) -> Optional[Dict]:
        boss_skills = {
            "横扫": {
                "name": "横扫",
                "cooldown": 1,
                "effect_type": "direct_damage",
                "damage": 3,
                "alternate_damage": 5,
                "target_type": "two_enemies_or_single",
                "description": "2人各-3血，或1人-5血"
            },
            "要害锁定": {
                "name": "要害锁定",
                "cooldown": 3,
                "effect_type": "buff",
                "duration": 3,
                "ignore_defense": True,
                "target_type": "self",
                "description": "下3回合攻击无视减伤"
            },
            "震天撼地": {
                "name": "震天撼地",
                "cooldown": 1,
                "effect_type": "control",
                "control_turns": 1,
                "target_type": "all_others",
                "description": "全场玩家施加1回合控制"
            },
            "能屈能伸": {
                "name": "能屈能伸",
                "cooldown": 4,
                "effect_type": "special",
                "heal_conversion": True,
                "no_attack_next": 1,
                "max_hp_cost": 10,
                "target_type": "self",
                "description": "本回合伤害转为治疗，下一回合无法攻击，血量上限-10"
            },
            "复刻": {
                "name": "复刻",
                "cooldown": 3,
                "effect_type": ["steal_skill"],
                "duration": 3,
                "max_skills": 2,
                "target_type": ["any_skill"],
                "description": "学习3回合内1玩家技能（最多2个）"
            }
        }
        return boss_skills.get(skill_name)

    def validate_targets(self, skill_data: Dict, targets: List[str], player_id: str) -> bool:
        target_type = skill_data["target_type"]
        alive_players = [pid for pid in self.players if self.players[pid]["is_alive"]]
        if target_type == "self" and targets != [player_id]:
            return False
        if target_type in ["single_enemy", "single_any"] and (len(targets) != 1 or targets[0] not in alive_players or (target_type == "single_enemy" and targets[0] == player_id)):
            return False
        if target_type in ["two_enemies", "two_any"] and (len(targets) != 2 or any(t not in alive_players for t in targets) or (target_type == "two_enemies" and player_id in targets)):
            return False
        if target_type == "all_others" and sorted(targets) != sorted([pid for pid in alive_players if pid != player_id]):
            return False
        return True

    def process_round(self) -> Dict:
        self.current_round += 1
        results = {
            "moves": {},
            "effects": [],
            "damages": [],
            "wins": {},
            "tasks": [],
            "players": [
                {"player_id": pid, **player_data}
                for pid, player_data in self.players.items()
            ]
        }
        logging.debug(f"处理第 {self.current_round} 回合")

        # 更新状态
        self.update_states_and_cooldowns(results)
        self.apply_round_passives()
        self.process_tasks(results)

        # 处理出拳
        for pid in self.players:
            if pid not in self.moves and self.players[pid]["is_alive"] and (self.mode != "boss" or pid != self.boss_id):
                self.moves[pid] = random.choice(self.MOVE_OPTIONS)
            if pid in self.moves:
                results["moves"][pid] = self.moves[pid]

        # 判定出拳
        wins = self.judge_moves()
        for pid, win in wins.items():
            if win and self.players[pid]["is_alive"]:
                self.players[pid]["wins"] += 1
                results["wins"][pid] = True
                results["effects"].append(f"玩家 {self.players[pid]['username']} 猜拳获胜，获得1胜局")

        # BOSS战：胜局同步
        if self.mode == "boss" and self.boss_id:
            max_wins = max(p["wins"] for pid, p in self.players.items() if pid != self.boss_id)
            self.players[self.boss_id]["wins"] = max_wins

        # 随机事件
        if self.current_round % 3 == 0:
            self.trigger_random_event(results)

        # 检查游戏结束
        self.check_game_over()
        if self.game_over:
            results["game_over"] = True
            results["winner"] = self.winner

        self.moves = {}
        return results

    def process_skill_phase(self) -> Dict:
        results = {
            "effects": [],
            "damages": [],
            "players": [
                {"player_id": pid, **player_data}
                for pid, player_data in self.players.items()
            ]
        }
        logging.debug(f"处理技能阶段")

        # 更新状态
        self.update_states_and_cooldowns(results)
        self.apply_round_passives()

        # 检查游戏结束
        self.check_game_over()
        if self.game_over:
            results["game_over"] = True
            results["winner"] = self.winner

        return results

    def settle_damage(self) -> Dict:
        results = {
            "effects": [],
            "damages": [],
            "players": [
                {"player_id": pid, **player_data}
                for pid, player_data in self.players.items()
            ]
        }
        logging.debug(f"处理伤害结算")

        # 处理技能
        game_state = self.get_public_state()
        for pid in self.players:
            if not self.players[pid]["is_alive"]:
                continue
            for skill in self.players[pid]["pending_skills"]:
                skill_result = self.skills.execute_skill(
                    skill["skill_name"],
                    pid,
                    skill["targets"],
                    game_state,
                    skill["params"]
                )
                if skill_result["success"]:
                    results["effects"].extend(skill_result.get("effects", []))
                else:
                    results["effects"].append(f"{self.players[pid]['username']} 使用 {skill['skill_name']} 失败: {skill_result['message']}")
            self.players[pid]["pending_skills"] = []

        # 更新冷却和buff
        self.skills.update_cooldowns(game_state)
        self.skills.update_buffs(game_state)

        # 检查游戏结束
        self.check_game_over()
        if self.game_over:
            results["game_over"] = True
            results["winner"] = self.winner

        return results

    def judge_moves(self) -> Dict[str, bool]:
        wins = {pid: False for pid in self.players}
        move_counts = {"石头": 0, "剪刀": 0, "布": 0}
        for pid, move in self.moves.items():
            if self.players[pid]["is_alive"]:
                move_counts[move] += 1

        if len(set(self.moves.values())) == 1:
            return wins

        for pid in self.players:
            if not self.players[pid]["is_alive"] or (self.mode == "boss" and pid == self.boss_id):
                continue
            move = self.moves[pid]
            if move == "石头" and move_counts["剪刀"] > 0 and move_counts["布"] == 0:
                wins[pid] = True
            elif move == "布" and move_counts["石头"] > 0 and move_counts["剪刀"] == 0:
                wins[pid] = True
            elif move == "剪刀" and move_counts["布"] > 0 and move_counts["石头"] == 0:
                wins[pid] = True
        return wins

    def apply_damage(self, player_id: str, damage: float, results: Dict, ignore_defense: bool = False, source: str = None):
        player = self.players[player_id]
        if not player["is_alive"] or player.get("states", {}).get("invincible", 0) > 0:
            return

        reduction = 0 if ignore_defense else self.get_player_buff(player_id, "damage_reduction")
        final_damage = max(0, damage - reduction)
        player["hp"] = max(0, player["hp"] - final_damage)
        results["damages"].append(f"{player['username']} 受到 {final_damage} 伤害，剩余 {player['hp']} 血")

        if player["hp"] <= 0 and player["is_alive"]:
            self.handle_death(player_id, results, source)

    def apply_heal(self, player_id: str, heal: float, results: Dict):
        player = self.players[player_id]
        if not player["is_alive"]:
            return
        heal_amount = heal * self.get_player_buff(player_id, "heal_multiplier")
        player["hp"] = min(player["hp"] + heal_amount, player["max_hp"])
        results["effects"].append(f"{player['username']} 恢复 {heal_amount} 血，当前 {player['hp']}")

    def handle_death(self, player_id: str, results: Dict, source: str = None):
        player = self.players[player_id]
        if self.mode == "boss" and source is not None and source == self.boss_id:
            player["hp"] = 15
            player["puppet_master"] = self.boss_id
            results["effects"].append(f"{player['username']} 成为BOSS傀儡")
        elif player["character"] == "幽灵" and not player["states"].get("ghost_mode"):
            player["states"]["ghost_mode"] = True
            player["ghost_hits"] = player["states"].get("ghost_hits", 3)
            player["revive_timer"] = player["states"].get("revive_time", 3)
            results["effects"].append(f"{player['username']} 进入幽灵状态")
        elif self.mode == "infinite" and player["revive_count"] < 3:
            player["revive_count"] += 1
            player["revive_timer"] = 2
            results["effects"].append(f"{player['username']} 将在2回合后复活")
        else:
            player["is_alive"] = False
            results["effects"].append(f"{player['username']} 已死亡")

    def update_states_and_cooldowns(self, results: Dict):
        for pid, player in self.players.items():
            if not player["is_alive"]:
                continue
            for skill, cd in list(player["skill_cooldowns"].items()):
                player["skill_cooldowns"][skill] = max(0, cd - 1)
                if player["skill_cooldowns"][skill] == 0:
                    del player["skill_cooldowns"][skill]
            for buff in player["buffs"][:]:
                buff["duration"] -= 1 if buff["duration"] > 0 else 0
                if buff["duration"] == 0:
                    player["buffs"].remove(buff)
            for debuff in player["debuffs"][:]:
                debuff["duration"] -= 1 if debuff["duration"] > 0 else 0
                if debuff["duration"] == 0:
                    player["debuffs"].remove(debuff)
            if player["states"].get("invincible", 0) > 0:
                player["states"]["invincible"] -= 1
            if player["states"].get("stealth", 0) > 0:
                player["states"]["stealth"] -= 1
            if player["states"].get("ghost_mode"):
                player["revive_timer"] -= 1
                if player["revive_timer"] <= 0:
                    player["hp"] = player["states"].get("revive_hp", player["max_hp"] // 2)
                    player["is_alive"] = True
                    player["states"]["ghost_mode"] = False
                    player["available_skills"].append(player["states"].get("revive_skill", "复仇"))
                    results["effects"].append(f"{player['username']} 复活")
            if player["revive_timer"] > 0:
                player["revive_timer"] -= 1
                if player["revive_timer"] == 0 and player["revive_count"] < 3:
                    player["hp"] = player["max_hp"]
                    player["is_alive"] = True
                    player["character"] = None
                    player["style"] = None
                    player["available_skills"] = []
                    results["effects"].append(f"{player['username']} 复活，需重新选择角色")

    def apply_round_passives(self):
        for pid, player in self.players.items():
            if not player["is_alive"]:
                continue
            if player["character"] == "幸运儿" and self.current_round % player["states"].get("win_interval", 3) == 0:
                player["wins"] += 1
            elif player["character"] == "记录员" and self.current_round % player["states"].get("auto_save_cd", 3) == 0:
                player["pending_skills"].append({"skill_name": "将军饮马", "targets": [pid], "params": {}})

    def process_tasks(self, results: Dict):
        for pid, player in self.players.items():
            for task in player["tasks"]:
                if task["name"] == "输出流" and task["progress"] >= 15:
                    player["wins"] += 1
                    results["tasks"].append(f"{player['username']} 完成输出流任务，获1胜局")
                    player["tasks"].remove(task)

    def trigger_random_event(self, results: Dict):
        event = random.choice(["全场血量+2", "禁用控制技能1回合"])
        if event == "全场血量+2":
            for pid, player in self.players.items():
                if player["is_alive"]:
                    self.apply_heal(pid, 2, results)
        elif event == "禁用控制技能1回合":
            for pid, player in self.players.items():
                for skill in player["available_skills"]:
                    if self.skills.get_skill(skill).get("effect_type") == "control":
                        player["skill_cooldowns"][skill] = 1
        results["effects"].append(f"随机事件: {event}")

    def get_player_buff(self, player_id: str, buff_type: str) -> float:
        player = self.players[player_id]
        value = 0
        for buff in player["buffs"]:
            if buff_type in buff["effect_data"]:
                value += buff["effect_data"][buff_type]
        for debuff in player["debuffs"]:
            if buff_type in debuff["effect_data"]:
                value -= debuff["effect_data"][buff_type]
        return value

    def has_wins(self) -> bool:
        return any(p["wins"] > 0 for p in self.players.values())

    def all_players_ready(self) -> bool:
        return len(self.ready_players) == len(self.players)

    def all_moves_submitted(self) -> bool:
        return all(pid in self.moves or not self.players[pid]["is_alive"] or (self.mode == "boss" and pid == self.boss_id) for pid in self.players)

    def all_skills_submitted(self) -> bool:
        return all(p["wins"] == 0 or not p["is_alive"] for p in self.players.values())

    def check_game_over(self):
        alive_players = [pid for pid in self.players if self.players[pid]["is_alive"]]
        if len(alive_players) <= 1:
            self.game_over = True
            self.winner = self.players[alive_players[0]]["username"] if alive_players else None
            return
        for pid, player in self.players.items():
            if player["wins"] >= self.MAX_WINS:
                self.game_over = True
                self.winner = player["username"]
                break

    def get_game_result(self) -> Dict:
        return {"winner": self.winner or "无"}

    def get_public_state(self) -> Dict:
        return {
            "round": self.current_round,
            "mode": self.mode,
            "boss_id": self.boss_id,
            "players": [
                {
                    "player_id": pid,
                    "socket_id": p["socket_id"],
                    "username": p["username"],
                    "hp": p["hp"],
                    "max_hp": p["max_hp"],
                    "wins": p["wins"],
                    "character": p["character"],
                    "style": p["style"],
                    "available_skills": p["available_skills"],
                    "is_alive": p["is_alive"],
                    "puppet_master": p["puppet_master"],
                    "buffs": [b["name"] for b in p["buffs"]]
                } for pid, p in self.players.items()
            ]
        }