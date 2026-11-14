package com.debuggers.crophealth.domain

import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test
import java.io.File

class AdvisoryDecisionModelTest {
    @Test fun fruitOrStemSignsAlsoEscalateLegacySavedConcern() {
        val symptoms = ReportedSymptoms(leafCoverage = LeafCoverage.FEW_SPOTS, fruitOrStemAffected = true)
        assertEquals(ConcernLevel.SEEK_LOCAL_EXPERT, ConcernGuidance.summarize(symptoms).level)
        assertEquals(ReportedSeverity.SEVERE, AdvisoryDecisionModel.assess("foliar", "fungal", symptoms).severity)
    }
    @Test fun reportedDamageAndUrgencyAreIndependent() {
        val result = AdvisoryDecisionModel.assess("rapid_blight", "oomycete", ReportedSymptoms(leafCoverage = LeafCoverage.FEW_SPOTS))
        assertEquals(ReportedSeverity.MILD, result.severity)
        assertEquals(CareUrgency.SAME_DAY, result.urgency)
        assertTrue(result.requiresConfirmation)
    }
    @Test fun noAnswersCannotProduceReassurance() {
        val result = AdvisoryDecisionModel.assess("foliar", "fungal", null)
        assertEquals(ReportedSeverity.UNKNOWN, result.severity)
        assertEquals(CareUrgency.SOON, result.urgency)
        assertTrue("awaiting_answers" in result.reasonCodes)
    }
    @Test fun fieldSpreadCanBeUrgentWithoutDamageOnThisLeaf() {
        val result = AdvisoryDecisionModel.assess("routine", "healthy", ReportedSymptoms(
            spreadingQuickly = true, manyPlantsAffected = true, leafCoverage = LeafCoverage.NO_VISIBLE_DAMAGE))
        assertEquals(ReportedSeverity.NONE, result.severity)
        assertEquals(CareUrgency.URGENT, result.urgency)
        assertTrue(result.healthyConflict)
    }
    @Test fun wetWeatherDoesNotInventDamage() {
        val symptoms = ReportedSymptoms(leafCoverage = LeafCoverage.NO_VISIBLE_DAMAGE, wetWeather = true)
        val result = AdvisoryDecisionModel.assess("routine", "healthy", symptoms)
        assertEquals(ReportedSeverity.NONE, result.severity)
        assertEquals(CareUrgency.MONITOR, result.urgency)
        assertFalse(result.healthyConflict)
    }
    @Test fun uncertainAnswersNeverRoutine() {
        val result = AdvisoryDecisionModel.assess("foliar", "fungal", ReportedSymptoms(
            leafCoverage = LeafCoverage.FEW_SPOTS, uncertainAnswers = true))
        assertEquals(CareUrgency.SOON, result.urgency)
    }
    @Test fun sameSharedBehaviorContractAsBrowser() {
        val root = sequenceOf(File("."), File(".."), File("../..")).first { File(it, "contracts/fixtures/advisory_cases.json").isFile }
        val cases = Json.parseToJsonElement(File(root, "contracts/fixtures/advisory_cases.json").readText()).jsonObject["cases"]!!.jsonArray
        val model = Json.parseToJsonElement(File(root, "content/advisory_model.json").readText()).jsonObject
        val profiles = model["profiles"]!!.jsonObject
        cases.forEach { value ->
            val c = value.jsonObject
            val name = c["name"]!!.jsonPrimitive.content
            val type = c["resultType"]!!.jsonPrimitive.content
            val blocked = type in setOf("retake", "crop_mismatch", "model_unavailable")
            val id = c["conditionId"]!!.jsonPrimitive.content
            val profile = if (blocked) null else profiles[id]?.jsonObject
            val x = c["symptoms"]?.takeUnless { it is JsonNull }?.jsonObject
            fun bool(key: String) = x?.get(key)?.jsonPrimitive?.booleanOrNull ?: false
            val symptoms = x?.let { ReportedSymptoms(bool("spreadingQuickly"), bool("manyPlantsAffected"), bool("wiltingOrDying"),
                LeafCoverage.valueOf(it["leafCoverage"]!!.jsonPrimitive.content), bool("uncertainAnswers"), bool("fruitOrStemAffected"), bool("wetWeather")) }
            val result = AdvisoryDecisionModel.assess(profile?.get("risk")?.jsonPrimitive?.content, profile?.get("kind")?.jsonPrimitive?.content, symptoms)
            val expected = c["expected"]!!.jsonObject
            expected["severity"]?.let { assertEquals(name, it.jsonPrimitive.content, result.severity.name) }
            expected["urgency"]?.let { assertEquals(name, it.jsonPrimitive.content, result.urgency.name) }
            expected["diseaseCareAllowed"]?.let { assertEquals(name, it.jsonPrimitive.boolean, profile != null && !result.healthyConflict) }
        }
    }
}
