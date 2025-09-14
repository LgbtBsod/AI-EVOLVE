#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
from typing import Dict, List, Optional
from panda3d.core import AudioSound, AudioManager

class AudioSystem:
    """Система звука и музыки"""
    
    def __init__(self, game):
        self.game = game
        self.sounds = {}
        self.music = {}
        self.audio_manager = None
        self.master_volume = 1.0
        self.sfx_volume = 1.0
        self.music_volume = 0.7
        self.current_music = None
        self.music_fade_time = 2.0
        
    def initialize(self):
        """Инициализация системы звука"""
        try:
            # Получаем аудио менеджер
            self.audio_manager = self.game.showbase.musicManager
            if not self.audio_manager:
                self.audio_manager = self.game.showbase.sfxManager
                
            print("✅ Аудио система инициализирована")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка инициализации аудио системы: {e}")
            return False
            
    def load_sound(self, name, file_path, volume=1.0):
        """Загрузка звукового эффекта"""
        try:
            if not os.path.exists(file_path):
                print(f"⚠️  Файл звука не найден: {file_path}")
                return False
                
            sound = self.audio_manager.getSound(file_path)
            if sound:
                sound.setVolume(volume * self.sfx_volume * self.master_volume)
                self.sounds[name] = sound
                print(f"✅ Звук загружен: {name}")
                return True
            else:
                print(f"❌ Не удалось загрузить звук: {name}")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка загрузки звука {name}: {e}")
            return False
            
    def load_music(self, name, file_path, volume=0.7):
        """Загрузка музыкального файла"""
        try:
            if not os.path.exists(file_path):
                print(f"⚠️  Файл музыки не найден: {file_path}")
                return False
                
            music = self.audio_manager.getSound(file_path)
            if music:
                music.setVolume(volume * self.music_volume * self.master_volume)
                music.setLoop(True)
                self.music[name] = music
                print(f"✅ Музыка загружена: {name}")
                return True
            else:
                print(f"❌ Не удалось загрузить музыку: {name}")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка загрузки музыки {name}: {e}")
            return False
            
    def play_sound(self, name, volume=None):
        """Воспроизведение звукового эффекта"""
        if name not in self.sounds:
            print(f"⚠️  Звук не найден: {name}")
            return False
            
        try:
            sound = self.sounds[name]
            
            # Устанавливаем громкость если указана
            if volume is not None:
                sound.setVolume(volume * self.sfx_volume * self.master_volume)
                
            sound.play()
            return True
            
        except Exception as e:
            print(f"❌ Ошибка воспроизведения звука {name}: {e}")
            return False
            
    def play_music(self, name, fade_in=True):
        """Воспроизведение музыки"""
        if name not in self.music:
            print(f"⚠️  Музыка не найдена: {name}")
            return False
            
        try:
            # Останавливаем текущую музыку
            if self.current_music:
                self.stop_music(fade_out=True)
                
            music = self.music[name]
            self.current_music = music
            
            if fade_in:
                # Плавное появление
                music.setVolume(0)
                music.play()
                self._fade_music_in(music)
            else:
                music.play()
                
            return True
            
        except Exception as e:
            print(f"❌ Ошибка воспроизведения музыки {name}: {e}")
            return False
            
    def stop_music(self, fade_out=True):
        """Остановка музыки"""
        if not self.current_music:
            return True
            
        try:
            if fade_out:
                self._fade_music_out(self.current_music)
            else:
                self.current_music.stop()
                
            self.current_music = None
            return True
            
        except Exception as e:
            print(f"❌ Ошибка остановки музыки: {e}")
            return False
            
    def _fade_music_in(self, music):
        """Плавное появление музыки"""
        def fade_in():
            target_volume = self.music_volume * self.master_volume
            steps = int(self.music_fade_time * 10)  # 10 FPS
            
            for i in range(steps + 1):
                volume = (i / steps) * target_volume
                music.setVolume(volume)
                time.sleep(0.1)
                
        import threading
        threading.Thread(target=fade_in, daemon=True).start()
        
    def _fade_music_out(self, music):
        """Плавное исчезновение музыки"""
        def fade_out():
            current_volume = music.getVolume()
            steps = int(self.music_fade_time * 10)  # 10 FPS
            
            for i in range(steps + 1):
                volume = current_volume * (1 - i / steps)
                music.setVolume(volume)
                time.sleep(0.1)
                
            music.stop()
            
        import threading
        threading.Thread(target=fade_out, daemon=True).start()
        
    def set_master_volume(self, volume):
        """Установка общей громкости"""
        self.master_volume = max(0, min(1, volume))
        self._update_all_volumes()
        
    def set_sfx_volume(self, volume):
        """Установка громкости звуковых эффектов"""
        self.sfx_volume = max(0, min(1, volume))
        self._update_sfx_volumes()
        
    def set_music_volume(self, volume):
        """Установка громкости музыки"""
        self.music_volume = max(0, min(1, volume))
        self._update_music_volumes()
        
    def _update_all_volumes(self):
        """Обновление всех громкостей"""
        self._update_sfx_volumes()
        self._update_music_volumes()
        
    def _update_sfx_volumes(self):
        """Обновление громкости звуковых эффектов"""
        for sound in self.sounds.values():
            sound.setVolume(sound.getVolume() * self.sfx_volume * self.master_volume)
            
    def _update_music_volumes(self):
        """Обновление громкости музыки"""
        for music in self.music.values():
            music.setVolume(music.getVolume() * self.music_volume * self.master_volume)
            
    def create_3d_sound(self, name, file_path, x, y, z, max_distance=10.0):
        """Создание 3D звука"""
        try:
            if not os.path.exists(file_path):
                print(f"⚠️  Файл 3D звука не найден: {file_path}")
                return False
                
            sound = self.audio_manager.getSound(file_path)
            if sound:
                # Настраиваем 3D позиционирование
                sound.set3dAttributes(x, y, z, 0, 0, 0)
                sound.set3dMinDistance(1.0)
                sound.set3dMaxDistance(max_distance)
                
                self.sounds[name] = sound
                print(f"✅ 3D звук загружен: {name}")
                return True
            else:
                print(f"❌ Не удалось загрузить 3D звук: {name}")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка загрузки 3D звука {name}: {e}")
            return False
            
    def update_3d_sound(self, name, x, y, z):
        """Обновление позиции 3D звука"""
        if name in self.sounds:
            try:
                self.sounds[name].set3dAttributes(x, y, z, 0, 0, 0)
                return True
            except Exception as e:
                print(f"❌ Ошибка обновления 3D звука {name}: {e}")
                return False
        return False
        
    def create_ambient_sound(self, name, file_path, volume=0.3):
        """Создание фонового звука"""
        return self.load_sound(name, file_path, volume)
        
    def play_ambient_sound(self, name, loop=True):
        """Воспроизведение фонового звука"""
        if name in self.sounds:
            sound = self.sounds[name]
            if loop:
                sound.setLoop(True)
            sound.play()
            return True
        return False
        
    def stop_ambient_sound(self, name):
        """Остановка фонового звука"""
        if name in self.sounds:
            self.sounds[name].stop()
            return True
        return False
        
    def create_sound_effect(self, effect_type, **kwargs):
        """Создание звукового эффекта программно"""
        if effect_type == "explosion":
            return self._create_explosion_sound(**kwargs)
        elif effect_type == "footstep":
            return self._create_footstep_sound(**kwargs)
        elif effect_type == "magic":
            return self._create_magic_sound(**kwargs)
        else:
            print(f"⚠️  Неизвестный тип звукового эффекта: {effect_type}")
            return False
            
    def _create_explosion_sound(self, intensity=1.0):
        """Создание звука взрыва"""
        # В реальной игре здесь была бы генерация звука
        print(f"💥 Звук взрыва (интенсивность: {intensity})")
        return True
        
    def _create_footstep_sound(self, surface="stone"):
        """Создание звука шагов"""
        # В реальной игре здесь была бы генерация звука
        print(f"👣 Звук шагов по {surface}")
        return True
        
    def _create_magic_sound(self, spell_type="heal"):
        """Создание магического звука"""
        # В реальной игре здесь была бы генерация звука
        print(f"✨ Магический звук: {spell_type}")
        return True
        
    def get_audio_info(self):
        """Получение информации об аудио системе"""
        return {
            'master_volume': self.master_volume,
            'sfx_volume': self.sfx_volume,
            'music_volume': self.music_volume,
            'loaded_sounds': len(self.sounds),
            'loaded_music': len(self.music),
            'current_music': self.current_music is not None
        }
        
    def destroy(self):
        """Уничтожение аудио системы"""
        # Останавливаем все звуки
        for sound in self.sounds.values():
            try:
                sound.stop()
            except:
                pass
                
        # Останавливаем музыку
        if self.current_music:
            try:
                self.current_music.stop()
            except:
                pass
                
        # Очищаем данные
        self.sounds.clear()
        self.music.clear()
        self.current_music = None
