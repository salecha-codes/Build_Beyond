package com.debuggers.crophealth.domain

import com.debuggers.crophealth.content.CareStagePlan
import com.debuggers.crophealth.presentation.*
import org.junit.Assert.*
import org.junit.Test

class CareProtocolFlowTest {
    @Test fun treatmentPriorityChangesWithDamageAndNeverDefaultsUnknownToMild() {
        val plans = mapOf("MILD" to CareStagePlan("Limited damage", listOf("Mark affected leaves")),
            "MODERATE" to CareStagePlan("Progressing damage", listOf("Assess new growth and discuss treatment")),
            "SEVERE" to CareStagePlan("Serious damage", listOf("Seek same-day crop examination")))
        assertEquals("Limited damage", CarePlanSelection.stage(plans, ReportedSeverity.MILD)?.title)
        assertEquals("Progressing damage", CarePlanSelection.stage(plans, ReportedSeverity.MODERATE)?.title)
        assertEquals("Serious damage", CarePlanSelection.stage(plans, ReportedSeverity.SEVERE)?.title)
        assertNull(CarePlanSelection.stage(plans, ReportedSeverity.UNKNOWN))
        assertNull(CarePlanSelection.stage(plans, ReportedSeverity.NONE))
    }

    @Test fun manualSelectionAndAnswersDoNotAlterTheScanOrItsSavedAnswers() {
        val saved = Observation("scan", 42, Crop.TOMATO, "/private/leaf.jpg", "likely_condition",
            "tomato_early_blight", .91f, "model", 11, "source estimate")
        val oldSymptoms = ReportedSymptoms(leafCoverage = LeafCoverage.FEW_SPOTS)
        val original = AppUiState(openedObservation = saved, savedObservationId = saved.id,
            selectedCrop = Crop.TOMATO, symptoms = oldSymptoms, symptomsComplete = true)
        val selected = original.selectManualCare("maize_common_rust")
            .reportCareSymptoms(ReportedSymptoms(wiltingOrDying = true, leafCoverage = LeafCoverage.MANY_SPOTS), true)
        assertEquals("maize_common_rust", selected.manualCare?.conditionId)
        assertTrue(selected.manualCare?.completed == true)
        assertEquals(saved, selected.openedObservation)
        assertEquals(oldSymptoms, selected.symptoms)
        assertEquals(Crop.TOMATO, selected.selectedCrop)
        assertEquals(saved.id, selected.savedObservationId)
        assertEquals(Screen.GUIDANCE, selected.backScreen())
    }

    @Test fun everyCategoryCanBeChosenManuallyButUnknownIdsAreRejected() {
        val state = AppUiState()
        for (id in Conditions.ids) assertEquals(id, state.selectManualCare(id).manualCare?.conditionId)
        assertEquals(state, state.selectManualCare("unregistered_condition"))
    }

    @Test fun savedAnswersArePrefilledWithoutInventingNoForUnknowns() {
        val known = ReportedSymptoms(spreadingQuickly = true, leafCoverage = LeafCoverage.SOME_SPOTS)
        val draft = CareAnswerDraft.seed(known, true)
        assertEquals(listOf(0, 2, 1, 1, 1, 1), draft)
        assertEquals(known, CareAnswerDraft.symptoms(draft))
        val uncertain = CareAnswerDraft.seed(known.copy(uncertainAnswers = true), true)
        assertEquals(listOf(0, 2, -1, -1, -1, -1), uncertain)
        assertTrue(CareAnswerDraft.symptoms(uncertain).uncertainAnswers)
        assertEquals(List(6) { -1 }, CareAnswerDraft.seed(known, false))
    }

    @Test fun completingAReviewClearsPreviousGlobalUncertaintyOnlyAfterExplicitAnswers() {
        assertFalse(CareAnswerDraft.symptoms(listOf(1, 0, 1, 1, 1, 1)).uncertainAnswers)
        assertTrue(CareAnswerDraft.symptoms(listOf(1, 4, 1, 1, 1, 1)).uncertainAnswers)
        assertTrue(CareAnswerDraft.symptoms(listOf(1, 1, 1, 1, 1, 2)).uncertainAnswers)
    }
}
