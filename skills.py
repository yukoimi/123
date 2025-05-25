import json
import random
from typing import Dict, List, Any, Optional

class SkillSystem:
    def __init__(self, skills_file: str = "skills.json"):
        with open(skills_file, 'r', encoding='utf-8') as f:
            self.skills_data = json.load(f)
        
    def get_skill(self, skill_name: str) -> Optional[Dict[str, Any]]:
        return self.skills_data.get(skill_name)
    
    def get_all_skills(self) -> Dict[str, Any]:
        return self.skills_data
    
    def execute_skill(self, skill_name: str, user_id: str, target_ids: List[str], 
                     game_state: Dict, additional_params: Dict = None) -> Dict:
        skill_data = self.get_skill(skill_name)
        if not skill_data:
            return {"success": False, "message": "技能不存在"}
        
        player = next((p for p in game_state["players"] if p["player_id"] == user_id), None)
        if not player:
            return {"success": False, "message": "玩家不存在"}
        
        # 检查冷却时间
        if skill_name in player.get("skill_cooldowns", {}) and player["skill_cooldowns"][skill_name] > 0:
            return {"success": False, "message": "技能冷却中"}
        
        # 检查胜局消耗
        if additional_params and additional_params.get("consume_win", False) and player.get("wins", 0) <= 0:
            return {"success": False, "message": "没有胜局可消耗"}
        
        # 执行技能效果
        result = self._execute_skill_effect(skill_data, user_id, target_ids, game_state, additional_params)
        
        # 设置冷却时间
        if skill_data["cooldown"] > 0:
            player["skill_cooldowns"][skill_name] = skill_data["cooldown"]
        
        return result
    
    def _execute_skill_effect(self, skill_data: Dict, user_id: str, target_ids: List[str], 
                            game_state: Dict, additional_params: Dict = None) -> Dict:
        effect_type = skill_data.get("effect_type")
        player = next((p for p in game_state["players"] if p["player_id"] == user_id), None)
        result = {"success": True, "effects": [], "message": ""}
        
        if effect_type == "direct_damage":
            result = self._handle_direct_damage(skill_data, user_id, target_ids, game_state)
        elif effect_type == "heal":
            result = self._handle_heal(skill_data, user_id, target_ids, game_state)
        elif effect_type == "control":
            result = self._handle_control(skill_data, user_id, target_ids, game_state)
        elif effect_type == "buff":
            result = self._handle_buff(skill_data, user_id, target_ids, game_state)
        elif effect_type == "defense":
            result = self._handle_defense(skill_data, user_id, target_ids, game_state)
        elif effect_type == "coin_damage":
            result = self._handle_coin_damage(skill_data, user_id, target_ids, game_state, additional_params)
        elif effect_type == "duel":
            result = self._handle_duel(skill_data, user_id, target_ids, game_state)
        elif effect_type == "charge_damage":
            result = self._handle_charge_damage(skill_data, user_id, target_ids, game_state)
        elif effect_type == "regen":
            result = self._handle_regen(skill_data, user_id, target_ids, game_state)
        elif effect_type == "damage_with_regen":
            result = self._handle_damage_with_regen(skill_data, user_id, target_ids, game_state)
        return result
    
    def _handle_direct_damage(self, skill_data: Dict, user_id: str, target_ids: List[str], 
                            game_state: Dict) -> Dict:
        damage = skill_data.get("damage", 0)
        ignore_defense = skill_data.get("ignore_defense", False)
        user = next((p for p in game_state["players"] if p["player_id"] == user_id), None)
        
        # 应用伤害加成
        damage_bonus = sum(b["effect_data"].get("damage_bonus", 0) for b in user.get("buffs", []) if "effect_data" in b)
        damage += damage_bonus
        
        effects = []
        for target_id in target_ids:
            target = next((p for p in game_state["players"] if p["player_id"] == target_id), None)
            if not target or not target["is_alive"]:
                continue
            actual_damage = damage
            
            # 检查规避
            if target.get("evasion", 0) > 0 and not ignore_defense:
                target["evasion"] -= 1
                effects.append(f"{target['username']} 规避了攻击")
                continue
            
            # 应用减伤
            if not ignore_defense:
                reduction = sum(b["effect_data"].get("damage_reduction", 0) for b in target.get("buffs", []) if "effect_data" in b)
                actual_damage = max(1, actual_damage - reduction)
            
            # 造成伤害
            target["hp"] = max(0, target["hp"] - actual_damage)
            effects.append(f"{target['username']} 受到 {actual_damage} 点伤害")
            
            # 检查死亡
            if target["hp"] <= 0:
                self._handle_death(target_id, game_state)
        
        return {"success": True, "effects": effects}
    
    def _handle_heal(self, skill_data: Dict, user_id: str, target_ids: List[str], 
                   game_state: Dict) -> Dict:
        heal = skill_data.get("heal", 0)
        user = next((p for p in game_state["players"] if p["player_id"] == user_id), None)
        
        # 应用治疗加成
        heal_bonus = sum(b["effect_data"].get("heal_bonus", 0) for b in user.get("buffs", []) if "effect_data" in b)
        heal += heal_bonus
        
        effects = []
        for target_id in target_ids:
            target = next((p for p in game_state["players"] if p["player_id"] == target_id), None)
            if not target or not target["is_alive"]:
                continue
            old_hp = target["hp"]
            target["hp"] = min(target["max_hp"], target["hp"] + heal)
            actual_heal = target["hp"] - old_hp
            if actual_heal > 0:
                effects.append(f"{target['username']} 恢复了 {actual_heal} 点生命值")
        
        return {"success": True, "effects": effects}
    
    def _handle_control(self, skill_data: Dict, user_id: str, target_ids: List[str], 
                      game_state: Dict) -> Dict:
        control_turns = skill_data.get("control_turns", 1)
        self_damage = skill_data.get("self_damage", 0)
        user = next((p for p in game_state["players"] if p["player_id"] == user_id), None)
        
        effects = []
        
        # 自身扣血
        if self_damage > 0:
            user["hp"] = max(0, user["hp"] - self_damage)
            effects.append(f"{user['username']} 损失了 {self_damage} 点生命值")
        
        # 控制目标
        for target_id in target_ids:
            target = next((p for p in game_state["players"] if p["player_id"] == target_id), None)
            if not target or not target["is_alive"]:
                continue
            target["debuffs"].append({
                "name": "controlled",
                "duration": control_turns,
                "effect_data": {"controlled": True, "controller": user_id}
            })
            effects.append(f"{target['username']} 被控制 {control_turns} 回合")
        
        return {"success": True, "effects": effects}
    
    def _handle_buff(self, skill_data: Dict, user_id: str, target_ids: List[str], 
                   game_state: Dict) -> Dict:
        user = next((p for p in game_state["players"] if p["player_id"] == user_id), None)
        effects = []
        
        # 自身扣血
        self_damage = skill_data.get("self_damage", 0)
        if self_damage > 0:
            user["hp"] = max(0, user["hp"] - self_damage)
            effects.append(f"{user['username']} 损失了 {self_damage} 点生命值")
        
        # 应用增益
        for target_id in target_ids:
            target = next((p for p in game_state["players"] if p["player_id"] == target_id), None)
            if not target or not target["is_alive"]:
                continue
            buff = {
                "name": skill_data["name"],
                "duration": skill_data.get("duration", 1),
                "effect_data": {}
            }
            if "damage_buff" in skill_data:
                buff["effect_data"]["damage_bonus"] = skill_data["damage_buff"]
            if "damage_multiplier" in skill_data:
                buff["effect_data"]["damage_multiplier"] = skill_data["damage_multiplier"]
            if "control_bonus" in skill_data:
                buff["effect_data"]["control_bonus"] = skill_data["control_bonus"]
            if "delayed_damage" in skill_data:
                buff["effect_data"]["delayed_damage"] = skill_data["delayed_damage"]
            target["buffs"].append(buff)
            effects.append(f"{target['username']} 获得 {skill_data['name']} 增益")
        
        return {"success": True, "effects": effects}
    
    def _handle_defense(self, skill_data: Dict, user_id: str, target_ids: List[str], 
                      game_state: Dict) -> Dict:
        user = next((p for p in game_state["players"] if p["player_id"] == user_id), None)
        effects = []
        
        # 规避次数
        if "evasion" in skill_data:
            user["evasion"] = user.get("evasion", 0) + skill_data["evasion"]
            effects.append(f"{user['username']} 获得 {skill_data['evasion']} 次规避")
        
        # 减伤
        if "damage_reduction" in skill_data:
            user["buffs"].append({
                "name": skill_data["name"],
                "duration": skill_data.get("duration", -1),
                "effect_data": {"damage_reduction": skill_data["damage_reduction"]}
            })
            effects.append(f"{user['username']} 获得减伤效果")
        
        # 血量上限消耗
        if "max_hp_cost" in skill_data:
            user["max_hp"] = max(1, user["max_hp"] - skill_data["max_hp_cost"])
            user["hp"] = min(user["hp"], user["max_hp"])
            effects.append(f"{user['username']} 血量上限减少 {skill_data['max_hp_cost']}")
        
        return {"success": True, "effects": effects}
    
    def _handle_coin_damage(self, skill_data: Dict, user_id: str, target_ids: List[str], 
                          game_state: Dict, additional_params: Dict) -> Dict:
        user = next((p for p in game_state["players"] if p["player_id"] == user_id), None)
        target_id = target_ids[0] if target_ids else None
        
        # 检查是否使用胜局选择结果
        if additional_params and additional_params.get("use_win", False):
            if user.get("wins", 0) > 0:
                user["wins"] -= 1
                coin_result = additional_params.get("coin_choice", True)
            else:
                return {"success": False, "message": "没有胜局可用"}
        else:
            coin_result = random.choice([True, False])
        
        effects = []
        if coin_result:
            self_damage = skill_data.get("heads_self_damage", 0)
            if self_damage > 0:
                user["hp"] = max(0, user["hp"] - self_damage)
                effects.append(f"{user['username']} 损失 {self_damage} 点生命值")
            
            if target_id:
                target = next((p for p in game_state["players"] if p["player_id"] == target_id), None)
                if target and target["is_alive"]:
                    enemy_damage = skill_data.get("heads_enemy_damage", 0)
                    target["hp"] = max(0, target["hp"] - enemy_damage)
                    effects.append(f"{target['username']} 受到 {enemy_damage} 点伤害")
            
            effects.insert(0, "硬币结果：正面")
        else:
            self_damage = skill_data.get("tails_self_damage", 0)
            if self_damage > 0:
                user["hp"] = max(0, user["hp"] - self_damage)
                effects.append(f"{user['username']} 损失 {self_damage} 点生命值")
            
            if target_id:
                target = next((p for p in game_state["players"] if p["player_id"] == target_id), None)
                if target and target["is_alive"]:
                    enemy_damage = skill_data.get("tails_enemy_damage", 0)
                    target["hp"] = max(0, target["hp"] - enemy_damage)
                    effects.append(f"{target['username']} 受到 {enemy_damage} 点伤害")
            
            effects.insert(0, "硬币结果：反面")
        
        return {"success": True, "effects": effects}
    
    def _handle_duel(self, skill_data: Dict, user_id: str, target_ids: List[str], 
                   game_state: Dict) -> Dict:
        if not target_ids:
            return {"success": False, "message": "需要选择单挑对象"}
        
        target_id = target_ids[0]
        user = next((p for p in game_state["players"] if p["player_id"] == user_id), None)
        target = next((p for p in game_state["players"] if p["player_id"] == target_id), None)
        if not target or not target["is_alive"]:
            return {"success": False, "message": "目标无效"}
        
        duel_state = {
            "type": "duel",
            "players": [user_id, target_id],
            "rounds": skill_data.get("duel_rounds", 1),
            "current_round": 0,
            "skill_data": skill_data,
            "exclude_self_damage": skill_data.get("exclude_self_damage", False)
        }
        
        game_state["special_state"] = duel_state
        
        return {
            "success": True, 
            "effects": [f"{user['username']} 向 {target['username']} 发起单挑"],
            "special_action": "start_duel"
        }

    def _handle_regen(self, skill_data: Dict, user_id: str, target_ids: List[str], 
                     game_state: Dict) -> Dict:
        user = next((p for p in game_state["players"] if p["player_id"] == user_id), None)
        effects = []
        
        for target_id in target_ids:
            target = next((p for p in game_state["players"] if p["player_id"] == target_id), None)
            if not target or not target["is_alive"]:
                continue
            target["buffs"].append({
                "name": skill_data["name"],
                "duration": skill_data.get("duration", 1),
                "effect_data": {
                    "heal": skill_data.get("heal", 1),
                    "heal_bonus": skill_data.get("heal_bonus", 0)
                }
            })
            effects.append(f"{target['username']} 获得每回合恢复 {skill_data['heal']} 点生命值效果，持续 {skill_data['duration']} 回合")
        
        return {"success": True, "effects": effects}

    def _handle_damage_with_regen(self, skill_data: Dict, user_id: str, target_ids: List[str], 
                                 game_state: Dict) -> Dict:
        user = next((p for p in game_state["players"] if p["player_id"] == user_id), None)
        effects = []
        
        for target_id in target_ids:
            target = next((p for p in game_state["players"] if p["player_id"] == target_id), None)
            if not target or not target["is_alive"]:
                continue
            damage = skill_data.get("damage", 0)
            target["hp"] = max(0, target["hp"] - damage)
            effects.append(f"{target['username']} 受到 {damage} 点伤害")
            
            if "enemy_regen" in skill_data and not skill_data.get("interrupted", False):
                target["buffs"].append({
                    "name": skill_data["name"] + "_regen",
                    "duration": skill_data.get("regen_duration", 1),
                    "effect_data": {"heal": skill_data["enemy_regen"]}
                })
                effects.append(f"{target['username']} 将在下 {skill_data['regen_duration']} 回合每回合恢复 {skill_data['enemy_regen']} 点生命值")
        
        return {"success": True, "effects": effects}
    
    def _handle_charge_damage(self, skill_data: Dict, user_id: str, target_ids: List[str], 
                            game_state: Dict) -> Dict:
        user = next((p for p in game_state["players"] if p["player_id"] == user_id), None)
        charge_time = skill_data.get("charge_time", 0)
        
        if "charge_skills" not in user:
            user["charge_skills"] = {}
        
        user["charge_skills"][skill_data["name"]] = {
            "remaining_time": charge_time,
            "target_ids": target_ids,
            "skill_data": skill_data
        }
        
        return {
            "success": True, 
            "effects": [f"{user['username']} 开始蓄力 {skill_data['name']}"],
            "message": f"需要蓄力 {charge_time} 回合"
        }
    
    def _handle_death(self, player_id: str, game_state: Dict):
        player = next((p for p in game_state["players"] if p["player_id"] == player_id), None)
        if not player:
            return
        
        if "不屈不挠" in player.get("available_skills", []):
            player["hp"] = 1
            player["buffs"].append({
                "name": "shield",
                "duration": 3,
                "effect_data": {"damage_reduction": 2}
            })
            player["available_skills"].remove("不屈不挠")
            return
        
        player["is_alive"] = False
        player["death_round"] = game_state.get("round", 0)
    
    def update_cooldowns(self, game_state: Dict):
        for player in game_state["players"]:
            if "skill_cooldowns" in player:
                for skill_name in list(player["skill_cooldowns"].keys()):
                    player["skill_cooldowns"][skill_name] -= 1
                    if player["skill_cooldowns"][skill_name] <= 0:
                        del player["skill_cooldowns"][skill_name]
    
    def update_buffs(self, game_state: Dict):
        for player in game_state["players"]:
            for buff in player["buffs"][:]:
                if buff["duration"] > 0:
                    # 应用再生效果
                    if "heal" in buff.get("effect_data", {}):
                        player["hp"] = min(player["max_hp"], player["hp"] + buff["effect_data"]["heal"])
                        print(f"{player['username']} 因 {buff['name']} 恢复 {buff['effect_data']['heal']} 点生命值")
                    buff["duration"] -= 1
                    if buff["duration"] <= 0:
                        if "delayed_damage" in buff.get("effect_data", {}):
                            player["hp"] = max(0, player["hp"] - buff["effect_data"]["delayed_damage"])
                            print(f"{player['username']} 因 {buff['name']} 效果结束，损失 {buff['effect_data']['delayed_damage']} 点生命值")
                        player["buffs"].remove(buff)
    
    def process_charge_skills(self, game_state: Dict):
        for player in game_state["players"]:
            if "charge_skills" not in player:
                continue
            for skill_name in list(player["charge_skills"].keys()):
                charge_info = player["charge_skills"][skill_name]
                charge_info["remaining_time"] -= 1
                if charge_info["remaining_time"] <= 0:
                    skill_data = charge_info["skill_data"]
                    target_ids = charge_info["target_ids"]
                    if skill_data["name"] == "五龙盘打":
                        damage = skill_data["damage"]
                        for p in game_state["players"]:
                            if p["player_id"] != player["player_id"] and p["is_alive"]:
                                p["hp"] = max(0, p["hp"] - damage)
                    del player["charge_skills"][skill_name]