package com.debuggers.crophealth.domain

enum class ReportedSeverity { UNKNOWN, NONE, MILD, MODERATE, SEVERE }
enum class CareUrgency { MONITOR, SOON, SAME_DAY, URGENT }

data class AdvisoryAssessment(
    val severity: ReportedSeverity,
    val urgency: CareUrgency,
    val reviewHours: Int,
    val reasonCodes: List<String>,
    val healthyConflict: Boolean,
    val modelVersion: String = "offline-advisory-v1",
    val requiresConfirmation: Boolean = true,
)

/** Explicit expert rules, not trained severity prediction or a disease confidence score. */
object AdvisoryDecisionModel {
    fun assess(risk: String?, kind: String?, symptoms: ReportedSymptoms?): AdvisoryAssessment {
        if (symptoms == null) return AdvisoryAssessment(ReportedSeverity.UNKNOWN,
            if (risk == "rapid_blight") CareUrgency.SAME_DAY else CareUrgency.SOON,
            if (risk == "rapid_blight") 24 else 48,
            listOf("awaiting_answers") + when (risk) { "rapid_blight" -> listOf("rapid_blight"); "virus" -> listOf("virus"); else -> emptyList() } +
                if (kind == null) listOf("confirm_cause") else emptyList(), false)
        val reasons = mutableListOf<String>()
        with(symptoms) {
            reasons += when (leafCoverage) {
                LeafCoverage.NO_VISIBLE_DAMAGE -> "coverage_none"
                LeafCoverage.FEW_SPOTS -> "coverage_low"
                LeafCoverage.SOME_SPOTS -> "coverage_moderate"
                LeafCoverage.MANY_SPOTS -> "coverage_high"
                LeafCoverage.NOT_REPORTED -> "coverage_unknown"
            }
            if (wiltingOrDying) reasons += "wilting"
            if (fruitOrStemAffected) reasons += "fruit_or_stem"
            if (spreadingQuickly) reasons += "rapid_spread"
            if (manyPlantsAffected) reasons += "multiple_plants"
            if (uncertainAnswers) reasons += "uncertain_answers"
            if (wetWeather && kind != "healthy") reasons += "wet_weather"
        }
        if (risk == "rapid_blight") reasons += "rapid_blight"
        if (risk == "virus") reasons += "virus"
        val severity = when {
            symptoms.wiltingOrDying || symptoms.fruitOrStemAffected || symptoms.leafCoverage == LeafCoverage.MANY_SPOTS -> ReportedSeverity.SEVERE
            symptoms.leafCoverage == LeafCoverage.SOME_SPOTS -> ReportedSeverity.MODERATE
            symptoms.leafCoverage == LeafCoverage.FEW_SPOTS -> ReportedSeverity.MILD
            symptoms.leafCoverage == LeafCoverage.NO_VISIBLE_DAMAGE -> ReportedSeverity.NONE
            else -> ReportedSeverity.UNKNOWN
        }
        val healthyConflict = kind == "healthy" && (symptoms.leafCoverage in setOf(LeafCoverage.FEW_SPOTS, LeafCoverage.SOME_SPOTS, LeafCoverage.MANY_SPOTS) ||
            symptoms.wiltingOrDying || symptoms.fruitOrStemAffected || symptoms.spreadingQuickly || symptoms.manyPlantsAffected)
        if (healthyConflict) reasons += "healthy_conflict"
        val urgency = when {
            symptoms.wiltingOrDying || (symptoms.spreadingQuickly && symptoms.manyPlantsAffected) -> CareUrgency.URGENT
            severity == ReportedSeverity.SEVERE || risk == "rapid_blight" || (risk == "virus" && symptoms.spreadingQuickly) -> CareUrgency.SAME_DAY
            severity == ReportedSeverity.MODERATE || symptoms.spreadingQuickly || symptoms.manyPlantsAffected ||
                symptoms.uncertainAnswers || severity == ReportedSeverity.UNKNOWN || risk == "virus" || healthyConflict -> CareUrgency.SOON
            else -> CareUrgency.MONITOR
        }
        if (kind == null || healthyConflict) reasons += "confirm_cause"
        return AdvisoryAssessment(severity, urgency, when (urgency) {
            CareUrgency.URGENT -> 0; CareUrgency.SAME_DAY -> 24; else -> 48
        }, reasons, healthyConflict)
    }
}
