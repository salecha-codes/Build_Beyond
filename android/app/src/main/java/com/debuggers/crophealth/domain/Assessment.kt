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
    // Smaller usable uploads are resized to 224 for inference; prefer 224+ when capturing.
    val minSide: Int = 128,
    val thresholdsValidated: Boolean = false,
)

enum class QualityIssue { UNREADABLE, TOO_SMALL, TOO_DARK, TOO_BRIGHT, BLURRY, NOT_A_LEAF }

data class QualityCheck(val issues: Set<QualityIssue>, val thresholdsValidated: Boolean) {
    val acceptable: Boolean get() = issues.isEmpty()
}

data class InferenceOutput(
    val labelIds: List<String>,
    val logits: List<Float>,
    val modelVersion: String,
    val modelReady: Boolean = true,
    val embeddingDistance: Float? = null,
    val leafProbability: Float? = null,
)

/** Values must come from the artifact, not an invented universal confidence cutoff. */
data class ClassAcceptanceThreshold(
    val enabled: Boolean,
    val minConfidence: Float?,
    val minMargin: Float?,
    val maxEmbeddingDistance: Float? = null,
)

data class PolicyConfig(
    val validated: Boolean = false,
    val temperature: Float = 1f,
    val minConfidence: Float = 0.8f,
    val minMargin: Float = 0.15f,
    val maxEmbeddingDistance: Float? = null,
    val enabledConditionIds: Set<String> = Conditions.ids,
    /** Source-test qualification permits a prototype estimate, never a field-validation claim. */
    val sourceEvaluated: Boolean = false,
    val classThresholds: Map<String, ClassAcceptanceThreshold> = emptyMap(),
    val allowConditionSpecificAdvice: Boolean = false,
    val minimumLeafProbability: Float? = null,
    /** Optional CAL-fitted gate. Null keeps the frozen acceptance policy unchanged. */
    val maxNormalizedEntropy: Float? = null,
)

data class RankedPrediction(val condition: ConditionLabel, val score: Float)

data class PredictionEvidence(
    val ranked: List<RankedPrediction>,
    val modelVersion: String,
    val calibratedAndValidated: Boolean,
    val embeddingDistance: Float?,
    val sourceEvaluated: Boolean = false,
    /** True only when an actual leaf output passed the configured artifact threshold. */
    val leafGatePassed: Boolean = false,
    val normalizedEntropy: Float = 0f,
) {
    val top: RankedPrediction get() = ranked.first()
    val margin: Float get() = top.score - (ranked.getOrNull(1)?.score ?: 0f)
}

enum class UncertaintyReason {
    MODEL_NOT_VALIDATED, LOW_SCORE, AMBIGUOUS, UNFAMILIAR_IMAGE,
    CONDITION_DISABLED, MISSING_EMBEDDING_DISTANCE,
    HIGH_ENTROPY,
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

/** Unknown visual appearance is not itself proof of a nonleaf. Expose only leaf-checked candidates. */
fun AssessmentResult.rejectsUnsupportedInput(): Boolean = this is AssessmentResult.Uncertain &&
    reasons.any { it == UncertaintyReason.UNFAMILIAR_IMAGE || it == UncertaintyReason.CONDITION_DISABLED } &&
    !hasLeafCheckedCandidate()

fun AssessmentResult.hasLeafCheckedCandidate(): Boolean = this is AssessmentResult.Uncertain &&
    evidence.sourceEvaluated && evidence.leafGatePassed && evidence.ranked.isNotEmpty() &&
    UncertaintyReason.MODEL_NOT_VALIDATED !in reasons

const val LEAF_CHECKED_CANDIDATE_NOTE = "Leaf-checked uncertain candidate:"
