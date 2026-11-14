package com.debuggers.crophealth.domain

import org.junit.Assert.*
import org.junit.Test

class DecisionPolicyTest {
    private fun scores(id: String, value: Float = 20f) = InferenceOutput(
        Conditions.all.map { it.id }, Conditions.all.map { if (it.id == id) value else 0f }, "test-model",
    )

    @Test fun unvalidatedModelNeverBecomesDiagnosisDespiteHighScore() {
        val result = DecisionPolicy.assess(Crop.TOMATO, scores("tomato_early_blight"))
        assertTrue(result is AssessmentResult.Uncertain)
        assertTrue((result as AssessmentResult.Uncertain).reasons.contains(UncertaintyReason.MODEL_NOT_VALIDATED))
        assertFalse(result.evidence.calibratedAndValidated)
    }
    @Test fun selectedCropDoesNotRenormalizeAnotherCropsScores() {
        val result = DecisionPolicy.assess(Crop.POTATO, scores("tomato_early_blight"), PolicyConfig(validated = true))
        assertTrue(result is AssessmentResult.CropMismatch)
        assertEquals(Crop.TOMATO, (result as AssessmentResult.CropMismatch).predictedCrop)
    }
    @Test fun unvalidatedWrongCropScoreRemainsUncertain() {
        val result = DecisionPolicy.assess(Crop.TOMATO, scores("potato_early_blight"))
        assertTrue(result is AssessmentResult.Uncertain)
        assertTrue((result as AssessmentResult.Uncertain).reasons.contains(UncertaintyReason.MODEL_NOT_VALIDATED))
        assertEquals(Crop.POTATO, result.evidence.top.condition.crop)
    }
    @Test fun stableSoftmaxHandlesLargeFiniteLogits() {
        val output = scores("tomato_early_blight").copy(logits = Conditions.all.map { if (it.id == "tomato_early_blight") 10000f else -10000f })
        val result = DecisionPolicy.assess(Crop.TOMATO, output, PolicyConfig(validated = true))
        assertTrue(result is AssessmentResult.LikelyCondition)
        assertTrue(result.evidence!!.ranked.all { it.score.isFinite() })
        assertEquals(1f, result.evidence!!.ranked.sumOf { it.score.toDouble() }.toFloat(), 0.0001f)
    }
    @Test fun invalidClassContractDoesNotMislabel() {
        val out = scores("tomato_early_blight").copy(labelIds = List(17) { "tomato_early_blight" })
        assertEquals(AssessmentResult.ModelUnavailable(ModelFailure.LABEL_MISMATCH), DecisionPolicy.assess(Crop.TOMATO, out))
    }
    @Test fun nonFiniteLogitsFailSafely() {
        val out = scores("tomato_early_blight").copy(logits = List(17) { Float.NaN })
        assertEquals(AssessmentResult.ModelUnavailable(ModelFailure.INVALID_SCORES), DecisionPolicy.assess(Crop.TOMATO, out))
    }
    @Test fun noImageQualityBypassForDarkImage() {
        val q = PhotoQuality.check(QualityMetrics(0.0, 100.0, 512, 512))
        assertTrue(q.issues.contains(QualityIssue.TOO_DARK))
        assertTrue(DecisionPolicy.assess(Crop.TOMATO, scores("tomato_early_blight"), quality = q) is AssessmentResult.Retake)
    }
    @Test fun optionalEmbeddingGateRequiresItsEvidence() {
        val result = DecisionPolicy.assess(Crop.TOMATO, scores("tomato_early_blight"), PolicyConfig(validated = true, maxEmbeddingDistance = 1f))
        assertTrue((result as AssessmentResult.Uncertain).reasons.contains(UncertaintyReason.MISSING_EMBEDDING_DISTANCE))
    }
    @Test fun healthyLookingIsNotADisease() {
        val result = DecisionPolicy.assess(Crop.POTATO, scores("potato_healthy"), PolicyConfig(validated = true))
        assertTrue(result is AssessmentResult.HealthyLooking)
    }
    @Test fun equalLogitsRemainAmbiguous() {
        val output = scores("tomato_early_blight").copy(logits = List(17) { 0f })
        val result = DecisionPolicy.assess(Crop.MAIZE, output, PolicyConfig(validated = true))
        assertTrue(result is AssessmentResult.Uncertain)
    }
    @Test fun concernUsesReportedSymptomsNotModelConfidence() {
        val result = ConcernGuidance.summarize(ReportedSymptoms(spreadingQuickly = true))
        assertEquals(ConcernLevel.SEEK_LOCAL_EXPERT, result.level)
        assertFalse(result.agronomistReviewed)
    }
    @Test fun leafCoverageIsAnExplicitUserReport() {
        val result = ConcernGuidance.summarize(ReportedSymptoms(leafCoverage = LeafCoverage.MANY_SPOTS))
        assertEquals(ConcernLevel.SEEK_LOCAL_EXPERT, result.level)
        assertEquals(LeafCoverage.MANY_SPOTS, result.reportedSymptoms.leafCoverage)
        assertFalse(result.agronomistReviewed)
    }
    @Test fun uncertainAnswersDoNotSilentlyBecomeLowConcern() {
        val result = ConcernGuidance.summarize(ReportedSymptoms(leafCoverage = LeafCoverage.FEW_SPOTS, uncertainAnswers = true))
        assertEquals(ConcernLevel.SEEK_LOCAL_EXPERT, result.level)
        assertFalse(result.agronomistReviewed)
    }
    @Test fun missingCoverageNeedsFollowUpRatherThanAssumedLowConcern() {
        assertEquals(ConcernLevel.SEEK_LOCAL_EXPERT, ConcernGuidance.summarize(ReportedSymptoms()).level)
    }
}
