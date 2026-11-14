package com.debuggers.crophealth.content

import android.content.Context
import com.debuggers.crophealth.domain.AppLanguage
import com.debuggers.crophealth.domain.Conditions
import org.json.JSONArray
import org.json.JSONObject

data class TreatmentOption(val id: String, val title: String, val whenToUse: String,
    val steps: List<String>, val limits: String, val sourceIds: List<String>)
data class CareFollowUp(val whenToCheck: String, val check: String, val action: String)
data class CareStagePlan(val title: String, val actions: List<String>)
data class CareProtocolCopy(val goal: String, val confirmChecks: List<String>, val lookAlikes: List<String>,
    val treatmentOptions: List<TreatmentOption>, val avoid: List<String>, val recoverySigns: List<String>,
    val failureSigns: List<String>, val followUp: List<CareFollowUp>, val stagePlans: Map<String, CareStagePlan>,
    val expertQuestions: List<String>)
data class CareProtocol(val conditionId: String, val cropId: String, val copy: CareProtocolCopy,
    val version: String, val sources: List<SourceReference>)

/** Complete locally packaged care information. Access does not establish a diagnosis. */
class CareProtocolCatalog(context: Context) {
    private val root = context.assets.open("content/care_protocols.json").bufferedReader(Charsets.UTF_8)
        .use { JSONObject(it.readText()) }
    val version: String = root.getString("version")
    init {
        require(root.getInt("schema_version") == 1)
        require(!root.getBoolean("agronomist_reviewed") && !root.getBoolean("field_validated"))
        require(root.getJSONObject("protocols").keys().asSequence().toSet() == Conditions.ids)
        Conditions.all.forEach { condition ->
            val item = root.getJSONObject("protocols").getJSONObject(condition.id)
            require(item.getString("crop_id") == condition.crop.id)
            AppLanguage.entries.forEach { language ->
                val copy = item.getJSONObject("translations").getJSONObject(language.id)
                require(copy.getString("goal").isNotBlank())
                listOf("confirm_checks", "look_alikes", "avoid", "recovery_signs", "failure_signs", "expert_questions").forEach {
                    require(copy.getJSONArray(it).length() > 0)
                }
                require(copy.getJSONArray("treatment_options").length() > 0 && copy.getJSONArray("follow_up").length() > 0)
                listOf("MILD", "MODERATE", "SEVERE").forEach {
                    require(copy.getJSONObject("stage_plans").getJSONObject(it).getJSONArray("actions").length() > 0)
                }
            }
        }
    }

    fun protocol(id: String, language: AppLanguage): CareProtocol? {
        val item = root.getJSONObject("protocols").optJSONObject(id) ?: return null
        val copy = item.getJSONObject("translations").getJSONObject(language.id)
        val ids = item.getJSONArray("source_ids").careStrings().toSet()
        val sources = root.getJSONArray("sources").careObjects().filter { it.getString("id") in ids }.map {
            SourceReference(it.getString("id"), it.getString("title"), it.getString("url"), it.getString("verification_status"))
        }
        return CareProtocol(id, item.getString("crop_id"), CareProtocolCopy(
            copy.getString("goal"), copy.getJSONArray("confirm_checks").careStrings(), copy.getJSONArray("look_alikes").careStrings(),
            copy.getJSONArray("treatment_options").careObjects().map {
                TreatmentOption(it.getString("id"), it.getString("title"), it.getString("when"),
                    it.getJSONArray("steps").careStrings(), it.getString("limits"), it.getJSONArray("source_ids").careStrings())
            }, copy.getJSONArray("avoid").careStrings(), copy.getJSONArray("recovery_signs").careStrings(),
            copy.getJSONArray("failure_signs").careStrings(), copy.getJSONArray("follow_up").careObjects().map {
                CareFollowUp(it.getString("when"), it.getString("check"), it.getString("action"))
            }, listOf("MILD", "MODERATE", "SEVERE").associateWith {
                val stage = copy.getJSONObject("stage_plans").getJSONObject(it)
                CareStagePlan(stage.getString("title"), stage.getJSONArray("actions").careStrings())
            }, copy.getJSONArray("expert_questions").careStrings()), version, sources)
    }
}

private fun JSONArray.careStrings(): List<String> = (0 until length()).map { getString(it) }
private fun JSONArray.careObjects(): List<JSONObject> = (0 until length()).map { getJSONObject(it) }
