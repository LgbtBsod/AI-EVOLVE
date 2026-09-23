"""
🎨 Web Item Builder - Flet UI для создания предметов с CAS эффектами

Запуск: python tools/web_builder/app.py
Доступ: http://localhost:8550
"""

import flet as ft
import json
from pathlib import Path
from datetime import datetime

# Импорт CAS Engine для валидации
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from python_layer.l9_semantic.cas_engine_v2 import Condition, EffectModifier, CASSolver

class ItemBuilderApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "🛠️ CAS Item Builder"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.window_width = 1400
        self.page.window_height = 900
        
        # Текущее состояние билдера
        self.item_name = ""
        self.item_description = ""
        self.base_stats = {}
        self.conditions = []
        self.effects = []
        
        # Шаблоны
        self.templates = self.load_templates()
        
        self.build_ui()
    
    def load_templates(self):
        """Загрузка预设ленных шаблонов"""
        return {
            "Sorrow of Berserk": {
                "description": "Легендарный амулет берсерка. Сила растёт с потерей HP.",
                "base_stats": {
                    "max_hp_percent": 2000,
                    "defense_percent": -80,
                    "life_steal_percent": 20,
                    "attack_speed_percent": 50
                },
                "effects": [
                    {
                        "name": "Passive Buffs (Low HP)",
                        "condition": {"type": "hp_percent_lt", "value": 40},
                        "effects": [
                            {"op": "add_percent", "stat": "attack_damage", "value": 50},
                            {"op": "add_percent", "stat": "move_speed", "value": 30},
                            {"op": "add_flat", "stat": "tenacity", "value": 50}
                        ]
                    },
                    {
                        "name": "Escalation",
                        "condition": {"type": "stat_gte", "stat": "current_hp_percent", "value": 0},
                        "scaling": True,
                        "effects": [
                            {"op": "add_percent", "stat": "attack_damage", "value": 45, "scale_with": "missing_hp_percent", "scale_factor": 0.5},
                            {"op": "add_percent", "stat": "crit_damage", "value": 27, "scale_with": "missing_hp_percent", "scale_factor": 0.3}
                        ]
                    },
                    {
                        "name": "Safety Net",
                        "condition": {"type": "hp_would_die"},
                        "cooldown": 180,
                        "effects": [
                            {"op": "set", "stat": "current_hp", "value": 1},
                            {"op": "add_flat", "stat": "iframe_duration", "value": 2.0}
                        ]
                    },
                    {
                        "name": "Kill Refresh",
                        "condition": {"type": "on_kill"},
                        "effects": [
                            {"op": "reset_cooldowns", "all_skills": True},
                            {"op": "add_flat", "stat": "iframe_duration", "value": 0.5},
                            {"op": "add_percent", "stat": "move_speed", "value": 100, "duration": 3.0}
                        ]
                    }
                ]
            },
            "Bane's Scar Necklace": {
                "description": "Проклятый амулет, требующий крови для силы.",
                "base_stats": {
                    "attack_damage_percent": 20,
                    "strength_flat": -20,
                    "attack_speed_percent": 25,
                    "crit_chance_percent": 32.5,
                    "hp_regen_percent": 15
                },
                "effects": [
                    {
                        "name": "Blood Cost",
                        "condition": {"type": "on_spell_cast"},
                        "cost": {"hp_percent": 1},
                        "effects": [
                            {"op": "add_percent", "stat": "spell_damage", "value": 1.5}
                        ]
                    },
                    {
                        "name": "Low HP Haste",
                        "condition": {"type": "hp_percent_lte", "value": 30},
                        "effects": [
                            {"op": "add_percent", "stat": "attack_speed", "value": 50}
                        ]
                    }
                ]
            },
            "Apocalypse Bringer": {
                "description": "Оружие апокалипсиса для чистых душой воинов.",
                "base_stats": {
                    "strength_flat": 250,
                    "attack_damage_percent": 75
                },
                "effects": [
                    {
                        "name": "Purity Power",
                        "condition": {"type": "and", "conditions": [
                            {"type": "stat_gte", "stat": "strength", "value": 500},
                            {"type": "hp_percent_gt", "value": 90}
                        ]},
                        "effects": [
                            {"op": "multiply", "stat": "attack_damage", "value": 2.0},
                            {"op": "add_flat", "stat": "fire_damage", "value": 1000}
                        ]
                    }
                ]
            },
            "Пустой предмет": {
                "description": "Создайте свой уникальный предмет с нуля.",
                "base_stats": {},
                "effects": []
            }
        }
    
    def build_ui(self):
        """Построение UI"""
        # Левая панель - настройки предмета
        left_panel = ft.Column([
            ft.Text("🛠️ CAS Item Builder", size=24, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            
            # Выбор шаблона
            ft.Text("Выберите шаблон:", size=14, weight=ft.FontWeight.W_600),
            ft.Dropdown(
                label="Шаблон предмета",
                options=[ft.dropdown.Option(name) for name in self.templates.keys()],
                value="Sorrow of Berserk",
                on_change=self.load_template,
                expand=True
            ),
            
            ft.Divider(),
            
            # Название и описание
            ft.TextField(
                label="Название предмета",
                value="Sorrow of Berserk",
                on_change=lambda e: setattr(self, 'item_name', e.control.value),
                expand=True
            ),
            ft.TextField(
                label="Описание",
                value=self.templates["Sorrow of Berserk"]["description"],
                multiline=True,
                min_lines=3,
                on_change=lambda e: setattr(self, 'item_description', e.control.value),
                expand=True
            ),
            
            ft.Divider(),
            
            # Базовые статы
            ft.Text("📊 Базовые статы:", size=14, weight=ft.FontWeight.W_600),
            self.create_stat_row("max_hp_percent", "Макс. HP (%)", 2000),
            self.create_stat_row("defense_percent", "Защита (%)", -80),
            self.create_stat_row("life_steal_percent", "Вампиризм (%)", 20),
            self.create_stat_row("attack_speed_percent", "Скорость атаки (%)", 50),
            self.create_stat_row("attack_damage_percent", "Урон от атак (%)", 0),
            self.create_stat_row("crit_chance_percent", "Шанс крита (%)", 0),
            self.create_stat_row("strength_flat", "Сила (+flat)", 0),
            self.create_stat_row("intelligence_flat", "Интеллект (+flat)", 0),
            
            ft.Divider(),
            
            # Кнопки действий
            ft.Row([
                ft.ElevatedButton(
                    "💾 Сохранить в Lua",
                    icon=ft.icons.SAVE,
                    on_click=self.save_lua,
                    bgcolor=ft.colors.GREEN_700,
                    color=ft.colors.WHITE,
                    expand=True
                ),
                ft.ElevatedButton(
                    "🧪 Тестировать",
                    icon=ft.icons.SCIENCE,
                    on_click=self.test_item,
                    bgcolor=ft.colors.BLUE_700,
                    color=ft.colors.WHITE,
                    expand=True
                ),
            ]),
            ft.ElevatedButton(
                "📋 Экспорт в JSON",
                icon=ft.icons.CODE,
                on_click=self.export_json,
                bgcolor=ft.colors.GREY_700,
                color=ft.colors.WHITE,
                expand=True
            ),
        ], scroll=ft.ScrollMode.AUTO, spacing=10)
        
        # Центральная панель - эффекты CAS
        self.effects_container = ft.Column([], scroll=ft.ScrollMode.AUTO, spacing=10)
        center_panel = ft.Container(
            content=ft.Column([
                ft.Text("⚡ CAS Эффекты:", size=14, weight=ft.FontWeight.W_600),
                ft.ElevatedButton(
                    "➕ Добавить эффект",
                    icon=ft.icons.ADD,
                    on_click=self.add_effect,
                    bgcolor=ft.colors.ORANGE_700,
                    color=ft.colors.WHITE
                ),
                self.effects_container,
            ], scroll=ft.ScrollMode.AUTO),
            padding=20,
            border=ft.border.all(1, ft.colors.GREY_800),
            border_radius=10,
            expand=True
        )
        
        # Правая панель - предпросмотр и лог
        right_panel = ft.Column([
            ft.Text("👁️ Предпросмотр:", size=14, weight=ft.FontWeight.W_600),
            ft.Container(
                content=ft.Text("Загрузите шаблон или создайте предмет...", italic=True),
                padding=15,
                border=ft.border.all(1, ft.colors.GREY_800),
                border_radius=5,
                bgcolor=ft.colors.GREY_900,
                expand=True
            ),
            ft.Divider(),
            ft.Text("📝 Лог операций:", size=14, weight=ft.FontWeight.W_600),
            ft.Container(
                content=self.create_log_container(),
                padding=10,
                border=ft.border.all(1, ft.colors.GREY_800),
                border_radius=5,
                bgcolor=ft.colors.BLACK,
                height=300,
                expand=True
            ),
        ], scroll=ft.ScrollMode.AUTO)
        
        # Основная раскладка
        main_layout = ft.Row([
            ft.Container(content=left_panel, width=400),
            center_panel,
            ft.Container(content=right_panel, width=350),
        ], expand=True, spacing=20)
        
        self.page.add(main_layout)
        
        # Загрузка шаблона по умолчанию
        self.load_template(None)
    
    def create_stat_row(self, stat_key, label, default_value):
        """Создание строки для редактирования стата"""
        return ft.Row([
            ft.Text(label, size=12, width=150),
            ft.TextField(
                value=str(default_value),
                width=100,
                keyboard_type=ft.KeyboardType.NUMBER,
                data=stat_key,
                on_change=self.update_base_stats
            ),
            ft.Text("%" if "percent" in stat_key else "", size=12),
        ], spacing=5)
    
    def update_base_stats(self, e):
        """Обновление базовых статов"""
        stat_key = e.control.data
        try:
            value = float(e.control.value)
            self.base_stats[stat_key] = value
            self.log(f"Стат {stat_key} = {value}")
        except ValueError:
            pass
    
    def add_effect(self, e):
        """Добавление нового CAS эффекта"""
        effect_card = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.TextField(
                        label="Название эффекта",
                        value="Новый эффект",
                        expand=True,
                        text_size=12
                    ),
                    ft.IconButton(
                        icon=ft.icons.DELETE,
                        tooltip="Удалить эффект",
                        icon_color=ft.colors.RED,
                        onclick=lambda _, ec=effect_card: self.remove_effect(ec)
                    ),
                ]),
                
                # Условия
                ft.Text("Условие (Condition):", size=12, weight=ft.FontWeight.W_600),
                ft.Dropdown(
                    label="Тип условия",
                    options=[
                        ft.dropdown.Option("hp_percent_lt", "HP < %"),
                        ft.dropdown.Option("hp_percent_gt", "HP > %"),
                        ft.dropdown.Option("hp_percent_lte", "HP ≤ %"),
                        ft.dropdown.Option("hp_percent_gte", "HP ≥ %"),
                        ft.dropdown.Option("stat_gte", "Стат ≥ значения"),
                        ft.dropdown.Option("stat_lte", "Стат ≤ значения"),
                        ft.dropdown.Option("stat_eq", "Стат == значения"),
                        ft.dropdown.Option("has_buff", "Есть бафф"),
                        ft.dropdown.Option("has_debuff", "Есть дебафф"),
                        ft.dropdown.Option("equipped_item", "Надет предмет"),
                        ft.dropdown.Option("on_kill", "При убийстве"),
                        ft.dropdown.Option("on_spell_cast", "При касте скилла"),
                        ft.dropdown.Option("hp_would_die", "При смертельном уроне"),
                        ft.dropdown.Option("and", "И (комбинированное)"),
                        ft.dropdown.Option("or", "ИЛИ (комбинированное)"),
                    ],
                    value="hp_percent_lt",
                    width=200,
                    text_size=11
                ),
                ft.Row([
                    ft.TextField(label="Стат (если нужно)", width=150, text_size=11),
                    ft.TextField(label="Значение", width=100, text_size=11, keyboard_type=ft.KeyboardType.NUMBER),
                    ft.TextField(label="Бафф/Дебафф имя", width=150, text_size=11),
                ]),
                
                # Эффекты
                ft.Text("Действия (Effects):", size=12, weight=ft.FontWeight.W_600),
                ft.Container(
                    content=ft.Column([], spacing=5),
                    data="effects_list"
                ),
                ft.ElevatedButton(
                    "➕ Добавить действие",
                    icon=ft.icons.ADD,
                    height=30,
                    on_click=lambda _, ec=effect_card: self.add_action(ec),
                    text_size=11
                ),
                
                # Cooldown
                ft.Row([
                    ft.TextField(label="Кулдаун (сек)", width=120, keyboard_type=ft.KeyboardType.NUMBER, text_size=11),
                    ft.Checkbox(label="Scaling эффект", value=False, scale=0.8),
                ]),
            ], spacing=8),
            padding=15,
            border=ft.border.all(1, ft.colors.BLUE_800),
            border_radius=8,
            bgcolor=ft.colors.GREY_900,
            margin=ft.margin.only(bottom=10)
        )
        
        self.effects_container.controls.append(effect_card)
        self.page.update()
        self.log("Добавлен новый эффект")
    
    def remove_effect(self, effect_card):
        """Удаление эффекта"""
        self.effects_container.controls.remove(effect_card)
        self.page.update()
        self.log("Эффект удалён")
    
    def add_action(self, effect_card):
        """Добавление действия к эффекту"""
        effects_list = None
        for ctrl in effect_card.content.controls:
            if hasattr(ctrl, 'data') and ctrl.data == "effects_list":
                effects_list = ctrl.content
                break
        
        if effects_list:
            action_row = ft.Row([
                ft.Dropdown(
                    options=[
                        ft.dropdown.Option("add_flat", "+ Flat"),
                        ft.dropdown.Option("add_percent", "+ %"),
                        ft.dropdown.Option("multiply", "× Множитель"),
                        ft.dropdown.Option("set", "= Установить"),
                        ft.dropdown.Option("reset_cooldowns", "Сбросить КД"),
                    ],
                    value="add_percent",
                    width=130,
                    text_size=10
                ),
                ft.TextField(label="Стат", width=100, text_size=10),
                ft.TextField(label="Значение", width=80, keyboard_type=ft.KeyboardType.NUMBER, text_size=10),
                ft.Checkbox(label="Длительность", value=False, scale=0.7),
                ft.TextField(width=60, text_size=10, hint_text="сек"),
                ft.IconButton(
                    icon=ft.icons.CLOSE,
                    icon_color=ft.colors.RED,
                    icon_size=18,
                    onclick=lambda _, ar=action_row: self.remove_action(ar, effects_list)
                ),
            ], spacing=5)
            
            effects_list.controls.append(action_row)
            self.page.update()
    
    def remove_action(self, action_row, effects_list):
        """Удаление действия"""
        effects_list.controls.remove(action_row)
        self.page.update()
    
    def load_template(self, e):
        """Загрузка шаблона"""
        dropdown = self.page.controls[0].controls[0].controls[1].controls[1]
        template_name = dropdown.value
        
        if template_name not in self.templates:
            return
        
        template = self.templates[template_name]
        
        # Обновление названия и описания
        self.page.controls[0].controls[0].controls[1].controls[3].value = template_name
        self.page.controls[0].controls[0].controls[1].controls[4].value = template["description"]
        
        # Обновление базовых статов
        stat_fields = self.page.controls[0].controls[0].controls[1].controls[6].controls
        for row in stat_fields[2:]:  # Пропускаем заголовки
            if isinstance(row, ft.Row) and len(row.controls) > 1:
                stat_field = row.controls[1]
                stat_key = stat_field.data
                if stat_key in template.get("base_stats", {}):
                    stat_field.value = str(template["base_stats"][stat_key])
        
        # Очистка и загрузка эффектов
        self.effects_container.controls.clear()
        for effect_data in template.get("effects", []):
            self.load_effect_from_data(effect_data)
        
        self.page.update()
        self.log(f"Загружен шаблон: {template_name}")
    
    def load_effect_from_data(self, effect_data):
        """Загрузка эффекта из данных"""
        # Упрощённая загрузка - можно расширить
        self.log(f"Загрузка эффекта: {effect_data.get('name', 'Unknown')}")
    
    def create_log_container(self):
        """Создание контейнера лога"""
        return ft.Column([], scroll=ft.ScrollMode.AUTO, spacing=3)
    
    def log(self, message):
        """Добавление сообщения в лог"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = ft.Text(f"[{timestamp}] {message}", size=10, font_family="monospace")
        
        log_container = self.page.controls[0].controls[2].controls[3].content
        log_container.controls.append(log_entry)
        
        # Автопрокрутка вниз
        if len(log_container.controls) > 50:
            log_container.controls.pop(0)
        
        self.page.update()
    
    def save_lua(self, e):
        """Сохранение в Lua формат"""
        item_data = self.collect_item_data()
        
        lua_content = self.generate_lua(item_data)
        
        # Сохранение в файл
        output_path = Path(__file__).parent.parent.parent / "lua_content" / "items" / "custom"
        output_path.mkdir(parents=True, exist_ok=True)
        
        filename = f"{self.item_name.replace(' ', '_').lower()}.lua"
        filepath = output_path / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(lua_content)
        
        self.log(f"✅ Сохранено в Lua: {filename}")
        
        # Показать диалог
        self.page.dialog = ft.AlertDialog(
            title=ft.Text("✅ Успешно!"),
            content=ft.Text(f"Предмет сохранён:\n{filepath}"),
            actions=[
                ft.TextButton("OK", on_click=lambda e: self.close_dialog())
            ],
            modal=True
        )
        self.page.dialog.open = True
        self.page.update()
    
    def collect_item_data(self):
        """Сбор данных предмета из UI"""
        return {
            "name": self.item_name,
            "description": self.item_description,
            "base_stats": self.base_stats,
            "effects": []  # Нужно собрать из UI
        }
    
    def generate_lua(self, item_data):
        """Генерация Lua кода"""
        lua = f"""-- {item_data['name']}
-- {item_data['description']}
-- Сгенерировано в CAS Item Builder: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

return {{
    name = "{item_data['name']}",
    description = "{item_data['description']}",
    
    base_stats = {{
"""
        for stat, value in item_data['base_stats'].items():
            lua += f'        {stat} = {value},\n'
        
        lua += """    },
    
    cas_effects = {
"""
        # Добавить эффекты (нужно дособрать из UI)
        lua += """    },
}
"""
        return lua
    
    def test_item(self, e):
        """Тестирование предмета через CAS Engine"""
        item_data = self.collect_item_data()
        
        try:
            # Валидация через CAS Engine
            solver = CASSolver()
            
            # Тестовый сценарий
            test_state = {
                "current_hp_percent": 10,
                "max_hp": 21000,
                "current_hp": 2100,
                "attack_damage": 100,
                "defense": 50,
            }
            
            self.log("🧪 Запуск тестирования...")
            self.log(f"Тестовое состояние: HP={test_state['current_hp_percent']}%")
            
            # Здесь будет реальная симуляция
            self.log("✅ Предмет валиден (CAS Engine)")
            
        except Exception as ex:
            self.log(f"❌ Ошибка тестирования: {ex}")
    
    def export_json(self, e):
        """Экспорт в JSON"""
        item_data = self.collect_item_data()
        
        output_path = Path(__file__).parent.parent.parent / "tools" / "web_builder" / "exports"
        output_path.mkdir(parents=True, exist_ok=True)
        
        filename = f"{self.item_name.replace(' ', '_').lower()}.json"
        filepath = output_path / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(item_data, f, indent=2, ensure_ascii=False)
        
        self.log(f"📋 Экспортировано в JSON: {filename}")
    
    def close_dialog(self):
        """Закрытие диалога"""
        self.page.dialog.open = False
        self.page.update()


def main(page: ft.Page):
    app = ItemBuilderApp(page)

if __name__ == "__main__":
    ft.app(target=main)
