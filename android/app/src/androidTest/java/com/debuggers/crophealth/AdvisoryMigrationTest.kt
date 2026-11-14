package com.debuggers.crophealth

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.debuggers.crophealth.data.*
import com.debuggers.crophealth.content.AdvisoryCatalog
import com.debuggers.crophealth.domain.*
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class AdvisoryMigrationTest {
    @Test fun packagedCareProfilesCoverEveryConditionAndLanguage() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val catalog = AdvisoryCatalog(context)
        assertEquals("offline-advisory-v1", catalog.version)
        for (condition in Conditions.ids) for (language in AppLanguage.entries) {
            val profile = catalog.profile(condition, language)!!
            assertTrue(profile.copy.curability.isNotBlank())
            assertTrue(profile.copy.doNow.isNotEmpty())
            assertTrue(profile.copy.management.isNotEmpty())
            assertTrue(profile.copy.prevention.isNotEmpty())
            assertTrue(profile.copy.escalation.isNotEmpty())
        }
    }
    @Test fun oldScanSurvivesAndNewAnswersRoundTrip() = runBlocking {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val name = "advisory-migration-test.db"
        context.deleteDatabase(name)
        context.openOrCreateDatabase(name, Context.MODE_PRIVATE, null).use { old ->
            old.execSQL("CREATE TABLE observations (id TEXT NOT NULL PRIMARY KEY, createdAt INTEGER NOT NULL, cropId TEXT NOT NULL, imagePath TEXT, resultType TEXT NOT NULL, conditionId TEXT, score REAL, modelVersion TEXT NOT NULL, inferenceMs INTEGER NOT NULL, note TEXT NOT NULL, validated INTEGER NOT NULL)")
            old.execSQL("INSERT INTO observations VALUES ('old-scan', 42, 'tomato', NULL, 'uncertain', 'tomato_early_blight', 0.5, 'old-model', 9, 'old record', 0)")
            old.version = 1
        }
        val db = Room.databaseBuilder(context, CropDatabase::class.java, name).addMigrations(OBSERVATION_MIGRATION_1_2).build()
        try {
            val saved = db.observations().find("old-scan")!!.observation()
            assertEquals("old record", saved.note)
            assertEquals("tomato_early_blight", saved.conditionId)
            assertNull(saved.reportedSymptoms)
            val symptoms = ReportedSymptoms(spreadingQuickly = true, leafCoverage = LeafCoverage.NO_VISIBLE_DAMAGE,
                fruitOrStemAffected = true, wetWeather = true)
            db.observations().updateSymptoms(saved.id, ReportedSymptomsJson.encode(symptoms))
            assertEquals(symptoms, db.observations().find(saved.id)!!.observation().reportedSymptoms)
            assertEquals(2, db.openHelper.readableDatabase.version)
        } finally { db.close(); context.deleteDatabase(name) }
    }
}
