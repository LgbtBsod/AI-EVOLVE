"""
Flet Web UI: Training Room Controller + Item Builder
Launch training simulations, build items visually, export to Lua/Rust
"""

import flet as ft
import json
import uuid
from datetime import datetime
from pathlib import Path

# Import Rust Training Room Engine (when compiled)
# from rust_core.training_room import TrainingRoomEngine

class TrainingRoomApp(ft.Column):
    def __init__(self):
        super().__init__()
        self.current_item = {}
        self.effects_list = []
        
        # Build UI on initialization
        self.controls = self._build_ui()
    
    def _build_ui(self):
        # Entity Setup
        entity_type_dropdown = ft.Dropdown(
            label="Entity Type",
            options=[
                ft.dropdown.Option("mannequin", "Mannequin (Passive)"),
                ft.dropdown.Option("immortal_bot", "Immortal Bot (Attacks)"),
                ft.dropdown.Option("player", "Player Character"),
            ],
            value="mannequin",
            width=300,
        )
        self.entity_type_dropdown = entity_type_dropdown
        
        hp_slider = ft.Slider(
            label="HP %",
            min=1,
            max=100,
            divisions=99,
            value=100,
            on_change=self.update_stats_preview,
        )
        self.hp_slider = hp_slider
        
        equipment_picker = ft.FilePicker(
            on_result=self.load_equipment,
        )
        self.equipment_picker = equipment_picker
        
        # Effect Builder fields
        effect_name_field = ft.TextField(
            label="e.g., Lost My Self",
            width=400,
        )
        self.effect_name = effect_name_field
        
        effect_type_dropdown = ft.Dropdown(
            options=[
                ft.dropdown.Option("triggered_buff"),
                ft.dropdown.Option("passive_buff"),
                ft.dropdown.Option("reactive_shield"),
                ft.dropdown.Option("passive_attack_modifier"),
                ft.dropdown.Option("debuff"),
            ],
            value="triggered_buff",
            width=300,
        )
        self.effect_type = effect_type_dropdown
        
        trigger_condition_dropdown = ft.Dropdown(
            options=[
                ft.dropdown.Option("hp_percent_lt", "HP < X%"),
                ft.dropdown.Option("hp_percent_gt", "HP > X%"),
                ft.dropdown.Option("has_debuff", "Has Debuff"),
                ft.dropdown.Option("cost_exceeds_hp", "Cost > Current HP"),
            ],
            value="hp_percent_lt",
            width=300,
        )
        self.trigger_condition_type = trigger_condition_dropdown
        
        trigger_threshold_field = ft.TextField(
            label="Threshold (%)",
            value="40.0",
            width=150,
        )
        self.trigger_threshold = trigger_threshold_field
        
        stat_modifiers_col = ft.Column([], scroll=ft.ScrollMode.AUTO)
        self.stat_modifiers_container = stat_modifiers_col
        
        cost_hp_field = ft.TextField(
            label="HP Cost (%)",
            value="0.5",
            width=150,
        )
        self.cost_hp_percent = cost_hp_field
        
        cost_can_kill_cb = ft.Checkbox(
            label="Can Kill (HP → 0)",
            value=False,
        )
        self.cost_can_kill = cost_can_kill_cb
        
        grants_iframe_cb = ft.Checkbox(
            label="Grants Iframe (Invulnerability)",
            value=False,
        )
        self.grants_iframe = grants_iframe_cb
        
        iframe_duration_field = ft.TextField(
            label="Iframe Duration (sec)",
            value="5.0",
            disabled=True,
            width=150,
        )
        self.iframe_duration = iframe_duration_field
        
        cooldown_field = ft.TextField(
            label="Cooldown (sec)",
            value="30.0",
            width=150,
        )
        self.cooldown = cooldown_field
        
        json_preview_field = ft.TextField(
            multiline=True,
            min_lines=15,
            max_lines=25,
            width=600,
            read_only=True,
        )
        self.json_preview = json_preview_field
        
        results_text = ft.Text("No simulation run yet.", italic=True)
        self.results_output = results_text
        
        return [ft.Column([
            ft.Text("🎮 Training Room Control Panel", size=24, weight="bold"),
            ft.Divider(),
            
            # Entity Setup
            ft.Text("📊 Entity Configuration", size=18, weight="bold"),
            entity_type_dropdown,
            hp_slider,
            equipment_picker,
            ft.FilledButton(
                "📦 Load Equipment Config",
                icon="folder",
                on_click=lambda _: equipment_picker.pick_files(),
            ),
            
            ft.Divider(),
            
            # Effect Builder
            ft.Text("⚡ Effect Contract Builder", size=18, weight="bold"),
            ft.Text("Effect Name:", size=14),
            effect_name_field,
            ft.Text("Effect Type:", size=14),
            effect_type_dropdown,
            ft.Text("Trigger Conditions:", size=14),
            trigger_condition_dropdown,
            trigger_threshold_field,
            ft.FilledButton(
                "➕ Add Trigger Condition",
                on_click=self.add_trigger_condition,
            ),
            ft.Text("Stat Modifiers:", size=14),
            stat_modifiers_col,
            ft.FilledButton(
                "➕ Add Stat Modifier",
                on_click=self.add_stat_modifier,
            ),
            
            ft.Divider(),
            
            # Cost Configuration
            ft.Text("💰 Cost Configuration", size=18, weight="bold"),
            cost_hp_field,
            cost_can_kill_cb,
            
            ft.Divider(),
            
            # Special Flags
            ft.Text("🛡️ Special Properties", size=18, weight="bold"),
            grants_iframe_cb,
            iframe_duration_field,
            cooldown_field,
            
            ft.Divider(),
            
            # Preview & Export
            ft.Text("📄 JSON Preview", size=18, weight="bold"),
            json_preview_field,
            ft.Row([
                ft.FilledButton(
                    "🔄 Generate JSON",
                    icon="refresh",
                    on_click=self.generate_json,
                ),
                ft.FilledButton(
                    "💾 Export to Lua",
                    icon="save",
                    on_click=self.export_lua,
                ),
                ft.FilledButton(
                    "▶️ Run Simulation",
                    icon="play_arrow",
                    on_click=self.run_simulation,
                    bgcolor="green",
                    color="white",
                ),
            ]),
            
            ft.Divider(),
            
            # Simulation Results
            ft.Text("📈 Simulation Results", size=18, weight="bold"),
            results_text,
        ], scroll=ft.ScrollMode.AUTO, width=800)]
    
    def update_stats_preview(self, e):
        """Update preview when sliders change"""
        pass
    
    def load_equipment(self, e):
        """Load equipment config from file"""
        if e.files:
            file_path = e.files[0].path
            with open(file_path, 'r') as f:
                content = f.read()
                if file_path.endswith('.json'):
                    self.current_item = json.loads(content)
                elif file_path.endswith('.lua'):
                    # Parse Lua (simplified - would need luaparser in production)
                    self.current_item = {"name": "Loaded from Lua", "effects": []}
            
            self.page.snack_bar = ft.SnackBar(
                ft.Text(f"✅ Loaded: {file_path}"),
                bgcolor=ft.colors.GREEN,
            )
            self.page.snack_bar.open = True
            self.page.update()
    
    def add_trigger_condition(self, e):
        """Add trigger condition to effects list"""
        condition = {
            "condition_type": self.trigger_condition_type.value,
            "threshold": float(self.trigger_threshold.value),
        }
        self.effects_list.append({"type": "trigger", "data": condition})
        
        self.page.snack_bar = ft.SnackBar(
            ft.Text(f"✅ Added trigger: {condition['condition_type']} < {condition['threshold']}%"),
            bgcolor="blue",
        )
        self.page.snack_bar.open = True
        self.page.update()
    
    def add_stat_modifier(self, e):
        """Add stat modifier row"""
        stat_name = ft.TextField(label="Stat Name", width=200)
        stat_value = ft.TextField(label="Value (%)", width=100, value="0")
        stat_type = ft.Dropdown(
            options=[
                ft.dropdown.Option("percent"),
                ft.dropdown.Option("flat"),
            ],
            value="percent",
            width=120,
        )
        
        row = ft.Row([stat_name, stat_value, stat_type])
        self.stat_modifiers_container.controls.append(row)
        self.page.update()
    
    def generate_json(self, e):
        """Generate JSON preview of effect contract"""
        effect_contract = {
            "id": str(uuid.uuid4()),
            "name": self.effect_name.value,
            "effect_type": self.effect_type.value,
            "trigger_conditions": [],
            "stats_modifiers": {},
            "cost": None,
            "grants_iframe": self.grants_iframe.value,
            "iframe_duration": float(self.iframe_duration.value) if self.grants_iframe.value else None,
            "cooldown": float(self.cooldown.value) if self.cooldown.value else None,
        }
        
        # Add triggers from list
        for item in self.effects_list:
            if item["type"] == "trigger":
                effect_contract["trigger_conditions"].append(item["data"])
        
        # Add stat modifiers from UI rows
        for row in self.stat_modifiers_container.controls:
            stat_name = row.controls[0].value
            stat_value = float(row.controls[1].value)
            stat_type = row.controls[2].value
            key = f"{stat_name}_{stat_type}"
            effect_contract["stats_modifiers"][key] = stat_value
        
        # Add cost if specified
        if self.cost_hp_percent.value:
            effect_contract["cost"] = {
                "hp_percent": float(self.cost_hp_percent.value),
                "can_kill": self.cost_can_kill.value,
            }
        
        self.current_item = effect_contract
        self.json_preview.value = json.dumps(effect_contract, indent=2)
        self.page.update()
        
        self.page.snack_bar = ft.SnackBar(
            ft.Text("✅ JSON Generated"),
            bgcolor=ft.colors.GREEN,
        )
        self.page.snack_bar.open = True
        self.page.update()
    
    def export_lua(self, e):
        """Export current item to Lua file"""
        if not self.current_item:
            self.page.snack_bar = ft.SnackBar(
                ft.Text("❌ Generate JSON first!"),
                bgcolor="red",
            )
            self.page.snack_bar.open = True
            self.page.update()
            return
        
        lua_template = f'''-- Auto-generated Item Contract
-- Exported: {datetime.now().isoformat()}

local UUID = require("uuid")

return {{
    id = UUID.generate(),
    name = "{self.current_item.get('name', 'Custom Item')}",
    effect_type = "{self.current_item.get('effect_type', 'passive')}",
    
    trigger_conditions = {json.dumps(self.current_item.get('trigger_conditions', []))},
    stats_modifiers = {json.dumps(self.current_item.get('stats_modifiers', {}))},
    
    cost = {json.dumps(self.current_item.get('cost', None))},
    
    grants_iframe = {str(self.current_item.get('grants_iframe', False)).lower()},
    iframe_duration = {self.current_item.get('iframe_duration', 'nil')},
    cooldown = {self.current_item.get('cooldown', 'nil')},
}}
'''
        
        # Save to file
        output_dir = Path("/workspace/tools/flet_builds")
        output_dir.mkdir(exist_ok=True)
        filename = f"item_{datetime.now().strftime('%Y%m%d_%H%M%S')}.lua"
        output_path = output_dir / filename
        
        with open(output_path, 'w') as f:
            f.write(lua_template)
        
        self.page.snack_bar = ft.SnackBar(
            ft.Text(f"✅ Exported to: {output_path}"),
            bgcolor=ft.colors.GREEN,
        )
        self.page.snack_bar.open = True
        self.page.update()
    
    def run_simulation(self, e):
        """Run training room simulation (Rust backend)"""
        self.results_output.value = "🔄 Running simulation... (Rust backend required)"
        self.page.update()
        
        # When Rust module is compiled:
        # engine = TrainingRoomEngine()
        # effect_json = json.dumps(self.current_item)
        # engine.register_effect(effect_json)
        # result = engine.simulate(duration=10.0, tick_rate=0.1)
        # self.results_output.value = f"DPS: {result.dps:.2f}\nTriggers: {len(result.effect_triggers)}"
        
        self.page.snack_bar = ft.SnackBar(
            ft.Text("⚠️ Rust backend not compiled yet. Build with: cargo build --release"),
            bgcolor="orange",
        )
        self.page.snack_bar.open = True
        self.page.update()


def main(page: ft.Page):
    page.title = "🎮 Training Room & Item Builder"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 20
    page.add(TrainingRoomApp())

if __name__ == "__main__":
    ft.app(target=main)
