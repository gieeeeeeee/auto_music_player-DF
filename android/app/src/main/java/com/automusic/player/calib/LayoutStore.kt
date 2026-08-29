package com.automusic.player.calib

import android.content.Context
import com.automusic.player.core.KeyPointMap
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/** 一套琴键布局:note_id -> 归一化坐标。 */
data class KeyLayout(
    val id: String,
    val name: String,
    val points: Map<String, Pair<Float, Float>>,
)

data class LayoutState(
    val layouts: List<KeyLayout> = emptyList(),
    val activeId: String = "",
) {
    val active: KeyLayout?
        get() = layouts.firstOrNull { it.id == activeId } ?: layouts.firstOrNull()
}

/**
 * 标定布局存储:filesDir/layouts.json。
 * 首次启动自动生成鸣潮/原神两套默认预设(真机截图估算值)。
 */
class LayoutStore(context: Context) {

    private val file = File(context.filesDir, "layouts.json")

    private val _state = MutableStateFlow(load())
    val state: StateFlow<LayoutState> = _state.asStateFlow()

    fun get(id: String): KeyLayout? = _state.value.layouts.firstOrNull { it.id == id }

    fun save(layout: KeyLayout, makeActive: Boolean = true) {
        val current = _state.value
        val list = current.layouts.filterNot { it.id == layout.id } + layout
        val activeId = when {
            makeActive -> layout.id
            current.activeId.isNotEmpty() -> current.activeId
            else -> list.first().id
        }
        persist(LayoutState(list, activeId))
    }

    fun delete(id: String) {
        val current = _state.value
        val list = current.layouts.filterNot { it.id == id }
        val activeId = if (current.activeId == id) list.firstOrNull()?.id ?: "" else current.activeId
        persist(LayoutState(list, activeId))
    }

    fun setActive(id: String) {
        val current = _state.value
        if (current.layouts.any { it.id == id }) persist(current.copy(activeId = id))
    }

    private fun persist(state: LayoutState) {
        _state.value = state
        runCatching { write(state) }
    }

    private fun load(): LayoutState {
        return try {
            if (file.exists()) {
                decode(file.readText())
            } else {
                // 首次启动:写入鸣潮/原神两套默认预设
                val initial = listOf(default("wuthering"), default("genshin"))
                val state = LayoutState(initial, initial.first().id)
                runCatching { write(state) }
                state
            }
        } catch (e: Exception) {
            LayoutState()
        }
    }

    private fun default(game: String): KeyLayout {
        val id = game
        val name = KeyPointMap.GAME_NAMES[game] ?: game
        return KeyLayout(id, name, KeyPointMap.defaultLayout(game))
    }

    private fun write(state: LayoutState) {
        val root = JSONObject()
        root.put("active", state.activeId)
        val arr = JSONArray()
        for (l in state.layouts) {
            val obj = JSONObject()
            obj.put("id", l.id)
            obj.put("name", l.name)
            val pts = JSONObject()
            for ((noteId, p) in l.points) {
                pts.put(noteId, JSONArray().put(p.first.toDouble()).put(p.second.toDouble()))
            }
            obj.put("points", pts)
            arr.put(obj)
        }
        root.put("layouts", arr)
        file.writeText(root.toString())
    }

    private fun decode(json: String): LayoutState {
        val root = JSONObject(json)
        val arr = root.optJSONArray("layouts") ?: JSONArray()
        val layouts = mutableListOf<KeyLayout>()
        for (i in 0 until arr.length()) {
            val o = arr.getJSONObject(i)
            val pts = mutableMapOf<String, Pair<Float, Float>>()
            val p = o.optJSONObject("points") ?: JSONObject()
            for (key in p.keys()) {
                val pair = p.getJSONArray(key)
                pts[key] = pair.getDouble(0).toFloat() to pair.getDouble(1).toFloat()
            }
            layouts.add(KeyLayout(o.optString("id"), o.optString("name"), pts))
        }
        return LayoutState(layouts, root.optString("active"))
    }
}
