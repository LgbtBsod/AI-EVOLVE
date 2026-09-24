-- lua_content/probe_config.lua
-- Конфигурация для dev_probe визуальной аналитики
-- Используется Rust probe модулем через mlua

return {
  -- Пороги для детекции проблем
  blank_frame_stddev_threshold = 2.0,
  motion_detection_threshold = 5.0,
  brightness_anomaly_threshold = 30.0,
  entity_tracking_max_distance = 150.0,
  
  -- Настройки перцептивного хеширования
  visual_hash_bits = 16,  -- 16x16 = 256 бит
  hamming_threshold = 8,  -- Максимальное расстояние для "похожих" кадров
  
  -- SSIM для сравнения кадров
  ssim_threshold = 0.95,  -- >0.95 = визуально идентичны
  
  -- Кластеризация похожих кадров
  max_clusters = 10,      -- Максимум репрезентативных кадров
  
  -- Детекция UI элементов
  ui_colors = {
    health_bar = {r=220, g=50, b=50},    -- Красный HP бар
    mana_bar = {r=50, g=100, b=220},     -- Синий MP бар
    stamina_bar = {r=50, g=200, b=50},   -- Зеленый SP бар
    damage_number = {r=255, g=255, b=255}, -- Белый текст урона
  },
  
  ui_color_tolerance = 30,  -- Допуск для цветовой сегментации
  
  -- Авто-детекция проблем
  auto_detect_issues = true,
  
  issues = {
    {
      name = "broken_ui",
      description = "Урон был но цифр нет = UI сломан",
      condition = "combat_damage > 0 AND damage_numbers_count == 0",
    },
    {
      name = "render_blackout",
      description = "Черный экран при живом game state",
      condition = "brightness_stddev < 2.0 AND entities_alive > 0",
    },
    {
      name = "frozen_game",
      description = "Нет движения между кадрами",
      condition = "motion_ratio < 0.01 FOR 10 FRAMES",
    },
    {
      name = "flash_bang",
      description = "Внезапная вспышка/затемнение",
      condition = "brightness_delta > 30.0",
    },
  },
  
  -- Профили для разных типов тестов
  profiles = {
    quick = {
      visual_hash_bits = 8,
      max_clusters = 5,
      description = "Быстрый тест: меньше точность, быстрее результат",
    },
    
    standard = {
      visual_hash_bits = 16,
      max_clusters = 10,
      description = "Стандартный режим: баланс скорости/точности",
    },
    
    detailed = {
      visual_hash_bits = 32,
      max_clusters = 20,
      description = "Детальный анализ: максимум точности для баг-репортов",
    },
  },
}
