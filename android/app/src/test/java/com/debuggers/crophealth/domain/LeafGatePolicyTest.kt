package com.debuggers.crophealth.domain

import org.junit.Assert.*
import org.junit.Test

/** Regression: an ordinary object must never receive a displayed crop disease. */
class LeafGatePolicyTest {
    private val target = Conditions.byId("tomato_early_blight")!!
    private val input = InferenceOutput(Conditions.all.map { it.id },
        Conditions.all.map { if (it.id == target.id) 12f else -12f }, "leaf-gate-fixture")
    private val policy = PolicyConfig(validated = true, minimumLeafProbability = .8f)

    @Test fun nonLeafIsRejectedWithoutDiseaseEvidenceDespiteHighDiseaseScore() {
        val result = DecisionPolicy.assess(Crop.TOMATO, input.copy(leafProbability = .1f), policy)
        assertTrue(result is AssessmentResult.Retake)
        assertEquals(setOf(QualityIssue.NOT_A_LEAF), (result as AssessmentResult.Retake).quality.issues)
        assertNull(result.evidence)
    }

    @Test fun leafPassesThroughToTheExistingDiseasePolicy() {
        val result = DecisionPolicy.assess(Crop.TOMATO, input.copy(leafProbability = .95f), policy)
        assertTrue(result is AssessmentResult.LikelyCondition)
        assertEquals(target, (result as AssessmentResult.LikelyCondition).condition)
    }

    @Test fun exactLeafThresholdIsAccepted() {
        assertTrue(DecisionPolicy.assess(Crop.TOMATO, input.copy(leafProbability = .8f), policy)
            is AssessmentResult.LikelyCondition)
    }

    @Test fun missingRequiredLeafOutputFailsClosed() {
        assertEquals(AssessmentResult.ModelUnavailable(ModelFailure.INVALID_SCORES),
            DecisionPolicy.assess(Crop.TOMATO, input, policy))
    }

    @Test fun malformedLeafOutputFailsClosed() {
        for (probability in listOf(Float.NaN, Float.POSITIVE_INFINITY, -0.1f, 1.1f)) {
            assertEquals(AssessmentResult.ModelUnavailable(ModelFailure.INVALID_SCORES),
                DecisionPolicy.assess(Crop.TOMATO, input.copy(leafProbability = probability), policy))
        }
    }

    @Test fun invalidArtifactLeafThresholdIsNotTreatedAsAnAcceptAllGate() {
        for (threshold in listOf(Float.NaN, 0f, -0.1f, 1.1f)) {
            assertEquals(AssessmentResult.ModelUnavailable(ModelFailure.INVALID_POLICY),
                DecisionPolicy.assess(Crop.TOMATO, input.copy(leafProbability = .9f),
                    policy.copy(minimumLeafProbability = threshold)))
        }
    }

    @Test fun unsupportedReasonsCannotBePromotedLikeOrdinaryLowConfidence() {
        val evidence = PredictionEvidence(listOf(RankedPrediction(target, .9f)), "fixture", false, .5f, true)
        assertTrue(AssessmentResult.Uncertain(setOf(UncertaintyReason.UNFAMILIAR_IMAGE), evidence).rejectsUnsupportedInput())
        assertTrue(AssessmentResult.Uncertain(setOf(UncertaintyReason.CONDITION_DISABLED), evidence).rejectsUnsupportedInput())
        assertFalse(AssessmentResult.Uncertain(setOf(UncertaintyReason.LOW_SCORE), evidence).rejectsUnsupportedInput())
    }
}
