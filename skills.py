import json
import random
from typing import Dict, List, Any, Optional

class SkillSystem:
    def __init__(self, skills_file: str = "skills.json"):
        with open(skills_file, 'r', encoding='utf-8') as f:
            self.skills_data = json.load(f)
        
    def get_skill(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """获取技能数据"""
        return self.skills_data.get(skill_name)
    
    def get_all_skills(self) -> Dict[str, Any]:
        """获取所有技能数据"""
        return self.skills_data
    
    def execute_skill(self, skill_name: str, user_id: str, target_ids: List[str], 
                     game_state: Dict, additional_params: Dict = None) -> Dict:
        """执行技能效果"""
        skill_data = self.get_skill(skill_name)
        if not skill_data:
            return {"success": False, "message": "技能不存在"}
        
        # 检查冷却时间
        player = game_state["players"][user_id]
        if skill_name in player.get("cooldowns", {}) and player["cooldowns"][skill_name] > 0:
            return {"success": False, "message": "技能冷却中"}
        
        # 执行技能效果
        result = self._execute_skill_effect(skill_data, user_id, target_ids, game_state, additional_params)
        
        # 设置冷却时间
        if skill_data["cooldown"] > 0:
            if "cooldowns" not in player:
                player["cooldowns"] = {}
            player["cooldowns"][skill_name] = skill_data["cooldown"]
        
        return result
    
    def _execute_skill_effect(self, skill_data: Dict, user_id: str, target_ids: List[str], 
                            game_state: Dict, additional_params: Dict = None) -> Dict:
        """执行具体技能效果"""
        effect_type = skill_data.get("effect_type")
        player = game_state["players"][user_id]
        result = {"success": True, "effects": [], "message": ""}
        
        # 根据效果类型执行不同逻辑
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
        # 添加更多效果类型...
        
        return result
    
    def _handle_direct_damage(self, skill_data: Dict, user_id: str, target_ids: List[str], 
                            game_state: Dict) -> Dict:
        """处理直接伤害"""
        damage = skill_data.get("damage", 0)
        ignore_defense = skill_data.get("ignore_defense", False)
        user = game_state["players"][user_id]
        
        # 应用伤害加成
        if "damage_buff" in user.get("buffs", {}):
            damage += user["buffs"]["damage_buff"]["value"]
        
        effects = []
        for target_id in target_ids:
            target = game_state["players"][target_id]
            actual_damage = damage
            
            # 检查规避
            if target.get("evasion", 0) > 0 and not ignore_defense:
                target["evasion"] -= 1
                effects.append(f"{target['name']} 规避了攻击")
                continue
            
            # 应用减伤
            if not ignore_defense and "damage_reduction" in target.get("buffs", {}):
                actual_damage = max(1, actual_damage - target["buffs"]["damage_reduction"]["value"])
            
            # 造成伤害
            target["hp"] = max(0, target["hp"] - actual_damage)
            effects.append(f"{target['name']} 受到 {actual_damage} 点伤害")
            
            # 检查死亡
            if target["hp"] <= 0:
                self._handle_death(target_id, game_state)
        
        return {"success": True, "effects": effects}
    
    def _handle_heal(self, skill_data: Dict, user_id: str, target_ids: List[str], 
                   game_state: Dict) -> Dict:
        """处理治疗"""
        heal = skill_data.get("heal", 0)
        user = game_state["players"][user_id]
        
        # 应用治疗加成
        if "heal_bonus" in user.get("buffs", {}):
            heal += user["buffs"]["heal_bonus"]["value"]
        
        effects = []
        for target_id in target_ids:
            target = game_state["players"][target_id]
            old_hp = target["hp"]
            target["hp"] = min(target["max_hp"], target["hp"] + heal)
            actual_heal = target["hp"] - old_hp
            if actual_heal > 0:
                effects.append(f"{target['name']} 恢复了 {actual_heal} 点生命值")
        
        return {"success": True, "effects": effects}
    
    def _handle_control(self, skill_data: Dict, user_id: str, target_ids: List[str], 
                      game_state: Dict) -> Dict:
        """处理控制效果"""
        control_turns = skill_data.get("control_turns", 1)
        self_damage = skill_data.get("self_damage", 0)
        user = game_state["players"][user_id]
        
        effects = []
        
        # 自身扣血
        if self_damage > 0:
            user["hp"] = max(0, user["hp"] - self_damage)
            effects.append(f"{user['name']} 损失了 {self_damage} 点生命值")
        
        # 控制目标
        for target_id in target_ids:
            target = game_state["players"][target_id]
            if "buffs" not in target:
                target["buffs"] = {}
            target["buffs"]["controlled"] = {
                "duration": control_turns,
                "controller": user_id
            }
            effects.append(f"{target['name']} 被控制 {control_turns} 回合")
        
        return {"success": True, "effects": effects}
    
    def _handle_buff(self, skill_data: Dict, user_id: str, target_ids: List[str], 
                   game_state: Dict) -> Dict:
        """处理增益效果"""
        user = game_state["players"][user_id]
        effects = []
        
        # 自身扣血
        self_damage = skill_data.get("self_damage", 0)
        if self_damage > 0:
            user["hp"] = max(0, user["hp"] - self_damage)
            effects.append(f"{user['name']} 损失了 {self_damage} 点生命值")
        
        # 应用增益
        if "buffs" not in user:
            user["buffs"] = {}
        
        if "damage_buff" in skill_data:
            user["buffs"]["damage_buff"] = {
                "value": skill_data["damage_buff"],
                "duration": skill_data.get("duration", 1)
            }
            effects.append(f"{user['name']} 获得伤害增益")
        
        if "damage_multiplier" in skill_data:
            user["buffs"]["damage_multiplier"] = {
                "value": skill_data["damage_multiplier"],
                "duration": skill_data.get("duration", 1)
            }
            effects.append(f"{user['name']} 获得伤害倍率增益")
        
        return {"success": True, "effects": effects}
    
    def _handle_defense(self, skill_data: Dict, user_id: str, target_ids: List[str], 
                      game_state: Dict) -> Dict:
        """处理防御效果"""
        user = game_state["players"][user_id]
        effects = []
        
        # 规避次数
        if "evasion" in skill_data:
            user["evasion"] = user.get("evasion", 0) + skill_data["evasion"]
            effects.append(f"{user['name']} 获得 {skill_data['evasion']} 次规避")
        
        # 减伤
        if "damage_reduction" in skill_data:
            if "buffs" not in user:
                user["buffs"] = {}
            user["buffs"]["damage_reduction"] = {
                "value": skill_data["damage_reduction"],
                "duration": skill_data.get("duration", -1)  # -1表示永久
            }
            effects.append(f"{user['name']} 获得减伤效果")
        
        # 血量上限消耗
        if "max_hp_cost" in skill_data:
            user["max_hp"] = max(1, user["max_hp"] - skill_data["max_hp_cost"])
            user["hp"] = min(user["hp"], user["max_hp"])
            effects.append(f"{user['name']} 血量上限减少 {skill_data['max_hp_cost']}")
        
        return {"success": True, "effects": effects}
    
    def _handle_coin_damage(self, skill_data: Dict, user_id: str, target_ids: List[str], 
                          game_state: Dict, additional_params: Dict) -> Dict:
        """处理抛硬币伤害"""
        user = game_state["players"][user_id]
        target_id = target_ids[0] if target_ids else None
        
        # 检查是否使用胜局选择结果
        if additional_params and additional_params.get("use_win", False):
            if user.get("wins", 0) > 0:
                user["wins"] -= 1
                coin_result = additional_params.get("coin_choice", True)  # True为正面
            else:
                return {"success": False, "message": "没有胜局可用"}
        else:
            coin_result = random.choice([True, False])  # True为正面，False为反面
        
        effects = []
        if coin_result:  # 正面
            # 自身扣血
            self_damage = skill_data.get("heads_self_damage", 0)
            if self_damage > 0:
                user["hp"] = max(0, user["hp"] - self_damage)
                effects.append(f"{user['name']} 损失 {self_damage} 点生命值")
            
            # 敌人扣血
            if target_id:
                target = game_state["players"][target_id]
                enemy_damage = skill_data.get("heads_enemy_damage", 0)
                target["hp"] = max(0, target["hp"] - enemy_damage)
                effects.append(f"{target['name']} 受到 {enemy_damage} 点伤害")
            
            effects.insert(0, "硬币结果：正面")
        else:  # 反面
            # 自身扣血
            self_damage = skill_data.get("tails_self_damage", 0)
            if self_damage > 0:
                user["hp"] = max(0, user["hp"] - self_damage)
                effects.append(f"{user['name']} 损失 {self_damage} 点生命值")
            
            # 敌人扣血
            if target_id:
                target = game_state["players"][target_id]
                enemy_damage = skill_data.get("tails_enemy_damage", 0)
                target["hp"] = max(0, target["hp"] - enemy_damage)
                effects.append(f"{target['name']} 受到 {enemy_damage} 点伤害")
            
            effects.insert(0, "硬币结果：反面")
        
        return {"success": True, "effects": effects}
    
    def _handle_duel(self, skill_data: Dict, user_id: str, target_ids: List[str], 
                   game_state: Dict) -> Dict:
        """处理单挑"""
        if not target_ids:
            return {"success": False, "message": "需要选择单挑对象"}
        
        target_id = target_ids[0]
        user = game_state["players"][user_id]
        target = game_state["players"][target_id]
        
        # 创建单挑状态
        duel_state = {
            "type": "duel",
            "players": [user_id, target_id],
            "rounds": skill_data.get("duel_rounds", 1),
            "current_round": 0,
            "skill_data": skill_data
        }
        
        game_state["special_state"] = duel_state
        
        return {
            "success": True, 
            "effects": [f"{user['name']} 向 {target['name']} 发起单挑"],
            "special_action": "start_duel"
        }
    
    def _handle_charge_damage(self, skill_data: Dict, user_id: str, target_ids: List[str], 
                            game_state: Dict) -> Dict:
        """处理蓄力伤害"""
        user = game_state["players"][user_id]
        charge_time = skill_data.get("charge_time", 0)
        
        if "charge_skills" not in user:
            user["charge_skills"] = {}
        
        # 开始蓄力
        user["charge_skills"][skill_data["name"]] = {
            "remaining_time": charge_time,
            "target_ids": target_ids,
            "skill_data": skill_data
        }
        
        return {
            "success": True, 
            "effects": [f"{user['name']} 开始蓄力 {skill_data['name']}"],
            "message": f"需要蓄力 {charge_time} 回合"
        }
    
    def _handle_death(self, player_id: str, game_state: Dict):
        """处理玩家死亡"""
        player = game_state["players"][player_id]
        
        # 检查是否有死亡拯救技能
        if "不屈不挠" in player.get("available_skills", []):
            # 触发不屈不挠
            player["hp"] = 1
            if "buffs" not in player:
                player["buffs"] = {}
            player["buffs"]["shield"] = {
                "value": 2,
                "duration": 3
            }
            # 移除不屈不挠（每局限1次）
            player["available_skills"].remove("不屈不挠")
            return
        
        # 标记为死亡
        player["is_dead"] = True
        player["death_round"] = game_state.get("current_round", 0)
    
    def update_cooldowns(self, game_state: Dict):
        """更新所有玩家的技能冷却"""
        for player in game_state["players"].values():
            if "cooldowns" in player:
                for skill_name in list(player["cooldowns"].keys()):
                    player["cooldowns"][skill_name] -= 1
                    if player["cooldowns"][skill_name] <= 0:
                        del player["cooldowns"][skill_name]
    
    def update_buffs(self, game_state: Dict):
        """更新所有玩家的buff效果"""
        for player in game_state["players"].values():
            if "buffs" in player:
                for buff_name in list(player["buffs"].keys()):
                    buff = player["buffs"][buff_name]
                    if "duration" in buff and buff["duration"] > 0:
                        buff["duration"] -= 1
                        if buff["duration"] <= 0:
                            del player["buffs"][buff_name]
    
    def process_charge_skills(self, game_state: Dict):
        """处理蓄力技能"""
        for player_id, player in game_state["players"].items():
            if "charge_skills" not in player:
                continue
            
            for skill_name in list(player["charge_skills"].keys()):
                charge_info = player["charge_skills"][skill_name]
                charge_info["remaining_time"] -= 1
                
                if charge_info["remaining_time"] <= 0:
                    # 蓄力完成，执行技能
                    skill_data = charge_info["skill_data"]
                    target_ids = charge_info["target_ids"]
                    
                    # 执行蓄力技能效果
                    if skill_data["name"] == "五龙盘打":
                        # 对除自己外的所有人造成伤害
                        damage = skill_data["damage"]
                        for tid, target in game_state["players"].items():
                            if tid != player_id and not target.get("is_dead", False):
                                target["hp"] = max(0, target["hp"] - damage)
                    
                    del player["charge_skills"][skill_name]