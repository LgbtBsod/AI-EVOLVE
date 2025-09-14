#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from direct.gui.DirectGui import DirectFrame, OnscreenText, DirectButton
from panda3d.core import LVector4, TextNode

class EnhancedHUD:
    """Улучшенный HUD с отображением всех характеристик"""

    def __init__(self, game):
        self.game = game
        self.elements = []
        self.is_skills_open = False
        self.is_attributes_open = False
        
    def create_hud(self):
        """Создание элементов HUD"""
        # Основной фрейм HUD
        self.main_frame = DirectFrame(
            frameColor=(0, 0, 0, 0.3),
            frameSize=(-1, 1, -1, 1),
            parent=self.game.aspect2d
        )
        self.elements.append(self.main_frame)
        
        # Создаем основные панели
        self._create_health_panel()
        self._create_mana_panel()
        self._create_stamina_panel()
        self._create_experience_panel()
        self._create_attributes_panel()
        self._create_skills_panel()
        self._create_effects_panel()
        self._create_minimap_panel()
        self._create_action_bar()
        
    def _create_health_panel(self):
        """Создание панели здоровья"""
        # Фон панели
        health_bg = DirectFrame(
            frameColor=(0.2, 0.2, 0.2, 0.8),
            frameSize=(-0.25, 0.25, -0.05, 0.05),
            pos=(0, 0, -0.9),
            parent=self.main_frame
        )
        self.elements.append(health_bg)
        
        # Полоса здоровья
        self.health_bar = DirectFrame(
            frameColor=(0.8, 0.2, 0.2, 1),
            frameSize=(-0.24, 0.24, -0.04, 0.04),
            pos=(0, 0, -0.9),
            parent=self.main_frame
        )
        self.elements.append(self.health_bar)
        
        # Текст здоровья
        self.health_text = OnscreenText(
            text="HP: 100/100",
            pos=(0, -0.9),
            scale=0.05,
            fg=(1, 1, 1, 1),
            parent=self.main_frame
        )
        self.elements.append(self.health_text)
        
    def _create_mana_panel(self):
        """Создание панели маны"""
        # Фон панели
        mana_bg = DirectFrame(
            frameColor=(0.2, 0.2, 0.2, 0.8),
            frameSize=(-0.25, 0.25, -0.05, 0.05),
            pos=(0, 0, -0.85),
            parent=self.main_frame
        )
        self.elements.append(mana_bg)
        
        # Полоса маны
        self.mana_bar = DirectFrame(
            frameColor=(0.2, 0.2, 0.8, 1),
            frameSize=(-0.24, 0.24, -0.04, 0.04),
            pos=(0, 0, -0.85),
            parent=self.main_frame
        )
        self.elements.append(self.mana_bar)
        
        # Текст маны
        self.mana_text = OnscreenText(
            text="MP: 100/100",
            pos=(0, -0.85),
            scale=0.05,
            fg=(1, 1, 1, 1),
            parent=self.main_frame
        )
        self.elements.append(self.mana_text)
        
    def _create_stamina_panel(self):
        """Создание панели выносливости"""
        # Фон панели
        stamina_bg = DirectFrame(
            frameColor=(0.2, 0.2, 0.2, 0.8),
            frameSize=(-0.25, 0.25, -0.05, 0.05),
            pos=(0, 0, -0.8),
            parent=self.main_frame
        )
        self.elements.append(stamina_bg)
        
        # Полоса выносливости
        self.stamina_bar = DirectFrame(
            frameColor=(0.2, 0.8, 0.2, 1),
            frameSize=(-0.24, 0.24, -0.04, 0.04),
            pos=(0, 0, -0.8),
            parent=self.main_frame
        )
        self.elements.append(self.stamina_bar)
        
        # Текст выносливости
        self.stamina_text = OnscreenText(
            text="SP: 100/100",
            pos=(0, -0.8),
            scale=0.05,
            fg=(1, 1, 1, 1),
            parent=self.main_frame
        )
        self.elements.append(self.stamina_text)
        
    def _create_experience_panel(self):
        """Создание панели опыта"""
        # Фон панели
        exp_bg = DirectFrame(
            frameColor=(0.2, 0.2, 0.2, 0.8),
            frameSize=(-0.25, 0.25, -0.05, 0.05),
            pos=(0, 0, -0.75),
            parent=self.main_frame
        )
        self.elements.append(exp_bg)
        
        # Полоса опыта
        self.exp_bar = DirectFrame(
            frameColor=(0.8, 0.8, 0.2, 1),
            frameSize=(-0.24, 0.24, -0.04, 0.04),
            pos=(0, 0, -0.75),
            parent=self.main_frame
        )
        self.elements.append(self.exp_bar)
        
        # Текст опыта
        self.exp_text = OnscreenText(
            text="EXP: 0/100",
            pos=(0, -0.75),
            scale=0.05,
            fg=(1, 1, 1, 1),
            parent=self.main_frame
        )
        self.elements.append(self.exp_text)
        
    def _create_attributes_panel(self):
        """Создание панели атрибутов"""
        # Кнопка открытия панели атрибутов
        self.attributes_button = DirectButton(
            text="Attributes",
            scale=0.05,
            pos=(-0.8, 0, 0.8),
            command=self.toggle_attributes,
            parent=self.main_frame,
            frameColor=(0.3, 0.3, 0.3, 0.8),
            text_fg=(1, 1, 1, 1),
            frameSize=(-1, 1, -0.3, 0.3)
        )
        self.elements.append(self.attributes_button)
        
        # Панель атрибутов (скрыта по умолчанию)
        self.attributes_panel = DirectFrame(
            frameColor=(0.1, 0.1, 0.1, 0.9),
            frameSize=(-0.4, 0.4, -0.6, 0.6),
            pos=(-0.6, 0, 0),
            parent=self.main_frame
        )
        self.attributes_panel.hide()
        self.elements.append(self.attributes_panel)
        
        # Заголовок панели атрибутов
        self.attributes_title = OnscreenText(
            text="Attributes",
            pos=(-0.6, 0.5),
            scale=0.08,
            fg=(1, 1, 1, 1),
            parent=self.attributes_panel
        )
        self.elements.append(self.attributes_title)
        
        # Список атрибутов
        self.attributes_text = OnscreenText(
            text="",
            pos=(-0.6, 0.3),
            scale=0.05,
            fg=(1, 1, 1, 1),
            align=TextNode.ALeft,
            parent=self.attributes_panel
        )
        self.elements.append(self.attributes_text)
        
    def _create_skills_panel(self):
        """Создание панели навыков"""
        # Кнопка открытия панели навыков
        self.skills_button = DirectButton(
            text="Skills",
            scale=0.05,
            pos=(-0.6, 0, 0.8),
            command=self.toggle_skills,
            parent=self.main_frame,
            frameColor=(0.3, 0.3, 0.3, 0.8),
            text_fg=(1, 1, 1, 1),
            frameSize=(-1, 1, -0.3, 0.3)
        )
        self.elements.append(self.skills_button)
        
        # Панель навыков (скрыта по умолчанию)
        self.skills_panel = DirectFrame(
            frameColor=(0.1, 0.1, 0.1, 0.9),
            frameSize=(-0.4, 0.4, -0.6, 0.6),
            pos=(0.6, 0, 0),
            parent=self.main_frame
        )
        self.skills_panel.hide()
        self.elements.append(self.skills_panel)
        
        # Заголовок панели навыков
        self.skills_title = OnscreenText(
            text="Skills",
            pos=(0.6, 0.5),
            scale=0.08,
            fg=(1, 1, 1, 1),
            parent=self.skills_panel
        )
        self.elements.append(self.skills_title)
        
        # Список навыков
        self.skills_text = OnscreenText(
            text="",
            pos=(0.6, 0.3),
            scale=0.05,
            fg=(1, 1, 1, 1),
            align=TextNode.ALeft,
            parent=self.skills_panel
        )
        self.elements.append(self.skills_text)
        
    def _create_effects_panel(self):
        """Создание панели эффектов"""
        # Панель эффектов
        self.effects_panel = DirectFrame(
            frameColor=(0.2, 0.2, 0.2, 0.6),
            frameSize=(-0.3, 0.3, -0.1, 0.1),
            pos=(0.7, 0, -0.7),
            parent=self.main_frame
        )
        self.elements.append(self.effects_panel)
        
        # Текст эффектов
        self.effects_text = OnscreenText(
            text="Effects: None",
            pos=(0.7, -0.7),
            scale=0.04,
            fg=(1, 1, 1, 1),
            parent=self.main_frame
        )
        self.elements.append(self.effects_text)
        
    def _create_minimap_panel(self):
        """Создание панели миникарты"""
        # Панель миникарты
        self.minimap_panel = DirectFrame(
            frameColor=(0.1, 0.1, 0.1, 0.8),
            frameSize=(-0.15, 0.15, -0.15, 0.15),
            pos=(0.8, 0, 0.8),
            parent=self.main_frame
        )
        self.elements.append(self.minimap_panel)
        
        # Текст миникарты
        self.minimap_text = OnscreenText(
            text="MAP",
            pos=(0.8, 0.8),
            scale=0.05,
            fg=(1, 1, 1, 1),
            parent=self.main_frame
        )
        self.elements.append(self.minimap_text)
        
    def _create_action_bar(self):
        """Создание панели действий"""
        # Панель действий
        self.action_bar = DirectFrame(
            frameColor=(0.2, 0.2, 0.2, 0.8),
            frameSize=(-0.4, 0.4, -0.1, 0.1),
            pos=(0, 0, -0.65),
            parent=self.main_frame
        )
        self.elements.append(self.action_bar)
        
        # Кнопки навыков
        self.skill_buttons = []
        for i in range(5):
            button = DirectButton(
                text=f"Skill {i+1}",
                scale=0.04,
                pos=(-0.3 + i * 0.15, 0, -0.65),
                command=lambda i=i: self.use_skill(i),
                parent=self.main_frame,
                frameColor=(0.3, 0.3, 0.3, 0.8),
                text_fg=(1, 1, 1, 1),
                frameSize=(-0.6, 0.6, -0.4, 0.4)
            )
            self.skill_buttons.append(button)
            self.elements.append(button)
            
    def update_hud(self, character):
        """Обновление HUD"""
        if not character:
            return
            
        # Обновляем полосы здоровья, маны и выносливости
        health_percent = character.health / character.max_health if character.max_health > 0 else 0
        self.health_bar['frameSize'] = (-0.24, -0.24 + 0.48 * health_percent, -0.04, 0.04)
        self.health_text.setText(f"HP: {int(character.health)}/{int(character.max_health)}")
        
        mana_percent = character.mana / character.max_mana if character.max_mana > 0 else 0
        self.mana_bar['frameSize'] = (-0.24, -0.24 + 0.48 * mana_percent, -0.04, 0.04)
        self.mana_text.setText(f"MP: {int(character.mana)}/{int(character.max_mana)}")
        
        stamina_percent = character.stamina / character.max_stamina if character.max_stamina > 0 else 0
        self.stamina_bar['frameSize'] = (-0.24, -0.24 + 0.48 * stamina_percent, -0.04, 0.04)
        self.stamina_text.setText(f"SP: {int(character.stamina)}/{int(character.max_stamina)}")
        
        # Обновляем полосу опыта
        exp_percent = character.experience / character.experience_to_next_level if character.experience_to_next_level > 0 else 0
        self.exp_bar['frameSize'] = (-0.24, -0.24 + 0.48 * exp_percent, -0.04, 0.04)
        self.exp_text.setText(f"EXP: {character.experience}/{character.experience_to_next_level}")
        
        # Обновляем панель атрибутов
        if self.is_attributes_open:
            self._update_attributes_panel(character)
            
        # Обновляем панель навыков
        if self.is_skills_open:
            self._update_skills_panel(character)
            
        # Обновляем панель эффектов
        self._update_effects_panel(character)
        
    def _update_attributes_panel(self, character):
        """Обновление панели атрибутов"""
        attributes_text = f"Level: {character.level}\n\n"
        attributes_text += "Base Attributes:\n"
        attributes_text += f"Strength: {character.base_attributes.strength}\n"
        attributes_text += f"Agility: {character.base_attributes.agility}\n"
        attributes_text += f"Intelligence: {character.base_attributes.intelligence}\n"
        attributes_text += f"Vitality: {character.base_attributes.vitality}\n"
        attributes_text += f"Wisdom: {character.base_attributes.wisdom}\n"
        attributes_text += f"Charisma: {character.base_attributes.charisma}\n"
        attributes_text += f"Luck: {character.base_attributes.luck}\n"
        attributes_text += f"Endurance: {character.base_attributes.endurance}\n\n"
        attributes_text += "Derived Stats:\n"
        attributes_text += f"Physical Damage: {getattr(character, 'physical_damage', 0):.1f}\n"
        attributes_text += f"Magical Damage: {getattr(character, 'magical_damage', 0):.1f}\n"
        attributes_text += f"Attack Range: {getattr(character, 'attack_range', 0):.1f}\n"
        attributes_text += f"Defense: {character.defense:.1f}\n"
        attributes_text += f"Movement Speed: {getattr(character, 'speed', 0):.1f}\n"
        attributes_text += f"Critical Chance: {character.critical_chance:.1f}%\n"
        attributes_text += f"Dodge Chance: {character.dodge_chance:.1f}%"
        
        self.attributes_text.setText(attributes_text)
        
    def _update_skills_panel(self, character):
        """Обновление панели навыков"""
        skills_text = "Learned Skills:\n\n"
        
        # Получаем изученные навыки
        learned_skills = []
        if hasattr(character, 'skill_system') and hasattr(character, 'entity_id'):
            for skill_id, skill in character.skill_system.get_entity_skills(character.entity_id).items():
                if skill.is_learned:
                    learned_skills.append((skill_id, skill))
        
        if learned_skills:
            for skill_id, skill in learned_skills:
                skills_text += f"{skill.name} (Lv.{skill.current_level})\n"
                skills_text += f"  {skill.description}\n\n"
        else:
            skills_text += "No skills learned yet.\n\n"
            
        # Получаем доступные навыки
        if hasattr(character, 'get_available_skills'):
            available_skills = character.get_available_skills()
            if available_skills:
                skills_text += "Available Skills:\n"
                for skill in available_skills:
                    skills_text += f"{skill.name}\n"
                    skills_text += f"  {skill.description}\n\n"
        
        self.skills_text.setText(skills_text)
        
    def _update_effects_panel(self, character):
        """Обновление панели эффектов"""
        if hasattr(character, 'effect_system') and hasattr(character, 'entity_id'):
            effects = character.effect_system.get_entity_effects(character.entity_id)
            active_effects = [effect for effect in effects if not effect.is_expired()]
            
            if active_effects:
                effects_text = "Effects: "
                effect_names = [effect.name for effect in active_effects]
                effects_text += ", ".join(effect_names)
            else:
                effects_text = "Effects: None"
        else:
            effects_text = "Effects: None"
            
        self.effects_text.setText(effects_text)
        
    def toggle_attributes(self):
        """Переключение видимости панели атрибутов"""
        if self.is_attributes_open:
            self.attributes_panel.hide()
            self.is_attributes_open = False
        else:
            self.attributes_panel.show()
            self.is_attributes_open = True
            
    def toggle_skills(self):
        """Переключение видимости панели навыков"""
        if self.is_skills_open:
            self.skills_panel.hide()
            self.is_skills_open = False
        else:
            self.skills_panel.show()
            self.is_skills_open = True
            
    def use_skill(self, skill_index):
        """Использование навыка"""
        # В реальной игре здесь была бы логика использования навыка
        print(f"Using skill {skill_index + 1}")
        
    def destroy(self):
        """Уничтожение HUD"""
        for element in self.elements:
            if hasattr(element, 'destroy'):
                element.destroy()
            elif hasattr(element, 'removeNode'):
                element.removeNode()
        self.elements.clear()
