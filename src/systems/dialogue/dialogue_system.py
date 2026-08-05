#!/usr/bin/env python3
"""
Система диалогов и взаимодействия с NPC
Поддержка проверки характеристик (харизма) для получения информации
"""

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DialogueOutcome(Enum):
    """Возможные исходы диалога"""
    SUCCESS = "success"  # Получена полезная информация
    PARTIAL = "partial"  # Получена частичная информация
    FAILURE = "failure"  # Отказ в информации
    HOSTILE = "hostile"  # Враждебная реакция (энкантер!)
    NEUTRAL = "neutral"  # Нейтральная беседа без информации


@dataclass
class DialogueLine:
    """Строка диалога"""
    speaker: str
    text: str
    emotion: str = "neutral"
    requires_check: bool = False
    check_attribute: str = ""
    check_difficulty: float = 0.0


@dataclass
class DialogueResult:
    """Результат диалога"""
    outcome: DialogueOutcome
    information: dict[str, Any] | None = None
    message: str = ""
    reputation_change: float = 0.0
    triggered_encounter: bool = False
    encounter_type: str = ""


@dataclass
class NPCProfile:
    """Профиль NPC"""
    npc_id: str
    name: str
    personality: str = "friendly"  # friendly, neutral, suspicious, hostile
    knowledge_level: float = 0.5  # 0.0 - 1.0
    knows_exit_location: bool = False
    exit_hint_accuracy: float = 0.8  # Точность подсказки
    charisma_threshold: float = 0.3  # Порог харизмы для сотрудничества
    gossip_topics: list[str] = field(default_factory=list)
    rewards_for_help: list[str] = field(default_factory=list)


class DialogueSystem:
    """
    Система диалогов с проверкой характеристик и случайными событиями
    """
    
    def __init__(self):
        # Профили NPC
        self.npc_profiles: dict[str, NPCProfile] = {}
        
        # История диалогов
        self.dialogue_history: list[DialogueResult] = []
        
        # Шаблоны ответов
        self.response_templates = self._load_response_templates()
        
    def _load_response_templates(self) -> dict[str, list[str]]:
        """Загрузить шаблоны ответов для разных ситуаций"""
        return {
            'exit_hint_success': [
                "Я видел светящийся столб на {direction}! Иди туда.",
                "Маяк находится примерно {distance} метров на {direction}.",
                "Если пойдешь на {direction}, найдешь выход.",
                "Держи путь на {direction}, там твой выход."
            ],
            'exit_hint_partial': [
                "Кажется, что-то светится на {direction}, но я не уверен.",
                "Слышал, выход где-то на {direction}, но точно не скажу.",
                "Может быть на {direction}, но я там не был."
            ],
            'exit_hint_failure': [
                "Понятия не имею, ищи сам.",
                "Не буду тебе помогать.",
                "У меня свои проблемы."
            ],
            'hostile_response': [
                "Ты мне не нравишься. Уходи!",
                "Пошел вон отсюда!",
                "Сейчас как дам!"
            ],
            'gossip': [
                "Ходят слухи о сокровищах где-то здесь...",
                "Говорят, в этом месте водятся опасные твари.",
                "Я слышал странные звуки прошлой ночью."
            ]
        }
    
    def register_npc(self, npc_id: str, name: str, 
                     personality: str = "friendly",
                     knows_exit: bool = False,
                     knowledge_level: float = 0.5,
                     charisma_threshold: float = 0.3):
        """Зарегистрировать NPC"""
        profile = NPCProfile(
            npc_id=npc_id,
            name=name,
            personality=personality,
            knows_exit_location=knows_exit,
            knowledge_level=knowledge_level,
            exit_hint_accuracy=max(0.5, knowledge_level),
            charisma_threshold=charisma_threshold,
            gossip_topics=random.sample(['treasure', 'monsters', 'strange_sounds'], k=2)
        )
        self.npc_profiles[npc_id] = profile
    
    def start_dialogue(self, npc_id: str, player_charisma: float = 0.5,
                       player_reputation: float = 0.0,
                       request_type: str = "exit_direction") -> DialogueResult:
        """
        Начать диалог с NPC
        
        Args:
            npc_id: ID NPC
            player_charisma: Харизма игрока (0.0 - 1.0)
            player_reputation: Репутация игрока (-1.0 - 1.0)
            request_type: Тип запроса (exit_direction, gossip, help)
        
        Returns:
            DialogueResult с результатом диалога
        """
        if npc_id not in self.npc_profiles:
            return DialogueResult(
                outcome=DialogueOutcome.FAILURE,
                message="NPC не найден"
            )
        
        npc = self.npc_profiles[npc_id]
        
        # Рассчитываем модификаторы
        charisma_modifier = player_charisma / max(0.1, npc.charisma_threshold)
        reputation_modifier = 1.0 + player_reputation * 0.5
        personality_modifier = self._get_personality_modifier(npc.personality)
        
        # Итоговый шанс успеха
        success_chance = min(1.0, max(0.0, 
            0.5 * charisma_modifier * reputation_modifier * personality_modifier
        ))
        
        # Проверка на враждебность
        if npc.personality == "hostile" or success_chance < 0.2:
            if random.random() < 0.3:  # 30% шанс враждебной реакции
                return self._handle_hostile_encounter(npc)
        
        # Определение исхода
        roll = random.random()
        
        if request_type == "exit_direction":
            if not npc.knows_exit_location:
                return DialogueResult(
                    outcome=DialogueOutcome.FAILURE,
                    message=f"{npc.name}: \"Я не знаю где выход.\""
                )
            
            if roll < success_chance * 0.7:  # Полный успех
                return self._provide_exit_hint(npc, accuracy=1.0)
            elif roll < success_chance:  # Частичный успех
                return self._provide_exit_hint(npc, accuracy=npc.exit_hint_accuracy * 0.5)
            else:  # Провал
                return DialogueResult(
                    outcome=DialogueOutcome.FAILURE,
                    message=random.choice(self.response_templates['exit_hint_failure'])
                )
        
        elif request_type == "gossip":
            return self._provide_gossip(npc)
        
        return DialogueResult(
            outcome=DialogueOutcome.NEUTRAL,
            message="Диалог завершен"
        )
    
    def _get_personality_modifier(self, personality: str) -> float:
        """Получить модификатор для типа личности"""
        modifiers = {
            'friendly': 1.3,
            'neutral': 1.0,
            'suspicious': 0.7,
            'hostile': 0.4
        }
        return modifiers.get(personality, 1.0)
    
    def _provide_exit_hint(self, npc: NPCProfile, accuracy: float = 1.0) -> DialogueResult:
        """Предоставить подсказку о выходе"""
        # Генерируем направление с учетом точности
        true_direction = self._get_true_exit_direction()
        
        if accuracy >= 1.0:
            direction = true_direction
            templates = self.response_templates['exit_hint_success']
            outcome = DialogueOutcome.SUCCESS
        else:
            # С некоторой вероятностью даем неточное направление
            if random.random() > accuracy:
                direction = self._get_random_wrong_direction(true_direction)
                templates = self.response_templates['exit_hint_partial']
                outcome = DialogueOutcome.PARTIAL
            else:
                direction = true_direction
                templates = self.response_templates['exit_hint_success']
                outcome = DialogueOutcome.SUCCESS
        
        # Расстояние (примерное)
        distance = random.randint(50, 200)
        
        message = random.choice(templates).format(
            direction=direction,
            distance=distance
        )
        
        return DialogueResult(
            outcome=outcome,
            information={
                'direction': direction,
                'distance_estimate': distance,
                'accuracy': accuracy,
                'true_direction': true_direction if accuracy >= 1.0 else None
            },
            message=f"{npc.name}: \"{message}\"",
            reputation_change=0.1
        )
    
    def _provide_gossip(self, npc: NPCProfile) -> DialogueResult:
        """Предоставить сплетни"""
        if not npc.gossip_topics:
            return DialogueResult(
                outcome=DialogueOutcome.NEUTRAL,
                message=f"{npc.name}: \"Нечего рассказать.\""
            )
        
        topic = random.choice(npc.gossip_topics)
        gossip_texts = {
            'treasure': "Ходят слухи о сокровищах где-то в этом месте...",
            'monsters': "Говорят, здесь водятся опасные твари!",
            'strange_sounds': "Я слышал странные звуки прошлой ночью..."
        }
        
        return DialogueResult(
            outcome=DialogueOutcome.SUCCESS,
            information={'topic': topic, 'text': gossip_texts.get(topic, "")},
            message=f"{npc.name}: \"{gossip_texts.get(topic, '')}\"",
            reputation_change=0.05
        )
    
    def _handle_hostile_encounter(self, npc: NPCProfile) -> DialogueResult:
        """Обработка враждебного энкантера"""
        encounter_types = ['ambush', 'theft', 'chase']
        encounter_type = random.choice(encounter_types)
        
        messages = {
            'ambush': f"{npc.name} свистнул, и из засады выскочили бандиты!",
            'theft': f"{npc.name} украл у вас предмет и убежал!",
            'chase': f"{npc.name} начал преследование!"
        }
        
        return DialogueResult(
            outcome=DialogueOutcome.HOSTILE,
            message=messages.get(encounter_type, "Враждебная реакция!"),
            triggered_encounter=True,
            encounter_type=encounter_type,
            reputation_change=-0.2
        )
    
    def _get_true_exit_direction(self) -> str:
        """Получить истинное направление к выходу (заглушка)"""
        # В реальной игре должно вычисляться относительно позиции игрока
        directions = ['север', 'юг', 'восток', 'запад', 'северо-восток', 'юго-запад']
        return random.choice(directions)
    
    def _get_random_wrong_direction(self, true_direction: str) -> str:
        """Получить неправильное направление"""
        all_directions = ['север', 'юг', 'восток', 'запад', 'северо-восток', 'юго-запад']
        wrong_directions = [d for d in all_directions if d != true_direction]
        return random.choice(wrong_directions)
    
    def get_npc_info(self, npc_id: str) -> NPCProfile | None:
        """Получить информацию о NPC"""
        return self.npc_profiles.get(npc_id)
    
    def add_dialogue_to_history(self, result: DialogueResult):
        """Добавить результат диалога в историю"""
        self.dialogue_history.append(result)
        if len(self.dialogue_history) > 100:
            self.dialogue_history.pop(0)
    
    def get_dialogue_statistics(self) -> dict[str, Any]:
        """Получить статистику диалогов"""
        stats = {
            'total_dialogues': len(self.dialogue_history),
            'outcomes': {}
        }
        
        for result in self.dialogue_history:
            outcome_name = result.outcome.value
            stats['outcomes'][outcome_name] = stats['outcomes'].get(outcome_name, 0) + 1
        
        return stats
