import json
from typing import Dict, List, Any, Optional

class CharacterSystem:
    def __init__(self, characters_file: str = "characters.json"):
        with open(characters_file, 'r', encoding='utf-8') as f:
            self.characters_data = json.load(f)

    def get_character(self, character_name: str) -> Optional[Dict[str, Any]]:
        return self.characters_data.get(character_name)

    def get_all_characters(self) -> Dict[str, Any]:
        return self.characters_data

    def get_character_skills(self, character_name: str) -> List[str]:
        character = self.get_character(character_name)
        if not character:
            return []
        
        skills = []
        for key in ["skill", "skill1", "skill2", "skill_normal", "skill_breakthrough"]:
            if key in character and character[key].get("name"):
                skills.append(character[key]["name"])
        
        # 添加默认技能
        if character_name == "幽灵":
            skills.append("不屈不挠")
        if character_name == "医师":
            skills.extend(["青囊秘要", "吃个桃桃"])
        if character_name == "圣骑士":
            skills.append("九锡黄龙")
        if character_name == "记录员":
            skills.append("将军饮马")
        
        return skills

    def apply_passive_effects(self, character_name: str, player_state: Dict):
        character = self.get_character(character_name)
        if not character or "passive" not in character:
            return
        
        passive = character["passive"]
        proficiency = player_state["proficiency"].get(character_name, 0)
        advanced = passive.get("advanced", {}) if proficiency >= 10 else {}

        if character_name == "幸运儿":
            player_state["wins"] += passive.get("start_wins", 0)
            player_state["states"]["win_interval"] = passive.get("win_interval", 3)
            if advanced:
                player_state["states"]["win_probability_bonus"] = advanced.get("win_probability_bonus", 0)
        elif character_name == "战士":
            damage_bonus = advanced.get("damage_bonus", passive.get("damage_bonus", 0))
            player_state["buffs"].append({
                "name": "战士被动",
                "duration": -1,
                "effect_data": {"damage_bonus": damage_bonus}
            })
        elif character_name == "医师":
            player_state["buffs"].append({
                "name": "青囊秘要",
                "duration": -1,
                "effect_data": {
                    "regen": passive["qingnang_bonus"].get("heal", 0),
                    "duration_bonus": passive["qingnang_bonus"].get("duration", 0)
                }
            })
            player_state["states"]["taotao_bonus"] = passive.get("taotao_bonus", 0)
            player_state["states"]["ignore_disable"] = passive.get("ignore_disable", False)
            if advanced:
                player_state["buffs"].append({
                    "name": "医师进阶",
                    "duration": -1,
                    "effect_data": {"heal_bonus": advanced.get("heal_bonus", 0)}
                })
        elif character_name == "圣骑士":
            player_state["buffs"].append({
                "name": "九锡黄龙",
                "duration": -1,
                "effect_data": passive.get("jiuxi_bonus", {})
            })