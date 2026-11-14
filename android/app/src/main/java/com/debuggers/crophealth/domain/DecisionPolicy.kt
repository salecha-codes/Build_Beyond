package com.debuggers.crophealth.domain

import kotlin.math.exp

object PhotoQuality {
    /** Prototype capture heuristics, not a guarantee that the image contains a leaf. */
    fun check(metrics: QualityMetrics, config: QualityConfig = QualityConfig()): QualityCheck {
        val issues = linkedSetOf<QualityIssue>()
        if (!metrics.decodeSucceeded || !metrics.meanLuminance.isFinite() ||
            !metrics.laplacianVariance.isFinite() || metrics.meanLuminance !in 0.0..255.0 ||
            metrics.laplacianVariance < 0.0) {
            issues += QualityIssue.UNREADABLE
        } else {
            if (metrics.width < config.minSide || metrics.height < config.minSide) issues += QualityIssue.TOO_SMALL
            if (metrics.meanLuminance < config.minLuminance) issues += QualityIssue.TOO_DARK
            if (metrics.meanLuminance > config.maxLuminance) issues += QualityIssue.TOO_BRIGHT
            if (metrics.laplacianVariance < config.minLaplacianVariance) issues += QualityIssue.BLURRY
        }
        return QualityCheck(issues, config.thresholdsValidated)
    }
}

object DecisionPolicy {
    fun assess(
        selectedCrop: Crop,
        output: InferenceOutput,
        policy: PolicyConfig = PolicyConfig(),
        quality: QualityCheck? = null,
    ): AssessmentResult {
        if (quality != null && !quality.acceptable) return AssessmentResult.Retake(quality)
        if (!output.modelReady) return AssessmentResult.ModelUnavailable(ModelFailure.NOT_READY)
        policy.minimumLeafProbability?.let { minimum ->
            if (!minimum.isFinite() || minimum <= 0f || minimum > 1f)
                return AssessmentResult.ModelUnavailable(ModelFailure.INVALID_POLICY)
            val probability = output.leafProbability
            if (probability == null || !probability.isFinite() || probability !in 0f..1f)
                return AssessmentResult.ModelUnavailable(ModelFailure.INVALID_SCORES)
            if (probability < minimum)
                return AssessmentResult.Retake(QualityCheck(setOf(QualityIssue.NOT_A_LEAF), false))
        }
        if (output.labelIds.size != output.logits.size || output.labelIds.size != Conditions.all.size ||
            output.labelIds.toSet() != Conditions.ids) {
            return AssessmentResult.ModelUnavailable(ModelFailure.LABEL_MISMATCH)
        }
        if (output.logits.any { !it.isFinite() } ||
            (output.embeddingDistance != null && (!output.embeddingDistance.isFinite() || output.embeddingDistance < 0f))) {
            return AssessmentResult.ModelUnavailable(ModelFailure.INVALID_SCORES)
        }
        if (!policy.temperature.isFinite() || policy.temperature <= 0f ||
            !policy.minConfidence.isFinite() || policy.minConfidence !in 0f..1f ||
            !policy.minMargin.isFinite() || policy.minMargin !in 0f..1f ||
            (policy.maxEmbeddingDistance != null && (!policy.maxEmbeddingDistance.isFinite() || policy.maxEmbeddingDistance < 0f))) {
            return AssessmentResult.ModelUnavailable(ModelFailure.INVALID_POLICY)
        }
        if (policy.sourceEvaluated && (policy.classThresholds.keys != Conditions.ids ||
            policy.classThresholds.values.any { threshold ->
                (threshold.minConfidence != null && (!threshold.minConfidence.isFinite() || threshold.minConfidence !in 0f..1f)) ||
                (threshold.minMargin != null && (!threshold.minMargin.isFinite() || threshold.minMargin !in 0f..1f)) ||
                (threshold.enabled && (threshold.minConfidence == null || threshold.minMargin == null ||
                    threshold.minConfidence <= 0f || threshold.minMargin <= 0f)) ||
                (threshold.maxEmbeddingDistance != null &&
                    (!threshold.maxEmbeddingDistance.isFinite() || threshold.maxEmbeddingDistance < 0f))
            })) {
            return AssessmentResult.ModelUnavailable(ModelFailure.INVALID_POLICY)
        }
        val scaled = output.logits.map { it.toDouble() / policy.temperature }
        val maximum = scaled.max()
        val exps = scaled.map { exp(it - maximum) }
        val sum = exps.sum()
        val ranked = output.labelIds.indices.map { i ->
            RankedPrediction(Conditions.byId(output.labelIds[i])!!, (exps[i] / sum).toFloat())
        }.sortedByDescending { it.score }
        val evidence = PredictionEvidence(ranked, output.modelVersion, policy.validated, output.embeddingDistance, policy.sourceEvaluated)
        // Unvalidated plumbing/model output must never assert that the farmer chose a wrong crop.
        if (!policy.validated && !policy.sourceEvaluated) {
            return AssessmentResult.Uncertain(setOf(UncertaintyReason.MODEL_NOT_VALIDATED), evidence)
        }
        val reasons = linkedSetOf<UncertaintyReason>()
        val threshold = if (policy.sourceEvaluated) policy.classThresholds[evidence.top.condition.id] else null
        val minimumConfidence = if (policy.sourceEvaluated) threshold?.minConfidence else policy.minConfidence
        val minimumMargin = if (policy.sourceEvaluated) threshold?.minMargin else policy.minMargin
        if (minimumConfidence != null && evidence.top.score < minimumConfidence) reasons += UncertaintyReason.LOW_SCORE
        if (minimumMargin != null && evidence.margin < minimumMargin) reasons += UncertaintyReason.AMBIGUOUS
        if (threshold?.enabled == false || evidence.top.condition.id !in policy.enabledConditionIds) reasons += UncertaintyReason.CONDITION_DISABLED
        (threshold?.maxEmbeddingDistance ?: policy.maxEmbeddingDistance)?.let { maximumDistance ->
            if (output.embeddingDistance == null) reasons += UncertaintyReason.MISSING_EMBEDDING_DISTANCE
            else if (output.embeddingDistance > maximumDistance) reasons += UncertaintyReason.UNFAMILIAR_IMAGE
        }
        if (reasons.isNotEmpty()) return AssessmentResult.Uncertain(reasons, evidence)
        // Crop correction is meaningful only after the model passes acceptance checks.
        // Never mask or renormalize scores to force the farmer's selected crop.
        if (evidence.top.condition.crop != selectedCrop) {
            return AssessmentResult.CropMismatch(selectedCrop, evidence.top.condition.crop, evidence)
        }
        return if (evidence.top.condition.isHealthy) AssessmentResult.HealthyLooking(evidence.top.condition, evidence)
        else AssessmentResult.LikelyCondition(evidence.top.condition, evidence)
    }
}
