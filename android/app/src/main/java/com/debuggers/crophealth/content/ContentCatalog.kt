package com.debuggers.crophealth.content

import android.content.Context
import com.debuggers.crophealth.domain.AppLanguage
import org.json.JSONArray
import org.json.JSONObject

data class SourceReference(val id: String, val title: String, val url: String, val verificationStatus: String)

data class Guidance(
    val conditionId: String,
    val name: String,
    val summary: String,
    val symptoms: List<String>,
    val actions: List<String>,
    val prevention: List<String>,
    val caution: String,
    val audioAsset: String?,
    val contentVersion: String,
    val reviewStatus: String,
    val translationStatus: String,
    val sources: List<SourceReference>,
)

data class Prompt(val key: String, val title: String, val message: String, val audioAsset: String?)

/** No network access; safe prototype observation guidance, never chemical treatment instructions. */
class ContentCatalog(context: Context) {
    private val root = context.assets.open("content/catalog.json").bufferedReader(Charsets.UTF_8).use { JSONObject(it.readText()) }
    val version: String = root.getString("content_version")
    val reviewNotice: String get() = root.getString("review_notice")

    fun guidance(conditionId: String, language: AppLanguage): Guidance? {
        val item = root.getJSONObject("conditions").optJSONObject(conditionId) ?: return null
        val copy = item.getJSONObject("translations").let { it.optJSONObject(language.id) ?: it.getJSONObject("en") }
        return Guidance(
            conditionId, copy.getString("name"), copy.getString("summary"),
            copy.optJSONArray("symptoms").strings(), copy.optJSONArray("actions").strings(),
            copy.optJSONArray("prevention").strings(), copy.getString("caution"),
            copy.optString("audio_asset").ifBlank { null }, version,
            item.getString("review_status"), copy.getString("translation_status"),
            item.optJSONArray("sources").objects().map {
                SourceReference(it.getString("id"), it.getString("title"), it.getString("url"), it.getString("verification_status"))
            },
        )
    }

    fun prompt(key: String, language: AppLanguage): Prompt {
        val item = root.getJSONObject("prompts").optJSONObject(key)
            ?: root.getJSONObject("prompts").getJSONObject("uncertain")
        val copy = item.optJSONObject(language.id) ?: item.getJSONObject("en")
        return Prompt(key, copy.getString("title"), copy.getString("message"), copy.optString("audio_asset").ifBlank { null })
    }

    fun text(key: String, language: AppLanguage): String {
        val strings = root.getJSONObject("ui_strings")
        return strings.optJSONObject(language.id)?.optString(key)?.takeIf { it.isNotBlank() }
            ?: strings.getJSONObject("en").optString(key, key)
    }
}

private fun JSONArray?.strings(): List<String> = if (this == null) emptyList() else (0 until length()).map { getString(it) }
private fun JSONArray?.objects(): List<JSONObject> = if (this == null) emptyList() else (0 until length()).map { getJSONObject(it) }
