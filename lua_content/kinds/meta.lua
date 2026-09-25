-- lua_content/kinds/meta.lua — Meta Layer (ЧАСТЬ 3.5). ВНИМАНИЕ: runtime НЕ игровой —
-- отдельный интерфейс к платформе (file IO в песочнице save-директории). События meta
-- пишутся в Timeline как irreversible (rewind не может отменить удаление файла).
local function k(id, fields, note)
  return { id = id, layer = "meta", handler = "platform", reversible = false,
           fields = fields, note = note }
end
return {
  k("file_access", { "target", "operations" }, "read/write/delete в песочнице сейвов"),
  k("file_delete", { "path" }, "удалить файл (Моника DDLC)"),
  k("save_corruption", { "target", "value" }, "порча сейва (Flowey давит SAV)"),
  k("game_transform", { "genre" }, "смена жанра игры (NieR: доска -> bullet hell)"),
  k("close_game", { "confirm" }, "закрыть игру с точки зрения персонажа"),
  k("author_contact", { "channel" }, "канал автора (Animal Man к Моррисону)"),
  k("see_panels", { "scope" }, "видеть панели комикса (Gwenpool)"),
  k("panel_jump", { "from", "to" }, "прыжок между панелями"),
  k("off_panel_win", {}, "победа вне кадра"),
  k("rule_authority", { "over" }, "власть над правилами игры (Лешья пересобирает зал)"),
  k("narrative_agent", { "voice", "style" }, "активный рассказчик (Stanley Parable)"),
}
