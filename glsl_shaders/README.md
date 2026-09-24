# GLSL Shaders Layer

## Назначение
Шейдеры изометрии, эффекты, пост-обработка.

## Структура
```
glsl_shaders/
├── isometric/          # Изометрический рендер
│   ├── tile.vert       # Вершины тайлов
│   ├── tile.frag       # Фрагменты тайлов (текстуры, свет)
│   ├── object.vert     # Вершины объектов
│   └── object.frag     # Фрагменты объектов
├── effects/            # Эффекты
│   ├── burn.vert       # Горение (анимация огня)
│   ├── burn.frag
│   ├── freeze.vert     # Заморозка (иней, лёд)
│   ├── freeze.frag
│   ├── shock.vert      # Удар молнии
│   └── shock.frag
├── postprocess/        # Пост-обработка
│   ├── bloom.frag      # Bloom эффект
│   ├── fog.frag        # Туман войны
│   ├── color_grading.frag  # Цветокоррекция
│   └── vignette.frag   # Виньетка
├── common/             # Общие функции
│   ├── lighting.glsl   # Освещение (PBR упрощённый)
│   ├── noise.glsl      # Шум Перлина для эффектов
│   └── utils.glsl      # Утилиты (трансформации)
└── shaders_config.json # Конфиг: какие шейдеры включать
```

## Пример: фрагмент горения
```glsl
// effects/burn.frag
#version 330 core

in vec2 TexCoord;
in float BurnIntensity;

uniform sampler2D texture0;
uniform float time;
uniform vec3 fireColor;

out vec4 FragColor;

// Импорт шума из common/noise.glsl
float perlinNoise(vec2 p);

void main() {
    vec4 baseColor = texture(texture0, TexCoord);
    
    // Анимация огня через шум и время
    float noiseVal = perlinNoise(TexCoord * 10.0 + time * 2.0);
    float flicker = sin(time * 10.0) * 0.5 + 0.5;
    
    // Смешивание с цветом огня
    vec3 burnColor = mix(baseColor.rgb, fireColor, BurnIntensity * noiseVal * flicker);
    
    // Добавление яркости в центре
    float brightness = 1.0 + BurnIntensity * 0.5;
    burnColor *= brightness;
    
    FragColor = vec4(burnColor, baseColor.a);
}
```

## Пример: туман войны
```glsl
// postprocess/fog.frag
#version 330 core

in vec2 TexCoord;

uniform sampler2D sceneTexture;
uniform sampler2D visibilityMask;  // 0 = не видно, 1 = видно
uniform float fogDensity;

out vec4 FragColor;

void main() {
    vec4 sceneColor = texture(sceneTexture, TexCoord);
    float visibility = texture(visibilityMask, TexCoord).r;
    
    // Плавное затухание к краям видимости
    float fogFactor = smoothstep(0.0, fogDensity, 1.0 - visibility);
    vec3 fogColor = vec3(0.1, 0.1, 0.15);  // Тёмно-синий
    
    vec3 finalColor = mix(sceneColor.rgb, fogColor, fogFactor);
    
    FragColor = vec4(finalColor, sceneColor.a);
}
```

## Интеграция с Panda3D
```python
# python_layer/l7_trainer/shader_manager.py
from panda3d.core import Shader, GraphicsStateGuardian

class ShaderManager:
    def __init__(self, render):
        self.render = render
        self.shaders = {}
        
    def load_shader(self, name, vert_path, frag_path):
        shader = Shader.load(vert_path, frag_path)
        self.shaders[name] = shader
        
    def apply_shader(self, node, shader_name, uniforms={}):
        shader = self.shaders[shader_name]
        node.setShader(shader)
        
        for uniform_name, value in uniforms.items():
            node.setShaderInput(uniform_name, value)
            
    def enable_bloom(self, intensity=1.5):
        self.apply_shader(
            self.render,
            "bloom",
            {"bloomIntensity": intensity}
        )
```

## Принципы
- **Модульность:** Каждый эффект — отдельный шейдер
- **Переиспользование:** Общие функции в `common/`
- **Производительность:** Low-poly + шейдеры вместо сложной геометрии
- **Настройка:** Uniforms для динамического изменения параметров

## Следующие шаги
1. Создать структуру директорий
2. Реализовать базовые шейдеры изометрии
3. Добавить эффекты статусов (горение, заморозка, шок)
4. Интегрировать с Panda3D рендером
