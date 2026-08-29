package com.automusic.player.core.settings

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import org.json.JSONArray
import org.json.JSONObject

private val Context.dataStore by preferencesDataStore(name = "settings")

/** 模型供应商(OpenAI 兼容多模态接口)。 */
data class Provider(
    val name: String,
    val baseUrl: String,
    val apiKey: String,
    val model: String,
)

/** 设置存储:供应商列表 + 激活项,JSON 持久化(协议与桌面版一致)。 */
class SettingsStore(private val context: Context) {

    private val KEY_PROVIDERS = stringPreferencesKey("providers")
    private val KEY_ACTIVE = stringPreferencesKey("active_provider")

    val providersFlow: Flow<List<Provider>> = context.dataStore.data.map { prefs ->
        decode(prefs[KEY_PROVIDERS] ?: "[]")
    }

    val activeNameFlow: Flow<String> = context.dataStore.data.map { prefs ->
        prefs[KEY_ACTIVE] ?: ""
    }

    suspend fun getActiveProvider(): Provider? {
        val prefs = context.dataStore.data.first()
        val active = prefs[KEY_ACTIVE] ?: return null
        return decode(prefs[KEY_PROVIDERS] ?: "[]").firstOrNull { it.name == active }
    }

    suspend fun save(provider: Provider) {
        context.dataStore.edit { prefs ->
            val list = decode(prefs[KEY_PROVIDERS] ?: "[]").toMutableList()
            val idx = list.indexOfFirst { it.name == provider.name }
            if (idx >= 0) list[idx] = provider else list.add(provider)
            prefs[KEY_PROVIDERS] = encode(list)
        }
    }

    suspend fun delete(name: String) {
        context.dataStore.edit { prefs ->
            val list = decode(prefs[KEY_PROVIDERS] ?: "[]").filter { it.name != name }
            prefs[KEY_PROVIDERS] = encode(list)
            if (prefs[KEY_ACTIVE] == name) prefs[KEY_ACTIVE] = ""
        }
    }

    suspend fun setActive(name: String) {
        context.dataStore.edit { prefs -> prefs[KEY_ACTIVE] = name }
    }

    private fun encode(list: List<Provider>): String {
        val arr = JSONArray()
        for (p in list) {
            arr.put(
                JSONObject()
                    .put("name", p.name)
                    .put("baseUrl", p.baseUrl)
                    .put("apiKey", p.apiKey)
                    .put("model", p.model)
            )
        }
        return arr.toString()
    }

    private fun decode(json: String): List<Provider> = try {
        val arr = JSONArray(json)
        buildList {
            for (i in 0 until arr.length()) {
                val o = arr.getJSONObject(i)
                add(
                    Provider(
                        name = o.optString("name"),
                        baseUrl = o.optString("baseUrl"),
                        apiKey = o.optString("apiKey"),
                        model = o.optString("model"),
                    )
                )
            }
        }
    } catch (e: Exception) {
        emptyList()
    }
}
