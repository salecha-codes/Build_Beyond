package com.debuggers.crophealth.domain

/** Farmer-reported observations only; this is not model-derived disease severity. */
data class ReportedSymptoms(
    val spreadingQuickly: Boolean = false,
    val manyPlantsAffected: Boolean = false,
    val wiltingOrDying: Boolean = false,
    val leafCoverage: LeafCoverage = LeafCoverage.NOT_REPORTED,
    val uncertainAnswers: Boolean = false,
    val fruitOrStemAffected: Boolean = false,
    val wetWeather: Boolean = false,
)

/** Leaf area is an answer selected by the farmer, never an image-model measurement. */
enum class LeafCoverage { NOT_REPORTED, NO_VISIBLE_DAMAGE, FEW_SPOTS, SOME_SPOTS, MANY_SPOTS }

enum class ConcernLevel { OBSERVE_AND_RECHECK, SEEK_LOCAL_EXPERT }

data class ConcernResult(
    val level: ConcernLevel,
    val reportedSymptoms: ReportedSymptoms,
    val ruleVersion: String = "prototype-observation-v1",
    val agronomistReviewed: Boolean = false,
)

object ConcernGuidance {
    fun summarize(symptoms: ReportedSymptoms): ConcernResult = ConcernResult(
        if (symptoms.spreadingQuickly || symptoms.manyPlantsAffected || symptoms.wiltingOrDying || symptoms.fruitOrStemAffected ||
            symptoms.leafCoverage == LeafCoverage.MANY_SPOTS || symptoms.leafCoverage == LeafCoverage.NOT_REPORTED ||
            symptoms.uncertainAnswers)
            ConcernLevel.SEEK_LOCAL_EXPERT else ConcernLevel.OBSERVE_AND_RECHECK,
        symptoms,
    )
}
