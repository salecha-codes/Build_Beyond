package com.debuggers.crophealth.presentation

import com.debuggers.crophealth.domain.Crop
import com.debuggers.crophealth.domain.LEAF_CHECKED_CANDIDATE_NOTE
import org.junit.Assert.*
import org.junit.Test

class ObservationCandidateTest {
    private val record = Observation("saved", 0L, Crop.TOMATO, null, "uncertain",
        "tomato_early_blight", .92f, "qualified-model", 100L,
        "$LEAF_CHECKED_CANDIDATE_NOTE tomato_early_blight. Low confidence: UNFAMILIAR_IMAGE.")

    @Test fun leafCheckedUncertainCandidateCanBeReopenedWithoutLosingScoreOrCondition() {
        assertTrue(record.isLeafCheckedCandidate())
        assertFalse(record.hidesUnsupportedCandidate())
        assertEquals("uncertain", record.resultType)
        assertFalse(record.validated)
        assertEquals("tomato_early_blight", record.conditionId)
        assertEquals(.92f, record.score!!, .0001f)
    }

    @Test fun oldUnsupportedHistoryCannotBeRetroactivelyPromoted() {
        val old = record.copy(note = "Uncertain: UNFAMILIAR_IMAGE. Model output is not a confirmed diagnosis.")
        assertFalse(old.isLeafCheckedCandidate())
        assertTrue(old.hidesUnsupportedCandidate())
    }

    @Test fun markerRequiresActualConditionAndFiniteScoreAndUncertainType() {
        for (invalid in listOf(record.copy(conditionId = null), record.copy(conditionId = "invalid"),
            record.copy(score = null), record.copy(score = Float.NaN), record.copy(score = 2f),
            record.copy(resultType = "retake"), record.copy(resultType = "model_unavailable"))) {
            assertFalse(invalid.isLeafCheckedCandidate())
            assertTrue(invalid.hidesUnsupportedCandidate())
        }
    }
}
