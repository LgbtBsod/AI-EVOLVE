#!/usr/bin/env python3
"""
Training Room Demo - Equipment Testing on Mannequins
=====================================================
Демонстрация новой функции: тестирование защитных предметов на манекенах.

Теперь можно:
1. Надевать шмотки на манекен для теста защиты
2. Тестировать mitigation (снижение урона) от разных наборов
3. Сравнивать эффективность танковальных билдов
4. Использовать test_defense=True для режима "не атаковать, только проверять статы"
"""

import sys
sys.path.insert(0, '/workspace/src')
sys.path.insert(0, '/workspace')

from tools.training_room import (
    TrainingRoom, MannequinType, TestScenario, 
    create_banes_scar_necklace, create_sorrow_of_berserk
)
from features.advanced_items import ItemDefinition, StatType


def create_tank_item(name: str, defense: float, phys_res: float, magic_res: float) -> ItemDefinition:
    """Создание танкового предмета для теста"""
    # Используем существующие StatType из advanced_items
    # Для resistance используем percent модификаторы к incoming damage
    return ItemDefinition(
        name=name,
        unique_id=f"tank_{name}",
        stats={
            StatType.DEFENSE: defense,
            StatType.MAX_HP: 500 + phys_res * 10 + magic_res * 10  # Симулируем resist через HP
        },
        effects=[]
    )


def main():
    print("\n" + "="*70)
    print("TRAINING ROOM - DEFENSE TESTING DEMO")
    print("="*70 + "\n")
    
    room = TrainingRoom()
    
    # Создаём манекены с разной экипировкой
    print("🛡️  Creating mannequins with different equipment...\n")
    
    # Манекен без экипировки (baseline)
    room.create_mannequin("naked_dummy", MannequinType.DUMMY)
    print("   ✅ Created naked dummy (no equipment)")
    
    # Манекен с лёгкой бронёй
    light_armor = create_tank_item("Light Plate", defense=100, phys_res=10, magic_res=5)
    room.create_mannequin("light_armor", MannequinType.DUMMY, equipment=[light_armor])
    print(f"   ✅ Created light armor mannequin ({light_armor.name})")
    
    # Манекен с тяжёлой бронёй
    heavy_armor = create_tank_item("Heavy Plate", defense=300, phys_res=25, magic_res=15)
    room.create_mannequin("heavy_armor", MannequinType.DUMMY, equipment=[heavy_armor])
    print(f"   ✅ Created heavy armor mannequin ({heavy_armor.name})")
    
    # Манекен с магической защитой
    mage_robe = create_tank_item("Mage Robe", defense=50, phys_res=5, magic_res=40)
    room.create_mannequin("mage_robe", MannequinType.TANK, equipment=[mage_robe])
    print(f"   ✅ Created mage robe mannequin ({mage_robe.name})")
    
    # Тестовые предметы игрока (для атаки)
    player_dps_items = [
        create_banes_scar_necklace(),
        create_sorrow_of_berserk()
    ]
    
    print("\n⚔️  Running DPS tests against different armor types...\n")
    
    results = {}
    
    # Тест против голого манекена
    scenario = TestScenario(
        name="defense_test",
        description="Testing damage mitigation",
        duration_seconds=5.0,
        attacks_per_second=2.0
    )
    room.setup_test_scenario(scenario)
    
    result_naked = room.run_dps_test(player_dps_items, "naked_dummy", duration=5.0)
    results["naked"] = result_naked
    print(f"   vs Naked:     {result_naked.dps:>8.1f} DPS | Mitigation: 0% (baseline)")
    
    # Тест против лёгкой брони
    result_light = room.run_dps_test(player_dps_items, "light_armor", duration=5.0)
    results["light"] = result_light
    mitigation_light = (1 - result_light.dps / result_naked.dps) * 100
    print(f"   vs Light:     {result_light.dps:>8.1f} DPS | Mitigation: {mitigation_light:>5.1f}%")
    
    # Тест против тяжёлой брони
    result_heavy = room.run_dps_test(player_dps_items, "heavy_armor", duration=5.0)
    results["heavy"] = result_heavy
    mitigation_heavy = (1 - result_heavy.dps / result_naked.dps) * 100
    print(f"   vs Heavy:     {result_heavy.dps:>8.1f} DPS | Mitigation: {mitigation_heavy:>5.1f}%")
    
    # Тест против магической защиты
    result_mage = room.run_dps_test(player_dps_items, "mage_robe", duration=5.0)
    results["mage"] = result_mage
    mitigation_mage = (1 - result_mage.dps / result_naked.dps) * 100
    print(f"   vs Mage Robe: {result_mage.dps:>8.1f} DPS | Mitigation: {mitigation_mage:>5.1f}%")
    
    # Анализ результатов
    print("\n📊 Analysis:\n")
    
    best_mitigation = max(results.items(), key=lambda x: (1 - x[1].dps / result_naked.dps))
    print(f"   🏆 Best Mitigation: {best_mitigation[0]} ({(1 - best_mitigation[1].dps / result_naked.dps)*100:.1f}%)")
    
    worst_mitigation = min(results.items(), key=lambda x: (1 - x[1].dps / result_naked.dps))
    print(f"   ⚠️  Worst Mitigation: {worst_mitigation[0]} ({(1 - worst_mitigation[1].dps / result_naked.dps)*100:.1f}%)")
    
    # Тест в режиме defense_only (без атак)
    print("\n🛡️  Testing defense mode (test_defense=True)...\n")
    
    room.setup_test_scenario(TestScenario(
        name="defense_only",
        description="Checking mannequin stats without attacking"
    ))
    
    # В этом режиме урон не наносится, только проверяются статы манекена
    result_defense = room.run_dps_test(
        player_dps_items, 
        "heavy_armor", 
        duration=3.0,
        test_defense=True
    )
    
    print(f"   Defense mode test complete:")
    print(f"      Total Damage: {result_defense.total_damage} (expected 0 - no attacks)")
    print(f"      Hits: {result_defense.total_hits} (simulation ticks)")
    
    # Экспорт отчёта
    report_path = room.export_report(result_heavy, "defense_comparison.json")
    print(f"\n📄 Report exported to: {report_path}")
    
    print("\n" + "="*70)
    print("DEFENSE TESTING COMPLETE!")
    print("="*70 + "\n")
    
    print("💡 Key Features Demonstrated:")
    print("   ✅ Equipment on mannequins (armor, resistances)")
    print("   ✅ Mitigation calculation (damage reduction)")
    print("   ✅ Comparison of different armor sets")
    print("   ✅ test_defense=True mode for stat checking")
    print("   ✅ JSON export for agent analysis (token optimized)")
    print("\n")


if __name__ == "__main__":
    main()
