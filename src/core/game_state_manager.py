#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Dict, Optional, Any, Type, Callable
import logging
from src.core.state_manager import StateManager, StateType

logger = logging.getLogger(__name__)

class EnhancedStateManager:
    """Улучшенный менеджер состояний игры - обертка над StateManager"""
    
    def __init__(self, game):
        self.game = game
        self.current_state = None
        self.previous_state = None
        self.states = {}
        self.state_stack = []
        
        # Используем централизованный StateManager
        self.state_manager = StateManager()
        self.state_manager.initialize()
        
    def register_state(self, state_name: str, state_class):
        """Регистрация состояния"""
        self.states[state_name] = state_class
        logger.info(f"Registered state: {state_name}")
        
    def change_state(self, state_name: str, *args, **kwargs):
        """Смена состояния"""
        if state_name not in self.states:
            logger.error(f"State {state_name} not found!")
            return False
            
        # Выходим из текущего состояния
        if self.current_state:
            self.current_state.exit()
            self.previous_state = self.current_state
            
        # Создаем новое состояние
        state_class = self.states[state_name]
        self.current_state = state_class(self.game, *args, **kwargs)
        
        # Входим в новое состояние
        try:
            self.current_state.enter()
            
            # Обновляем состояние в централизованном менеджере
            self.state_manager.set_state(f"current_game_state", state_name, source="enhanced_state_manager")
            self.state_manager.set_state(f"previous_game_state", self.previous_state.__class__.__name__ if self.previous_state else None, source="enhanced_state_manager")
            
            logger.info(f"Changed state to: {state_name}")
            return True
        except Exception as e:
            logger.error(f"Error entering state {state_name}: {e}")
            return False
            
    def push_state(self, state_name: str, *args, **kwargs):
        """Добавление состояния в стек"""
        if state_name not in self.states:
            logger.error(f"State {state_name} not found!")
            return False
            
        # Сохраняем текущее состояние в стек
        if self.current_state:
            self.state_stack.append(self.current_state)
            
        # Создаем новое состояние
        state_class = self.states[state_name]
        self.current_state = state_class(self.game, *args, **kwargs)
        
        # Входим в новое состояние
        try:
            self.current_state.enter()
            logger.info(f"Pushed state: {state_name}")
            return True
        except Exception as e:
            logger.error(f"Error entering state {state_name}: {e}")
            return False
            
    def pop_state(self):
        """Удаление состояния из стека"""
        if not self.state_stack:
            logger.warning("No states in stack to pop!")
            return False
            
        # Выходим из текущего состояния
        if self.current_state:
            self.current_state.exit()
            
        # Восстанавливаем предыдущее состояние
        self.current_state = self.state_stack.pop()
        
        logger.info("Popped state from stack")
        return True
        
    def update(self, dt: float):
        """Обновление текущего состояния"""
        if self.current_state and hasattr(self.current_state, 'update'):
            try:
                self.current_state.update(dt)
            except Exception as e:
                logger.error(f"Error updating state: {e}")
                
    def handle_input(self, keys):
        """Обработка ввода для текущего состояния"""
        if self.current_state and hasattr(self.current_state, 'handle_input'):
            try:
                self.current_state.handle_input(keys)
            except Exception as e:
                logger.error(f"Error handling input: {e}")
                
    def get_current_state_name(self) -> Optional[str]:
        """Получение имени текущего состояния"""
        for name, state_class in self.states.items():
            if isinstance(self.current_state, state_class):
                return name
        return None
        
    def is_state_active(self, state_name: str) -> bool:
        """Проверка, активно ли состояние"""
        return self.get_current_state_name() == state_name
