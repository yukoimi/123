import json
import random
import logging
from typing import Dict, List, Optional
from copy import deepcopy

logging.basicConfig(level=logging.DEBUG)

class GameEngine:
    def __init__(self, player_ids: List[str], mode: str = "standard"):
        # 未更改部分省略
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
        self.characters = self.load_json("characters.json")
        self.skills = self.load_json("skills.json")
        self.common_skills = list(self.skills.keys())
        self.mode = mode
        self.boss_id = None
        self.MAX_WINS = 3
        self.MOVE_OPTIONS = ["石头", "剪刀", "布"]

    def load_json(self, filename: str) -> Dict:
        """加载 JSON 文件"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"加载 {filename} 失败: {str(e)}")
            return {}

    def select_character(self, player_id: str, character_name: str, style: str, username: str, selected_skills: List[str] = []) -> Dict:
        """选择角色、流派和技能（无限乱斗）"""
        if player_id not in self.players:
            return {"success": False, "message": "玩家不存在"}
        if character_name not in self.characters:
            return {"success": False, "message": "角色不存在"}
        if style not in ["伤害流", "控制流", "回复流", "增益流", "防御流"]:
            return {"success": False, "message": "无效流派"}
        if self.mode == "infinite" and len(selected_skills) != 5:
            return {"success": False, "message": "无限乱斗需选择5个技能"}

        player = self.players[player_id]
        character = self.characters[character_name]
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
        player["available_skills"] = selected_skills if self.mode == "infinite" else self.common_skills.copy()
        if "skill" in character:
            player["available_skills"].append(character["skill"]["name"])
        for key in ["skill1", "skill2", "skill_normal", "skill_breakthrough"]:
            if key in character and character[key]["name"] not in player["available_skills"]:
                player["available_skills"].append(character[key]["name"])
        if self.mode == "infinite":
            player["available_skills"].append("鸿运当头")

        # 熟练度
        player["proficiency"][character_name] = player["proficiency"].get(character_name, 0) + 1

        # 初始化被动
        self.apply_passive_effects(player_id)
        self.ready_players.add(player_id)
        logging.debug(f"玩家 {player_id} ({username}) 选择角色 {character_name} ({style})，技能: {player['available_skills']}")

        # BOSS战初始化
        if self.mode == "boss" and not self.boss_id and len(self.ready_players) == len(self.players):
            self.boss_id = random.choice(list(self.players.keys()))
            self.players[self.boss_id]["max_hp"] = 50 + 10 * len(self.players)
            self.players[self.boss_id]["hp"] = self.players[self.boss_id]["max_hp"]
            self.players[self.boss_id]["available_skills"] += ["横扫", "要害锁定", "震天撼地", "能屈能伸", "复刻"]

        return {"success": True}

    def apply_passive_effects(self, player_id: str):
        """应用角色被动效果"""
        player = self.players[player_id]
        character = self.characters.get(player["character"])
        if not character or "passive" not in character:
            return

        passive = character["passive"]
        advanced = passive.get("advanced", {}) if player["proficiency"].get(player["character"], 0) >= 10 else {}

        if player["character"] == "幸运儿":
            player["wins"] += passive["start_wins"]
            player["states"]["win_interval"] = passive["win_interval"]
            if advanced:
                player["states"]["win_probability_bonus"] = advanced["win_probability_bonus"]
        elif player["character"] == "战士":
            damage_bonus = advanced.get("damage_bonus", passive["damage_bonus"])
            player["buffs"].append({"name": "战士被动", "duration": -1, "effect_data": {"damage_bonus": damage_bonus}})
        elif player["character"] == "医师":
            qingnang = passive["qingnang_bonus"]
            player["buffs"].append({
                "name": "青囊秘要",
                "duration": -1,
                "effect_data": {"regen": qingnang["heal"], "duration_bonus": qingnang["duration"]}
            })
            player["states"]["taotao_bonus"] = passive["taotao_bonus"]
            player["states"]["ignore_disable"] = passive["ignore_disable"]
            if advanced:
                player["buffs"].append({"name": "医师进阶", "duration": -1, "effect_data": {"heal_bonus": advanced["heal_bonus"]}})
        # 其他角色被动略，类似实现
        logging.debug(f"玩家 {player_id} 应用被动: {player['character']}")

    def submit_move(self, player_id: str, move: str) -> Dict:
        """提交出拳"""
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

    def use_skill(self, player_id: str, skill_name: str, targets: List[str], params: Dict = {}) -> Dict:
        """使用技能"""
        if player_id not in self.players:
            return {"success": False, "message": "玩家不存在"}
        if not self.players[player_id]["is_alive"]:
            return {"success": False, "message": "玩家已死亡"}
        if skill_name not in self.players[player_id]["available_skills"]:
            return {"success": False, "message": "技能不可用"}

        player = self.players[player_id]
        skill_data = self.skills.get(skill_name, self.find_character_skill(player["character"], skill_name))
        if not skill_data:
            skill_data = self.get_boss_skill(skill_name) if skill_name in ["横扫", "要害锁定", "震天撼地", "能屈能伸", "复刻"] else None
        if not skill_data:
            return {"success": False, "message": "技能数据不存在"}

        if skill_name in player["skill_cooldowns"] and player["skill_cooldowns"][skill_name] > 0:
            return {"success": False, "message": "技能在冷却中"}
        if "usage_limit" in skill_data and sum(1 for s in player["pending_skills"] if s["skill_name"] == skill_name) >= skill_data["usage_limit"]:
            return {"success": False, "message": "技能使用次数已达上限"}

        if not self.validate_targets(skill_data, targets, player_id):
            return {"success": False, "message": "无效目标"}

        player["pending_skills"].append({"skill_name": skill_name, "targets": targets, "params": params})
        return {"success": True}

    def get_boss_skill(self, skill_name: str) -> Optional[Dict]:
        """获取BOSS技能"""
        boss_skills = {
            "横扫": {"name": "横扫", "cooldown": 1, "effect_type": "direct_damage", "damage": 3, "target_type": "two_enemies"},
            "要害锁定": {"name": "要害锁定", "cooldown": 3, "effect_type": "buff", "duration": 3, "ignore_defense": True, "target_type": "self"},
            "震天撼地": {"name": "震天撼地", "cooldown": 1, "effect_type": "control", "control_turns": 1, "target_type": "all_others"},
            "能屈能伸": {"name": "能屈能伸", "cooldown": 4, "effect_type": "special", "heal_conversion": True, "no_attack_next": 1, "max_hp_cost": 10, "target_type": "self"},
            "复刻": {"name": "复刻", "cooldown": 3, "effect_type": "steal_skill", "duration": 3, "max_skills": 2, "target_type": "any_skill"}
        }
        return boss_skills.get(skill_name)

    def find_character_skill(self, character_name: str, skill_name: str) -> Optional[Dict]:
        """查找角色专属技能"""
        character = self.characters.get(character_name, {})
        for key in ["skill", "skill1", "skill2", "skill_normal", "skill_breakthrough"]:
            if key in character and character[key]["name"] == skill_name:
                return character[key]
        return None

    def validate_targets(self, skill_data: Dict, targets: List[str], player_id: str) -> bool:
        """验证技能目标"""
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
        """处理回合"""
        self.current_round += 1
        results = {"moves": {}, "effects": [], "damages": [], "wins": {}, "tasks": []}
        logging.debug(f"处理第 {self.current_round} 回合")

        # 更新状态
        self.update_states_and_cooldowns(results)  # 传递 results
        self.apply_round_passives()
        self.process_tasks(results)

        # 处理出拳
        for pid in self.players:
            if pid not in self.moves and self.players[pid]["is_alive"] and (self.mode != "boss" or pid != self.boss_id):
                self.moves[pid] = random.choice(self.MOVE_OPTIONS)
            if pid in self.moves:
                results["moves"][pid] = self.moves[pid]

        # 判定出拳胜负
        wins = self.judge_moves()
        for pid, win in wins.items():
            if win and self.players[pid]["is_alive"]:
                self.players[pid]["wins"] += 1
                results["wins"][pid] = True
                damage = 1 + self.get_player_buff(pid, "damage_bonus")
                for target_id in [p for p in self.players if p != pid and self.players[p]["is_alive"]]:
                    self.apply_damage(target_id, damage, results, source=pid)  # 传递 source

        # 处理技能
        for pid in self.players:
            if not self.players[pid]["is_alive"]:
                continue
            for skill in self.players[pid]["pending_skills"]:
                skill_result = self.apply_skill(pid, skill["skill_name"], skill["targets"], skill["params"])
                results["effects"].extend(skill_result["effects"])
                if "damages" in skill_result:
                    results["damages"].extend(skill_result["damages"])
            self.players[pid]["pending_skills"] = []

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

    def judge_moves(self) -> Dict[str, bool]:
        """判定出拳胜负"""
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

    def apply_skill(self, player_id: str, skill_name: str, targets: List[str], params: Dict) -> Dict:
        """应用技能效果"""
        player = self.players[player_id]
        skill_data = self.skills.get(skill_name, self.find_character_skill(player["character"], skill_name))
        if not skill_data:
            skill_data = self.get_boss_skill(skill_name)
        results = {"effects": [], "damages": []}

        # 设置冷却
        if skill_data["cooldown"] > 0:
            player["skill_cooldowns"][skill_name] = skill_data["cooldown"]

        effect_type = skill_data["effect_type"]
        style_bonus = self.get_player_buff(player_id, "buff_multiplier") if player["style"] == "增益流" else 1
        control_bonus = self.get_player_buff(player_id, "control_bonus") if player["style"] == "控制流" else 0
        heal_bonus = self.get_player_buff(player_id, "heal_bonus") if player["style"] == "回复流" else 0

        if effect_type == "direct_damage":
            damage = skill_data["damage"] + self.get_player_buff(player_id, "damage_bonus")
            for target_id in targets:
                self.apply_damage(target_id, damage, results, skill_data.get("ignore_defense", False), source=player_id)
        elif effect_type == "heal":
            heal = (skill_data["heal"] + heal_bonus) * self.get_player_buff(player_id, "heal_multiplier")
            self.apply_heal(player_id, heal, results)
        elif effect_type == "buff":
            player["buffs"].append({
                "name": skill_name,
                "duration": skill_data["duration"] * style_bonus,
                "effect_data": {
                    "damage_buff": skill_data.get("damage_buff", 0) * style_bonus,
                    "always_attack": skill_data.get("always_attack", 0)
                }
            })
            if skill_data.get("self_damage"):
                self.apply_damage(player_id, skill_data["self_damage"], results, source=player_id)
            results["effects"].append(f"{player_id} 获得 {skill_name} 增益")
        elif effect_type == "defense":
            player["buffs"].append({
                "name": skill_name,
                "duration": -1,
                "effect_data": {
                    "evasion": skill_data.get("evasion", 0),
                    "damage_reduction": skill_data.get("damage_reduction", 0) + (1 if player["style"] == "防御流" else 0)
                }
            })
            if skill_data.get("max_hp_cost"):
                player["max_hp"] -= skill_data["max_hp_cost"]
                player["hp"] = min(player["hp"], player["max_hp"])
            results["effects"].append(f"{player_id} 激活 {skill_name}")
        elif effect_type == "control":
            for target_id in targets:
                player["debuffs"].append({
                    "name": skill_name,
                    "duration": skill_data["control_turns"] + control_bonus,
                    "effect_data": {"controlled": True}
                })
                results["effects"].append(f"{target_id} 被 {skill_name} 控制")
            if skill_data.get("self_damage"):
                self.apply_damage(player_id, skill_data["self_damage"], results, source=player_id)
        elif effect_type == "coin_damage":  # 激昂
            target_id = targets[0]
            coin = params.get("coin_result", random.choice(["heads", "tails"]))
            if coin == "heads":
                self.apply_damage(player_id, skill_data["heads_self_damage"], results, source=player_id)
                self.apply_damage(target_id, skill_data["heads_enemy_damage"], results, source=player_id)
            else:
                self.apply_damage(player_id, skill_data["tails_self_damage"], results, source=player_id)
                self.apply_damage(target_id, skill_data["tails_enemy_damage"], results, source=player_id)
            results["effects"].append(f"{player_id} 使用激昂，硬币结果: {coin}")
        # 其他效果类型需实现
        return results

    def apply_damage(self, player_id: str, damage: float, results: Dict, ignore_defense: bool = False, source: str = None):
        """应用伤害"""
        player = self.players[player_id]
        if not player["is_alive"] or player.get("states", {}).get("invincible", 0) > 0:
            return

        reduction = 0 if ignore_defense else self.get_player_buff(player_id, "damage_reduction")
        final_damage = max(0, damage - reduction)
        player["hp"] = max(0, player["hp"] - final_damage)
        results["damages"].append(f"{player['username']} 受到 {final_damage} 伤害，剩余 {player['hp']} 血")

        if player["hp"] <= 0 and player["is_alive"]:
            self.handle_death(player_id, results, source)  # 传递 source

    def apply_heal(self, player_id: str, heal: float, results: Dict):
        """应用治疗"""
        player = self.players[player_id]
        if not player["is_alive"]:
            return
        heal_amount = heal * self.get_player_buff(player_id, "heal_multiplier")
        player["hp"] = min(player["hp"] + heal_amount, player["max_hp"])
        results["effects"].append(f"{player['username']} 恢复 {heal_amount} 血，当前 {player['hp']}")

    def handle_death(self, player_id: str, results: Dict, source: str = None):
        """处理玩家死亡"""
        player = self.players[player_id]
        if self.mode == "boss" and source is not None and source == self.boss_id:
            player["hp"] = 15
            player["puppet_master"] = self.boss_id
            results["effects"].append(f"{player['username']} 成为BOSS傀儡")
        elif player["character"] == "幽灵" and not player["states"].get("ghost_mode"):
            player["states"]["ghost_mode"] = True
            player["ghost_hits"] = player["states"]["ghost_hits"]
            player["revive_timer"] = player["states"]["revive_time"]
            results["effects"].append(f"{player['username']} 进入幽灵状态")
        elif self.mode == "infinite" and player["revive_count"] < 3:
            player["revive_count"] += 1
            player["revive_timer"] = 2
            results["effects"].append(f"{player['username']} 将在2回合后复活")
        else:
            player["is_alive"] = False
            results["effects"].append(f"{player['username']} 已死亡")

    def update_states_and_cooldowns(self, results: Dict):
        """更新状态和冷却"""
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
                    player["hp"] = player["states"]["revive_hp"]
                    player["is_alive"] = True
                    player["states"]["ghost_mode"] = False
                    player["available_skills"].append(player["states"]["revive_skill"])
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
        """应用每回合被动效果"""
        for pid, player in self.players.items():
            if not player["is_alive"]:
                continue
            if player["character"] == "幸运儿" and self.current_round % player["states"]["win_interval"] == 0:
                player["wins"] += 1
            elif player["character"] == "记录员" and self.current_round % player["states"]["auto_save_cd"] == 0:
                player["pending_skills"].append({"skill_name": "将军饮马", "targets": [pid], "params": {}})

    def process_tasks(self, results: Dict):
        """处理任务和奖励"""
        for pid, player in self.players.items():
            for task in player["tasks"]:
                if task["name"] == "输出流" and task["progress"] >= 15:
                    player["wins"] += 1
                    results["tasks"].append(f"{player['username']} 完成输出流任务，获1胜局")
                    player["tasks"].remove(task)
                # 其他任务略

    def trigger_random_event(self, results: Dict):
        """触发随机事件"""
        event = random.choice(["全场血量+2", "禁用控制技能1回合"])
        if event == "全场血量+2":
            for pid, player in self.players.items():
                if player["is_alive"]:
                    self.apply_heal(pid, 2, results)
        elif event == "禁用控制技能1回合":
            for pid, player in self.players.items():
                for skill in player["available_skills"]:
                    if self.skills.get(skill, {}).get("effect_type") == "control":
                        player["skill_cooldowns"][skill] = 1
        results["effects"].append(f"随机事件: {event}")

    def get_player_buff(self, player_id: str, buff_type: str) -> float:
        """获取玩家的buff/debuff值"""
        player = self.players[player_id]
        value = 0
        for buff in player["buffs"]:
            if buff_type in buff["effect_data"]:
                value += buff["effect_data"][buff_type]
        for debuff in player["debuffs"]:
            if buff_type in debuff["effect_data"]:
                value -= debuff["effect_data"][buff_type]
        return value

    def all_players_ready(self) -> bool:
        """检查所有玩家是否已选择角色"""
        return len(self.ready_players) == len(self.players)

    def all_moves_submitted(self) -> bool:
        """检查所有存活玩家是否已提交出拳"""
        return all(pid in self.moves or not self.players[pid]["is_alive"] or (self.mode == "boss" and pid == self.boss_id) for pid in self.players)

    def check_game_over(self):
        """检查游戏是否结束"""
        alive_players = [pid for pid in self.players if self.players[pid]["is_alive"]]
        if len(alive_players) <= 1:
            self.game_over = True
            self.winner = alive_players[0] if alive_players else None
            return
        for pid, player in self.players.items():
            if player["wins"] >= self.MAX_WINS:
                self.game_over = True
                self.winner = pid
                break

    def get_game_result(self) -> Dict:
        """获取游戏结果"""
        return {"winner": self.winner or "无"}

    def get_public_state(self) -> Dict:
        """获取公开游戏状态"""
        return {
            "round": self.current_round,
            "mode": self.mode,
            "boss_id": self.boss_id,
            "players": {
                pid: {
                    "socket_id": p["socket_id"],
                    "username": p["username"],
                    "hp": p["hp"],
                    "max_hp": p["max_hp"],
                    "wins": p["wins"],
                    "character": p["character"],
                    "style": p["style"],
                    "available_skills": p["available_skills"],
                    "is_alive": p["is_alive"],
                    "puppet_master": p["puppet_master"]
                } for pid, p in self.players.items()
            }
        }