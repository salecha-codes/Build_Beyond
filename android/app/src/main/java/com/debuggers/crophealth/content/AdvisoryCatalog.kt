package com.debuggers.crophealth.content

import android.content.Context
import com.debuggers.crophealth.domain.AppLanguage
import com.debuggers.crophealth.domain.Conditions
import org.json.JSONArray
import org.json.JSONObject

data class AdvisoryCopy(val overview: String, val curability: String, val doNow: List<String>,
    val management: List<String>, val prevention: List<String>, val escalation: List<String>)
data class AdvisoryProfile(val conditionId: String, val cropId: String, val kind: String, val risk: String,
    val copy: AdvisoryCopy, val sources: List<SourceReference>)

/** The second model is a bundled, transparent decision model; no network service. */
class AdvisoryCatalog(context: Context) {
    private val root = context.assets.open("content/advisory_model.json").bufferedReader(Charsets.UTF_8).use { JSONObject(it.readText()) }
    val version: String = root.getString("model_version")
    init {
        require(root.getInt("schema_version") == 1 && root.getString("model_type") == "expert_decision_model")
        require(!root.getBoolean("trained") && !root.getBoolean("field_validated"))
        require(root.getJSONObject("profiles").keys().asSequence().toSet() == Conditions.ids)
    }
    fun profile(id: String, language: AppLanguage): AdvisoryProfile? {
        val item = root.getJSONObject("profiles").optJSONObject(id) ?: return null
        val copy = item.getJSONObject("translations").getJSONObject(language.id)
        val sourceIds = item.optJSONArray("source_ids").strings().toSet()
        val sources = root.optJSONArray("sources").objects().filter { it.getString("id") in sourceIds }.map {
            SourceReference(it.getString("id"), it.getString("title"), it.getString("url"), it.getString("verification_status"))
        }
        return AdvisoryProfile(id, item.getString("crop_id"), item.getString("kind"), item.getString("risk"),
            AdvisoryCopy(copy.getString("overview"), copy.getString("curability"), copy.getJSONArray("do_now").strings(),
                copy.getJSONArray("management").strings(), copy.getJSONArray("prevention").strings(), copy.getJSONArray("escalation").strings()), sources)
    }
}

private fun JSONArray?.strings(): List<String> = if (this == null) emptyList() else (0 until length()).map { getString(it) }
private fun JSONArray?.objects(): List<JSONObject> = if (this == null) emptyList() else (0 until length()).map { getJSONObject(it) }
