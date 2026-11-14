package com.debuggers.crophealth.domain

data class QualityMetrics(
    val meanLuminance: Double,
    val laplacianVariance: Double,
    val width: Int,
    val height: Int,
    val decodeSucceeded: Boolean = true,
)

data class QualityConfig(
    val minLuminance: Double = 20.0,
    val maxLuminance: Double = 240.0,
    val minLaplacianVariance: Double = 25.0,
    val minSide: Int = 224,
    val thresholdsValidated: Boolean = false,
)

enum class QualityIssue { UNREADABLE, TOO_SMALL, TOO_DARK, TOO_BRIGHT, BLURRY }

data class QualityCheck(val issues: Set<QualityIssue>, val thresholdsValidated: Boolean) {
    val acceptable: Boolean get() = issues.isEmpty()
}

data class InferenceOutput(
    val labelIds: List<String>,
    val logits: List<Float>,
    val modelVersion: String,
    val modelReady: Boolean = true,
    val embeddingDistance: Float? = null,
)

/** Values must come from the artifact, not an invented universal confidence cutoff. */
data class PolicyConfig(
    val validated: Boolean = false,
    val temperature: Float = 1f,
    val minConfidence: Float = 0.8f,
    val minMargin: Float = 0.15f,
    val maxEmbeddingDistance: Float? = null,
    val enabledConditionIds: Set<String> = Conditions.ids,
)

data class RankedPrediction(val condition: ConditionLabel, val score: Float)

data class PredictionEvidence(
    val ranked: List<RankedPrediction>,
    val modelVersion: String,
    val calibratedAndValidated: Boolean,
    val embeddingDistance: Float?,
) {
    val top: RankedPrediction get() = ranked.first()
    val margin: Float get() = top.score - (ranked.getOrNull(1)?.score ?: 0f)
}

enum class UncertaintyReason {
    MODEL_NOT_VALIDATED, LOW_SCORE, AMBIGUOUS, UNFAMILIAR_IMAGE,
    CONDITION_DISABLED, MISSING_EMBEDDING_DISTANCE,
}

enum class ModelFailure { NOT_READY, LABEL_MISMATCH, INVALID_SCORES, INVALID_POLICY }

sealed interface AssessmentResult {
    val evidence: PredictionEvidence?

    data class Retake(val quality: QualityCheck) : AssessmentResult {
        override val evidence: PredictionEvidence? = null
    }
    data class ModelUnavailable(val reason: ModelFailure) : AssessmentResult {
        override val evidence: PredictionEvidence? = null
    }
    data class CropMismatch(
        val selectedCrop: Crop,
        val predictedCrop: Crop,
        override val evidence: PredictionEvidence,
    ) : AssessmentResult
    data class Uncertain(
        val reasons: Set<UncertaintyReason>,
        override val evidence: PredictionEvidence,
    ) : AssessmentResult
    data class LikelyCondition(
        val condition: ConditionLabel,
        override val evidence: PredictionEvidence,
    ) : AssessmentResult
    data class HealthyLooking(
        val condition: ConditionLabel,
        override val evidence: PredictionEvidence,
    ) : AssessmentResult
}
