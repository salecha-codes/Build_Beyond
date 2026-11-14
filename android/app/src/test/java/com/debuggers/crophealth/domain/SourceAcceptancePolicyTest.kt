package com.debuggers.crophealth.domain

import kotlin.math.ln
import org.junit.Assert.*
import org.junit.Test

/** Policy fixtures exercise acceptance semantics; they are not model-accuracy results. */
class SourceAcceptancePolicyTest {
    private val target = "tomato_early_blight"
    private val baseline = ClassAcceptanceThreshold(
        enabled = true,
        minConfidence = 0.8f,
        minMargin = 0.2f,
        maxEmbeddingDistance = 0.75f,
    )

    private fun sourcePolicy(
        conditionId: String = target,
        threshold: ClassAcceptanceThreshold = baseline,
    ) = PolicyConfig(
        validated = false,
        sourceEvaluated = true,
        // Deliberately stricter global fallbacks prove that source-qualified
        // inference uses the artifact's per-class acceptance table.
        minConfidence = 0.99f,
        minMargin = 0.99f,
        maxEmbeddingDistance = 0.05f,
        classThresholds = Conditions.ids.associateWith { baseline } + (conditionId to threshold),
    )

    private fun prediction(
        topId: String = target,
        topProbability: Double = 0.91,
        runnerId: String = "tomato_late_blight",
        runnerProbability: Double = 0.03,
        distance: Float? = 0.2f,
    ): InferenceOutput {
        require(topId != runnerId && topProbability + runnerProbability < 1.0)
        val remainder = (1.0 - topProbability - runnerProbability) / (Conditions.all.size - 2)
        return InferenceOutput(
            labelIds = Conditions.all.map { it.id },
            logits = Conditions.all.map {
                ln(when (it.id) {
                    topId -> topProbability
                    runnerId -> runnerProbability
                    else -> remainder
                }).toFloat()
            },
            modelVersion = "source-acceptance-policy-test-fixture",
            embeddingDistance = distance,
        )
    }

    private fun uncertain(result: AssessmentResult): AssessmentResult.Uncertain {
        assertTrue("Expected an uncertain result, got $result", result is AssessmentResult.Uncertain)
        return result as AssessmentResult.Uncertain
    }

    @Test fun sourceQualifiedStrongMatchUsesClassGatesWithoutClaimingFieldValidation() {
        val result = DecisionPolicy.assess(Crop.TOMATO, prediction(), sourcePolicy())
        assertTrue(result is AssessmentResult.LikelyCondition)
        val accepted = result as AssessmentResult.LikelyCondition
        assertEquals(target, accepted.condition.id)
        assertTrue(accepted.evidence.sourceEvaluated)
        assertFalse(accepted.evidence.calibratedAndValidated)
        assertEquals(0.91f, accepted.evidence.top.score, 0.00001f)
        assertEquals(1.0, accepted.evidence.ranked.sumOf { it.score.toDouble() }, 0.00001)
    }

    @Test fun sourceQualifiedHealthyMatchIsHealthyLookingWithoutAFieldValidationClaim() {
        val id = "potato_healthy"
        val result = DecisionPolicy.assess(
            Crop.POTATO,
            prediction(topId = id, runnerId = "potato_early_blight"),
            sourcePolicy(conditionId = id),
        )
        assertTrue(result is AssessmentResult.HealthyLooking)
        val accepted = result as AssessmentResult.HealthyLooking
        assertEquals(id, accepted.condition.id)
        assertTrue(accepted.evidence.sourceEvaluated)
        assertFalse(accepted.evidence.calibratedAndValidated)
    }

    @Test fun classConfidenceGateWithholdsAScoreBelowItsOwnEvaluatedThreshold() {
        val result = uncertain(DecisionPolicy.assess(
            Crop.TOMATO, prediction(), sourcePolicy(threshold = baseline.copy(minConfidence = 0.95f)),
        ))
        assertEquals(setOf(UncertaintyReason.LOW_SCORE), result.reasons)
        assertFalse(result.evidence.calibratedAndValidated)
    }

    @Test fun classMarginGateWithholdsAnAmbiguousPairEvenWhenConfidencePasses() {
        val result = uncertain(DecisionPolicy.assess(
            Crop.TOMATO,
            prediction(topProbability = 0.55, runnerProbability = 0.4),
            sourcePolicy(threshold = baseline.copy(minConfidence = 0.5f, minMargin = 0.2f)),
        ))
        assertEquals(setOf(UncertaintyReason.AMBIGUOUS), result.reasons)
    }

    @Test fun disabledConditionIsWithheldByEitherClassOrGlobalEnablement() {
        val policies = listOf(
            sourcePolicy(threshold = baseline.copy(enabled = false)),
            sourcePolicy().copy(enabledConditionIds = Conditions.ids - target),
        )
        policies.forEach { policy ->
            val result = uncertain(DecisionPolicy.assess(Crop.TOMATO, prediction(), policy))
            assertEquals(setOf(UncertaintyReason.CONDITION_DISABLED), result.reasons)
        }
    }

    @Test fun configuredEmbeddingGateRequiresActualDistanceEvidence() {
        val result = uncertain(DecisionPolicy.assess(
            Crop.TOMATO, prediction(distance = null), sourcePolicy(),
        ))
        assertEquals(setOf(UncertaintyReason.MISSING_EMBEDDING_DISTANCE), result.reasons)
    }

    @Test fun unfamiliarEmbeddingIsWithheldDespiteAHighCandidateScore() {
        val result = uncertain(DecisionPolicy.assess(
            Crop.TOMATO, prediction(distance = 0.9f), sourcePolicy(),
        ))
        assertEquals(setOf(UncertaintyReason.UNFAMILIAR_IMAGE), result.reasons)
        assertFalse(result.evidence.calibratedAndValidated)
    }

    @Test fun wrongCropIsReportedOnlyAfterGlobalPredictionPassesEveryGate() {
        val id = "potato_early_blight"
        val result = DecisionPolicy.assess(
            Crop.TOMATO,
            prediction(topId = id, runnerId = "potato_late_blight"),
            sourcePolicy(conditionId = id),
        )
        assertTrue(result is AssessmentResult.CropMismatch)
        val mismatch = result as AssessmentResult.CropMismatch
        assertEquals(Crop.TOMATO, mismatch.selectedCrop)
        assertEquals(Crop.POTATO, mismatch.predictedCrop)
        assertEquals(id, mismatch.evidence.top.condition.id)
        assertEquals(0.91f, mismatch.evidence.top.score, 0.00001f)
        assertFalse(mismatch.evidence.calibratedAndValidated)
    }

    @Test fun weakWrongCropPredictionStaysUncertainInsteadOfCorrectingTheFarmer() {
        val id = "potato_early_blight"
        val result = uncertain(DecisionPolicy.assess(
            Crop.TOMATO,
            prediction(topId = id, topProbability = 0.4, runnerId = "potato_late_blight", runnerProbability = 0.35),
            sourcePolicy(conditionId = id),
        ))
        assertEquals(setOf(UncertaintyReason.LOW_SCORE, UncertaintyReason.AMBIGUOUS), result.reasons)
        assertEquals(Crop.POTATO, result.evidence.top.condition.crop)
    }

    @Test fun legacyUnqualifiedModelRemainsUncertainEvenWithAnAcceptanceTablePresent() {
        val result = uncertain(DecisionPolicy.assess(
            Crop.TOMATO, prediction(), sourcePolicy().copy(sourceEvaluated = false),
        ))
        assertEquals(setOf(UncertaintyReason.MODEL_NOT_VALIDATED), result.reasons)
        assertFalse(result.evidence.sourceEvaluated)
        assertFalse(result.evidence.calibratedAndValidated)
    }

    @Test fun incompleteSourceClassTableFailsClosedInsteadOfUsingGlobalFallbacks() {
        val incomplete = sourcePolicy().copy(classThresholds = mapOf(target to baseline))
        assertEquals(
            AssessmentResult.ModelUnavailable(ModelFailure.INVALID_POLICY),
            DecisionPolicy.assess(Crop.TOMATO, prediction(), incomplete),
        )
    }
}
