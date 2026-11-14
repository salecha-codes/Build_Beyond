package com.debuggers.crophealth

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.debuggers.crophealth.domain.*
import com.debuggers.crophealth.inference.ImagePreparation
import com.debuggers.crophealth.inference.LocalModelEngine
import java.io.File
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Real external negative input; never bundled or seeded into production scans. */
@RunWith(AndroidJUnit4::class)
class NonLeafGuardIntegrationTest {
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val app get() = instrumentation.targetContext

    @Test fun heldOutComputerMouseProducesNoDiseaseEvidence() {
        val mouse = File(app.filesDir, "nonleaf-mouse.jpg")
        assertTrue("Parent must stream the held-out mouse photo into app-private files/nonleaf-mouse.jpg", mouse.isFile && mouse.length() > 0)
        val metadata = app.assets.open("model/model_metadata.json").bufferedReader().use { JSONObject(it.readText()) }
        assertTrue("The deployed bundle must enable its trained leaf check", metadata.getJSONObject("leaf_gate").getBoolean("enabled"))
        val photo = ImagePreparation.decode(mouse)
        try {
            LocalModelEngine(app).use { engine ->
                assertTrue("Actual guarded model must load: ${engine.load().message}", engine.status.ready)
                val prediction = engine.infer(photo.bitmap)
                val minimum = prediction.policy.minimumLeafProbability
                val leafProbability = prediction.output.leafProbability
                assertNotNull("Native policy must use the artifact leaf threshold", minimum)
                assertNotNull("Actual ONNX leaf output must be executed", leafProbability)
                assertTrue("Held-out mouse must fail leaf check: $leafProbability >= $minimum", leafProbability!! < minimum!!)
                val result = DecisionPolicy.assess(Crop.TOMATO, prediction.output, prediction.policy)
                assertTrue("Mouse must request a leaf photo rather than return any disease", result is AssessmentResult.Retake)
                assertEquals(setOf(QualityIssue.NOT_A_LEAF), (result as AssessmentResult.Retake).quality.issues)
                assertNull("Rejected objects must expose no disease candidates", result.evidence)
                File(app.filesDir, "native-nonleaf-mouse-smoke.json").writeText(JSONObject()
                    .put("model_sha256", metadata.getString("model_sha256"))
                    .put("model_version", prediction.output.modelVersion)
                    .put("leaf_probability", leafProbability)
                    .put("minimum_leaf_probability", minimum)
                    .put("result_type", "retake")
                    .put("quality_issue", "NOT_A_LEAF")
                    .put("disease_evidence_present", result.evidence != null)
                    .put("input_scope", "held_out_computer_mouse_external_fixture")
                    .toString(2))
            }
        } finally { photo.bitmap.recycle() }
    }

    @Test fun knownLeafStillPassesTheLeafCheck() {
        val fixture = File(app.cacheDir, "positive-leaf-guard-fixture.jpg")
        instrumentation.context.assets.open("leaf_input.jpg").use { input -> fixture.outputStream().use { input.copyTo(it) } }
        val photo = ImagePreparation.decode(fixture)
        try {
            LocalModelEngine(app).use { engine ->
                assertTrue("Actual guarded model must load", engine.load().ready)
                val prediction = engine.infer(photo.bitmap)
                val minimum = prediction.policy.minimumLeafProbability
                val probability = prediction.output.leafProbability
                assertNotNull(minimum)
                assertNotNull(probability)
                assertTrue("A genuine QA leaf must pass the input gate", probability!! >= minimum!!)
                val result = DecisionPolicy.assess(Crop.TOMATO, prediction.output, prediction.policy)
                assertFalse("Leaf guard must preserve genuine leaf analysis", result is AssessmentResult.Retake && QualityIssue.NOT_A_LEAF in result.quality.issues)
                val metadata = app.assets.open("model/model_metadata.json").bufferedReader().use { JSONObject(it.readText()) }
                File(app.filesDir, "native-leaf-positive-smoke.json").writeText(JSONObject()
                    .put("model_sha256", metadata.getString("model_sha256"))
                    .put("leaf_probability", probability)
                    .put("minimum_leaf_probability", minimum)
                    .put("input_scope", "known_genuine_leaf_runtime_fixture")
                    .put("rejected_as_nonleaf", false).toString(2))
            }
        } finally { photo.bitmap.recycle(); fixture.delete() }
    }
}
