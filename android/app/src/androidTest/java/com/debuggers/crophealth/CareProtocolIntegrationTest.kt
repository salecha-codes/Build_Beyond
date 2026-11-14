package com.debuggers.crophealth

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.debuggers.crophealth.content.CareProtocolCatalog
import com.debuggers.crophealth.domain.*
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class CareProtocolIntegrationTest {
    @Test fun allSeventeenProtocolsHaveCompleteTreatmentAndRecoveryInEveryLanguage() {
        val catalog = CareProtocolCatalog(ApplicationProvider.getApplicationContext<Context>())
        assertEquals("care-protocols-v2", catalog.version)
        for (condition in Conditions.all) for (language in AppLanguage.entries) {
            val protocol = catalog.protocol(condition.id, language)!!
            assertEquals(condition.crop.id, protocol.cropId)
            assertTrue(protocol.copy.goal.isNotBlank())
            assertTrue(protocol.copy.treatmentOptions.all { it.steps.isNotEmpty() && it.whenToUse.isNotBlank() && it.limits.isNotBlank() })
            assertTrue(protocol.copy.recoverySigns.isNotEmpty())
            assertTrue(protocol.copy.failureSigns.isNotEmpty())
            assertTrue(protocol.copy.followUp.all { it.whenToCheck.isNotBlank() && it.check.isNotBlank() && it.action.isNotBlank() })
            assertTrue(protocol.sources.isNotEmpty())
            val mild = CarePlanSelection.stage(protocol.copy.stagePlans, ReportedSeverity.MILD)!!
            val moderate = CarePlanSelection.stage(protocol.copy.stagePlans, ReportedSeverity.MODERATE)!!
            val severe = CarePlanSelection.stage(protocol.copy.stagePlans, ReportedSeverity.SEVERE)!!
            assertNotEquals(mild.actions, moderate.actions)
            assertNotEquals(moderate.actions, severe.actions)
            assertNull(CarePlanSelection.stage(protocol.copy.stagePlans, ReportedSeverity.UNKNOWN))
        }
    }
}
